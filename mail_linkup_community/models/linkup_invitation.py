# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.addons.mail_linkup_reflet.client_context import server_context
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError
from odoo.addons.mail_linkup_reflet.models.linkup_invitation import (
    DEFAULT_EXPIRY_DAYS,
    token_hash,
)

from .. import tools

# Wrong numbers typed on the page of a share link before it stops working.
MAX_PHONE_ATTEMPTS = 5


class LinkupInvitation(models.Model):
    """NewLink by phone and by personal code (LU-F-020 RM3, LU-F-112 RM2).

    By phone, LinkUp sends nothing (Q-25): the answer of the sending holds
    a share link, ``share_url``, which the inviter sends themself, and only
    that answer and the one of ``action_resend`` hold it. The reflection is
    attached when the person who uses the link types the number of the
    invitation; another number lets it expire, as a forwarded link does.

    By code, the inviter types the personal code a member gave them; the
    invitation then reaches that member inside LinkUp, as for their
    address, when their preference allows it. A code that names nobody
    reaches nobody, with the same answer.
    """

    _inherit = "linkup.invitation"

    email = fields.Char(required=False)
    phone = fields.Char(readonly=True)
    phone_attempts = fields.Integer(
        readonly=True, copy=False, groups="base.group_system"
    )

    def _linkup_channel(self):
        """``email``, ``phone`` or ``code``: how the inviter named the
        person."""
        self.ensure_one()
        invitation = self.sudo()
        if invitation.email:
            return "email"
        if invitation.phone:
            return "phone"
        return "code"

    @api.depends("email", "phone")
    def _compute_display_name(self):
        super()._compute_display_name()
        for invitation in self:
            channel = invitation._linkup_channel()
            if channel == "phone":
                invitation.display_name = tools.mask_phone(
                    invitation.sudo().phone
                )
            elif channel == "code":
                invitation.display_name = _("Personal code")

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    @api.model
    def _linkup_create_for(self, reflet, invite):
        """Dispatch a sending by its channel: an address goes to the
        module of the reflections, a phone or a code is handled here. A
        sending names one channel only."""
        invite = invite if isinstance(invite, dict) else {}
        named = [key for key in ("email", "phone", "code") if invite.get(key)]
        if len(named) > 1:
            raise LinkupError(
                "linkup.validation",
                _("Choose one way to reach this person."),
                field=named[-1],
            )
        if named == ["phone"]:
            return self._linkup_create_by_phone(reflet, invite)
        if named == ["code"]:
            return self._linkup_create_by_code(reflet, invite)
        return super()._linkup_create_for(reflet, invite)

    @api.model
    def _linkup_new_invitation(self, reflet, invite, vals):
        """Create an invitation of the current member from ``vals``, with
        the name the inviter gave, after the daily limit; return it with a
        new token, as ``(invitation, token)``."""
        me = self.env.user
        name = invite.get("name")
        name = name.strip()[:100] if isinstance(name, str) else ""
        self._linkup_take_quota(me)
        token, hashed = self._linkup_new_token()
        days = self._linkup_param(
            "linkup.invitation_expiry_days", DEFAULT_EXPIRY_DAYS
        )
        invitation = self.sudo().create(
            dict(
                vals,
                inviter_id=me.id,
                reflet_id=reflet.id,
                name=name or False,
                lang=me.lang or self.env.lang,
                token_hash=hashed,
                expiry_date=fields.Datetime.now() + timedelta(days=days),
            )
        )
        invitation._linkup_count_sending()
        return invitation, token

    @api.model
    def _linkup_create_by_phone(self, reflet, invite):
        """An invitation by share link: nothing is sent, the answer holds
        the link."""
        phone = tools.normalize_phone(invite.get("phone"))
        if not phone:
            raise LinkupError(
                "linkup.validation",
                _("Enter a valid phone number."),
                field="phone",
            )
        invitation, token = self._linkup_new_invitation(
            reflet, invite, {"phone": phone}
        )
        return invitation.with_context(linkup_share_token=token)

    @api.model
    def _linkup_create_by_code(self, reflet, invite):
        """An invitation to the member holding a personal code: it reaches
        them inside LinkUp when their preference and the blocks allow it.
        A code that names nobody gives the same answer and reaches nobody:
        the answer tells nothing of the codes, and the daily limit of the
        invitations bounds the tries. The own code is refused."""
        code = tools.normalize_code(invite.get("code"))
        if not code:
            raise LinkupError(
                "linkup.validation",
                _("Check the code this person gave you."),
                field="code",
            )
        holder = self.env["res.users"]._linkup_find_by_code(code)
        if holder == self.env.user:
            raise LinkupError(
                "linkup.validation",
                _("This is your own code."),
                field="code",
            )
        invitation, _token = self._linkup_new_invitation(reflet, invite, {})
        if holder:
            invitation._linkup_offer_to(holder, "code")
        return invitation

    def _linkup_send_mail(self, token, deliver=True):
        """Only an invitation by address has an email."""
        if not self.sudo().email:
            return
        return super()._linkup_send_mail(token, deliver=deliver)

    def _linkup_dispatch(self, token):
        """A new sending by code reaches the member again; by phone, the
        new link is in the answer."""
        channel = self._linkup_channel()
        if channel == "code":
            invitation = self.sudo()
            if invitation.invitee_id:
                invitation.invitee_id.partner_id._bus_send(
                    "linkup.invitation/received", {"id": invitation.id}
                )
            return
        if channel == "phone":
            return
        return super()._linkup_dispatch(token)

    @server_context
    def action_resend(self):
        """By phone, a new sending gives a new share link, in the answer
        only; the former one stops working."""
        if self._linkup_channel() != "phone":
            return super().action_resend()
        invitation = self._linkup_begin()
        self.env.user._linkup_check_not_suspended()
        invitation._linkup_check_usable()
        self._linkup_take_quota(self.env.user)
        token, hashed = self._linkup_new_token()
        invitation.write({"token_hash": hashed})
        invitation._linkup_count_sending()
        return invitation.with_context(linkup_share_token=token)._linkup_info()

    # ------------------------------------------------------------------
    # What the inviter sees
    # ------------------------------------------------------------------

    def _linkup_share_url(self):
        """The share link of a phone invitation, when the token of the
        context is its own: only its sending and its new sending hold it."""
        self.ensure_one()
        token = self.env.context.get("linkup_share_token")
        invitation = self.sudo()
        if (
            not token
            or not invitation.phone
            or token_hash(token) != invitation.token_hash
        ):
            return False
        return f"{self.get_base_url()}/linkup/invite/{token}"

    def _linkup_info(self):
        """The channel of the invitation, its masked phone or "Personal
        code" in place of the address, and the share link of a phone
        invitation just sent."""
        info = super()._linkup_info()
        channel = self._linkup_channel()
        info["channel"] = channel
        if channel != "email":
            info["email"] = self.display_name
        share_url = self._linkup_share_url()
        if share_url:
            info["share_url"] = share_url
        return info

    # ------------------------------------------------------------------
    # Use of the link
    # ------------------------------------------------------------------

    def _linkup_matches(self, user):
        """By phone, the number typed on the page of the link
        (``linkup_typed_phone`` of the context, set by the controller) must
        be the one of the invitation; by code, the user must be the member
        it reached."""
        self.ensure_one()
        invitation = self.sudo()
        channel = self._linkup_channel()
        if channel == "phone":
            return tools.phones_match(
                self.env.context.get("linkup_typed_phone"), invitation.phone
            )
        if channel == "code":
            return invitation.invitee_id == user
        return super()._linkup_matches(user)

    def _linkup_wrong_phone(self):
        """Count a wrong number typed by a logged-in member; past
        ``MAX_PHONE_ATTEMPTS``, the invitation expires with its
        reflection."""
        self.ensure_one()
        invitation = self.sudo()
        attempts = invitation.phone_attempts + 1
        vals = {"phone_attempts": attempts}
        if attempts >= MAX_PHONE_ATTEMPTS:
            vals["state"] = "expired"
            invitation.reflet_id.filtered(
                lambda reflet: reflet.state == "pending_invite"
            ).write({"state": "expired"})
        invitation.write(vals)
