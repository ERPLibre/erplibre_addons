# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models

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

    @api.model
    def get_values(self):
        """Show the half-life the server applies: an invalid stored value
        reads 0 in ``res.config.settings``, which a later save would store
        and so turn the decay off, where the server reads the 90 days of
        the default."""
        res = super().get_values()
        res["linkup_energy_half_life_days"] = self.env[
            "linkup.reflet"
        ]._linkup_param(HALF_LIFE_PARAM, DEFAULT_HALF_LIFE_DAYS)
        return res
