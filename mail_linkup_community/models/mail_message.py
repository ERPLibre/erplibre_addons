# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError


class MailMessage(models.Model):
    _inherit = "mail.message"

    # Set by the moderation, which moves the body and the attachments of the
    # message to ``linkup.hidden.content`` (LU-F-116 RM2).
    linkup_hidden = fields.Boolean(
        string="Hidden by the moderation", readonly=True, copy=False
    )

    def write(self, vals):
        """Keep the mark of the moderation to the server: the author of a
        message may otherwise write it on their own message."""
        if "linkup_hidden" in vals and not self.env.su:
            raise AccessError(
                _("Only the moderation hides a message or shows it again.")
            )
        return super().write(vals)

    def _to_store(self, store: Store, /, *, fields=None, **kwargs):
        """Mark a hidden message, which every client then draws as
        "Message hidden by the moderation". Its body is already empty; the
        key is sent for a hidden message only, the client reading its
        absence as visible."""
        super()._to_store(store, fields=fields, **kwargs)
        for message in self.filtered("linkup_hidden"):
            store.add(message, {"linkup_hidden": True})
