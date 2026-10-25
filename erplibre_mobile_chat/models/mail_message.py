# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""L'identifiant client d'un message publié depuis l'application mobile."""

import logging

from odoo import fields, models
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
        " même identifiant par le même auteur dans le même canal ne crée"
        " pas de second message.",
    )

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
