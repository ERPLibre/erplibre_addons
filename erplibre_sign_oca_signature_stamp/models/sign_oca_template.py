# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class SignOcaTemplate(models.Model):
    _inherit = "sign.oca.template"

    sign_stamp_policy = fields.Selection(
        [
            ("company", "As the company"),
            ("enabled", "Always"),
            ("disabled", "Never"),
        ],
        string="Signature Stamp",
        default="company",
        help="Whether the signatures of the requests of this template carry "
        "the stamp set in the Sign settings of their company.",
    )
