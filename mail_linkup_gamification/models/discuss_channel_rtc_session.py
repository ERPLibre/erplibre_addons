# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models


class DiscussChannelRtcSession(models.Model):
    _inherit = "discuss.channel.rtc.session"

    def unlink(self):
        """End the answered calls that wait for their end in the
        conversations these sessions leave."""
        channels = self.sudo().channel_id
        res = super().unlink()
        self.env["linkup.points.call"].sudo()._linkup_close_ended(channels)
        return res
