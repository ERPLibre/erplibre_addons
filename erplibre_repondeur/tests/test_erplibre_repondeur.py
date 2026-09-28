# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Le repondeur cote Odoo : reception d'un message, reglages, rapprochement.

Les numeros sont INVENTES, dans la plage 555-01xx reservee a la fiction.
"""
import base64

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestRepondeur(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contact = cls.env["res.partner"].create(
            {"name": "Ecole de danse", "mobile": "+1 514-555-0142"}
        )
        cls.messages = cls.env["erplibre.repondeur.message"]
        cls.societe = cls.env.company

    def _charge(self, numero="15145550142", reference="msg-1"):
        return {
            "numero": numero,
            "recu_le": "2026-09-05 12:00:00",
            "duree_secondes": 7,
            "crete": 24000,
            "nom_fichier": "message.wav",
            "audio_b64": base64.b64encode(b"RIFF....WAVE").decode("ascii"),
            "reference": reference,
        }

    def test_un_message_recu_trouve_sa_fiche(self):
        """Le rapprochement se fait par les chiffres, comme pour un appel.

        Un message dont l'appelant est « inconnu » alors que sa fiche existe
        oblige a chercher qui a appele, ce que le numero disait deja.
        """
        message = self.messages.browse(
            self.messages.enregistrer_depuis_le_service(self._charge())
        )
        self.assertEqual(message.partner_id, self.contact)
        self.assertEqual(message.state, "new")
        self.assertEqual(message.taille_du_son(), len(b"RIFF....WAVE"))

    def test_un_service_qui_reessaie_ne_cree_pas_de_doublon(self):
        """Une reponse perdue fait reessayer le service.

        Sans cette garde, la liste se remplirait de doublons de la meme voix,
        et le service televerserait en boucle.
        """
        premier = self.messages.enregistrer_depuis_le_service(self._charge())
        second = self.messages.enregistrer_depuis_le_service(self._charge())
        self.assertEqual(premier, second)
        self.assertEqual(self.messages.search_count([("source_ref", "=", "msg-1")]), 1)

    def test_un_message_se_marque_ecoute_et_se_demarque(self):
        """Distinguer ce qui reste a traiter est ce qu'on demande d'abord a
        une liste de repondeur."""
        message = self.messages.browse(
            self.messages.enregistrer_depuis_le_service(self._charge())
        )
        message.action_marquer_ecoute()
        self.assertEqual(message.state, "heard")
        message.action_marquer_nouveau()
        self.assertEqual(message.state, "new")

    def test_un_numero_inconnu_prepare_une_fiche_neuve(self):
        """Retaper le numero a la main est le meilleur moyen de s'y tromper."""
        message = self.messages.browse(
            self.messages.enregistrer_depuis_le_service(
                self._charge(numero="15145550199", reference="msg-2")
            )
        )
        self.assertFalse(message.partner_id)
        action = message.action_ouvrir_contact()
        self.assertEqual(action["context"]["default_phone"], "15145550199")
        self.assertNotIn("res_id", action)

    def test_une_fiche_creee_apres_coup_se_rattache(self):
        """Le rapprochement a lieu a la reception, deja passee."""
        message = self.messages.browse(
            self.messages.enregistrer_depuis_le_service(
                self._charge(numero="15145550188", reference="msg-3")
            )
        )
        self.assertFalse(message.partner_id)
        neuve = self.env["res.partner"].create(
            {"name": "Nouvelle eleve", "phone": "+1 514-555-0188"}
        )
        message.action_rapprocher()
        self.assertEqual(message.partner_id, neuve)

    def test_les_reglages_partent_vers_le_service(self):
        """Le service a besoin des sonneries ET de l'annonce ensemble.

        Deux appels qui peuvent reussir separement laisseraient une annonce
        d'hier avec des sonneries d'aujourd'hui.
        """
        self.societe.write(
            {
                "repondeur_actif": True,
                "repondeur_sonneries": 3,
                "repondeur_annonce": base64.b64encode(b"RIFF"),
                "repondeur_annonce_filename": "bonjour.wav",
            }
        )
        reglages = self.societe.reglages_du_repondeur()
        self.assertTrue(reglages["actif"])
        self.assertEqual(reglages["sonneries"], 3)
        self.assertEqual(reglages["annonce_nom"], "bonjour.wav")
        self.assertTrue(reglages["annonce_b64"])

    def test_un_nombre_de_sonneries_impossible_est_refuse(self):
        """A l'ecran on REFUSE, la ou le service corrige en silence.

        Une saisie a un humain devant elle : lui dire vaut mieux que changer
        son chiffre sans le prevenir.
        """
        with self.assertRaises(ValidationError):
            self.societe.write(
                {
                    "repondeur_actif": True,
                    "repondeur_sonneries": 12,
                }
            )

    def test_les_bornes_ne_genent_pas_un_repondeur_eteint(self):
        """Un repondeur eteint n'a pas de sonneries a valider : refuser
        empecherait de garder un reglage a revoir."""
        self.societe.write({"repondeur_actif": False, "repondeur_sonneries": 12})
        self.assertEqual(self.societe.repondeur_sonneries, 12)

    def test_la_reception_previent_les_personnes_designees(self):
        """Un repondeur dont personne n'apprend qu'il a recu quelque chose ne
        vaut pas mieux que pas de repondeur.

        Le destinataire est CREE ici plutot que pris dans `env.user` : celui
        d'un essai est OdooBot, qui est archive, et Odoo ecarte les
        enregistrements inactifs d'un champ relationnel. La liste se relirait
        vide sans qu'aucune ecriture ait echoue.
        """
        prevenu = self.env["res.users"].create(
            {"name": "Reception", "login": "reception_essai"}
        )
        self.societe.repondeur_notify_user_ids = prevenu
        message = self.messages.browse(
            self.messages.enregistrer_depuis_le_service(self._charge(reference="msg-4"))
        )
        annonces = message.message_ids.filtered(
            lambda m: prevenu.partner_id in m.partner_ids
        )
        self.assertTrue(annonces, "personne n'a ete prevenu du message")
        self.assertIn("Ecole de danse", annonces[0].body)

    def test_un_message_de_l_operateur_n_a_pas_de_numero(self):
        """La boite vocale de l'operateur annonce l'appelant a la voix et ne
        le transmet pas : un numero vide dit qu'on ne le sait pas, la ou celui
        de la messagerie pretendrait le contraire."""
        charge = self._charge(numero="", reference="op-1")
        charge["source"] = "operateur"
        message = self.messages.browse(
            self.messages.enregistrer_depuis_le_service(charge)
        )
        self.assertEqual(message.source, "operateur")
        self.assertFalse(message.number)
        self.assertFalse(message.partner_id)
        # Le nom affiche nomme la source, faute de mieux : « — 12:04 » ne dirait
        # rien.
        self.assertIn("operateur", message.display_name.lower())

    def test_la_source_par_defaut_reste_le_repondeur_erplibre(self):
        message = self.messages.browse(
            self.messages.enregistrer_depuis_le_service(self._charge(reference="def-1"))
        )
        self.assertEqual(message.source, "erplibre")

    def test_l_annonce_nomme_la_source_quand_le_numero_manque(self):
        """Prevenir quelqu'un d'un message « de » rien du tout ne se lit pas."""
        prevenu = self.env["res.users"].create(
            {"name": "Accueil", "login": "accueil_operateur_essai"}
        )
        self.societe.repondeur_notify_user_ids = prevenu
        charge = self._charge(numero="", reference="op-2")
        charge["source"] = "operateur"
        message = self.messages.browse(
            self.messages.enregistrer_depuis_le_service(charge)
        )
        annonces = message.message_ids.filtered(
            lambda m: prevenu.partner_id in m.partner_ids
        )
        self.assertTrue(annonces)
        self.assertIn("inconnu", annonces[0].body)
