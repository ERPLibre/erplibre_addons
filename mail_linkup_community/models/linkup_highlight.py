# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, models
from odoo.addons.mail_linkup_reflet.client_context import server_context


class LinkupHighlight(models.Model):
    _inherit = "linkup.highlight"

    @api.model
    @server_context
    def action_send(self, recipient_id, channel_id=None):
        """A highlight is an exchange: it needs a verified address and the
        required consents."""
        self.env.user._linkup_check_can_exchange()
        return super().action_send(recipient_id, channel_id=channel_id)
