# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Le rapprochement d'un appel VoIP avec sa fiche, et l'historique du panneau.

Les numeros de ces essais sont INVENTES, dans la plage 555-01xx reservee a la
fiction. Un numero pris dans le parc figerait pour toujours une donnee reelle
dans un fichier suivi par le depot.
"""
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestVoipContact(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contact = cls.env["res.partner"].create(
            {"name": "Ecole de danse", "mobile": "+1 514-555-0142"}
        )
        cls.autre = cls.env["res.partner"].create(
            {"name": "Fournisseur", "mobile": "+1 514-555-0177"}
        )
        cls.appels = cls.env["voip.call"]
        cls.contacts = cls.env["res.partner"]

    def _appel(self, numero, **valeurs):
        donnees = {"phone_number": numero, "type_call": "outgoing"}
        donnees.update(valeurs)
        return self.appels.browse(self.appels.create_call(donnees)["id"])

    def test_le_formatage_ne_separe_plus_le_numero_de_sa_fiche(self):
        """« 15145550142 » et « +1 514-555-0142 » sont la meme personne.

        C'est le cas courant : le softphone presente les chiffres seuls, la
        fiche porte le numero formate. L'egalite de chaine d'origine les
        separe, et l'appel s'affiche sans contact.
        """
        appel = self._appel("15145550142")
        self.assertEqual(appel.partner_id, self.contact)

    def test_un_numero_inconnu_ne_prend_pas_la_fiche_du_voisin(self):
        """Un rapprochement trop large est pire que pas de rapprochement.

        Annoncer le mauvais correspondant fait rappeler quelqu'un d'autre.
        """
        appel = self._appel("15145550199")
        self.assertFalse(appel.partner_id)

    def test_le_contact_donne_par_l_appelant_prime(self):
        """Cliquer sur une fiche precise nomme le correspondant sans ambiguite.

        Deux fiches peuvent partager la fin d'un numero ; celle qu'on a
        designee du doigt l'emporte sur celle que les chiffres suggerent.
        """
        appel = self._appel("15145550142", partner_id=self.autre.id)
        self.assertEqual(appel.partner_id, self.autre)

    def test_l_historique_reunit_les_numeros_d_une_meme_personne(self):
        """Un mobile et un poste fixe restent une seule personne.

        L'historique suit le CONTACT, sans quoi il se scinderait en autant de
        listes que la fiche porte de numeros.
        """
        self.contact.phone = "+1 514-555-0143"
        ancien = self._appel("15145550143")
        courant = self._appel("15145550142")
        historique = self.contacts.historique_correspondant(
            phone_number=courant.phone_number,
            partner_id=self.contact.id,
            exclude_call_id=courant.id,
        )
        self.assertEqual([l["id"] for l in historique["appels"]], [ancien.id])

    def test_l_historique_d_un_inconnu_suit_les_chiffres(self):
        """Sans fiche, deux ecritures du meme numero restent le meme appelant.

        C'est le cas d'un numero qu'on n'a pas encore enregistre, et c'est
        precisement celui ou savoir « il a deja appele deux fois » sert.
        """
        ancien = self._appel("+1 514-555-0199")
        courant = self._appel("15145550199")
        historique = self.contacts.historique_correspondant(
            phone_number=courant.phone_number, exclude_call_id=courant.id
        )
        self.assertEqual([l["id"] for l in historique["appels"]], [ancien.id])

    def test_l_historique_ecarte_l_appel_en_cours(self):
        """Le panneau montre deja l'appel en cours au-dessus de la liste."""
        courant = self._appel("15145550142")
        historique = self.contacts.historique_correspondant(
            phone_number=courant.phone_number,
            partner_id=self.contact.id,
            exclude_call_id=courant.id,
        )
        self.assertEqual(historique["appels"], [])

    def test_une_fiche_creee_pendant_l_appel_est_rattachee(self):
        """Le rapprochement a lieu a la CREATION de l'appel, deja passee.

        Creer la fiche depuis le panneau laisserait donc « aucun contact » a
        l'ecran jusqu'a la fin de l'appel.
        """
        appel = self._appel("15145550188")
        self.assertFalse(appel.partner_id)
        nouveau = self.env["res.partner"].create(
            {"name": "Nouvelle eleve", "phone": "+1 514-555-0188"}
        )
        appel.rattacher_le_contact()
        self.assertEqual(appel.partner_id, nouveau)

    def test_le_rattachement_ne_change_pas_un_contact_deja_pose(self):
        """Fermer la fenetre sans rien creer ne doit rien deplacer."""
        appel = self._appel("15145550142")
        appel.rattacher_le_contact()
        self.assertEqual(appel.partner_id, self.contact)

    def test_un_rappel_sans_numero_prend_celui_de_la_fiche(self):
        """Le pied du softphone rappelait en lisant une propriete inexistante.

        L'appel partait alors sans numero ET sans contact, et l'echec se
        presentait comme « un champ obligatoire n'est pas rempli » — un
        message que rien ne rattachait au bouton qu'on venait de presser.
        """
        appel = self._appel(False, partner_id=self.contact.id)
        self.assertEqual(appel.phone_number, self.contact.mobile)

    def test_le_mobile_prime_sur_le_fixe(self):
        """Le mobile joint la personne, le fixe joint le lieu."""
        self.contact.phone = "+1 514-555-0143"
        appel = self._appel(False, partner_id=self.contact.id)
        self.assertEqual(appel.phone_number, self.contact.mobile)

    def test_une_fiche_sans_numero_le_dit(self):
        """« Un champ obligatoire n'est pas rempli » ne nomme ni le champ ni
        la cause. Le refus doit dire quoi faire."""
        muet = self.env["res.partner"].create({"name": "Sans telephone"})
        with self.assertRaises(UserError) as pris:
            self._appel(False, partner_id=muet.id)
        self.assertIn("Aucun numero a composer", str(pris.exception))

    def test_un_appel_sans_numero_ni_fiche_le_dit_aussi(self):
        """Le cas exact du bogue : ni numero, ni contact."""
        with self.assertRaises(UserError):
            self._appel(False)

    def _sms_envoye(self, numero, texte, partner=None):
        return self.env["erplibre.sms.dispatch"].create(
            {
                "sms_uuid": "essai-%s" % texte,
                "number": numero,
                "body": texte,
                "partner_id": partner and partner.id,
                "company_id": self.env.company.id,
            }
        )

    def _sms_recu(self, numero, texte, partner=None):
        return self.env["erplibre.sms.inbound"].create(
            {
                "number": numero,
                "body": texte,
                "partner_id": partner and partner.id,
                "received_at": fields.Datetime.now(),
            }
        )

    def test_l_historique_reunit_les_sms_des_deux_sens(self):
        """Une conversation se lit dans les deux sens ou pas du tout.

        Ne montrer que les envois laisserait croire qu'on n'a jamais eu de
        reponse, ce qui est l'inverse de ce que l'historique sert a savoir.
        """
        self._sms_envoye("15145550142", "Cours annule", self.contact)
        self._sms_recu("15145550142", "Bien recu", self.contact)
        historique = self.contacts.historique_correspondant(partner_id=self.contact.id)
        self.assertEqual(sorted(l["sens"] for l in historique["sms"]), ["in", "out"])

    def test_les_sms_ne_sont_pas_bornes_a_un_utilisateur(self):
        """Un SMS est un echange de l'organisation avec la personne.

        Contrairement aux appels : celui qu'un collegue a envoye hier explique
        precisement l'appel d'aujourd'hui.
        """
        autre = self.env["res.users"].create(
            {
                "name": "Collegue",
                "login": "collegue_essai",
            }
        )
        self._sms_envoye("15145550142", "Envoye par un collegue", self.contact)
        historique = self.contacts.with_user(self.env.user).historique_correspondant(
            partner_id=self.contact.id
        )
        self.assertTrue(historique["sms"], "l'envoi d'un collegue a disparu")
        self.assertTrue(autre.exists())

    def test_les_sms_se_retrouvent_par_les_chiffres(self):
        """Un SMS recu d'un numero sans fiche reste retrouvable."""
        self._sms_recu("+1 514-555-0199", "Bonjour")
        historique = self.contacts.historique_correspondant(phone_number="15145550199")
        self.assertEqual(len(historique["sms"]), 1)

    def test_un_numero_trop_court_ne_propose_rien(self):
        """Le rapprochement compare des FINS de numero.

        « 514 » se termine comme la moitie du carnet : proposer cet
        historique-la pendant la composition desinforme au lieu d'aider.
        """
        self._sms_recu("15145550142", "Bonjour", self.contact)
        historique = self.contacts.historique_correspondant(phone_number="514")
        self.assertEqual(historique, {"appels": [], "sms": []})
