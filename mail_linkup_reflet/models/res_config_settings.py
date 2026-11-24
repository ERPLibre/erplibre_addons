# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, fields, models

from .discuss_channel import (
    START_RULE_DEFAULT,
    START_RULE_MODES,
    START_RULE_PARAM,
)
from .res_users import FIRST_USE_TOUR_PARAM


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    linkup_start_rule_mode = fields.Selection(
        START_RULE_MODES,
        string="LinkUp start rule",
        config_parameter=START_RULE_PARAM,
        default=START_RULE_DEFAULT,
        help="Strict: in a direct conversation, free text, attachments and"
        " calls open once a reflection is confirmed. Incentive: free text is"
        " open, and a banner suggests a reflection. Off: no rule. A"
        " conversation may set its own mode.",
    )
    linkup_invitation_expiry_days = fields.Integer(
        string="Days an invitation lasts",
        config_parameter="linkup.invitation_expiry_days",
        default=14,
    )
    linkup_max_invitations_per_day = fields.Integer(
        string="Invitations per member and per day",
        config_parameter="linkup.max_invitations_per_day",
        default=10,
        help="Every invitation link sent counts, a new one or one sent again.",
    )
    linkup_privacy_policy_url = fields.Char(
        string="Privacy policy",
        config_parameter="linkup.privacy_policy_url",
        help="Address of the privacy policy, linked from the invitation"
        " emails and pages.",
    )
    # Not a ``config_parameter`` field: unchecking one deletes its parameter,
    # which this switch reads as on.
    linkup_first_use_tour = fields.Boolean(
        string="First-use tour",
        help="A short tour starts the first time a member opens Discuss.",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        res["linkup_first_use_tour"] = self.env[
            "res.users"
        ]._linkup_first_use_tour_enabled()
        return res

    def set_values(self):
        super().set_values()
        self.env["ir.config_parameter"].sudo().set_param(
            FIRST_USE_TOUR_PARAM,
            "True" if self.linkup_first_use_tour else "False",
        )

    def action_linkup_reset_first_use_tour(self):
        """Show the first-use tour again to every member."""
        count = self.env["res.users"]._linkup_reset_first_use_tour()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": _(
                    "The tour will start again for %(count)s members.",
                    count=count,
                ),
            },
        }
