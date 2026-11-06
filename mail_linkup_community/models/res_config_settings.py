# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models

from .linkup_moderation_notice import APPEAL_DAYS_PARAM, DEFAULT_APPEAL_DAYS
from .linkup_personal_data import RETENTION
from .linkup_report import (
    CONTEXT_PARAM,
    DEFAULT_CONTEXT_MESSAGES,
    DEFAULT_DUE_HOURS,
    DEFAULT_SUSPENSION_DAYS,
    DEFAULT_URGENT_HOURS,
    DUE_HOURS_PARAM,
    SUSPENSION_DAYS_PARAM,
    URGENT_HOURS_PARAM,
)
from .res_users import (
    CONSENT_ALL_PARAM,
    DEFAULT_RESEND_MINUTES,
    DEFAULT_SIGNUP_RATE,
    DISPOSABLE_PARAM,
    HELP_RESOURCES_PARAM,
    MODERATION_HOURS_PARAM,
    RESEND_MINUTES_PARAM,
    SIGNUP_RATE_PARAM,
    TERMS_URL_PARAM,
    VERIFICATION_PARAM,
)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Not ``config_parameter`` fields: unchecking one deletes its parameter,
    # which these switches read as on.
    linkup_email_verification = fields.Boolean(
        string="Verify the email address",
        help="A new account sends, invites and earns nothing before the"
        " click on the link of its verification email.",
    )
    linkup_signup_rate_per_ip_hour = fields.Integer(
        string="Signups per IP address and per hour",
        config_parameter=SIGNUP_RATE_PARAM,
        default=DEFAULT_SIGNUP_RATE,
    )
    linkup_verification_resend_minutes = fields.Integer(
        string="Minutes between two verification emails",
        config_parameter=RESEND_MINUTES_PARAM,
        default=DEFAULT_RESEND_MINUTES,
    )
    linkup_disposable_email_domains = fields.Char(
        string="Refused email domains",
        config_parameter=DISPOSABLE_PARAM,
        help="Domains of disposable addresses, separated by commas; their"
        " subdomains are refused too.",
    )
    linkup_terms_url = fields.Char(
        string="Terms of use",
        config_parameter=TERMS_URL_PARAM,
        help="Address of the terms of use, linked from the signup and the"
        " profile.",
    )
    linkup_consent_all_members = fields.Boolean(
        string="Consents of every member",
        config_parameter=CONSENT_ALL_PARAM,
        help="Every member, also those created by an administrator, accepts"
        " the terms of use, the privacy policy and the processing of"
        " sensitive information before sending anything.",
    )

    linkup_help_resources = fields.Text(
        string="Help resources",
        config_parameter=HELP_RESOURCES_PARAM,
        help="One resource per line, shown under “Need help now” and with a"
        " report of a person in distress. Empty, LinkUp shows the crisis"
        " line 9-8-8 and the emergency number 9-1-1 of Canada.",
    )
    linkup_moderation_hours = fields.Char(
        string="Hours of the moderation",
        config_parameter=MODERATION_HOURS_PARAM,
        help="When moderators read the reports, as members read it; outside"
        " these hours, the help resources stand in.",
    )
    linkup_report_urgent_hours = fields.Integer(
        string="Hours to handle an urgent report",
        config_parameter=URGENT_HOURS_PARAM,
        default=DEFAULT_URGENT_HOURS,
        help="Shown to the members who report a threat, a minor in danger or"
        " a person in distress.",
    )
    linkup_report_due_hours = fields.Integer(
        string="Hours to handle another report",
        config_parameter=DUE_HOURS_PARAM,
        default=DEFAULT_DUE_HOURS,
    )
    linkup_moderation_context_messages = fields.Integer(
        string="Messages of context",
        config_parameter=CONTEXT_PARAM,
        default=DEFAULT_CONTEXT_MESSAGES,
        help="Messages a moderator reads before and after a reported one.",
    )
    linkup_suspension_days = fields.Integer(
        string="Days of a suspension",
        config_parameter=SUSPENSION_DAYS_PARAM,
        default=DEFAULT_SUSPENSION_DAYS,
    )
    linkup_appeal_days = fields.Integer(
        string="Days to contest a decision",
        config_parameter=APPEAL_DAYS_PARAM,
        default=DEFAULT_APPEAL_DAYS,
    )

    # Retention of the personal data (LU-NF-015, Q-31).
    linkup_deletion_grace_days = fields.Integer(
        string="Days before a deletion",
        config_parameter=RETENTION["deletion_grace"][0],
        default=RETENTION["deletion_grace"][2],
        help="Delay of grace between the request of a member and the"
        " erasure of their account; the member cancels it meanwhile.",
    )
    linkup_retention_unverified_days = fields.Integer(
        string="Days of an unverified account",
        config_parameter=RETENTION["unverified"][0],
        default=RETENTION["unverified"][2],
        help="An account of the public signup never verified is erased"
        " after this delay.",
    )
    linkup_retention_draft_days = fields.Integer(
        string="Days of a draft",
        config_parameter=RETENTION["draft"][0],
        default=RETENTION["draft"][2],
    )
    linkup_retention_closed_reflet_months = fields.Integer(
        string="Months of a rejected or expired reflection",
        config_parameter=RETENTION["closed_reflet"][0],
        default=RETENTION["closed_reflet"][2],
        help="Its texts are erased after this delay; its dates stay.",
    )
    linkup_retention_inactive_pair_months = fields.Integer(
        string="Months without activity of a pair",
        config_parameter=RETENTION["inactive_pair"][0],
        default=RETENTION["inactive_pair"][2],
        help="The reflections and the messages of a pair are erased after"
        " this delay without any exchange.",
    )
    linkup_retention_closed_report_months = fields.Integer(
        string="Months of a closed report",
        config_parameter=RETENTION["closed_report"][0],
        default=RETENTION["closed_report"][2],
        help="A closed report is deleted after this delay, with its audit"
        " log and the originals of the content it hid.",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        res["linkup_email_verification"] = self.env[
            "res.users"
        ]._linkup_verification_enabled()
        return res

    def set_values(self):
        super().set_values()
        self.env["ir.config_parameter"].sudo().set_param(
            VERIFICATION_PARAM,
            "True" if self.linkup_email_verification else "False",
        )
