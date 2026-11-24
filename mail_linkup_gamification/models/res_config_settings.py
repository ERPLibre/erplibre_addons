# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models
from odoo.addons.base.models.res_partner import _tz_get

from .linkup_points_call import CALL_MIN_DURATION_PARAM
from .linkup_points_rule import VIRTUAL_ROUND_PARAM
from .linkup_report import (
    COLLUSION_DAYS_PARAM,
    NEW_ACCOUNT_CONFIRMATIONS_PARAM,
    NEW_ACCOUNT_HOURS_PARAM,
    PAIR_CONFIRMATIONS_PARAM,
)
from .res_users import (
    DEFAULT_TIMEZONE,
    MIN_ACCOUNT_HOURS_PARAM,
    TIMEZONE_PARAM,
)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    linkup_timezone = fields.Selection(
        _tz_get,
        string="LinkUp time zone",
        config_parameter=TIMEZONE_PARAM,
        default=DEFAULT_TIMEZONE,
        help="Time zone of the members who set none: their decreasing"
        " sequences of points start again at its midnight.",
    )
    linkup_virtual_round_points = fields.Char(
        string="Points of the rounds of free text",
        config_parameter=VIRTUAL_ROUND_PARAM,
        help="Integers separated by commas, such as 100,50,25,12,6,3,1,0;"
        " empty, each round pays half of the previous one.",
    )
    linkup_call_min_duration = fields.Integer(
        string="Minimum duration of a call (seconds)",
        config_parameter=CALL_MIN_DURATION_PARAM,
        default=0,
        help="0 pays an answered call at once; above, the call is paid at"
        " its end, if it lasted that long.",
    )
    linkup_points_min_account_hours = fields.Integer(
        string="Age of an account before its points (hours)",
        config_parameter=MIN_ACCOUNT_HOURS_PARAM,
        default=72,
    )
    linkup_collusion_days = fields.Integer(
        string="Days of the collusion alerts",
        config_parameter=COLLUSION_DAYS_PARAM,
        default=7,
    )
    linkup_collusion_pair_confirmations = fields.Integer(
        string="Confirmations of a pair before an alert",
        config_parameter=PAIR_CONFIRMATIONS_PARAM,
        default=3,
    )
    linkup_collusion_new_account_confirmations = fields.Integer(
        string="Confirmations of new accounts before an alert",
        config_parameter=NEW_ACCOUNT_CONFIRMATIONS_PARAM,
        default=5,
    )
    linkup_collusion_new_account_hours = fields.Integer(
        string="Age of a new account (hours)",
        config_parameter=NEW_ACCOUNT_HOURS_PARAM,
        default=48,
    )
