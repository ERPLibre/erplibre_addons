# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""L'identifiant client d'un message publié depuis l'application mobile."""

from odoo import fields, models


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
        self.env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS"
            " mail_message_erplibre_client_uuid_uniq"
            " ON mail_message (author_id, model, res_id,"
            " erplibre_client_uuid)"
            " WHERE erplibre_client_uuid IS NOT NULL"
        )
