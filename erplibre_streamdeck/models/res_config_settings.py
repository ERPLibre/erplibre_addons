# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import str2bool

# Every setting is the `ir.config_parameter` PARAM_PREFIX + <name>.
PARAM_PREFIX = "erplibre_streamdeck."

# The problems that may open an activity, each with its own check box.
ALERT_KINDS = ("service_failed", "silent", "moved", "unplugged")

# The smallest value each delay accepts. Two missed 15-minute heartbeats
# make the silent floor: one missed heartbeat is not silence.
DELAY_FLOORS = {
    "silent_after_min": 30,
    "unplugged_after_h": 1,
    "service_failed_after_min": 0,
}
DELAY_DEFAULTS = {
    "silent_after_min": 60,
    "unplugged_after_h": 72,
    "service_failed_after_min": 10,
}

# What Odoo does at the first pilot report of a workstation whose free
# local values differ from Odoo's: ask its employee, or the choice the
# organisation forces.
FIRST_PILOT_POLICIES = [
    ("ask", "Ask the employee"),
    ("keep_local", "Keep local values"),
    ("take_odoo", "Take Odoo's values"),
]

RECIPIENTS = [
    ("employee", "Employee"),
    ("manager", "Manager"),
    ("both", "Employee and manager"),
]


def _manager_domain(settings):
    """The internal users of the Stream Deck manager group: only they read
    every workstation and deck an activity is about."""
    group = settings.env.ref(
        "erplibre_streamdeck.group_streamdeck_manager",
        raise_if_not_found=False,
    )
    return [("share", "=", False), ("groups_id", "in", group.ids)]


class ResConfigSettings(models.TransientModel):
    """Settings › Stream Deck: what the monitoring does beyond history,
    and the first-pilot policy of the managed configuration.

    Each setting lives in `ir.config_parameter` under PARAM_PREFIX, so
    only the Settings page (`base.group_system`) writes it. The four alert
    boxes are checked by default; Odoo's `config_parameter` deletes the
    parameter of a cleared box, which would bring the default back, so
    `get_values` / `set_values` store them as "True" / "False" instead.

    `streamdeck_first_pilot_policy` reads "ask" when its parameter is
    missing or unknown (`streamdeck.config.schema._first_pilot_policy`).

    `set_values` refuses, with ValidationError, a delay below its floor
    and activities enabled for a manager nobody is named for.
    """

    _inherit = "res.config.settings"

    streamdeck_activities_enabled = fields.Boolean(
        string="Stream Deck detection activities",
        config_parameter=PARAM_PREFIX + "activities_enabled",
        help=(
            "Open an Odoo activity for each problem the monitoring"
            " detects, and close it when the problem is solved. Without"
            " it, the monitoring only writes the history."
        ),
    )
    streamdeck_activity_recipient = fields.Selection(
        RECIPIENTS,
        string="Activities for",
        default="manager",
        config_parameter=PARAM_PREFIX + "activity_recipient",
        help=(
            "The employee is the one of the workstation, or of the"
            " workstation that holds the deck. Both give one activity"
            " to each."
        ),
    )
    streamdeck_activity_manager_id = fields.Many2one(
        "res.users",
        string="Activity manager",
        domain=_manager_domain,
        config_parameter=PARAM_PREFIX + "activity_manager_id",
        help="The Stream Deck manager who receives the activities.",
    )
    streamdeck_alert_service_failed = fields.Boolean(
        string="Deck service failed", default=True
    )
    streamdeck_alert_silent = fields.Boolean(
        string="Workstation silent", default=True
    )
    streamdeck_alert_moved = fields.Boolean(
        string="Deck changed workstation", default=True
    )
    streamdeck_alert_unplugged = fields.Boolean(
        string="Deck unplugged for long", default=True
    )
    streamdeck_silent_after_min = fields.Integer(
        string="Silent after (minutes)",
        default=DELAY_DEFAULTS["silent_after_min"],
        config_parameter=PARAM_PREFIX + "silent_after_min",
        help=(
            "A workstation that has not reported for this delay is"
            " silent. The workstation reports every 15 minutes."
        ),
    )
    streamdeck_unplugged_after_h = fields.Integer(
        string="Unplugged for long after (hours)",
        default=DELAY_DEFAULTS["unplugged_after_h"],
        config_parameter=PARAM_PREFIX + "unplugged_after_h",
    )
    streamdeck_service_failed_after_min = fields.Integer(
        string="Service failed for (minutes)",
        default=DELAY_DEFAULTS["service_failed_after_min"],
        config_parameter=PARAM_PREFIX + "service_failed_after_min",
        help=(
            "The deck service restarts by itself after a failure: a"
            " failure shorter than this delay opens no activity."
        ),
    )

    streamdeck_first_pilot_policy = fields.Selection(
        FIRST_PILOT_POLICIES,
        string="First pilot",
        default="ask",
        required=True,
        config_parameter=PARAM_PREFIX + "first_pilot_policy",
        help=(
            "At the first report of a piloted workstation, the free"
            " settings whose local value differs from Odoo's: the"
            " employee chooses, or this choice applies. Locked settings"
            " are always offered for the employee's confirmation."
        ),
    )

    def get_values(self):
        res = super().get_values()
        res["streamdeck_first_pilot_policy"] = self.env[
            "streamdeck.config.schema"
        ]._first_pilot_policy()
        params = self.env["ir.config_parameter"].sudo()
        for kind in ALERT_KINDS:
            stored = params.get_param(PARAM_PREFIX + "alert_" + kind)
            res["streamdeck_alert_" + kind] = str2bool(stored or "True", True)
        return res

    def set_values(self):
        self._check_streamdeck_settings()
        super().set_values()
        params = self.env["ir.config_parameter"].sudo()
        for kind in ALERT_KINDS:
            params.set_param(
                PARAM_PREFIX + "alert_" + kind,
                str(bool(self["streamdeck_alert_" + kind])),
            )

    def _check_streamdeck_settings(self):
        floors = DELAY_FLOORS
        for settings in self:
            if (
                settings.streamdeck_silent_after_min
                < floors["silent_after_min"]
            ):
                raise ValidationError(
                    _(
                        "A workstation is silent after %(floor)s minutes at"
                        " least: one missed heartbeat is not silence.",
                        floor=floors["silent_after_min"],
                    )
                )
            if (
                settings.streamdeck_unplugged_after_h
                < floors["unplugged_after_h"]
            ):
                raise ValidationError(
                    _(
                        "A deck is unplugged for long after %(floor)s hour at"
                        " least.",
                        floor=floors["unplugged_after_h"],
                    )
                )
            if (
                settings.streamdeck_service_failed_after_min
                < floors["service_failed_after_min"]
            ):
                raise ValidationError(
                    _(
                        "The delay of a failed deck service is %(floor)s"
                        " minutes at least.",
                        floor=floors["service_failed_after_min"],
                    )
                )
            if (
                settings.streamdeck_activities_enabled
                and settings.streamdeck_activity_recipient != "employee"
                and not settings.streamdeck_activity_manager_id
            ):
                raise ValidationError(
                    _(
                        "Name the manager who receives the Stream Deck"
                        " activities, or send them to the employee only."
                    )
                )
