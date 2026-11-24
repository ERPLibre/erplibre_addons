# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import datetime, timedelta

from markupsafe import Markup
from odoo import Command, _, api, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError, ValidationError

from ..authorization import linkup_post
from ..client_context import server_context
from ..exceptions import LinkupError
from .res_users import MEMBER_GROUP

# Fields a member writes on their draft through ``action_save_draft``.
DRAFT_FIELDS = (
    "category_id",
    "you_said",
    "understood",
    "real_world_declared",
    "real_world_date",
)
# States in which the recipient reads a reflection.
RECEIVED_STATES = ("sent", "confirmed", "rejected", "inaccurate", "expired")
KINDS = (
    "initial",
    "precision",
    "continue",
    "self_disclosure",
    "answer_exact",
    "close",
)

DEFAULT_TEXT_MAX_LENGTH = 1000
DEFAULT_PRECISION_MAX_LENGTH = 2000
DEFAULT_EXPIRY_DAYS = 30
# Reflections of a pair given to the web client with a conversation.
RECENT_REFLET_LIMIT = 5
# Reflections of a pair given at most by one reading of the history.
HISTORY_LIMIT = 50


class LinkupReflet(models.Model):
    """A reflection: what a member understood of a real-life exchange.

    An ``initial`` reflection is written as a draft, sent to one member,
    then confirmed, rejected or marked inaccurate by them. Once it is
    confirmed, the pair takes turns through child reflections created
    directly in the ``sent`` state: ``answer_exact``, ``precision``,
    ``continue``, ``self_disclosure`` and ``close``; ``parent_id`` chains
    them and ``linkup.link.turn_reflet_id`` points to the one whose
    recipient acts next.

    Members hold no write access on this model. Every change goes through
    an ``action_*`` method that checks the acting user against the author or
    the recipient, locks the row and checks the state again, then writes
    under ``sudo``. ``_linkup_event`` is called after each scoring event
    with its code; it does nothing here and is the entry point of the
    scoring module.

    Each sent reflection has a carrier message in the conversation of the
    pair, posted by its author; the clients draw the card of the reflection
    from the Store data of that message. Every action then sends the
    updated card over the bus to the conversation, and to each party what
    belongs to that party only.
    """

    _name = "linkup.reflet"
    _inherit = ["linkup.server.record"]
    _description = "LinkUp reflection"
    _order = "id desc"

    author_id = fields.Many2one(
        "res.users",
        required=True,
        index=True,
        default=lambda self: self.env.user,
        ondelete="cascade",
        readonly=True,
    )
    recipient_id = fields.Many2one(
        "res.users", index=True, ondelete="cascade", readonly=True
    )
    link_id = fields.Many2one(
        "linkup.link", index=True, ondelete="cascade", readonly=True
    )
    channel_id = fields.Many2one(
        "discuss.channel",
        string="Conversation",
        ondelete="set null",
        readonly=True,
    )
    message_id = fields.Many2one(
        "mail.message",
        string="Carrier message",
        index=True,
        ondelete="set null",
        readonly=True,
    )
    # Kept to the system administrators: the many2one would give its
    # display name to any reader of the reflection, its recipient included.
    invitation_id = fields.Many2one(
        "linkup.invitation",
        string="NewLink invitation",
        index="btree_not_null",
        ondelete="set null",
        readonly=True,
        copy=False,
        groups="base.group_system",
    )
    parent_id = fields.Many2one(
        "linkup.reflet",
        string="Previous reflection",
        index=True,
        ondelete="cascade",
        readonly=True,
    )
    child_ids = fields.One2many("linkup.reflet", "parent_id")
    kind = fields.Selection(
        [
            ("initial", "Reflection"),
            ("precision", "Precision"),
            ("continue", "Continued reflection"),
            ("self_disclosure", "Talking about oneself"),
            ("answer_exact", "Exact answer"),
            ("close", "Closing"),
        ],
        required=True,
        default="initial",
        readonly=True,
    )
    category_id = fields.Many2one(
        "linkup.category",
        string="Visible category",
        ondelete="restrict",
        readonly=True,
    )
    revealed_category_ids = fields.Many2many(
        "linkup.category",
        string="Hidden themes",
        compute="_compute_revealed_category_ids",
        help="Hidden themes of a precision, given to its author, and to"
        " everybody once the guess is made.",
    )
    you_said = fields.Text(string="You told me", readonly=True)
    understood = fields.Text(string="I understood that", readonly=True)
    body_text = fields.Text(string="Text", readonly=True)
    real_world_declared = fields.Boolean(
        string="Exchange declared in person", readonly=True
    )
    real_world_date = fields.Date(string="Date of the exchange", readonly=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending_invite", "Waiting for the invitation"),
            ("sent", "Sent"),
            ("confirmed", "Confirmed"),
            ("rejected", "Rejected"),
            ("inaccurate", "Inaccurate"),
            ("expired", "Expired"),
            ("withdrawn", "Withdrawn"),
        ],
        required=True,
        default="draft",
        index=True,
        readonly=True,
    )
    # Never readable by the author: a member does not learn that their
    # reflection was ignored.
    recipient_ignored = fields.Boolean(
        groups="base.group_system", readonly=True
    )
    # Never readable by the author either: a reflection sent to a member
    # who blocked its author reaches nobody, and looks delivered to them.
    phantom = fields.Boolean(
        groups="base.group_system",
        readonly=True,
        copy=False,
        help="Sent to a member who blocks its author: it has no carrier"
        " message, its recipient never reads it and it expires as usual.",
    )
    response_state = fields.Selection(
        [("none", "None"), ("exact", "Exact"), ("precision", "Precision")],
        required=True,
        default="none",
        readonly=True,
    )
    guess_state = fields.Selection(
        [
            ("none", "None"),
            ("pending", "Pending"),
            ("found", "Found"),
            ("missed", "Missed"),
        ],
        required=True,
        default="none",
        readonly=True,
    )
    guessed_category_id = fields.Many2one(
        "linkup.category", ondelete="restrict", readonly=True
    )
    sent_date = fields.Datetime(readonly=True)
    read_date = fields.Datetime(readonly=True)
    answered_date = fields.Datetime(readonly=True)
    round_index = fields.Integer(
        readonly=True, help="Depth of the reflection in its chain of turns."
    )

    _sql_constraints = [
        (
            "author_not_recipient",
            "CHECK(author_id != recipient_id)",
            "A reflection is never addressed to its author.",
        ),
    ]

    def init(self):
        """A member holds at most one draft, enforced by a partial index."""
        super().init()
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS linkup_reflet_one_draft_idx
            ON linkup_reflet (author_id) WHERE state = 'draft'
            """
        )

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    @api.depends("kind", "category_id", "state")
    def _compute_display_name(self):
        """Name a reflection by its category, or by its kind.

        A many2one value is read with its display name under ``sudo``, so a
        reader who no longer reads the reflection, such as the recipient of
        a withdrawn one through its carrier message, still gets this name:
        a withdrawn reflection is named by its kind only, its category
        being part of the withdrawn content.
        """
        kinds = dict(self._fields["kind"]._description_selection(self.env))
        for reflet in self:
            category = reflet.state != "withdrawn" and reflet.category_id
            reflet.display_name = (category and category.name) or kinds.get(
                reflet.kind, ""
            )

    @api.depends("author_id", "guess_state")
    @api.depends_context("uid")
    def _compute_revealed_category_ids(self):
        """Give the hidden themes to the author, to all once guessed.

        The themes live in ``linkup.reflet.secret``, read here under
        ``sudo``. The field is neither stored nor searchable, so no search,
        count or grouping run by the other party reaches them.
        """
        secrets = (
            self.env["linkup.reflet.secret"]
            .sudo()
            .search([("reflet_id", "in", self.ids)])
        )
        by_reflet = {secret.reflet_id.id: secret for secret in secrets}
        for reflet in self:
            secret = by_reflet.get(reflet.id)
            visible = secret and (
                reflet.author_id.id == self.env.uid
                or reflet.guess_state in ("found", "missed")
            )
            reflet.revealed_category_ids = (
                secret.category_ids.ids if visible else False
            )

    @api.constrains("kind", "state", "you_said", "understood")
    def _check_texts(self):
        """A sent reflection carries its texts.

        An initial reflection needs both "You told me" and "I understood
        that"; a continued reflection needs at least the second one, its
        reformulation.
        """
        for reflet in self:
            if reflet.state == "draft":
                continue
            required = {
                "initial": ("you_said", "understood"),
                "continue": ("understood",),
            }.get(reflet.kind, ())
            for field in required:
                if not (reflet[field] or "").strip():
                    raise ValidationError(
                        _(
                            "The field %(field)s of a sent reflection is"
                            " required.",
                            field=self._fields[field]._description_string(
                                self.env
                            ),
                        )
                    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @api.model
    def _linkup_param(self, key, default):
        """Integer setting of LinkUp, or ``default`` when unset or invalid."""
        value = self.env["ir.config_parameter"].sudo().get_param(key)
        try:
            return int(value) if value else default
        except ValueError:
            return default

    @api.model
    def _linkup_check_member(self):
        if not self.env.user._linkup_has_group_id(MEMBER_GROUP):
            raise AccessError(_("Only a LinkUp member can do this."))

    @api.model
    def _linkup_clean_text(self, value, field, max_length, required):
        """Return a plain text value, refusing a missing or long one.

        The text is stored as typed, without its surrounding blanks; the
        clients escape it on display.
        """
        text = (value or "").strip() if isinstance(value, str) else ""
        label = self._fields[field]._description_string(self.env)
        if required and not text:
            raise LinkupError(
                "linkup.validation",
                _("The field %(field)s is required.", field=label),
                field=field,
            )
        if len(text) > max_length:
            raise LinkupError(
                "linkup.validation",
                _(
                    "The field %(field)s holds at most %(count)s characters.",
                    field=label,
                    count=max_length,
                ),
                field=field,
                limit=max_length,
            )
        return text or False

    @api.model
    def _linkup_get_category(self, category_id, required=True):
        """The active category of the given id, as sent by a client."""
        Category = self.env["linkup.category"].sudo()
        try:
            ids = [int(category_id)] if category_id else []
        except (TypeError, ValueError):
            ids = []
        category = Category.browse(ids).exists().filtered("active")
        if required and not category:
            raise LinkupError(
                "linkup.validation",
                _("Choose a category."),
                field="category_id",
            )
        return category

    @api.model
    def _linkup_get_hidden_categories(self, category_ids):
        """Active categories of the given ids, in order, without repeats."""
        ids = []
        for category_id in category_ids or []:
            try:
                ids.append(int(category_id))
            except (TypeError, ValueError):
                continue
        categories = (
            self.env["linkup.category"]
            .sudo()
            .browse(list(dict.fromkeys(ids)))
            .exists()
            .filtered("active")
        )
        maximum = self.env["linkup.reflet.secret"]._linkup_max_hidden_themes()
        if len(categories) != len(set(ids)) or len(categories) > maximum:
            raise LinkupError(
                "linkup.validation",
                _(
                    "Choose at most %(count)s themes among the categories.",
                    count=maximum,
                ),
                field="hidden_category_ids",
            )
        return categories

    @api.model
    def _linkup_get_recipient(self, recipient_id):
        """The member a reflection may be sent to, seen by the author.

        The recipient must be readable by the author under the record rules,
        that is inside their scope: a linked member, the other party of a
        reflection in progress, or a member of a conversation they share.
        A member who blocked the author stays a recipient, out of the scope
        as they are: the sending then looks delivered and reaches nobody
        (``linkup.block``). Any other id, and a suspended member, get the
        same generic refusal, whether the user exists or not.
        """
        unavailable = LinkupError(
            "linkup.unavailable", _("This reflection cannot be sent.")
        )
        try:
            user_id = int(recipient_id)
        except (TypeError, ValueError):
            raise unavailable from None
        recipient = self.env["res.users"].search([("id", "=", user_id)])
        if not recipient:
            blocker = self.env["res.users"].sudo().browse(user_id).exists()
            if blocker and self.env["linkup.block"]._linkup_has_blocked(
                blocker, self.env.user
            ):
                recipient = blocker
        if (
            not recipient
            or recipient == self.env.user
            or recipient.sudo().share
            or not recipient.sudo()._linkup_has_group_id(MEMBER_GROUP)
            or recipient.sudo()._linkup_is_suspended()
        ):
            raise unavailable
        return recipient.sudo()

    def _linkup_lock(self):
        """Lock the rows of the reflections for the rest of the transaction.

        ``NOWAIT`` makes a concurrent transaction fail at once with a lock
        error, which the RPC layer retries; the retry then reads the state
        written by the first one and gets ``linkup.already_answered``.
        """
        self.flush_recordset()
        self.env.cr.execute(
            "SELECT id FROM linkup_reflet WHERE id IN %s FOR UPDATE NOWAIT",
            [tuple(self.ids)],
        )
        self.invalidate_recordset()

    def _linkup_check_state(self, states):
        """Refuse an action on a reflection that left the given states."""
        self.ensure_one()
        if self.state in states:
            return
        if self.state in ("withdrawn", "expired"):
            raise LinkupError(
                "linkup.expired", _("This reflection is no longer available.")
            )
        raise LinkupError(
            "linkup.already_answered",
            _("This reflection has already been answered."),
        )

    def _linkup_already_answered(self):
        return LinkupError(
            "linkup.already_answered",
            _("This reflection has already been answered."),
        )

    def _linkup_begin(self, actor, states, kinds, exchange=True):
        """Start an action: check the actor, lock, check kind and state.

        ``actor`` names the field, ``author_id`` or ``recipient_id``, that
        must hold the current user; the recipient of a phantom reflection
        is a stranger to it. The lock is taken only once the actor is
        known, so a stranger to the reflection never holds it.

        An ``exchange`` reaches the other party: a suspended member makes
        none, and a ``blocked`` pair takes none, with the code of an
        unavailable sending. Withdrawing, reading, ignoring and discarding
        are not exchanges. Return the reflection under ``sudo``.
        """
        self.ensure_one()
        reflet = self.sudo()
        if reflet[actor] != self.env.user or (
            actor == "recipient_id" and reflet.phantom
        ):
            raise AccessError(
                _("This action belongs to another party of the reflection.")
            )
        if exchange:
            self.env.user._linkup_check_not_suspended()
            if reflet.link_id.state == "blocked":
                raise LinkupError(
                    "linkup.unavailable",
                    _("This conversation is unavailable."),
                )
        reflet._linkup_lock()
        if reflet.kind not in kinds:
            raise LinkupError(
                "linkup.validation",
                _("This action does not apply to this kind of reflection."),
                field="kind",
            )
        reflet._linkup_check_state(states)
        return reflet

    def _linkup_take_turn(self):
        """Lock the link and check that the reflection holds its turn."""
        self.ensure_one()
        link = self.link_id
        link._linkup_lock()
        if link.turn_reflet_id != self:
            raise self._linkup_already_answered()
        return link

    def _linkup_check_answerable(self):
        """An initial reflection is answered once confirmed, a continued
        one once sent; each takes a single answer."""
        if self.kind == "initial" and self.state == "sent":
            raise LinkupError(
                "linkup.validation",
                _("Confirm this reflection before answering it."),
                field="state",
            )
        self._linkup_check_state(
            ("confirmed",) if self.kind == "initial" else ("sent",)
        )
        if self.response_state != "none":
            raise self._linkup_already_answered()

    def _linkup_check_options(self):
        """The three follow-up options open on an exact answer, and on a
        precision whose guess is made or that hides no theme."""
        if self.kind == "precision" and self.guess_state == "pending":
            raise LinkupError(
                "linkup.validation",
                _("Guess the hidden theme first."),
                field="guess_state",
            )

    def _linkup_create_child(self, kind, vals):
        """Create the next reflection of the chain, from the current user
        back to the author of this one, directly ``sent``."""
        self.ensure_one()
        return self.sudo().create(
            dict(
                vals,
                kind=kind,
                parent_id=self.id,
                author_id=self.env.uid,
                recipient_id=self.author_id.id,
                link_id=self.link_id.id,
                channel_id=self.channel_id.id,
                state="sent",
                sent_date=fields.Datetime.now(),
                round_index=self.round_index + 1,
            )
        )

    def _linkup_move_turn(self, link, reflet):
        """Give the turn of the pair to ``reflet``; return the reflection
        that held it, whose card changes too."""
        previous = link.turn_reflet_id
        link.sudo().write(
            {
                "turn_reflet_id": reflet.id,
                "last_interaction_date": fields.Datetime.now(),
            }
        )
        return previous

    def _linkup_after_child(self, child):
        """Post the carrier of a new child and send the updated parent.

        The new card reaches the conversation with its carrier message; the
        parent, whose answer or turn changed, follows on the bus, and the
        author of the child gets its private part, such as the hidden
        themes of a precision, on their own partner.
        """
        child._linkup_post_carrier()
        self._linkup_notify()
        child._linkup_notify(conversation=False)

    def _linkup_parties(self):
        self.ensure_one()
        return self.author_id | self.recipient_id

    def _linkup_event(self, code, users, link=None, channel=None, key=None):
        """Report a scoring event of the reflection; does nothing here.

        ``code`` is a rule code (``reflect_sent``, ``reflect_confirmed``,
        ``answer_exact``…), ``users`` the members it concerns, ``link`` the
        pair. The method is called after the state is written, inside the
        same transaction, on the reflection that carries the event, or on
        an empty recordset for an event of the pair that no reflection
        carries, such as a call answered outside the options of a turn. ``channel`` is the
        conversation of the event when the reflection does not give it, and
        ``key`` a stable identifier of an event that the reflection does not
        identify alone, such as one answered call. The scoring module
        overrides it to apply its rules.
        """
        return None

    # ------------------------------------------------------------------
    # Carrier message, Store and bus
    # ------------------------------------------------------------------

    def _linkup_carrier_text(self):
        """The neutral sentence of the carrier message, in the recipient's
        language.

        It is what the notifications show and what a client that does not
        draw the card displays: it names the author and the kind of turn,
        never the texts, the category or the hidden themes.
        """
        self.ensure_one()
        reflet = self.sudo()
        lang = reflet.recipient_id.lang or self.env.lang
        env = reflet.with_context(lang=lang).env
        if reflet.state == "withdrawn":
            return env._("Reflection withdrawn.")
        name = reflet.author_id.partner_id.name
        if reflet.kind == "answer_exact":
            return env._("%(name)s answered: that's exactly it!", name=name)
        if reflet.kind == "precision":
            return env._("%(name)s clarified their thought.", name=name)
        if reflet.kind == "continue":
            return env._("%(name)s continued the reflection.", name=name)
        if reflet.kind == "self_disclosure":
            return env._("%(name)s talked about themselves.", name=name)
        if reflet.kind == "close":
            return env._("%(name)s closed the exchange.", name=name)
        return env._("%(name)s sent you a reflection.", name=name)

    def _linkup_direct_channel(self):
        """The direct conversation of the pair, kept on its link.

        The conversation of the link is reused while it is still the chat of
        the two parties. Otherwise ``discuss.channel.channel_get``, called as
        the author, finds or creates the canonical chat of the two partners;
        it pins the chat for the author only, and the recipient sees it when
        the first message arrives. Return the channel under ``sudo``.
        """
        self.ensure_one()
        reflet = self.sudo()
        link = reflet.link_id
        partners = reflet.author_id.partner_id | reflet.recipient_id.partner_id
        channel = link.channel_id
        if (
            not channel
            or channel.channel_type != "chat"
            or channel.channel_member_ids.partner_id != partners
        ):
            channel = (
                self.env["discuss.channel"]
                .with_user(reflet.author_id)
                .channel_get([reflet.recipient_id.partner_id.id])
            )
            link.write({"channel_id": channel.id})
        return channel.sudo()

    def _linkup_post_carrier(self):
        """Post the carrier message of the reflection, as its author.

        The message goes to the conversation of the reflection, or to the
        direct conversation of the pair when it has none. It is a
        ``comment`` (``message_post`` of a channel defaults to
        ``notification``) whose body is the neutral sentence of
        ``_linkup_carrier_text``. Opening the conversation and posting run
        inside ``authorization.linkup_post``: the contact is initiated by the
        server, and ``discuss.channel._message_post_after_hook`` links the
        message to the reflection before the conversation is notified, so
        the broadcast carries the card. Return the message.
        """
        self.ensure_one()
        reflet = self.sudo()
        with linkup_post(reflet):
            if not reflet.channel_id:
                reflet.channel_id = reflet._linkup_direct_channel()
            message = reflet.channel_id.with_user(
                reflet.author_id
            ).message_post(
                body=Markup("<p>%s</p>") % reflet._linkup_carrier_text(),
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        if not reflet.message_id:
            reflet.message_id = message.id
        return message

    def _linkup_replace_carrier(self):
        """Replace the body of the carrier message by the current neutral
        sentence, and send the new body to the conversation."""
        self.ensure_one()
        message = self.sudo().message_id
        if not message:
            return
        message.write(
            {"body": Markup("<p>%s</p>") % self._linkup_carrier_text()}
        )
        self.sudo().channel_id._bus_send_store(message, {"body": message.body})

    def _linkup_card_values(self):
        """The card of the reflection, the same for every reader.

        A fixed list of fields read under ``sudo``: the reflection is sent
        to a whole conversation, so nothing here depends on the reader. The
        hidden themes and ``recipient_ignored`` are never part of it; the
        texts and the category of a withdrawn reflection are dropped. The
        role of a reader follows from the ``author`` and ``recipient``
        partners; ``holds_turn`` tells that the recipient of this reflection
        acts next in the pair. Categories go by code, their translated
        texts being read by each client in its own language.
        """
        self.ensure_one()
        reflet = self.sudo()
        withdrawn = reflet.state == "withdrawn"
        return {
            "id": reflet.id,
            "kind": reflet.kind,
            "state": reflet.state,
            "response_state": reflet.response_state,
            "guess_state": reflet.guess_state,
            "round_index": reflet.round_index,
            "sent_date": reflet.sent_date,
            "read_date": reflet.read_date,
            "answered_date": reflet.answered_date,
            "author": Store.one(reflet.author_id.partner_id, only_id=True),
            "recipient": Store.one(
                reflet.recipient_id.partner_id, only_id=True
            ),
            "parent_id": reflet.parent_id.id,
            "message_id": reflet.message_id.id,
            "holds_turn": bool(reflet.link_id)
            and reflet.link_id.turn_reflet_id == reflet,
            "category_id": Store.one(
                (
                    self.env["linkup.category"]
                    if withdrawn
                    else reflet.category_id
                ),
                fields=["code"],
            ),
            "guessed_category_id": Store.one(
                reflet.guessed_category_id, fields=["code"]
            ),
            "you_said": not withdrawn and reflet.you_said,
            "understood": not withdrawn and reflet.understood,
            "body_text": not withdrawn and reflet.body_text,
            "real_world_declared": not withdrawn
            and reflet.real_world_declared,
            "real_world_date": not withdrawn and reflet.real_world_date,
        }

    def _to_store(self, store: Store, /):
        """Add the cards of the reflections to a Store; see
        ``_linkup_card_values`` for what a card holds."""
        for reflet in self:
            store.add(self._name, reflet._linkup_card_values())

    def _linkup_private_to_store(self, store, user):
        """Add to a Store what belongs to ``user`` alone.

        The author of a precision gets its hidden themes, and both parties
        once the guess is made; the recipient of an ignored reflection gets
        the ignore flag. The Store must then be sent to ``user`` only.
        """
        reflets = self.sudo()
        secrets = {
            secret.reflet_id.id: secret
            for secret in self.env["linkup.reflet.secret"]
            .sudo()
            .search([("reflet_id", "in", reflets.ids)])
        }
        for reflet in reflets:
            values = {}
            secret = secrets.get(reflet.id)
            if secret and (
                reflet.author_id == user
                or (
                    reflet.guess_state in ("found", "missed")
                    and user in reflet._linkup_parties()
                )
            ):
                values["revealed_category_ids"] = Store.many(
                    secret.category_ids, fields=["code"]
                )
                values["primary_category_id"] = Store.one(
                    secret.primary_category_id, fields=["code"]
                )
            if reflet.recipient_id == user and reflet.recipient_ignored:
                values["recipient_ignored"] = True
            if values:
                store.add(self._name, dict(values, id=reflet.id))

    def _linkup_notify(self, conversation=True):
        """Send the updated reflections over the bus.

        The cards go to the conversation of each reflection, which reaches
        both parties; the private part of each party goes to that party's
        partner. With ``conversation`` false, only the private parts are
        sent, for an action the other party must not notice. The recipient
        of a phantom reflection gets nothing. The bus writes at commit:
        nothing leaves a transaction that fails.
        """
        reflets = self.sudo()
        if conversation:
            for channel in reflets.channel_id:
                channel._bus_send_store(
                    Store(reflets.filtered(lambda r: r.channel_id == channel))
                )
        users = (
            reflets.author_id
            | reflets.filtered(lambda reflet: not reflet.phantom).recipient_id
        )
        for user in users:
            store = Store()
            reflets._linkup_private_to_store(store, user)
            user.partner_id._bus_send_store(store)

    @api.model
    def _linkup_demo_post_carriers(self, reflet_ids):
        """Post the carrier messages of demonstration reflections, in the
        given order. The demonstration data creates the reflections in their
        final state; this gives each sent one the message its action would
        have posted."""
        for reflet in self.sudo().browse(reflet_ids):
            if reflet.state != "draft" and not reflet.message_id:
                reflet._linkup_post_carrier()
        return True

    # ------------------------------------------------------------------
    # Web client
    # ------------------------------------------------------------------

    @api.model
    @server_context
    def linkup_channel_info(self, channel_id):
        """What the web client shows of a direct conversation of the member.

        ``channel_id`` must be a ``chat`` the current member belongs to,
        whose other member is a LinkUp member; otherwise the answer is
        ``{"available": False}``, whatever the reason. The answer gives:

        * ``recipient_id``: the user a reflection of this conversation goes
          to, and ``can_send``: whether that user is in the member's scope;
        * ``link_state``: ``none``, ``pending``, ``active`` or ``closed``,
          with ``first_link_date``; a ``blocked`` link reads ``closed``, so
          the answer never tells who blocked whom;
        * ``needs_real_world``: whether a sending requires the declaration
          of an exchange in person, that is while the link is not active;
        * ``reflet_count`` and ``reflet_ids``: the reflections of the pair
          the member reads, the most recent first, at most ``limit``; their
          cards, with the member's private part, are in ``store``;
        * ``draft``: the single draft of the member, or ``False``;
        * ``blocked_by_me``: whether the member blocks the other one. A
          block the other member holds is never told: the conversation then
          reads ``{"available": False}``, as for a deleted account.
        """
        self._linkup_check_member()
        me = self.env.user
        recipient = self._linkup_chat_peer(channel_id)
        if not recipient:
            return {"available": False}
        link = self.env["linkup.link"]._get_between(me, recipient)
        state = {"blocked": "closed"}.get(link.state, link.state or "none")
        domain = [("link_id", "=", link.id), ("state", "!=", "draft")]
        reflets = (
            self.search(domain, limit=RECENT_REFLET_LIMIT)
            if link
            else self.browse()
        )
        store = Store(reflets)
        reflets._linkup_private_to_store(store, me)
        return {
            "available": True,
            "can_send": bool(
                self.env["res.users"].search_count([("id", "=", recipient.id)])
            ),
            "recipient_id": recipient.id,
            "link_state": state,
            "first_link_date": link.first_link_date or False,
            "needs_real_world": link.state != "active",
            "reflet_count": self.search_count(domain) if link else 0,
            "reflet_ids": reflets.ids,
            "draft": self._linkup_draft_info(),
            "blocked_by_me": self.env["linkup.block"]._linkup_has_blocked(
                me, recipient
            ),
            "store": store.get_result(),
        }

    @api.model
    def _linkup_chat_peer(self, channel_id):
        """The other party of a direct conversation of the current member,
        as a ``sudo`` user, when it is a LinkUp member; an empty recordset
        when ``channel_id`` is not such a conversation, whatever the
        reason.

        A member who blocks the current member, without being blocked by
        them, reads here as an account that no longer exists: the state of
        the link, the scope and the history of the pair would otherwise
        tell the blocked member that a link once active closed, which only
        a block does.
        """
        Users = self.env["res.users"].sudo()
        try:
            channel_id = int(channel_id)
        except (TypeError, ValueError):
            return Users
        me = self.env.user
        channel = self.env["discuss.channel"].search(
            [
                ("id", "=", channel_id),
                ("channel_type", "=", "chat"),
                ("is_member", "=", True),
            ]
        )
        # sudo: discuss.channel.member - the member reads their own chat
        partner = channel.sudo().channel_member_ids.partner_id - me.partner_id
        recipient = partner.sudo().user_ids.filtered(
            lambda user: not user.share
            and user._linkup_has_group_id(MEMBER_GROUP)
        )[:1]
        if len(partner) != 1:
            return Users
        Block = self.env["linkup.block"]
        if (
            recipient
            and Block._linkup_has_blocked(recipient, me)
            and not Block._linkup_has_blocked(me, recipient)
        ):
            return Users
        return recipient

    @api.model
    @server_context
    def linkup_history(
        self, channel_id, category_id=False, state=False, limit=HISTORY_LIMIT
    ):
        """The reflections of the pair of a direct conversation, sent and
        received, for the history of the LinkUp panel (LU-F-018).

        ``channel_id`` is read as by ``linkup_channel_info``; any other
        conversation gives ``{"available": False}``. ``category_id`` keeps
        the reflections of that visible category, ``state`` those in that
        state. The hidden themes of a precision are never a visible
        category, so filtering never reveals them. The answer gives
        ``reflet_ids``, the most recent first, at most ``limit`` (capped at
        ``HISTORY_LIMIT``), ``count``, and the cards in ``store``, with the
        private part of the member.
        """
        self._linkup_check_member()
        me = self.env.user
        recipient = self._linkup_chat_peer(channel_id)
        if not recipient:
            return {"available": False}
        states = dict(self._fields["state"]._description_selection(self.env))
        if state and (state == "draft" or state not in states):
            raise LinkupError(
                "linkup.validation", _("Unknown state."), field="state"
            )
        link = self.env["linkup.link"]._get_between(me, recipient)
        domain = [("link_id", "=", link.id), ("state", "!=", "draft")]
        if category_id:
            try:
                domain.append(("category_id", "=", int(category_id)))
            except (TypeError, ValueError) as error:
                raise LinkupError(
                    "linkup.validation",
                    _("Unknown category."),
                    field="category_id",
                ) from error
        if state:
            domain.append(("state", "=", state))
        try:
            limit = min(max(int(limit), 1), HISTORY_LIMIT)
        except (TypeError, ValueError):
            limit = HISTORY_LIMIT
        reflets = self.search(domain, limit=limit) if link else self.browse()
        store = Store(reflets)
        reflets._linkup_private_to_store(store, me)
        return {
            "available": True,
            "reflet_ids": reflets.ids,
            "count": self.search_count(domain) if link else 0,
            "store": store.get_result(),
        }

    @api.model
    def _linkup_draft_info(self):
        """The single draft of the current member as the web client restores
        it, or ``False``."""
        draft = self.search(
            [("author_id", "=", self.env.uid), ("state", "=", "draft")],
            limit=1,
        )
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

    @api.model
    @server_context
    def linkup_reflet_view_info(self):
        """What the Reflet view shows to the current member.

        ``contacts`` lists the LinkUp members a reflection of the view can go
        to, all of them inside the member's scope:

        * the members of the groups and channels the member belongs to;
        * the other party of an ``active`` link;
        * the other party of a ``pending`` link in which the member received
          a reflection. A ``pending`` link the member opened alone adds
          nobody: the reflection waits in the conversation of the pair.

        A ``blocked`` link removes the other member whatever the path. The
        users are searched again under the record rules, so the list never
        widens the scope. The contacts holding a received initial reflection
        not read yet come first, then the most recent interaction of the
        pair, then the name.

        Each contact gives ``user_id``, ``partner_id``, ``name``,
        ``unread_count``, ``link_state`` (``none``, ``pending``, ``active``
        or ``closed``), ``last_interaction_date``, ``needs_real_world``, as
        ``linkup_channel_info`` gives them, and ``channel_id``: the direct
        conversation of the pair when the member belongs to it, or ``False``.
        ``draft`` is the single draft of the member, or ``False``;
        ``newlink`` the invitations of the member still waiting, with the
        sendings of the day (``linkup.invitation.linkup_invitations_info``);
        ``received_invitations`` the invitations that reach the member inside
        LinkUp (``linkup.invitation.linkup_received_invitations``).
        ``sent_ids`` are the initial reflections of the member still waiting
        for their recipient (LU-F-010 RM2), whose cards and recipient names
        are in ``store``; a phantom one is among them, as delivered.
        """
        self._linkup_check_member()
        me = self.env.user
        links = (
            self.env["linkup.link"]
            .sudo()
            .search(
                ["|", ("user_a_id", "=", me.id), ("user_b_id", "=", me.id)]
            )
        )
        received_link_ids = set(
            self.sudo()
            .search(
                [
                    ("recipient_id", "=", me.id),
                    ("link_id", "in", links.ids),
                    ("state", "not in", ("draft", "withdrawn")),
                    ("phantom", "=", False),
                ]
            )
            .link_id.ids
        )
        link_by_user = {link._linkup_other_user(me).id: link for link in links}
        candidates = self.env["res.users"].sudo()
        for link in links:
            if link.state == "active" or (
                link.state == "pending" and link.id in received_link_ids
            ):
                candidates |= link._linkup_other_user(me)
        channels = self.env["discuss.channel"].search(
            [("channel_type", "!=", "chat"), ("is_member", "=", True)]
        )
        # sudo: discuss.channel.member - the members of the member's channels
        candidates |= channels.sudo().channel_member_ids.partner_id.user_ids
        blocked_ids = {
            user_id
            for user_id, link in link_by_user.items()
            if link.state == "blocked"
        }
        member_group = self.env.ref(MEMBER_GROUP)
        users = self.env["res.users"].search(
            [
                (
                    "id",
                    "in",
                    [u for u in candidates.ids if u not in blocked_ids],
                ),
                ("id", "!=", me.id),
                ("share", "=", False),
                ("groups_id", "in", member_group.ids),
            ]
        )
        unread = {
            author.id: count
            for author, count in self.sudo()._read_group(
                [
                    ("recipient_id", "=", me.id),
                    ("author_id", "in", users.ids),
                    ("kind", "=", "initial"),
                    ("state", "=", "sent"),
                    ("read_date", "=", False),
                    ("recipient_ignored", "=", False),
                    ("phantom", "=", False),
                ],
                ["author_id"],
                ["__count"],
            )
        }
        contacts = []
        for user in users.sudo():
            link = link_by_user.get(user.id, self.env["linkup.link"])
            channel = link.channel_id
            contacts.append(
                {
                    "user_id": user.id,
                    "partner_id": user.partner_id.id,
                    "name": user.partner_id.name or user.name,
                    "unread_count": unread.get(user.id, 0),
                    "link_state": {"blocked": "closed"}.get(
                        link.state, link.state or "none"
                    ),
                    "last_interaction_date": link.last_interaction_date
                    or False,
                    "needs_real_world": link.state != "active",
                    "channel_id": (
                        channel.id
                        if me.partner_id
                        in channel.channel_member_ids.partner_id
                        else False
                    ),
                }
            )
        # Stable sorts, the last key applied first.
        contacts.sort(key=lambda contact: contact["name"].casefold())
        contacts.sort(
            key=lambda contact: contact["last_interaction_date"]
            or datetime.min,
            reverse=True,
        )
        contacts.sort(key=lambda contact: not contact["unread_count"])
        sent = self.search(
            [
                ("author_id", "=", me.id),
                ("kind", "=", "initial"),
                ("state", "=", "sent"),
            ],
            limit=HISTORY_LIMIT,
        )
        store = Store(sent)
        sent._linkup_private_to_store(store, me)
        # The author named the recipient when sending: the name is given
        # again even once the scope of the pair is closed.
        for partner in sent.sudo().recipient_id.partner_id:
            store.add(partner, {"name": partner.name})
        return {
            "contacts": contacts,
            "draft": self._linkup_draft_info(),
            "newlink": self.env["linkup.invitation"].linkup_invitations_info(),
            "received_invitations": self.env[
                "linkup.invitation"
            ].linkup_received_invitations(),
            "sent_ids": sent.ids,
            "store": store.get_result(),
        }

    # ------------------------------------------------------------------
    # Draft and sending (author of an initial reflection)
    # ------------------------------------------------------------------

    @api.model
    @server_context
    def action_save_draft(self, vals):
        """Create or update the single draft of the current member.

        Only the fields of ``DRAFT_FIELDS`` are taken from ``vals``. The
        draft row is locked while it is written, so a send from another tab
        either runs before, and the save creates a new draft, or after.

        The row of the author in ``res_users`` is locked first. Two first
        saves at once would otherwise both insert a draft, and the second
        would fail on the unique index of drafts, an error the RPC layer
        does not retry; on the lock, it fails at once with an error that
        the RPC layer retries, and the retry updates the draft of the first.
        ``NO KEY UPDATE`` does not conflict with the foreign keys that point
        to the user. Return the id of the draft.
        """
        self._linkup_check_member()
        vals = vals or {}
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
        self.flush_model(["author_id", "state"])
        self.env.cr.execute(
            "SELECT id FROM res_users WHERE id = %s FOR NO KEY UPDATE NOWAIT",
            [self.env.uid],
        )
        self.env.cr.execute(
            """
            SELECT id FROM linkup_reflet
            WHERE author_id = %s AND state = 'draft'
            FOR UPDATE NOWAIT
            """,
            [self.env.uid],
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
                    author_id=self.env.uid,
                    kind="initial",
                    state="draft",
                )
            )
        return draft.id

    @server_context
    def action_discard_draft(self):
        """Delete the draft of the current member."""
        reflet = self._linkup_begin(
            "author_id", ("draft",), ("initial",), exchange=False
        )
        reflet.unlink()
        return True

    def _linkup_sendable_texts(self):
        """Check the category and the texts of a draft being sent; return
        them cleaned, as ``(you_said, understood)``."""
        max_length = self._linkup_param(
            "linkup.reflet_text_max_length", DEFAULT_TEXT_MAX_LENGTH
        )
        if not self.category_id.active:
            raise LinkupError(
                "linkup.validation",
                _("Choose a category."),
                field="category_id",
            )
        return (
            self._linkup_clean_text(
                self.you_said, "you_said", max_length, required=True
            ),
            self._linkup_clean_text(
                self.understood, "understood", max_length, required=True
            ),
        )

    def _linkup_require_real_world(self):
        if not self.real_world_declared:
            raise LinkupError(
                "linkup.validation",
                _("Confirm that this exchange took place in person."),
                field="real_world_declared",
            )

    @server_context
    def action_send(self, recipient_id=None, invite=None):
        """Send the draft to a member of the author's scope, or by NewLink.

        The texts and the category are required. A first reflection of a
        pair without a confirmed link also requires the declaration of an
        exchange in person; its date defaults to today. The link of the pair
        is created ``pending`` when missing, and a ``closed`` one is made
        ``pending`` again.

        In a ``blocked`` pair, the author who blocked the recipient is
        refused; the author whom the recipient blocked gets a phantom
        delivery: the reflection is ``sent`` for them, has no carrier
        message, reaches nobody, gives no scoring event and expires as
        usual (LU-F-016 RM9).

        With ``invite``, ``{"email": …, "name": …}``, the reflection goes to
        a person who may not be a member (LU-F-020): it waits in the
        ``pending_invite`` state on a ``linkup.invitation``, which emails
        the link of the signup, and the answer is what
        ``linkup.invitation._linkup_info`` gives, the same whoever holds the
        address. Otherwise, return ``True``.
        """
        reflet = self._linkup_begin("author_id", ("draft",), ("initial",))
        if invite is not None:
            return reflet._linkup_send_invite(invite)
        author = self.env.user
        recipient = self._linkup_get_recipient(recipient_id)
        you_said, understood = reflet._linkup_sendable_texts()
        Link = self.env["linkup.link"]
        if not Link._is_active_between(author, recipient):
            reflet._linkup_require_real_world()
        link = Link._get_or_create(author, recipient)
        link._linkup_lock()
        reach = self.env["linkup.block"]._linkup_reach(author, recipient)
        if reach == "blocker":
            raise LinkupError(
                "linkup.unavailable", _("This reflection cannot be sent.")
            )
        link._linkup_reopen()
        now = fields.Datetime.now()
        vals = {
            "recipient_id": recipient.id,
            "link_id": link.id,
            "state": "sent",
            "sent_date": now,
            "you_said": you_said,
            "understood": understood,
        }
        if reflet.real_world_declared and not reflet.real_world_date:
            vals["real_world_date"] = fields.Date.context_today(self)
        if reach == "phantom":
            reflet.write(dict(vals, phantom=True))
            return True
        reflet.write(vals)
        link._linkup_touch()
        reflet._linkup_post_carrier()
        reflet._linkup_event("reflect_sent", author, link=link)
        return True

    def _linkup_send_invite(self, invite):
        """Turn the locked draft into a reflection waiting for an invited
        person; see ``action_send``. An invitation is always a first
        reflection, which declares an exchange in person."""
        you_said, understood = self._linkup_sendable_texts()
        self._linkup_require_real_world()
        invitation = self.env["linkup.invitation"]._linkup_create_for(
            self, invite
        )
        vals = {
            "state": "pending_invite",
            "invitation_id": invitation.id,
            "you_said": you_said,
            "understood": understood,
        }
        if not self.real_world_date:
            vals["real_world_date"] = fields.Date.context_today(self)
        self.write(vals)
        return invitation._linkup_info()

    def _linkup_deliver_invited(self, recipient):
        """Deliver a ``pending_invite`` reflection to the member who used
        its invitation, as ``action_send`` delivers to a member.

        The link of the pair is created ``pending``, and the carrier message
        opens the direct conversation of the pair, where the reflection
        waits unread. A recipient who is not a restricted member reachable
        by the author, or who is suspended, receives nothing and the
        reflection expires; a block in either direction gives a phantom
        delivery. Return whether the recipient received it.
        """
        self.ensure_one()
        reflet = self.sudo()
        reflet._linkup_lock()
        if reflet.state != "pending_invite":
            return False
        author = reflet.author_id
        recipient = recipient.sudo()
        if (
            recipient == author
            or recipient.share
            or not recipient._linkup_has_group_id(MEMBER_GROUP)
            or recipient._linkup_is_suspended()
        ):
            reflet.write({"state": "expired"})
            return False
        link = self.env["linkup.link"]._get_or_create(author, recipient)
        link._linkup_lock()
        reach = self.env["linkup.block"]._linkup_reach(author, recipient)
        link._linkup_reopen()
        vals = {
            "recipient_id": recipient.id,
            "link_id": link.id,
            "state": "sent",
            "sent_date": fields.Datetime.now(),
        }
        if reach != "open":
            reflet.write(dict(vals, phantom=True))
            return False
        reflet.write(vals)
        link._linkup_touch()
        reflet._linkup_post_carrier()
        reflet._linkup_event("reflect_sent", author, link=link)
        return True

    @server_context
    def action_withdraw(self):
        """Withdraw a sent reflection that its recipient has not read; a
        ``pending`` link that no other reflection waits on is closed."""
        reflet = self._linkup_begin(
            "author_id", ("sent",), ("initial",), exchange=False
        )
        if reflet.read_date:
            raise self._linkup_already_answered()
        reflet.link_id._linkup_lock()
        reflet.write({"state": "withdrawn"})
        reflet.link_id._linkup_close_unanswered()
        reflet._linkup_replace_carrier()
        reflet._linkup_notify()
        reflet._linkup_event(
            "reflect_withdrawn", reflet.author_id, link=reflet.link_id
        )
        return True

    # ------------------------------------------------------------------
    # Reception (recipient of an initial reflection)
    # ------------------------------------------------------------------

    @server_context
    def action_mark_read(self):
        """Record the first reading of the reflection by its recipient."""
        reflet = self._linkup_begin(
            "recipient_id", RECEIVED_STATES, KINDS, exchange=False
        )
        if not reflet.read_date:
            reflet.write({"read_date": fields.Datetime.now()})
            reflet._linkup_notify()
        return True

    def _linkup_answer_initial(self, vals):
        """Write the decision of the recipient on an initial reflection."""
        now = fields.Datetime.now()
        vals = dict(vals, answered_date=now)
        if not self.read_date:
            vals["read_date"] = now
        self.write(vals)

    @server_context
    def action_confirm(self):
        """Confirm the exchange: the pair becomes linked and the recipient
        takes the turn."""
        reflet = self._linkup_begin("recipient_id", ("sent",), ("initial",))
        link = reflet.link_id
        link._linkup_lock()
        reflet._linkup_answer_initial({"state": "confirmed"})
        link._linkup_activate()
        previous = reflet._linkup_move_turn(link, reflet)
        (reflet | previous)._linkup_notify()
        reflet._linkup_event(
            "reflect_confirmed", reflet._linkup_parties(), link=link
        )
        return True

    @server_context
    def action_reject(self):
        """Declare that the exchange never took place; a ``pending`` link
        that no other reflection waits on is closed."""
        reflet = self._linkup_begin("recipient_id", ("sent",), ("initial",))
        reflet.link_id._linkup_lock()
        reflet._linkup_answer_initial({"state": "rejected"})
        reflet.link_id._linkup_close_unanswered()
        reflet._linkup_notify()
        reflet._linkup_event(
            "reflect_rejected", reflet.author_id, link=reflet.link_id
        )
        self.env["linkup.report"]._linkup_check_rejections(reflet.author_id)
        return True

    @server_context
    def action_ignore(self):
        """Set the reflection aside for the recipient only.

        For the author it stays ``sent`` until it expires.
        """
        reflet = self._linkup_begin(
            "recipient_id", ("sent",), ("initial",), exchange=False
        )
        if not reflet.recipient_ignored:
            # The flag is written in SQL: an ORM write moves ``write_uid``
            # and ``write_date``, which the author reads, and would tell
            # them that the recipient acted on the reflection.
            self.env.cr.execute(
                "UPDATE linkup_reflet SET recipient_ignored = TRUE"
                " WHERE id = %s",
                [reflet.id],
            )
            reflet.invalidate_recordset(["recipient_ignored"])
            reflet._linkup_notify(conversation=False)
        return True

    @server_context
    def action_mark_inaccurate(self, body=None):
        """The exchange took place but the reformulation is wrong; ``body``
        is an optional correction for the author. No link results."""
        reflet = self._linkup_begin("recipient_id", ("sent",), ("initial",))
        body = self._linkup_clean_text(
            body,
            "body_text",
            self._linkup_param(
                "linkup.precision_text_max_length",
                DEFAULT_PRECISION_MAX_LENGTH,
            ),
            required=False,
        )
        reflet._linkup_answer_initial(
            {"state": "inaccurate", "body_text": body}
        )
        reflet.link_id._linkup_touch()
        reflet._linkup_notify()
        return True

    # ------------------------------------------------------------------
    # Answers (recipient of a confirmed initial or of a continued one)
    # ------------------------------------------------------------------

    @server_context
    def action_answer_exact(self, body=None):
        """Answer "that's exactly it", with an optional text.

        Return the id of the ``answer_exact`` reflection, which takes the
        turn: its recipient chooses how to go on.
        """
        reflet = self._linkup_begin(
            "recipient_id", ("confirmed", "sent"), ("initial", "continue")
        )
        reflet._linkup_check_answerable()
        link = reflet._linkup_take_turn()
        body = self._linkup_clean_text(
            body,
            "body_text",
            self._linkup_param(
                "linkup.precision_text_max_length",
                DEFAULT_PRECISION_MAX_LENGTH,
            ),
            required=False,
        )
        child = reflet._linkup_create_child(
            "answer_exact", {"body_text": body}
        )
        reflet.write(
            {"response_state": "exact", "answered_date": fields.Datetime.now()}
        )
        reflet._linkup_move_turn(link, child)
        reflet._linkup_after_child(child)
        code = (
            "answer_exact"
            if reflet.kind == "initial"
            else "continue_confirmed"
        )
        child._linkup_event(code, child._linkup_parties(), link=link)
        return child.id

    @server_context
    def action_answer_precision(self, body, hidden_category_ids=None):
        """Answer "I would like to clarify…", hiding up to N themes.

        ``body`` is stored as given: a precision never receives the starter
        of a hidden theme, which would give the theme away before the
        guess. The first theme is the main one. The themes go to
        ``linkup.reflet.secret``, never to a field of the reflection. Return
        the id of the ``precision`` reflection, whose recipient guesses.
        """
        reflet = self._linkup_begin(
            "recipient_id", ("confirmed", "sent"), ("initial", "continue")
        )
        reflet._linkup_check_answerable()
        link = reflet._linkup_take_turn()
        body = self._linkup_clean_text(
            body,
            "body_text",
            self._linkup_param(
                "linkup.precision_text_max_length",
                DEFAULT_PRECISION_MAX_LENGTH,
            ),
            required=True,
        )
        categories = self._linkup_get_hidden_categories(hidden_category_ids)
        child = reflet._linkup_create_child(
            "precision",
            {
                "body_text": body,
                "guess_state": "pending" if categories else "none",
            },
        )
        if categories:
            self.env["linkup.reflet.secret"].sudo().create(
                {
                    "reflet_id": child.id,
                    "category_ids": [Command.set(categories.ids)],
                    "primary_category_id": categories[0].id,
                }
            )
        reflet.write(
            {
                "response_state": "precision",
                "answered_date": fields.Datetime.now(),
            }
        )
        reflet._linkup_move_turn(link, child)
        reflet._linkup_after_child(child)
        child._linkup_event(
            "precision_sent", child._linkup_parties(), link=link
        )
        return child.id

    @server_context
    def action_guess(self, category_id):
        """Guess the hidden theme of a precision, once.

        Any of the hidden themes counts. Both outcomes reveal the themes to
        both parties. Return the resulting ``guess_state``.
        """
        reflet = self._linkup_begin("recipient_id", ("sent",), ("precision",))
        if reflet.guess_state == "none":
            raise LinkupError(
                "linkup.validation",
                _("This precision hides no theme."),
                field="guess_state",
            )
        if reflet.guess_state != "pending":
            raise self._linkup_already_answered()
        category = self._linkup_get_category(category_id)
        secret = (
            self.env["linkup.reflet.secret"]
            .sudo()
            .search([("reflet_id", "=", reflet.id)])
        )
        guess_state = "found" if category in secret.category_ids else "missed"
        reflet.write(
            {
                "guess_state": guess_state,
                "guessed_category_id": category.id,
                "answered_date": fields.Datetime.now(),
            }
        )
        reflet._linkup_notify()
        reflet._linkup_event(
            "theme_guessed" if guess_state == "found" else "theme_missed",
            reflet._linkup_parties(),
            link=reflet.link_id,
        )
        return guess_state

    # ------------------------------------------------------------------
    # Follow-up options (member whose turn it is)
    # ------------------------------------------------------------------

    @server_context
    def action_continue(self, category_id, body, you_said=None):
        """Reformulate again: "So if I understand correctly…".

        It applies to an exact answer or a resolved precision, by the member
        whose turn it is, and to a disclosure, by its recipient. ``body`` is
        the reformulation, stored in ``understood``; ``category_id`` the
        visible starter category. Return the id of the ``continue``
        reflection.
        """
        reflet = self._linkup_begin(
            "recipient_id",
            ("sent",),
            ("answer_exact", "precision", "self_disclosure"),
        )
        if reflet.kind == "self_disclosure":
            if reflet.response_state != "none":
                raise self._linkup_already_answered()
        else:
            reflet._linkup_check_options()
        link = reflet._linkup_take_turn()
        max_length = self._linkup_param(
            "linkup.reflet_text_max_length", DEFAULT_TEXT_MAX_LENGTH
        )
        child = reflet._linkup_create_child(
            "continue",
            {
                "category_id": self._linkup_get_category(category_id).id,
                "understood": self._linkup_clean_text(
                    body, "understood", max_length, required=True
                ),
                "you_said": self._linkup_clean_text(
                    you_said, "you_said", max_length, required=False
                ),
            },
        )
        if reflet.kind == "self_disclosure":
            reflet.write(
                {
                    "response_state": "precision",
                    "answered_date": fields.Datetime.now(),
                }
            )
        reflet._linkup_move_turn(link, child)
        reflet._linkup_after_child(child)
        child._linkup_event(
            "continue_sent", child._linkup_parties(), link=link
        )
        return child.id

    @server_context
    def action_self_disclosure(self, category_id, body):
        """Talk about oneself: the recipient is invited to reformulate.

        ``category_id`` is optional. No scoring event: the reformulation that
        follows is the one that scores. Return the id of the
        ``self_disclosure`` reflection.
        """
        reflet = self._linkup_begin(
            "recipient_id", ("sent",), ("answer_exact", "precision")
        )
        reflet._linkup_check_options()
        link = reflet._linkup_take_turn()
        child = reflet._linkup_create_child(
            "self_disclosure",
            {
                "category_id": self._linkup_get_category(
                    category_id, required=False
                ).id,
                "body_text": self._linkup_clean_text(
                    body,
                    "body_text",
                    self._linkup_param(
                        "linkup.precision_text_max_length",
                        DEFAULT_PRECISION_MAX_LENGTH,
                    ),
                    required=True,
                ),
            },
        )
        reflet._linkup_move_turn(link, child)
        reflet._linkup_after_child(child)
        return child.id

    @server_context
    def action_close(self, body=None):
        """End the turn politely; nobody has a turn until the next
        confirmed reflection. ``body`` is optional: without it, the clients
        show the closing sentence in the reader's language. Return the id
        of the ``close`` reflection."""
        reflet = self._linkup_begin(
            "recipient_id", ("sent",), ("answer_exact", "precision")
        )
        reflet._linkup_check_options()
        link = reflet._linkup_take_turn()
        child = reflet._linkup_create_child(
            "close",
            {
                "body_text": self._linkup_clean_text(
                    body,
                    "body_text",
                    self._linkup_param(
                        "linkup.reflet_text_max_length",
                        DEFAULT_TEXT_MAX_LENGTH,
                    ),
                    required=False,
                )
            },
        )
        reflet._linkup_move_turn(link, child)
        reflet._linkup_after_child(child)
        child._linkup_event("close", child._linkup_parties(), link=link)
        return child.id

    @api.model
    def _linkup_call_answered(self, channel, member):
        """Report a call of a direct conversation that the other party
        answered (LU-F-044 RM2, RM3).

        ``discuss.channel.member._rtc_join_call`` calls this after each
        join of ``member``: the call is answered when the conversation holds
        two RTC sessions, the other one being the caller's. Both sessions
        are then marked ``linkup_call_answered``, so that a participant who
        leaves and joins the same call again reports nothing more; the call
        ends with its last session. It counts between two restricted
        members of an ``active`` link, and reports ``call_answered`` for
        both, whoever started it and from wherever. ``key`` names the call
        by the session of its caller.

        A call also ends the turn when it opens from the three options: the
        call buttons of "Talking about oneself" belong to the member whose
        turn it is, while the turn shows the options (an exact answer, or a
        precision whose guess is made or that hides no theme). A call that
        this member started takes the options off the card, and its event
        is reported on that reflection. The caller is read from the state of
        the server, never from the client.
        """
        channel = channel.sudo()
        sessions = channel.rtc_session_ids
        if len(sessions) != 2:
            return False
        caller_session = sessions.filtered(
            lambda session: session.channel_member_id != member
        )
        if len(caller_session) != 1 or caller_session.linkup_call_answered:
            return False
        users = channel._linkup_chat_users()
        if not users or not all(
            user._linkup_is_restricted_member() for user in users
        ):
            return False
        link = self.env["linkup.link"]._get_between(users[0], users[1])
        if link.state != "active":
            return False
        link._linkup_lock()
        sessions.write({"linkup_call_answered": True})
        caller = caller_session.channel_member_id.partner_id.user_ids & users
        key = f"call:rtc:{caller_session.id}"
        reflet = link.turn_reflet_id
        if (
            reflet
            and reflet.kind in ("answer_exact", "precision")
            and reflet.state == "sent"
            and reflet.response_state == "none"
            and not (
                reflet.kind == "precision" and reflet.guess_state == "pending"
            )
            and reflet.recipient_id == caller
        ):
            link.write(
                {
                    "turn_reflet_id": False,
                    "last_interaction_date": fields.Datetime.now(),
                }
            )
            reflet._linkup_notify()
        else:
            link._linkup_touch()
            reflet = self.browse()
        reflet._linkup_event(
            "call_answered", users, link=link, channel=channel, key=key
        )
        return True

    # ------------------------------------------------------------------
    # Expiry
    # ------------------------------------------------------------------

    @api.model
    def _cron_expire_reflets(self):
        """Expire the initial reflections left unanswered for N days.

        The reflection and its link are locked together; a reflection
        whose row or link is held by an action in progress is skipped and
        expires at the next run. A ``pending`` link that no other reflection
        waits on is then closed. No scoring event: an expiry neither gives
        nor takes points.
        """
        days = self._linkup_param(
            "linkup.reflet_expiry_days", DEFAULT_EXPIRY_DAYS
        )
        limit = fields.Datetime.now() - timedelta(days=days)
        self.flush_model(["kind", "state", "sent_date", "link_id"])
        self.env["linkup.link"].flush_model(["state"])
        self.env.cr.execute(
            """
            SELECT reflet.id FROM linkup_reflet reflet
            JOIN linkup_link link ON link.id = reflet.link_id
            WHERE reflet.kind = 'initial'
              AND reflet.state = 'sent'
              AND reflet.sent_date < %s
            FOR UPDATE OF reflet, link SKIP LOCKED
            """,
            [limit],
        )
        ids = [row[0] for row in self.env.cr.fetchall()]
        reflets = self.sudo().browse(ids)
        reflets.invalidate_recordset()
        reflets.link_id.invalidate_recordset()
        reflets.write({"state": "expired"})
        reflets.link_id._linkup_close_unanswered()
        reflets._linkup_notify()
        return True
