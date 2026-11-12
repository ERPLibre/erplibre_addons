# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models

from .linkup_link import DEFAULT_TOP_COUNT, TOP_COUNT_PARAM
from .linkup_points_ledger import DEFAULT_HALF_LIFE_DAYS, HALF_LIFE_PARAM


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    linkup_network_top_count = fields.Integer(
        string="Partners of the strongest density",
        config_parameter=TOP_COUNT_PARAM,
        default=DEFAULT_TOP_COUNT,
        help="Number of partners the density X3 of the Network view keeps,"
        " the strongest links first.",
    )
    linkup_energy_half_life_days = fields.Integer(
        string="Half-life of the energy (days)",
        config_parameter=HALF_LIFE_PARAM,
        default=DEFAULT_HALF_LIFE_DAYS,
        help="Days after which a point counts half in the energy of a"
        " member and of a link. 0 turns the decay off.",
    )
