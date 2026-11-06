# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import timedelta

from markupsafe import Markup
from odoo import Command, _, api, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.addons.mail_linkup_reflet.client_context import server_context
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError
from odoo.addons.mail_linkup_reflet.models.linkup_reflet import (
    DEFAULT_EXPIRY_DAYS,
    DEFAULT_TEXT_MAX_LENGTH,
    DRAFT_FIELDS,
)
from odoo.addons.mail_linkup_reflet.models.res_users import MEMBER_GROUP
from odoo.exceptions import AccessError

from ..authorization import livechat_post

# The answers of the recipient of a reflection in a live chat, with the
# scoring event each one reports.
LIVECHAT_ANSWERS = {
    "confirmed": "reflect_confirmed",
    "rejected": "reflect_rejected",
}
# The scoring events a pair of a visitor and a member earns once, whatever
# the number of reflections it confirms.
PAIR_CODES = frozenset({"reflect_confirmed"})


class LinkupReflet(models.Model):
    """A reflection between a visitor and a member of a live chat
    conversation (LU-F-127), and the draft of a visitor (LU-F-125 RM2).

    Each party of a reflection is a member (``author_id``,
    ``recipient_id``) or a visitor (``author_guest_id``,
    ``recipient_guest_id``), never both. A reflection of a live chat
    conversation lives in it (``channel_id``) and has no link: a visitor
    has no account to link. Its actions take the locks of the core: the
    party whose step it is, the row locked with ``NOWAIT`` and its state
    checked again, a member neither suspended nor unverified. Its carrier
    message is posted in the conversation by its author, and its scoring
    events wait on ``linkup.guest.event`` until the visitor signs up
    (Q-43).

    A visitor holds at most one draft, as a member does; the chatbot of the
    guide writes it, and the signup of the visitor, once verified, gives
    it to the new member (LU-F-124 RM4).
    """

    _inherit = "linkup.reflet"

    author_id = fields.Many2one(required=False)
    author_guest_id = fields.Many2one(
        "mail.guest",
        string="Author visitor",
        index="btree_not_null",
        ondelete="cascade",
        readonly=True,
    )
    recipient_guest_id = fields.Many2one(
        "mail.guest",
        string="Recipient visitor",
        index="btree_not_null",
        ondelete="cascade",
        readonly=True,
    )

    _sql_constraints = [
        (
            "author_one_party",
            "CHECK((author_id IS NULL) != (author_guest_id IS NULL))",
            "A reflection has one author, a member or a visitor.",
        ),
        (
            "recipient_one_party",
            "CHECK(recipient_id IS NULL OR recipient_guest_id IS NULL)",
            "A reflection has one recipient, a member or a visitor.",
        ),
    ]

    def init(self):
        """A visitor holds at most one draft, enforced by a partial
        index."""
        super().init()
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS linkup_reflet_one_guest_draft_idx
            ON linkup_reflet (author_guest_id)
            WHERE state = 'draft' AND author_guest_id IS NOT NULL
            """
        )

    # ------------------------------------------------------------------
    # Card and carrier
    # ------------------------------------------------------------------

    def _linkup_card_values(self):
        """A visitor party is given by its ``mail.guest`` persona; a
        reflection of a live chat holds no turn."""
        values = super()._linkup_card_values()
        reflet = self.sudo()
        if reflet.author_guest_id:
            values["author"] = Store.one(reflet.author_guest_id, only_id=True)
        if reflet.recipient_guest_id:
            values["recipient"] = Store.one(
                reflet.recipient_guest_id, only_id=True
            )
        if reflet.channel_id.channel_type == "livechat":
            values["livechat"] = True
        return values

    def _linkup_guest_parties(self):
        return self.author_guest_id or self.recipient_guest_id

    def _linkup_carrier_text(self):
        """The neutral sentence of a reflection with a visitor party, in
        the language of its recipient; it names the author by their name in
        the conversation."""
        self.ensure_one()
        reflet = self.sudo()
        if not reflet._linkup_guest_parties():
            return super()._linkup_carrier_text()
        lang = (
            reflet.recipient_guest_id.lang
            or reflet.recipient_id.lang
            or self.env.lang
        )
        env = reflet.with_context(lang=lang).env
        if reflet.state == "withdrawn":
            return env._("Reflection withdrawn.")
        name = (
            reflet.author_guest_id.name
            or reflet.author_id.livechat_username
            or reflet.author_id.partner_id.name
        )
        return env._("%(name)s sent you a reflection.", name=name)

    def _linkup_begin(self, actor, states, kinds, exchange=True):
        """A reflection of a live chat conversation has no link: the
        actions of the core, which lock and move the link of the pair, do
        not apply to it, and it is answered through the live chat
        (``_linkup_livechat_answer``), whose scoring events wait for the
        visitor. Only its recipient still reads, ignores or erases it;
        any other action reads ``linkup.unavailable``."""
        reflet = self.sudo()
        if (
            len(reflet) == 1
            and reflet.channel_id.channel_type == "livechat"
            and not reflet.link_id
            and (exchange or actor != "recipient_id")
        ):
            raise self._linkup_livechat_unavailable()
        return super()._linkup_begin(actor, states, kinds, exchange=exchange)

    def _linkup_livechat_post_carrier(self):
        """Post the carrier message of the reflection in its live chat
        conversation, as its author: a member, or the visitor, whom
        ``mail`` names as the author of a post of the public user in its
        guest context. ``authorization.livechat_post`` lets it through the
        start rule and links it to the reflection before the broadcast."""
        self.ensure_one()
        reflet = self.sudo()
        channel = reflet.channel_id
        if reflet.author_guest_id:
            channel = channel.with_user(
                self.env.ref("base.public_user")
            ).with_context(guest=reflet.author_guest_id)
        else:
            channel = channel.with_user(reflet.author_id)
        with livechat_post(reflet):
            message = channel.sudo().message_post(
                body=Markup("<p>%s</p>") % reflet._linkup_carrier_text(),
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        if not reflet.message_id:
            reflet.message_id = message.id
        return message

    # ------------------------------------------------------------------
    # Parties of a live chat conversation
    # ------------------------------------------------------------------

    @api.model
    def _linkup_livechat_unavailable(self):
        return LinkupError(
            "linkup.unavailable", _("This conversation is unavailable.")
        )

    @api.model
    def _linkup_livechat_party(self, channel_id, guest=None):
        """The conversation ``channel_id`` of the welcome channel and the
        party who acts in it: ``(conversation, user, guest)``, one of the
        last two empty.

        ``guest`` is the visitor of the request, given by the route; the
        visitor must be a member of the conversation. Without it, the
        current user must be. Any other case gets the same
        ``linkup.unavailable``, whether the conversation exists or not.
        """
        channel = self.env["discuss.channel"]._linkup_livechat_conversation(
            channel_id
        )
        users = self.env["res.users"]
        guests = self.env["mail.guest"].sudo()
        if not channel:
            raise self._linkup_livechat_unavailable()
        members = channel.channel_member_ids
        if guest:
            if guest not in members.guest_id:
                raise self._linkup_livechat_unavailable()
            return channel, users, guest.sudo()
        user = self.env.user
        if user._is_public() or user.partner_id not in members.partner_id:
            raise self._linkup_livechat_unavailable()
        return channel, user, guests

    @api.model
    def _linkup_livechat_counterpart(self, channel, user, guest):
        """The other party of the conversation: the member who operates it
        for a visitor, the visitor for a member. Return ``(user, guest)``,
        one of them empty; the refusal is ``linkup.unavailable`` while the
        conversation does not hold exactly one such party, or when that
        member is suspended."""
        members = channel.channel_member_ids
        if guest:
            operators = members.partner_id.with_context(
                active_test=False
            ).user_ids.filtered(
                lambda operator: not operator.share
                and operator.active
                and operator._linkup_has_group_id(MEMBER_GROUP)
            )
            if len(operators) != 1 or operators._linkup_is_suspended():
                raise self._linkup_livechat_unavailable()
            return operators.sudo(), self.env["mail.guest"].sudo()
        visitors = members.guest_id
        if len(visitors) != 1:
            raise self._linkup_livechat_unavailable()
        return self.env["res.users"].sudo(), visitors.sudo()

    def _linkup_livechat_begin(self, user, guest, actor, states):
        """Start an action of a reflection of a live chat conversation, as
        ``_linkup_begin`` does: ``actor`` (``author`` or ``recipient``)
        must be the party acting, a member neither suspended nor unable to
        exchange; then lock the row and check the state again. Return the
        reflection under ``sudo``."""
        self.ensure_one()
        reflet = self.sudo()
        if guest:
            allowed = reflet[f"{actor}_guest_id"] == guest
        else:
            allowed = reflet[f"{actor}_id"] == user
        if not allowed:
            raise AccessError(
                _("This action belongs to another party of the reflection.")
            )
        # A sent reflection whose visitor signed up has two members as
        # parties and no visitor left to hold the scoring events for: it
        # stays as it is.
        if reflet.state != "draft" and not reflet._linkup_guest_parties():
            raise self._linkup_livechat_unavailable()
        if user:
            user._linkup_check_not_suspended()
            user._linkup_check_can_exchange()
        reflet._linkup_lock()
        if reflet.kind != "initial":
            raise LinkupError(
                "linkup.validation",
                _("This action does not apply to this kind of reflection."),
                field="kind",
            )
        reflet._linkup_check_state(states)
        return reflet

    # ------------------------------------------------------------------
    # Draft of a visitor
    # ------------------------------------------------------------------

    @api.model
    def _linkup_draft_values(self, vals):
        """The fields of ``DRAFT_FIELDS`` of ``vals``, cleaned as
        ``action_save_draft`` cleans them."""
        vals = vals if isinstance(vals, dict) else {}
        values = {key: vals[key] for key in DRAFT_FIELDS if key in vals}
        max_length = self._linkup_param(
            "linkup.reflet_text_max_length", DEFAULT_TEXT_MAX_LENGTH
        )
        for field in ("you_said", "understood"):
            if field in values:
                values[field] = self._linkup_clean_text(
                    values[field], field, max_length, required=False
                )
        if "category_id" in values:
            values["category_id"] = self._linkup_get_category(
                values["category_id"], required=False
            ).id
        if "real_world_declared" in values:
            values["real_world_declared"] = bool(values["real_world_declared"])
        return values

    @api.model
    def _linkup_guest_draft(self, guest):
        return self.sudo().search(
            [("author_guest_id", "=", guest.id), ("state", "=", "draft")],
            limit=1,
        )

    @api.model
    def _linkup_guest_save_draft(self, guest, vals):
        """Create or update the single draft of the visitor ``guest``, as
        ``action_save_draft`` does for a member: the row of the visitor
        serializes two first saves, the row of the draft a save and a
        sending. Return the id of the draft."""
        values = self._linkup_draft_values(vals)
        self.flush_model(["author_guest_id", "state"])
        self.env.cr.execute(
            "SELECT id FROM mail_guest WHERE id = %s FOR NO KEY UPDATE NOWAIT",
            [guest.id],
        )
        self.env.cr.execute(
            """
            SELECT id FROM linkup_reflet
            WHERE author_guest_id = %s AND state = 'draft'
            FOR UPDATE NOWAIT
            """,
            [guest.id],
        )
        row = self.env.cr.fetchone()
        if row:
            draft = self.sudo().browse(row[0])
            draft.invalidate_recordset()
            draft.write(values)
        else:
            draft = self.sudo().create(
                dict(
                    values,
                    author_id=False,
                    author_guest_id=guest.id,
                    kind="initial",
                    state="draft",
                )
            )
        return draft.id

    @api.model
    def _linkup_guest_draft_info(self, guest):
        """The draft of the visitor as a client restores it, or
        ``False``."""
        draft = self._linkup_guest_draft(guest)
        if not draft:
            return False
        return {
            "id": draft.id,
            "category_id": draft.category_id.id,
            "you_said": draft.you_said or "",
            "understood": draft.understood or "",
            "real_world_declared": draft.real_world_declared,
            "real_world_date": draft.real_world_date or False,
        }

    # ------------------------------------------------------------------
    # Reflections of a live chat conversation (LU-F-127)
    # ------------------------------------------------------------------

    @api.model
    def _linkup_livechat_info(self, channel_id, guest=None):
        """What a party reads of the reflections of a live chat
        conversation: the cards of its reflections, the draft of the
        party, whether a reflection may go to the other party now and the
        name this party reads of them, and the start rule. A card never
        holds a hidden theme: a reflection of a live chat has none."""
        channel, user, guest = self._linkup_livechat_party(channel_id, guest)
        reflets = self.sudo().search(
            [("channel_id", "=", channel.id), ("state", "!=", "draft")]
        )
        try:
            to_user, to_guest = self._linkup_livechat_counterpart(
                channel, user, guest
            )
        except LinkupError:
            to_user, to_guest = self.env["res.users"], self.env["mail.guest"]
        info = channel.with_user(user or self.env.user)
        return {
            "available": True,
            "reflet_ids": reflets.ids,
            "can_send": bool(to_user or to_guest),
            "recipient_name": to_guest.name
            or to_user.livechat_username
            or to_user.partner_id.name
            or False,
            "draft": (
                self._linkup_guest_draft_info(guest)
                if guest
                else self.with_user(user)._linkup_draft_info()
            ),
            **info._linkup_start_rule_info(),
            "store": Store(reflets).get_result(),
        }

    @api.model
    def _linkup_livechat_save_draft(self, channel_id, vals, guest=None):
        """Save the draft of the party of a live chat conversation."""
        channel, user, guest = self._linkup_livechat_party(channel_id, guest)
        if guest:
            return self._linkup_guest_save_draft(guest, vals)
        return self.with_user(user).action_save_draft(vals)

    @api.model
    def _linkup_livechat_send(self, channel_id, guest=None):
        """Send the draft of the party to the other party of the live chat
        conversation.

        The texts and the category are required, with the declaration of
        an exchange in person, as for a first reflection. The reflection
        becomes ``sent`` in the conversation, its carrier message is posted
        there by its author, and its card reaches both parties. Return the
        id of the reflection.
        """
        channel, user, guest = self._linkup_livechat_party(channel_id, guest)
        to_user, to_guest = self._linkup_livechat_counterpart(
            channel, user, guest
        )
        if guest:
            draft = self._linkup_guest_draft(guest)
        else:
            draft = self.sudo().search(
                [("author_id", "=", user.id), ("state", "=", "draft")],
                limit=1,
            )
        if not draft:
            raise LinkupError(
                "linkup.validation",
                _("Write a reflection first."),
                field="category_id",
            )
        reflet = draft._linkup_livechat_begin(
            user, guest, "author", ("draft",)
        )
        you_said, understood = reflet._linkup_sendable_texts()
        reflet._linkup_require_real_world()
        vals = {
            "recipient_id": to_user.id,
            "recipient_guest_id": to_guest.id,
            "channel_id": channel.id,
            "state": "sent",
            "sent_date": fields.Datetime.now(),
            "you_said": you_said,
            "understood": understood,
        }
        if not reflet.real_world_date:
            vals["real_world_date"] = fields.Date.context_today(self)
        reflet.write(vals)
        reflet._linkup_livechat_post_carrier()
        reflet._linkup_notify()
        reflet._linkup_livechat_event("reflect_sent")
        return reflet.id

    def _linkup_livechat_answer(self, state, guest=None):
        """Confirm or reject, as its recipient, a reflection of a live chat
        conversation.

        A confirmation opens the free text of the conversation in
        ``strict`` mode, which both parties are told. The scoring event
        waits for the signup of the visitor (Q-43).
        """
        self.ensure_one()
        if state not in LIVECHAT_ANSWERS:
            raise LinkupError(
                "linkup.validation", _("Unknown answer."), field="state"
            )
        channel = self.sudo().channel_id
        if channel.channel_type != "livechat":
            raise self._linkup_livechat_unavailable()
        channel, user, guest = self._linkup_livechat_party(channel.id, guest)
        reflet = self._linkup_livechat_begin(
            user, guest, "recipient", ("sent",)
        )
        now = fields.Datetime.now()
        reflet.write(
            {
                "state": state,
                "answered_date": now,
                "read_date": reflet.read_date or now,
            }
        )
        reflet._linkup_notify()
        channel._linkup_send_start_rule()
        reflet._linkup_livechat_event(LIVECHAT_ANSWERS[state])
        return True

    def _linkup_livechat_event(self, code):
        """Hold the scoring event ``code`` of the reflection until the
        visitor of the pair signs up (Q-43).

        A pair of a visitor and a member has no link, so the caps of a
        pair, which count the lines of its link, do not bind it: a
        confirmation is keyed by the pair instead of the reflection
        (``PAIR_CODES``), and the pair earns it once, as the first link of
        two members does."""
        self.ensure_one()
        reflet = self.sudo()
        guest = reflet._linkup_guest_parties()
        member = reflet.author_id or reflet.recipient_id
        key = None
        if code in PAIR_CODES:
            key = f"livechat:{guest.id}:{member.id}"
        self.env["linkup.guest.event"]._linkup_hold(
            guest, code, reflet, member, key=key
        )

    # Methods of the member who operates a live chat conversation; the
    # visitor reaches the same ones through ``/linkup/v1/livechat/*``.

    @api.model
    @server_context
    def linkup_livechat_info(self, channel_id):
        return self._linkup_livechat_info(channel_id)

    @api.model
    @server_context
    def action_livechat_send(self, channel_id):
        return self._linkup_livechat_send(channel_id)

    @server_context
    def action_livechat_confirm(self):
        return self._linkup_livechat_answer("confirmed")

    @server_context
    def action_livechat_reject(self):
        return self._linkup_livechat_answer("rejected")

    # ------------------------------------------------------------------
    # Guide of a member (LU-F-125 RM5)
    # ------------------------------------------------------------------

    @api.model
    @server_context
    def linkup_start_guide(self):
        """Open, for the current member, a live chat conversation with the
        chatbot of the reflection guide, and post its welcome steps.

        The conversation belongs to the welcome channel; the chatbot alone
        answers in it, so the start rule never refuses the answers of the
        member. Return its id and its Store data.
        """
        self._linkup_check_member()
        user = self.env.user
        script = self.env.ref(
            "im_livechat_linkup_reflect.chatbot_script_guide",
            raise_if_not_found=False,
        )
        livechat = self.env["im_livechat.channel"]._linkup_get("welcome")
        if not script or not livechat:
            raise self._linkup_livechat_unavailable()
        script = script.sudo().with_context(lang=user.lang)
        bot = script.operator_partner_id
        now = fields.Datetime.now()
        channel = (
            self.env["discuss.channel"]
            .with_context(lang=user.lang)
            ._linkup_server_create(
                {
                    "channel_member_ids": [
                        Command.create(
                            {
                                "partner_id": bot.id,
                                "last_interest_dt": now
                                - timedelta(seconds=30),
                                "unpin_dt": now,
                            }
                        ),
                        Command.create({"partner_id": user.partner_id.id}),
                    ],
                    "livechat_active": True,
                    "livechat_operator_id": bot.id,
                    "livechat_channel_id": livechat.id,
                    "chatbot_current_step_id": script._get_welcome_steps()[
                        -1
                    ].id,
                    "channel_type": "livechat",
                    "name": script.title,
                }
            )
        )
        script._post_welcome_steps(channel)
        channel.channel_member_ids.filtered(
            lambda member: member.partner_id == user.partner_id
        ).fold_state = "open"
        store = Store(channel.with_user(user).sudo(False))
        return {"channel_id": channel.id, "store": store.get_result()}

    # ------------------------------------------------------------------
    # Expiry
    # ------------------------------------------------------------------

    @api.model
    def _cron_expire_livechat_reflets(self):
        """Expire the reflections of the live chat conversations left
        unanswered for ``linkup.reflet_expiry_days`` days, which have no
        link for the expiry of the core to follow."""
        days = self._linkup_param(
            "linkup.reflet_expiry_days", DEFAULT_EXPIRY_DAYS
        )
        limit = fields.Datetime.now() - timedelta(days=days)
        self.flush_model(["kind", "state", "sent_date", "link_id"])
        self.env.cr.execute(
            """
            SELECT id FROM linkup_reflet
            WHERE kind = 'initial' AND state = 'sent' AND link_id IS NULL
              AND sent_date < %s
              AND (author_guest_id IS NOT NULL
                   OR recipient_guest_id IS NOT NULL)
            FOR UPDATE SKIP LOCKED
            """,
            [limit],
        )
        reflets = self.sudo().browse(
            [row[0] for row in self.env.cr.fetchall()]
        )
        reflets.invalidate_recordset()
        reflets.write({"state": "expired"})
        reflets._linkup_notify()
        return True
