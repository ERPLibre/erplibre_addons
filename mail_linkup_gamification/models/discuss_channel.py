# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models
from odoo.addons.mail_linkup_reflet.authorization import current_post
from odoo.tools import html2plaintext

from .linkup_points_rule import VIRTUAL_ROUND


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    def _message_post_after_hook(self, message, msg_vals):
        """Count the rounds of free text of a pair (LU-F-045)."""
        res = super()._message_post_after_hook(message, msg_vals)
        if (
            len(self) == 1
            and self.channel_type == "chat"
            and message.message_type == "comment"
            and not current_post(self.env)
        ):
            self._linkup_free_text(message)
        return res

    def _linkup_free_text(self, message):
        """Close a round when the other member answers a free text.

        A round opens with a free text of one member of an ``active`` pair
        and closes when the other one posts free text in turn; consecutive
        messages of one author open nothing more. The closing pays
        ``virtual_round`` to both, each at the rank of their own sequence.
        The carrier message of a reflection, posted inside
        ``authorization.linkup_post``, and a message without text are not
        free text. The link is locked, so two answers at once close one
        round.
        """
        if not html2plaintext(message.body or "").strip():
            return
        users = self._linkup_chat_users()
        if not users or not all(
            user._linkup_is_restricted_member() for user in users
        ):
            return
        author = users.sudo().filtered(
            lambda user: user.partner_id == message.author_id
        )
        if not author:
            return
        link = self.env["linkup.link"]._get_between(users[0], users[1])
        if link.state != "active":
            return
        link._linkup_lock()
        opener = link.linkup_round_user_id
        if not opener:
            link.linkup_round_user_id = author
            return
        if opener == author:
            return
        link.linkup_round_user_id = False
        self.env["linkup.points.rule"]._linkup_apply_event(
            VIRTUAL_ROUND,
            users,
            link=link,
            channel=self,
            key=f"round:{message.id}",
            message=message,
        )
