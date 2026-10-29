# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""L'identifiant client d'un message publié depuis l'application mobile,
l'empreinte de son corps, le favori idempotent et le niveau du module."""

import hashlib
import logging

from odoo import api, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.tools.sql import index_exists

_logger = logging.getLogger(__name__)


def erplibre_ensure_unique_uuid_index(cr, table, index, columns):
    """Crée l'index unique partiel (columns) sur les lignes dont
    erplibre_client_uuid est renseigné, s'il n'existe pas.

    Une base montée avec une version sans l'index peut porter des doublons
    qui feraient échouer la création, donc la mise à jour du module : avant
    de créer l'index, tout doublon d'un groupe garde son identifiant pour la
    ligne de plus petit id et le perd pour les autres (la ligne reste, seul
    le dédoublonnage futur la perd). Sans effet quand l'index existe déjà.
    """
    if index_exists(cr, index):
        return
    cols = ", ".join(columns)
    cr.execute(
        f"UPDATE {table} SET erplibre_client_uuid = NULL"
        f" WHERE id IN (SELECT id FROM (SELECT id, ROW_NUMBER() OVER"
        f" (PARTITION BY {cols} ORDER BY id) AS rank FROM {table}"
        f" WHERE erplibre_client_uuid IS NOT NULL) ranked WHERE rank > 1)"
    )
    if cr.rowcount:
        _logger.warning(
            "%s: %s duplicate erplibre_client_uuid cleared before indexing",
            table,
            cr.rowcount,
        )
    cr.execute(
        f"CREATE UNIQUE INDEX {index} ON {table} ({cols})"
        f" WHERE erplibre_client_uuid IS NOT NULL"
    )


class MailMessage(models.Model):
    _inherit = "mail.message"

    erplibre_client_uuid = fields.Char(
        string="Client UUID",
        index="btree_not_null",
        copy=False,
        readonly=True,
        help="Identifiant généré par l'application mobile ; un renvoi du"
        " même identifiant par le même auteur sur le même fil ne crée"
        " pas de second message.",
    )

    erplibre_body_fingerprint = fields.Char(
        string="Body Fingerprint",
        compute="_compute_erplibre_body_fingerprint",
        help="SHA-256 hexadécimal du corps HTML tel que le rend Store,"
        " encodé en UTF-8 ; la modification gardée le compare à"
        " l'empreinte attendue par l'application.",
    )

    erplibre_chat_level = fields.Selection(
        [("1.4", "1.4"), ("1.5", "1.5")],
        string="ERPLibre Chat Level",
        compute="_compute_erplibre_chat_level",
        help="Niveau du module : la plus haute clé de la sélection. Un"
        " niveau suivant ajoute sa clé en fin de sélection.",
    )

    @api.depends("body")
    def _compute_erplibre_body_fingerprint(self):
        # Le champ, non stocké et sans groupe, figure dans fields_get pour
        # tout utilisateur interne : sa présence signale aussi le niveau
        # 1.3 du module, qui offre la modification gardée.
        for message in self:
            message.erplibre_body_fingerprint = hashlib.sha256(
                str(message.body or "").encode()
            ).hexdigest()

    def _compute_erplibre_chat_level(self):
        # La sélection, non stockée et sans groupe, figure dans fields_get
        # pour tout utilisateur interne, avec ses clés : l'application lit
        # le niveau dans `selection` sans lire d'enregistrement.
        # Un niveau s'ajoute en fin de sélection : la dernière clé est la
        # plus haute.
        level = self._fields["erplibre_chat_level"].selection[-1][0]
        for message in self:
            message.erplibre_chat_level = level

    def erplibre_set_starred(self, starred):
        """Met les messages en favori (`starred` vrai) ou les en retire pour
        l'utilisateur courant, et rend leur état au format de
        `toggle_message_starred`.

        Contrairement à la bascule d'Odoo, un renvoi ne défait rien : seuls
        les messages dont l'état diffère changent, et le bus
        `mail.message/toggle_star` de l'utilisateur ne porte que ceux-là ;
        aucun envoi quand rien ne change. Comme chez Odoo, tout message
        lisible peut être mis en favori : un message illisible lève
        AccessError.
        """
        starred = bool(starred)
        self.check_access("read")
        changed = self.filtered(lambda message: message.starred != starred)
        if changed:
            partner = self.env.user.partner_id
            if starred:
                partner.starred_message_ids |= changed
            else:
                partner.starred_message_ids -= changed
            self.env.user._bus_send(
                "mail.message/toggle_star",
                {"message_ids": changed.ids, "starred": starred},
            )
        return Store(self, {"starred": starred}).get_result()

    def init(self):
        # Garantie du dédoublonnage de message_post (voir
        # erplibre_lock_uuid : le verrou sérialise, cet index garantit).
        # L'index btree_not_null du champ reste pour la recherche par seul
        # identifiant.
        super().init()
        erplibre_ensure_unique_uuid_index(
            self.env.cr,
            "mail_message",
            "mail_message_erplibre_client_uuid_uniq",
            ["author_id", "model", "res_id", "erplibre_client_uuid"],
        )
