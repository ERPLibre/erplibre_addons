# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

AUDIT_ACTIONS = [
    ("content_read", "Read the reported content"),
    ("take", "Took the report"),
    ("dismiss", "Dismissed"),
    ("hide", "Hid the content"),
    ("warn", "Warned"),
    ("suspend", "Suspended"),
    ("ban", "Banned"),
    ("appeal", "Appeal of the member"),
    ("uphold", "Decision upheld"),
    ("reverse", "Decision reversed"),
    ("update", "Changed the processing"),
]


class LinkupAuditLog(models.Model):
    """The audit log of the moderation (LU-NF-040).

    One row per action of the moderation and per reading of a content by a
    person who is not a party to it: who (``actor_id``), when (``date``),
    what (``action``, the record ``res_model`` / ``res_id``) and why
    (``reason``). Rows are only added, by ``_linkup_log`` under ``sudo``:
    no access right lets anyone write or delete one, and ``write`` and
    ``unlink`` refuse it even under ``sudo``, except an ``unlink`` made by
    a purge that passes ``linkup_audit_purge`` in its context. It is not a
    ``mail.thread``, whose messages can be edited.

    Moderators and LinkUp administrators read the rows of the reports they
    may process (``linkup.report.linkup_moderator_conflict``), so that each
    one sees what the others did; members read none.
    """

    _name = "linkup.audit.log"
    _inherit = ["linkup.server.record"]
    _description = "LinkUp moderation audit log"
    _order = "date desc, id desc"
    _log_access = False

    date = fields.Datetime(
        required=True, readonly=True, default=fields.Datetime.now, index=True
    )
    actor_id = fields.Many2one(
        "res.users",
        string="Who",
        required=True,
        readonly=True,
        ondelete="restrict",
        index=True,
    )
    action = fields.Selection(
        AUDIT_ACTIONS, string="What", required=True, readonly=True
    )
    report_id = fields.Many2one(
        "linkup.report",
        string="Report",
        required=True,
        readonly=True,
        ondelete="restrict",
        index=True,
    )
    res_model = fields.Char(string="Record model", readonly=True)
    res_id = fields.Integer(string="Record", readonly=True)
    reason = fields.Text(string="Why", readonly=True)

    @api.model
    def _linkup_log(self, report, action, reason=None, record=None):
        """Add a row for an action of the current user on ``report``,
        about ``record`` when the action reads or changes one."""
        values = {
            "actor_id": self.env.uid,
            "action": action,
            "report_id": report.id,
            "reason": reason or False,
        }
        if record:
            values.update(res_model=record._name, res_id=record.id)
        return self.sudo().create(values)

    def write(self, vals):
        raise AccessError(_("The audit log of the moderation is not changed."))

    def unlink(self):
        if not (self.env.su and self.env.context.get("linkup_audit_purge")):
            raise AccessError(
                _("The audit log of the moderation is not deleted.")
            )
        return super().unlink()
