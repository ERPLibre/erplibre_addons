# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""L'identifiant client d'une pièce jointe téléversée depuis l'application
mobile."""

from odoo import api, fields, models

from .mail_message import erplibre_ensure_unique_uuid_index


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    erplibre_client_uuid = fields.Char(
        string="Client UUID",
        index="btree_not_null",
        copy=False,
        readonly=True,
        help="Identifiant généré par l'application mobile ; un renvoi du"
        " même identifiant par le même utilisateur ne crée pas de seconde"
        " pièce jointe.",
    )

    def init(self):
        # Garantie du dédoublonnage du téléversement (voir
        # erplibre_lock_uuid). L'index btree_not_null du champ reste pour la
        # recherche par seul identifiant.
        super().init()
        erplibre_ensure_unique_uuid_index(
            self.env.cr,
            "ir_attachment",
            "ir_attachment_erplibre_client_uuid_uniq",
            ["create_uid", "erplibre_client_uuid"],
        )

    @api.model_create_multi
    def create(self, vals_list):
        """Avec `erplibre_attachment_uuid` dans le contexte, enregistre cet
        identifiant sur chaque pièce jointe créée qui n'en porte pas.

        La clé de contexte est distincte de `erplibre_client_uuid`, que lit
        discuss.channel.create : un canal et une pièce jointe ne partagent
        pas d'identifiant. L'index unique refuse une seconde pièce jointe
        du même créateur avec le même identifiant.
        """
        uuid = self.env.context.get("erplibre_attachment_uuid")
        if uuid:
            vals_list = [
                (
                    vals
                    if vals.get("erplibre_client_uuid")
                    else dict(vals, erplibre_client_uuid=uuid)
                )
                for vals in vals_list
            ]
        return super().create(vals_list)
