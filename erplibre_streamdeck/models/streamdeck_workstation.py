# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.exceptions import AccessError

MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"

# State of the deck's systemd service, as the workstation reports it.
SERVICE_STATES = [
    ("active", "Active"),
    ("failed", "Failed"),
    ("inactive", "Inactive"),
    ("absent", "Absent"),
]


class StreamdeckWorkstation(models.Model):
    """A workstation of an employee, as its own reports describe it.

    The routes create and update it in sudo, bounded to the workstation of
    the token. Outside sudo, `write` accepts only the fields a person may
    change: the name for its employee, the name and the archive flag for
    the manager. Archiving a workstation clears its token hash, so an
    archived workstation can no longer report.
    """

    _name = "streamdeck.workstation"
    _description = "Stream Deck workstation"
    _order = "name, id"

    _USER_WRITABLE = frozenset({"name"})
    _MANAGER_WRITABLE = frozenset({"name", "active"})

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
            " user and this database: the raw identifier never leaves the"
            " workstation, and two databases cannot match the same"
            " workstation."
        ),
    )
    active = fields.Boolean(default=True)
    os_name = fields.Char(string="Operating system")
    os_version = fields.Char(string="Operating system version")
    gnome_shell = fields.Char(string="GNOME Shell version")
    extension_version = fields.Char()
    contract_version = fields.Char()
    erplibre_branch = fields.Char(string="ERPLibre branch")
    erplibre_commit = fields.Char(string="ERPLibre commit")
    deck_program = fields.Char()
    service_state = fields.Selection(SERVICE_STATES, string="Deck service")
    last_report = fields.Datetime()
    token_hash = fields.Char(
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
    token_created = fields.Datetime(copy=False)
    token_last_used = fields.Datetime(copy=False)
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

    def write(self, vals):
        if not self.env.su:
            self._check_writable(vals)
        result = super().write(vals)
        if "active" in vals and not vals["active"]:
            self.sudo().write({"token_hash": False})
        return result

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

    def action_revoke_token(self):
        """Clear the token hash of workstations the current user may
        write: the workstation must enroll again to report."""
        self.check_access("write")
        self.sudo().write({"token_hash": False})
        return True
