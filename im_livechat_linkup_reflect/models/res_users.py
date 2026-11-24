# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models
from odoo.http import request


class ResUsers(models.Model):
    """The signup of a visitor of the live chat (LU-F-124 RM4).

    A signup made in the browser of a visitor who talked in a live chat
    conversation of LinkUp remembers that visitor (``mail.guest``, read
    from its cookie) on the new account. Once the address is verified, the
    draft of the visitor becomes the draft of the member, unless the member
    already holds one, the reflections of the visitor become theirs, and
    the scoring events held for the visitor are paid (Q-43); before, nothing
    is given.
    """

    _inherit = "res.users"

    linkup_livechat_guest_id = fields.Many2one(
        "mail.guest",
        string="Visitor of the signup",
        copy=False,
        readonly=True,
        ondelete="set null",
        groups="base.group_system",
        help="The visitor of the live chat who signed up from the same"
        " browser; given to the account once its address is verified.",
    )

    @api.model
    def _linkup_request_guest(self):
        """The visitor of the cookie of the current request, when it talked
        in a conversation of LinkUp, a welcome conversation or one that
        "Need help now" moved to the distress channel; an empty recordset
        otherwise."""
        Guest = self.env["mail.guest"].sudo()
        if not request:
            return Guest
        token = request.cookies.get(Guest._cookie_name, "")
        guest = Guest._get_guest_from_token(token)
        if not guest:
            return Guest
        member = (
            self.env["discuss.channel.member"]
            .sudo()
            .search_count(
                [
                    ("guest_id", "=", guest.id),
                    ("channel_id.channel_type", "=", "livechat"),
                    (
                        "channel_id.livechat_channel_id.linkup_kind",
                        "!=",
                        False,
                    ),
                ],
                limit=1,
            )
        )
        return guest.sudo() if member else Guest

    @api.model
    def _signup_create_user(self, values):
        user = super()._signup_create_user(values)
        guest = self._linkup_request_guest()
        if guest:
            user.sudo().linkup_livechat_guest_id = guest
            if user._linkup_is_verified():
                user._linkup_livechat_attach()
        return user

    @api.model
    def _linkup_verify_token(self, token):
        user = super()._linkup_verify_token(token)
        if user:
            user._linkup_livechat_attach()
        return user

    def _linkup_livechat_attach(self):
        """Give the account what its visitor left, once its address is
        verified: the draft, the reflections of the live chat, then the
        scoring events held, paid by the rules of the scale with their keys,
        so a second call pays nothing more."""
        self.ensure_one()
        user = self.sudo()
        guest = user.linkup_livechat_guest_id
        if not guest or not user._linkup_is_verified():
            return False
        Reflet = self.env["linkup.reflet"].sudo()
        draft = Reflet._linkup_guest_draft(guest)
        if draft:
            if Reflet.search_count(
                [("author_id", "=", user.id), ("state", "=", "draft")]
            ):
                draft.unlink()
            else:
                draft.write({"author_id": user.id, "author_guest_id": False})
        Reflet.search([("author_guest_id", "=", guest.id)]).write(
            {"author_id": user.id, "author_guest_id": False}
        )
        Reflet.search([("recipient_guest_id", "=", guest.id)]).write(
            {"recipient_id": user.id, "recipient_guest_id": False}
        )
        self.env["linkup.guest.event"]._linkup_release(guest)
        user.linkup_livechat_guest_id = False
        return True
