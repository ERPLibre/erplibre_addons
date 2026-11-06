# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, models
from odoo.exceptions import UserError


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    def _check_can_update_message_content(self, message):
        """Refuse the edition and the deletion of a message the moderation
        hid: ``/mail/message/update_content`` would otherwise write a new
        body under ``sudo`` in its place."""
        if message.sudo().linkup_hidden:
            raise UserError(
                _("A message hidden by the moderation cannot be changed.")
            )
        return super()._check_can_update_message_content(message)
