# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError
from odoo.tools import SQL

from ..authorization import in_channel_post
from . import privacy

# Fields of a carrier message that only the server writes: its content, and
# what ties it to its conversation and to its author.
CARRIER_FIELDS = frozenset(
    {
        "attachment_ids",
        "author_guest_id",
        "author_id",
        "body",
        "message_type",
        "model",
        "res_id",
        "subject",
        "subtype_id",
    }
)
# Fields that put a message before other people than the members of its
# conversation: its recipients, its notifications, the stars of others.
RECIPIENT_FIELDS = frozenset(
    {"notification_ids", "partner_ids", "starred_partner_ids"}
)


class MailMessage(models.Model):
    _inherit = ["mail.message", "linkup.contact.privacy"]
    _name = "mail.message"

    _linkup_contact_fields = privacy.AUTHOR_CONTACT_FIELDS

    # Reverse side of linkup.reflet.message_id, kept to the administrators:
    # members reach the reflection of a message through the Store only.
    linkup_reflet_ids = fields.One2many(
        "linkup.reflet", "message_id", groups="base.group_system"
    )
    linkup_reflet_id = fields.Many2one(
        "linkup.reflet",
        string="Reflection",
        compute="_compute_linkup_reflet_id",
        compute_sudo=True,
    )

    @api.depends("linkup_reflet_ids")
    def _compute_linkup_reflet_id(self):
        for message in self:
            message.linkup_reflet_id = message.linkup_reflet_ids[:1]

    def _to_store(self, store: Store, /, *, fields=None, **kwargs):
        """Add the card of the reflection each carrier message holds.

        The card is the same for every reader (``linkup.reflet._to_store``),
        since ``discuss.channel._notify_thread`` builds the Store once, as
        the poster, and broadcasts it to the whole conversation. What
        belongs to one reader only, the hidden themes and the ignore flag,
        is added when ``for_current_user`` is set: the caller then builds the
        Store for ``env.user`` and sends it to that user alone.
        """
        super()._to_store(store, fields=fields, **kwargs)
        if fields is not None and "linkup_reflet_id" not in fields:
            return
        reflets = self.env["linkup.reflet"].sudo()
        for message in self:
            # sudo: mail.message - the card holds a fixed list of safe fields
            reflet = message.sudo().linkup_reflet_id
            if reflet:
                store.add(message, {"linkup_reflet_id": Store.one(reflet)})
                reflets |= reflet
        if reflets and kwargs.get("for_current_user"):
            reflets._linkup_private_to_store(store, self.env.user)

    def _author_to_store(self, store: Store):
        """Leave out of the Store the address of the author of a message,
        as ``res.partner._to_store`` leaves it out of the partner: for
        every message a restricted member reads, and for the messages of a
        restricted member whoever reads. A client draws the author of a
        message from its partner."""
        super()._author_to_store(store)
        closed = privacy.contact_closed(self.env)
        members = {}
        for message in self:
            author = message.sudo().author_id
            if author and author.id not in members:
                members[author.id] = author._linkup_is_member_partner()
            if closed or members.get(author.id):
                store.add(message, {"email_from": False})

    def _read_format(self, fnames, load="_classic_read"):
        """Blank the address of the author in the messages a restricted
        member reads, but in their own messages."""
        result = super()._read_format(fnames, load)
        closed = privacy.AUTHOR_CONTACT_FIELDS.intersection(fnames)
        if closed and privacy.contact_closed(self.env):
            own = self.env.user.partner_id.id
            authors = {
                message.id: message.author_id.id for message in self.sudo()
            }
            for vals in result:
                if authors.get(vals.get("id")) == own:
                    continue
                for fname in closed:
                    if fname in vals:
                        vals[fname] = False
        return result

    def _linkup_contact_own(self):
        own = self.env.user.partner_id
        # sudo: mail.message - the author of the messages read
        return self.filtered(lambda message: message.sudo().author_id == own)

    def _condition_to_sql(self, alias, fname, operator, value, query):
        """A restricted member searches no message by the address of its
        author."""
        if privacy.search_closed(self, fname, privacy.AUTHOR_CONTACT_FIELDS):
            return SQL("FALSE")
        return super()._condition_to_sql(alias, fname, operator, value, query)

    def _is_empty(self):
        """A carrier message is never empty: its card is its content."""
        return super()._is_empty() and not self.sudo().linkup_reflet_id

    def _linkup_check_carrier_change(self):
        """Refuse a change of a carrier message outside ``sudo``.

        The author of a message may otherwise edit or delete it by RPC, and
        so replace the neutral sentence of a reflection or detach its card
        from the conversation. The server changes a carrier under ``sudo``
        only, when a reflection is withdrawn.
        """
        if self.env.su:
            return
        # sudo: mail.message - the reverse field is kept to administrators
        if self.sudo().filtered("linkup_reflet_ids"):
            raise AccessError(
                _("The message of a reflection cannot be changed.")
            )

    @api.model
    def _linkup_check_member_channel_write(self, vals_list, messages=None):
        """Keep a restricted member from writing a message by the ORM.

        A member holds the create and write access on ``mail.message``, and
        ``mail`` lets any internal user create a message without a document
        and notify anybody of it, or create the message of a conversation
        they only read: the ORM would otherwise carry free text to any
        partner id, past the start rule of ``discuss.channel.message_post``,
        a block and a suspension. Outside ``sudo``, a restricted member
        creates a message only from within the ``message_post`` of a
        conversation (``authorization.channel_post``). They change neither
        the content nor the conversation of a message of a conversation,
        nor the recipients or the stars of any message; Discuss edits a
        message and stars it under ``sudo``, after its own checks.
        """
        if self.env.su or not self.env.user._linkup_is_restricted_member():
            return
        refused = False
        if messages is None:
            refused = any(
                vals.get("model") != "discuss.channel"
                or not in_channel_post(vals.get("res_id"))
                for vals in vals_list
            )
        else:
            vals = vals_list[0]
            refused = RECIPIENT_FIELDS.intersection(vals) or (
                CARRIER_FIELDS.intersection(vals)
                and (
                    vals.get("model") == "discuss.channel"
                    # sudo: mail.message - the conversation of the messages
                    or "discuss.channel" in messages.sudo().mapped("model")
                )
            )
        if refused:
            raise AccessError(
                _(
                    "A LinkUp member posts and changes a message through"
                    " its conversation only."
                )
            )

    def _message_reaction(self, content, action, partner, guest, store=None):
        """Refuse a reaction that the start rule forbids (LU-F-063 RM4).

        The content of a reaction is any text the client sends, shown under
        the message to the whole conversation: in a conversation that the
        start rule keeps closed, a member adds none. ``/mail/message/reaction``
        calls this method under ``sudo``, as the member; withdrawing a
        reaction stays possible. A suspended member adds none, and a block
        refuses a reaction to a message of the other party, in any
        conversation (LU-F-115 RM1).
        """
        self.ensure_one()
        if action == "add" and self.model == "discuss.channel":
            # sudo: discuss.channel - the rules of the conversation
            channel = self.env["discuss.channel"].sudo().browse(self.res_id)
            channel._linkup_check_reach("reaction")
            authors = (
                self.sudo().author_id.with_context(active_test=False).user_ids
            )
            if authors & self.env["linkup.block"]._linkup_blocked_users(
                self.env.user
            ):
                raise channel._linkup_unavailable()
            channel._linkup_check_start_rule("reaction")
        return super()._message_reaction(
            content, action, partner, guest, store=store
        )

    @api.model_create_multi
    def create(self, vals_list):
        self._linkup_check_member_channel_write(vals_list)
        return super().create(vals_list)

    def write(self, vals):
        if CARRIER_FIELDS.intersection(vals):
            self._linkup_check_carrier_change()
        if (CARRIER_FIELDS | RECIPIENT_FIELDS).intersection(vals):
            self._linkup_check_member_channel_write([vals], messages=self)
        return super().write(vals)

    def unlink(self):
        self._linkup_check_carrier_change()
        return super().unlink()
