# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models

from .linkup_reflet import in_action_reply


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    def _linkup_free_text(self, message):
        """A quick reply to a request for action is no free text: it opens
        and closes no round, and pays nothing (LU-F-046 RM2)."""
        if in_action_reply():
            return None
        return super()._linkup_free_text(message)
