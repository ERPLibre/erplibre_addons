# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models

from .linkup_link import DEFAULT_TOP_COUNT, TOP_COUNT_PARAM


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    linkup_network_top_count = fields.Integer(
        string="Partners of the strongest density",
        config_parameter=TOP_COUNT_PARAM,
        default=DEFAULT_TOP_COUNT,
        help="Number of partners the density X3 of the Network view keeps,"
        " the strongest links first.",
    )
