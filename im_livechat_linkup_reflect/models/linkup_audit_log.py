# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


def _purge(rows):
    """Delete the rows of an action of this module at its uninstallation,
    through the purge the audit log allows."""
    rows.sudo().with_context(linkup_audit_purge=True).unlink()


class LinkupAuditLog(models.Model):
    _inherit = "linkup.audit.log"

    action = fields.Selection(
        selection_add=[
            ("distress_open", "Opened a conversation of distress"),
        ],
        ondelete={"distress_open": _purge},
    )
