# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Un message laisse sur le repondeur de la ligne cellulaire.

Le son vit dans une piece jointe et non dans une colonne : un enregistrement
de deux minutes pese deux megaoctets, et cent messages dans la table
alourdiraient chaque lecture de la liste, qui n'a pourtant besoin que des
dates et des numeros.
"""
import base64
import logging
from urllib.parse import urlencode

from markupsafe import Markup
from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class RepondeurMessage(models.Model):
    _name = "erplibre.repondeur.message"
    _description = "Message du repondeur"
    _inherit = ["mail.thread"]
    _order = "received_at DESC, id DESC"
    _rec_name = "number"

    # Le numero est FACULTATIF : la boite vocale de l'operateur annonce
    # l'appelant a la voix, dans son annonce parlee, et ne le transmet sous
    # aucune forme lisible. Le laisser vide dit qu'on ne le sait pas ;
    # y mettre le numero de la messagerie pretendrait le contraire.
    number = fields.Char("Numero", readonly=True, index=True)
    source = fields.Selection(
        [("erplibre", "Repondeur ERPLibre"),
         ("operateur", "Boite vocale de l'operateur")],
        default="erplibre", required=True, readonly=True, index=True,
        help="Les deux ne se traitent pas pareil : un message de l'operateur "
             "a deja ete efface chez lui au moment ou il arrive ici, et il "
             "porte rarement le numero de l'appelant.",
    )
    partner_id = fields.Many2one(
        "res.partner",
        "Contact",
        index=True,
        ondelete="set null",
        help="Rapproche par les chiffres du numero. Vide quand aucune fiche "
        "ne porte ce numero.",
    )
    received_at = fields.Datetime("Recu le", required=True, readonly=True, index=True)
    duration_seconds = fields.Integer("Duree (s)", readonly=True)
    audio = fields.Binary("Enregistrement", attachment=True, readonly=True)
    audio_filename = fields.Char("Nom du fichier", readonly=True)
    audio_numero = fields.Binary(
        "Numero annonce",
        attachment=True,
        readonly=True,
        help="Les secondes ou la messagerie enonce le numero de l'appelant. "
        "Elle ne le transmet sous aucune forme lisible : c'est en les "
        "ecoutant qu'on remplit le champ Numero.",
    )
    audio_numero_filename = fields.Char("Nom du fichier du numero", readonly=True)
    numero_duration_seconds = fields.Integer("Duree du numero (s)", readonly=True)
    audio_numero_player = fields.Html(
        "Ecoute du numero",
        compute="_compute_audio_player",
        sanitize=False,
    )
    audio_player = fields.Html(
        "Ecoute",
        compute="_compute_audio_player",
        sanitize=False,
        help="Lecteur du navigateur. Un champ binaire ne sait que "
        "telecharger, et un message qu'on doit ouvrir hors d'Odoo pour "
        "l'entendre n'est pas ecoute.",
    )
    state = fields.Selection(
        [("new", "Nouveau"), ("heard", "Ecoute")],
        default="new",
        required=True,
        index=True,
        tracking=True,
    )
    peak = fields.Integer(
        "Crete",
        readonly=True,
        help="Amplitude maximale de l'enregistrement. Une crete nulle dit que "
        "rien n'est entre dans la carte son, ce qu'un fichier de la bonne "
        "duree ne distingue pas d'un silence legitime.",
    )
    company_id = fields.Many2one(
        "res.company",
        "Societe",
        required=True,
        readonly=True,
        default=lambda self: self.env.company,
    )
    #: Le nom du fichier chez le service. Sert a ne pas televerser deux fois le
    #: meme message quand une reponse se perd et que le service reessaie.
    source_ref = fields.Char("Reference du service", readonly=True, index=True)

    _sql_constraints = [
        (
            "source_ref_unique",
            "UNIQUE(source_ref)",
            "Ce message a deja ete recu : le service a reessaye apres une "
            "reponse perdue, et le rejouer creerait un doublon.",
        ),
    ]

    @api.depends("audio_filename", "audio_numero_filename")
    def _compute_audio_player(self):
        """Rend la balise qui joue l'enregistrement dans la fiche.

        Elle POINTE la piece jointe au lieu de porter le son : incruster deux
        megaoctets encodes ferait peser chaque ouverture de fiche, et
        « preload=none » laisse le navigateur ne les chercher qu'au premier
        clic sur la lecture.

        Le declencheur est le NOM du fichier et non le son : dependre du
        binaire le lirait depuis la piece jointe a chaque calcul, pour n'en
        regarder que la presence. Les deux sont ecrits ensemble.
        """
        for message in self:
            message.audio_player = message._lecteur("audio", "audio_filename")
            message.audio_numero_player = message._lecteur(
                "audio_numero", "audio_numero_filename"
            )

    def _lecteur(self, champ, champ_nom):
        """La balise qui joue un des sons de la fiche, ou Faux s'il manque."""
        self.ensure_one()
        if not self[champ_nom] or not isinstance(self.id, int):
            return False
        lien = "/web/content?" + urlencode(
            {
                "model": self._name,
                "id": self.id,
                "field": champ,
                "filename_field": champ_nom,
            }
        )
        return Markup('<audio controls preload="none" src="%s"></audio>') % lien

    @api.depends("number", "partner_id", "received_at", "source")
    def _compute_display_name(self):
        for message in self:
            # Sans contact ni numero, on nomme la SOURCE : « — 12:04 » ne dit
            # rien, et un message de l'operateur n'a souvent que cela.
            qui = (message.partner_id.display_name or message.number
                   or dict(self._fields["source"].selection)[message.source])
            message.display_name = "%s — %s" % (qui, message.received_at or "")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("partner_id") and vals.get("number"):
                vals["partner_id"] = (
                    self.env["voip.call"]._partenaire_du_numero(vals["number"]) or False
                )
        messages = super().create(vals_list)
        messages._prevenir()
        return messages

    def _prevenir(self):
        """Annonce le message aux personnes designees dans les reglages.

        Un repondeur dont personne n'apprend qu'il a recu quelque chose ne
        vaut pas mieux que pas de repondeur : le message attend jusqu'a ce que
        quelqu'un pense a regarder.
        """
        for message in self:
            destinataires = message.company_id.repondeur_notify_user_ids
            if not destinataires:
                continue
            message.message_post(
                body=_(
                    "Message sur le repondeur, de %(qui)s (%(duree)s s).",
                    qui=(message.partner_id.display_name or message.number
                         or _("appelant inconnu, annonce a la voix")),
                    duree=message.duration_seconds,
                ),
                partner_ids=destinataires.partner_id.ids,
                subtype_xmlid="mail.mt_comment",
            )

    def _completer_depuis_le_service(self, charge):
        """Ajoute a une fiche connue ce qui lui manque, sans rien remplacer.

        Jamais d'ecrasement : ce qui est deja la a ete televerse une fois et
        ecoute peut-etre depuis, et un reessai ne doit pas pouvoir le changer.
        """
        self.ensure_one()
        son = charge.get("numero_audio_b64") or ""
        if not son or self.audio_numero:
            return False
        self.sudo().write({
            "audio_numero": son.encode("ascii"),
            "audio_numero_filename": charge.get("numero_nom_fichier")
            or "numero.wav",
            "numero_duration_seconds": int(charge.get("numero_duree_secondes") or 0),
        })
        return True

    def action_marquer_ecoute(self):
        self.write({"state": "heard"})
        return True

    def action_marquer_nouveau(self):
        self.write({"state": "new"})
        return True

    def action_ouvrir_contact(self):
        """Ouvre la fiche, ou en prepare une neuve avec le numero deja pose.

        Un numero inconnu qui laisse un message est souvent quelqu'un a
        inscrire, et retaper le numero a la main est le meilleur moyen de s'y
        tromper.
        """
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "res_model": "res.partner",
            "view_mode": "form",
            "target": "current",
        }
        if self.partner_id:
            action["res_id"] = self.partner_id.id
        else:
            action["context"] = {"default_phone": self.number}
        return action

    def action_rapprocher(self):
        """Rejoue le rapprochement, pour une fiche creee apres coup."""
        for message in self:
            if message.partner_id:
                continue
            trouve = self.env["voip.call"]._partenaire_du_numero(message.number)
            if trouve:
                message.partner_id = trouve
        return True

    @api.model
    def enregistrer_depuis_le_service(self, charge):
        """Cree un message a partir de ce que le service televerse.

        Rend l'identifiant cree, ou celui qui existait deja : un service qui
        reessaie apres une reponse perdue doit obtenir la meme reponse, sans
        quoi il televerse en boucle.

        Une fiche connue est ENRICHIE de ce qu'elle n'a pas encore. Un
        relevement rejoue apres une mise a jour apporte parfois davantage —
        l'annonce du numero, que les anciens ne portaient pas — et l'ignorer
        obligerait a effacer la fiche pour en profiter.
        """
        reference = charge.get("reference")
        if reference:
            connu = self.sudo().search([("source_ref", "=", reference)], limit=1)
            if connu:
                connu._completer_depuis_le_service(charge)
                return connu.id
        son = charge.get("audio_b64") or ""
        message = self.sudo().create(
            {
                # Faux plutot que chaine vide : un champ vide se cherche par
                # « = False », et une chaine vide y echappe.
                "number": charge.get("numero") or False,
                "source": charge.get("source") or "erplibre",
                "received_at": charge.get("recu_le"),
                "duration_seconds": int(charge.get("duree_secondes") or 0),
                "peak": int(charge.get("crete") or 0),
                "audio": son.encode("ascii") if son else False,
                "audio_filename": charge.get("nom_fichier") or "message.wav",
                # Le numero annonce arrive AVEC le message, dans la meme
                # charge : deux envois separes laisseraient une fiche
                # portant l'un sans l'autre.
                "audio_numero": (
                    (charge.get("numero_audio_b64") or "").encode("ascii") or False
                ),
                "audio_numero_filename": charge.get("numero_nom_fichier") or False,
                "numero_duration_seconds": int(
                    charge.get("numero_duree_secondes") or 0
                ),
                "source_ref": reference or False,
            }
        )
        _logger.info(
            "erplibre_repondeur: message %s recu de %s (%s s)",
            message.id,
            message.number,
            message.duration_seconds,
        )
        return message.id

    def taille_du_son(self):
        """Les octets de l'enregistrement, pour un essai ou un diagnostic."""
        self.ensure_one()
        return len(base64.b64decode(self.audio)) if self.audio else 0
