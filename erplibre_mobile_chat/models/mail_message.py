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
