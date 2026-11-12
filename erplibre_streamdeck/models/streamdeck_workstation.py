# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import re

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .streamdeck_device import usb_model_name

MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"

# State of the deck's systemd service, as the workstation reports it.
SERVICE_STATES = [
    ("active", "Active"),
    ("failed", "Failed"),
    ("inactive", "Inactive"),
    ("absent", "Absent"),
]

# Where the managed configuration of a workstation stands: no managed key;
# a revision offered and not yet applied; the offered revision applied;
# refused by the workstation; a locked key changed in the workstation file.
CONFIG_STATES = [
    ("unmanaged", "Unmanaged"),
    ("pending", "Pending"),
    ("applied", "Applied"),
    ("refused", "Refused"),
    ("drift", "Changed locally"),
]

# The first contract of the GNOME extension that takes in the managed
# configuration (protocol 1.1): an older one reports and is never piloted.
PILOT_CONTRACT = (1, 3)
_VERSION_RE = re.compile(r"(\d+)\.(\d+)")

# How the first pilot of a workstation settled the free settings whose
# local value differed from Odoo's.
FIRST_CHOICES = [
    ("keep_local", "Keep local values"),
    ("take_odoo", "Take Odoo's values"),
]


class StreamdeckWorkstation(models.Model):
    """A workstation of an employee, as its own reports describe it.

    The routes create and update it in sudo, bounded to the workstation of
    the token. Outside sudo, `write` accepts only the fields a person may
    change: the name for its employee, the name and the archive flag for
    the manager. Archiving a workstation clears its token hash, so an
    archived workstation can no longer report.

    `silent_since` marks a workstation that stopped reporting: it is dated
    the end of the silent delay after `last_report`, and the next report
    clears it. `service_state_since` is the reception time of the report
    that first carried the current `service_state`, or of the next report
    when it has no date. Neither is in the writable sets: only sudo writes
    them.

    The managed configuration: `config_profile_id` and `config_line_ids`
    are layers of `streamdeck.config.schema._effective`. The employee
    writes them on their own workstations within the manager's limits:
    `_check_profile_pick` bounds the profile, `streamdeck.config.line`
    the overrides. The other `config_*` fields are the state of the
    configuration offered to the workstation; only sudo writes them.

    Archiving a workstation or clearing its token closes, before anything
    else, the monitoring activities it will never solve
    (`streamdeck.monitor._resolve_all`): Odoo deletes the open activities
    of an archived record, so they are closed first and stay done. It
    clears `silent_since` too, which no report will clear any more.
    """

    _name = "streamdeck.workstation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Stream Deck workstation"
    _order = "name, id"

    _USER_WRITABLE = frozenset(
        {"name", "config_profile_id", "config_line_ids", "layout_ids"}
    )
    _MANAGER_WRITABLE = frozenset(
        {
            "name",
            "active",
            "config_profile_id",
            "config_line_ids",
            "layout_ids",
        }
    )

    user_id = fields.Many2one(
        "res.users",
        string="Employee",
        required=True,
        index=True,
        ondelete="restrict",
    )
    name = fields.Char(
        required=True,
        help="Host name given at enrollment; the employee may rename it.",
    )
    fingerprint = fields.Char(
        size=64,
        required=True,
        help=(
            "HMAC-SHA256 of the machine identifier, keyed by the Linux"
            " user, the URL of this Odoo and this database: the raw"
            " identifier never leaves the workstation, and two Odoo"
            " destinations cannot match the same workstation."
        ),
    )
    active = fields.Boolean(default=True)
    os_name = fields.Char(string="Operating system")
    os_version = fields.Char(string="Operating system version")
    gnome_shell = fields.Char(string="GNOME Shell version")
    extension_version = fields.Char(string="Extension version")
    contract_version = fields.Char(string="Contract version")
    erplibre_branch = fields.Char(string="ERPLibre branch")
    erplibre_commit = fields.Char(string="ERPLibre commit")
    deck_program = fields.Char(string="Deck program")
    deck_plugins = fields.Text(
        string="Deck plugins",
        readonly=True,
        help="The ids of the deck plugins found on the workstation's disk,"
        " separated by commas, as its last report of protocol 1.1 or later"
        " listed them.",
    )
    service_state = fields.Selection(SERVICE_STATES, string="Deck service")
    service_state_since = fields.Datetime(
        string="Deck service state since",
        readonly=True,
        copy=False,
        help="When this database first received the current state of the"
        " deck service.",
    )
    last_report = fields.Datetime(string="Last report")
    silent_since = fields.Datetime(
        string="Silent since",
        readonly=True,
        copy=False,
        help="Set when the workstation has not reported for the silent"
        " delay, dated the end of that delay; its next report clears it.",
    )
    token_hash = fields.Char(
        string="Token hash",
        groups="base.group_system",
        copy=False,
        index="btree_not_null",
        help="SHA-256 of the workstation token; the token itself is kept"
        " only by the workstation.",
    )
    token_active = fields.Boolean(
        compute="_compute_token_active",
        store=True,
        string="Enrolled",
        help="The workstation holds a token that this database accepts.",
    )
    token_created = fields.Datetime(string="Token created", copy=False)
    token_last_used = fields.Datetime(string="Token last used", copy=False)
    lost_events_total = fields.Integer(
        string="Lost events",
        readonly=True,
        help="Events the workstation dropped unsent because its offline"
        " queue was full or too old: the largest running total it"
        " reported, so a report sent again changes nothing.",
    )
    device_ids = fields.One2many(
        "streamdeck.device",
        "workstation_id",
        string="Decks",
        help="Decks whose last report came from this workstation.",
    )
    event_ids = fields.One2many(
        "streamdeck.event", "workstation_id", string="Events"
    )

    config_profile_id = fields.Many2one(
        "streamdeck.config.profile",
        string="Configuration profile",
        index="btree_not_null",
        ondelete="restrict",
        help="The manager assigns any profile; the employee picks a"
        " selectable one, unless the manager assigned one that is not.",
    )
    config_line_ids = fields.One2many(
        "streamdeck.config.line",
        "workstation_id",
        string="Configuration overrides",
    )
    layout_ids = fields.One2many(
        "streamdeck.key.layout",
        "workstation_id",
        string="Key layouts",
        help="The key layouts of this workstation, over those of its"
        " profile and of its deck models.",
    )
    config_layouts_html = fields.Html(
        string="Key layouts of the connected decks",
        compute="_compute_config_layouts_html",
        sanitize=False,
    )
    config_revision = fields.Integer(
        string="Offered revision",
        readonly=True,
        copy=False,
        help="Grows each time the effective configuration changes.",
    )
    config_hash = fields.Char(
        string="Offered configuration hash", readonly=True, copy=False
    )
    config_offered = fields.Text(
        string="Offered configuration",
        readonly=True,
        copy=False,
        help="JSON of the settings of the offered revision.",
    )
    config_applied_revision = fields.Integer(
        string="Applied revision", readonly=True, copy=False
    )
    config_applied = fields.Text(
        string="Applied configuration",
        readonly=True,
        copy=False,
        help="JSON of the settings the workstation last applied.",
    )
    config_written = fields.Text(
        string="Configuration in the file",
        readonly=True,
        copy=False,
        help="JSON of the settings of the last revision written to the"
        " workstation's file: the applied one, or a later one refused after"
        " its write. A local change is measured against them.",
    )
    config_state = fields.Selection(
        CONFIG_STATES,
        string="Configuration",
        default="unmanaged",
        required=True,
        readonly=True,
        copy=False,
    )
    config_reason = fields.Char(
        string="Refusal reason", readonly=True, copy=False
    )
    config_pending_since = fields.Datetime(
        string="Configuration pending since", readonly=True, copy=False
    )
    config_ask = fields.Char(
        string="Settings asked",
        readonly=True,
        copy=False,
        help="The free settings, separated by commas, whose local value"
        " the employee is asked to keep or replace by Odoo's: the first"
        " pilot waits for their choice.",
    )
    config_first_choice = fields.Selection(
        FIRST_CHOICES,
        string="First pilot choice",
        readonly=True,
        copy=False,
        help="Set once, at the first pilot of the workstation, by the"
        " employee's answer or by the organisation's policy.",
    )
    config_effective_html = fields.Html(
        string="Effective configuration",
        compute="_compute_config_effective_html",
        sanitize=False,
    )
    config_profile_selectable = fields.Boolean(
        related="config_profile_id.selectable",
        string="Profile selectable",
    )
    config_several_models = fields.Boolean(
        string="Several deck models",
        compute="_compute_config_several_models",
        help="Decks of several models that have a settings layer are"
        " connected: their layers apply by ascending USB product id.",
    )
    config_too_old = fields.Boolean(
        string="Extension too old to pilot",
        compute="_compute_config_too_old",
        help="The contract version the workstation reports is older than"
        " the first one that takes in the managed configuration.",
    )

    _sql_constraints = [
        (
            "user_fingerprint_unique",
            "UNIQUE(user_id, fingerprint)",
            "An employee has one workstation per fingerprint.",
        ),
    ]

    @api.depends("token_hash")
    def _compute_token_active(self):
        for workstation in self:
            workstation.token_active = bool(workstation.token_hash)

    def _compute_config_effective_html(self):
        """A table of the effective configuration: setting, value as a
        person reads it, layer it comes from, lock."""
        schema = self.env["streamdeck.config.schema"]
        keys = dict(
            self.env["streamdeck.config.line"]
            ._fields["key"]
            ._description_selection(self.env)
        )
        layer_names = {
            "profile": _("Profile"),
            "model": _("Deck model"),
            "workstation": _("Workstation"),
        }
        for workstation in self:
            effective = schema._effective(workstation)
            if not effective["settings"]:
                workstation.config_effective_html = Markup("<p>%s</p>") % _(
                    "Odoo manages no setting of this workstation."
                )
                continue
            rows = Markup().join(
                Markup("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>")
                % (
                    keys.get(key, key),
                    schema._format(key, value),
                    layer_names[effective["sources"][key]],
                    _("Locked") if key in effective["locked"] else "",
                )
                for key, value in effective["settings"].items()
            )
            workstation.config_effective_html = Markup(
                '<table class="table table-sm"><thead><tr><th>%s</th>'
                "<th>%s</th><th>%s</th><th>%s</th></tr></thead>"
                "<tbody>%s</tbody></table>"
            ) % (_("Setting"), _("Value"), _("Layer"), _("Lock"), rows)

    def _compute_config_layouts_html(self):
        """Per connected deck model, the layout Odoo sends: the layer it
        comes from, its lock and its grid; or why there is none."""
        schema = self.env["streamdeck.config.schema"]
        layer_names = {
            "profile": _("Profile"),
            "model": _("Deck model"),
            "workstation": _("Workstation"),
        }
        for workstation in self:
            products = schema._connected_products(workstation)
            if not products:
                workstation.config_layouts_html = Markup("<p>%s</p>") % _(
                    "No deck is connected to this workstation."
                )
                continue
            layouts = schema._effective_layouts(workstation)
            parts = []
            for product in products:
                title = Markup("<h5>%s (%s)</h5>") % (
                    usb_model_name(product),
                    product,
                )
                entry = layouts.get(product)
                if not entry:
                    parts.append(
                        title
                        + Markup("<p>%s</p>")
                        % _(
                            "Automatic layout: no layer lays out this"
                            " deck model."
                        )
                    )
                    continue
                layout = entry["layout"].sudo()
                origin = layer_names[entry["source"]]
                if entry["locked"]:
                    origin = "%s, %s" % (origin, _("Locked"))
                parts.append(
                    title
                    + Markup('<p class="text-muted">%s</p>') % origin
                    + layout._preview(layout._missing_plugins())
                )
            workstation.config_layouts_html = Markup().join(parts)

    def _compute_config_several_models(self):
        schema = self.env["streamdeck.config.schema"]
        for workstation in self:
            layers = schema._layers(workstation)
            workstation.config_several_models = (
                sum(1 for layer, _lines in layers if layer == "model") > 1
            )

    @api.depends("contract_version")
    def _compute_config_too_old(self):
        """True when `contract_version` reads `<major>.<minor>` below
        PILOT_CONTRACT; an empty or unreadable version tells nothing."""
        for workstation in self:
            match = _VERSION_RE.fullmatch(workstation.contract_version or "")
            workstation.config_too_old = bool(match) and (
                tuple(int(part) for part in match.groups()) < PILOT_CONTRACT
            )

    def write(self, vals):
        if not self.env.su:
            self._check_writable(vals)
            if not self.env.user.has_group(MANAGER_GROUP):
                self._check_profile_pick(vals)
        if "active" in vals and not vals["active"]:
            self.filtered("active")._end_monitoring("archived")
        elif "token_hash" in vals and not vals["token_hash"]:
            self.sudo().filtered("token_hash")._end_monitoring("unenrolled")
        result = super().write(vals)
        if "active" in vals and not vals["active"]:
            self.sudo().write({"token_hash": False})
        return result

    def toggle_active(self):
        self.filtered("active")._end_monitoring("archived")
        return super().toggle_active()

    def _end_monitoring(self, reason):
        """Close the monitoring activities of these workstations, `reason`
        being "archived" or "unenrolled", and clear their `silent_since`:
        the cron watches only active workstations with a token, so a mark
        left there would never be cleared. The `silent` event stays in
        the history."""
        Monitor = self.env["streamdeck.monitor"]
        for workstation in self:
            Monitor._resolve_all(workstation, reason)
        self.sudo().filtered("silent_since").write({"silent_since": False})

    def _check_writable(self, vals):
        """Raise AccessError when `vals` holds a field that the current
        user may not change by hand; the record rules still decide which
        workstations the user may write."""
        if self.env.user.has_group(MANAGER_GROUP):
            allowed = self._MANAGER_WRITABLE
        else:
            allowed = self._USER_WRITABLE
        refused = sorted(set(vals) - allowed)
        if refused:
            raise AccessError(
                _(
                    "These workstation fields come from the workstation's"
                    " reports and cannot be changed by hand: %(fields)s",
                    fields=", ".join(refused),
                )
            )

    def _check_profile_pick(self, vals):
        """Raise AccessError unless the employee's `vals` leaves
        `config_profile_id` alone or sets it to an active selectable
        profile on workstations whose current profile is empty or
        selectable: an employee never clears a profile nor replaces one
        the manager assigned without making it selectable. An archived
        profile is no layer of `_effective`, so picking one would clear
        the profile and its locks."""
        if "config_profile_id" not in vals:
            return
        profile = (
            self.env["streamdeck.config.profile"]
            .sudo()
            .browse(vals["config_profile_id"])
        )
        current = self.sudo().mapped("config_profile_id")
        if not (profile.selectable and profile.active) or not all(
            current.mapped("selectable")
        ):
            raise AccessError(
                _(
                    "An employee picks a selectable configuration profile,"
                    " in place of no profile or of a selectable one."
                )
            )

    def _get_mail_message_access(self, res_ids, operation, model_name=None):
        """Name the right on the workstation that `operation` on a message
        or an activity of its thread requires.

        Odoo lets a user who writes a record modify or delete any message
        and any activity of its thread. An employee writes their
        workstation only to rename it, so for anyone but a Stream Deck
        manager a write or an unlink there asks for the unlink right on
        the workstation, which ir.model.access.csv grants no group. The
        employee still posts on the thread, edits their own messages, and
        modifies or closes the activities assigned to them or created by
        them: mail.activity's own rule allows those.
        """
        check = super()._get_mail_message_access(
            res_ids, operation, model_name=model_name
        )
        if operation in ("write", "unlink") and not self.env.user.has_group(
            MANAGER_GROUP
        ):
            return "unlink"
        return check

    def action_revoke_token(self):
        """Clear the token hash of workstations the current user may
        write: the workstation must enroll again to report."""
        self.check_access("write")
        self.sudo().write({"token_hash": False})
        return True
