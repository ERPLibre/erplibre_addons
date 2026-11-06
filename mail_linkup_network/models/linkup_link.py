# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.addons.mail_linkup_reflet.client_context import server_context
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError
from odoo.addons.mail_linkup_reflet.models.linkup_reflet import (
    RECEIVED_STATES,
)
from odoo.addons.mail_linkup_reflet.models.res_users import MEMBER_GROUP
from odoo.tools import html2plaintext

# Partners kept by the strongest density (Q-40: the top N, N = 2).
TOP_COUNT_PARAM = "linkup.network_top_count"
DEFAULT_TOP_COUNT = 2
# Nodes drawn at most around the member, the strongest first (LU-F-070 RM3).
MAX_NODES = 50
# Densities of the graph, by the values a client sends: X1 draws the direct
# links and the grey lines between the contacts, X2 the direct links, X3
# the strongest partners. ``2``, ``1`` and ``top`` are the levels of §9.8.
LEVELS = {
    "x1": "x1",
    "2": "x1",
    "x2": "x2",
    "1": "x2",
    "x3": "x3",
    "top": "x3",
}
DEFAULT_LEVEL = "x1"
# Kinds of ranking: the energy of each contact who shows it (LU-F-073), or
# the energy of the link with the member (LU-F-074).
RANKING_KINDS = ("active", "partners")
# Periods of a ranking, in days; ``all`` counts every line.
PERIODS = {"all": 0, "30d": 30}
# The energy of another member is shown to the hundred (LU-F-073 RM2).
ENERGY_ROUNDING = 100
# Entries of the thread of a link card, at most.
CARD_THREAD_LIMIT = 50
CARD_TEXT_LENGTH = 280


def round_energy(points):
    """Round a sum of points to the nearest hundred, halves up."""
    return (points + ENERGY_ROUNDING // 2) // ENERGY_ROUNDING * ENERGY_ROUNDING


class LinkupLink(models.Model):
    _inherit = "linkup.link"

    # ------------------------------------------------------------------
    # Contacts of the network
    # ------------------------------------------------------------------

    @api.model
    def _linkup_network_reader(self):
        """Check that the current user is a LinkUp member, and give the
        model back with ``active_test`` forced on.

        A caller sets the context of an RPC call: with ``active_test``
        off, the searches of the network would let in the archived
        accounts and the highlights put out, which the views keep away.
        """
        self.env["linkup.reflet"]._linkup_check_member()
        return self.with_context(active_test=True)

    @api.model
    def _linkup_network_top_count(self):
        """The number of partners the density X3 keeps, at least 1."""
        count = self.env["linkup.reflet"]._linkup_param(
            TOP_COUNT_PARAM, DEFAULT_TOP_COUNT
        )
        return max(count, 1)

    @api.model
    def _linkup_network_contacts(self, user, user_ids=None):
        """The contacts of ``user`` in the Network view: the other member
        of each ``active`` link, as ``{user id: link}``, links under
        ``sudo``.

        A ``pending``, ``closed`` or ``blocked`` link adds nobody, so the
        view never tells a reflection waiting or rejected, nor a block:
        a member who blocks ``user``, or whom ``user`` blocks, is absent
        as an archived account is. Only the active accounts of LinkUp
        members count. ``user_ids`` keeps those users only.
        """
        domain = [
            "|",
            ("user_a_id", "=", user.id),
            ("user_b_id", "=", user.id),
            ("state", "=", "active"),
        ]
        links = self.sudo().search(domain)
        by_user = {link._linkup_other_user(user).id: link for link in links}
        if user_ids is not None:
            by_user = {
                user_id: link
                for user_id, link in by_user.items()
                if user_id in user_ids
            }
        if not by_user:
            return {}
        members = (
            self.env["res.users"]
            .sudo()
            .search(
                [
                    ("id", "in", list(by_user)),
                    ("share", "=", False),
                    ("groups_id", "in", self.env.ref(MEMBER_GROUP).ids),
                ]
            )
        )
        return {user_id: by_user[user_id] for user_id in members.ids}

    @api.model
    def _linkup_highlighted_by(self, user, sender_ids):
        """The ids among ``sender_ids`` of the members whose highlight to
        ``user`` is active: the golden halo of their node."""
        if not sender_ids:
            return set()
        highlights = (
            self.env["linkup.highlight"]
            .sudo()
            .search(
                [
                    ("recipient_id", "=", user.id),
                    ("sender_id", "in", list(sender_ids)),
                    ("phantom", "=", False),
                ]
            )
        )
        return set(highlights.sender_id.ids)

    @api.model
    def _linkup_contact_values(self, user, highlighted):
        """What a node or a ranking row gives of a contact."""
        partner = user.partner_id
        return {
            "user_id": user.id,
            "partner_id": partner.id,
            "name": partner.name or user.name,
            "highlight": user.id in highlighted,
        }

    @api.model
    def _linkup_sort_key(self, value_of):
        """Sort contacts by decreasing value, then by name and id."""

        def key(user):
            name = user.partner_id.name or user.name or ""
            return (-value_of[user.id], name.casefold(), user.id)

        return key

    # ------------------------------------------------------------------
    # Graph (LU-F-070, LU-F-072)
    # ------------------------------------------------------------------

    @api.model
    def _linkup_network_level(self, level):
        level = LEVELS.get(str(level).lower() if level else DEFAULT_LEVEL)
        if not level:
            raise LinkupError(
                "linkup.validation",
                _("Unknown density of the network."),
                field="level",
            )
        return level

    @api.model
    @server_context
    def get_network_graph(self, level=DEFAULT_LEVEL, limit=MAX_NODES):
        """The graph of the Network view, centred on the current member.

        ``level`` is the density: ``x1`` (or ``2``) draws the direct links
        and, between two contacts, the grey line of their own ``active``
        link when both show their links (LU-NF-012, Q-09); ``x2`` (or
        ``1``) the direct links only; ``x3`` (or ``top``) the strongest
        partners only, ``linkup.network_top_count`` of them. ``limit``
        bounds the nodes, the strongest kept, at most ``MAX_NODES``.

        The answer gives ``me`` (``user_id``, ``partner_id``, ``name``,
        ``energy``: the karma of the member, Q-08), ``nodes`` (each with
        ``energy``, the energy of the link as the member received it,
        LU-F-071 RM2, and ``highlight``, an active highlight it sent to the
        member), ``edges`` (``direct`` ones from the member, with their
        energy; ``contacts`` ones without any, the energy of a pair being
        theirs) and ``more``, whether stronger nodes hid weaker ones. Nobody
        outside the contacts appears, not even as an anonymous node.

        The number of queries does not grow with the number of contacts.
        """
        self = self._linkup_network_reader()
        level = self._linkup_network_level(level)
        try:
            limit = min(max(int(limit), 1), MAX_NODES)
        except (TypeError, ValueError):
            limit = MAX_NODES
        me = self.env.user
        contacts = self._linkup_network_contacts(me)
        energy = {
            user_id: link._linkup_energy_for(me)
            for user_id, link in contacts.items()
        }
        users = self.env["res.users"].sudo().browse(list(contacts))
        ordered = users.sorted(self._linkup_sort_key(energy))
        if level == "x3":
            limit = min(limit, self._linkup_network_top_count())
        shown = ordered[:limit]
        highlighted = self._linkup_highlighted_by(me, shown.ids)
        nodes = []
        edges = []
        for user in shown:
            nodes.append(
                dict(
                    self._linkup_contact_values(user, highlighted),
                    energy=energy[user.id],
                )
            )
            edges.append(
                {
                    "source": me.id,
                    "target": user.id,
                    "kind": "direct",
                    "energy": energy[user.id],
                }
            )
        if level == "x1":
            edges += self._linkup_consented_edges(shown)
        partner = me.partner_id
        return {
            "level": level,
            "me": {
                "user_id": me.id,
                "partner_id": partner.id,
                "name": partner.name or me.name,
                "energy": me.sudo().karma,
            },
            "nodes": nodes,
            "edges": edges,
            "more": level != "x3" and len(ordered) > len(shown),
        }

    @api.model
    def _linkup_consented_edges(self, users):
        """The grey lines between ``users``: their ``active`` links whose
        two members both show their links. ``users`` are ``sudo``."""
        consenting = users.filtered("linkup_links_visible")
        if len(consenting) < 2:
            return []
        links = self.sudo().search(
            [
                ("user_a_id", "in", consenting.ids),
                ("user_b_id", "in", consenting.ids),
                ("state", "=", "active"),
            ]
        )
        return [
            {
                "source": link.user_a_id.id,
                "target": link.user_b_id.id,
                "kind": "contacts",
            }
            for link in links
        ]

    # ------------------------------------------------------------------
    # Rankings (LU-F-073, LU-F-074)
    # ------------------------------------------------------------------

    @api.model
    @server_context
    def get_ranking(self, kind="partners", period="all"):
        """A ranking of the contacts of the current member, never of the
        whole community (LU-NF-032).

        ``kind`` ``partners`` ranks the contacts by the energy of the link
        with the member: the points the member received in the events of
        each pair (LU-F-074), the value of the link card. ``active`` ranks
        the contacts who show their energy (``linkup_energy_visible``) by
        the points they received from anybody, penalties left out, rounded
        to the hundred (LU-F-073 RM2). ``period`` is ``all`` or ``30d``.

        Each row gives ``position``, ``user_id``, ``partner_id``, ``name``,
        ``value`` and ``highlight``; equal values go by name.
        """
        self = self._linkup_network_reader()
        if kind not in RANKING_KINDS:
            raise LinkupError(
                "linkup.validation",
                _("Unknown ranking."),
                field="kind",
            )
        if period not in PERIODS:
            raise LinkupError(
                "linkup.validation",
                _("Unknown period."),
                field="period",
            )
        me = self.env.user
        contacts = self._linkup_network_contacts(me)
        users = self.env["res.users"].sudo().browse(list(contacts))
        domain = []
        if PERIODS[period]:
            since = fields.Datetime.now() - timedelta(days=PERIODS[period])
            domain.append(("date", ">=", since))
        Ledger = self.env["linkup.points.ledger"].sudo()
        if kind == "partners":
            totals = dict(
                Ledger._read_group(
                    domain
                    + [
                        ("user_id", "=", me.id),
                        (
                            "link_id",
                            "in",
                            [link.id for link in contacts.values()],
                        ),
                    ],
                    ["link_id"],
                    ["points:sum"],
                )
            )
            values = {
                user.id: totals.get(contacts[user.id], 0) for user in users
            }
        else:
            users = users.filtered("linkup_energy_visible")
            totals = dict(
                Ledger._read_group(
                    domain
                    + [("user_id", "in", users.ids), ("points", ">", 0)],
                    ["user_id"],
                    ["points:sum"],
                )
            )
            values = {
                user.id: round_energy(totals.get(user, 0)) for user in users
            }
        highlighted = self._linkup_highlighted_by(me, users.ids)
        rows = []
        for position, user in enumerate(
            users.sorted(self._linkup_sort_key(values)), start=1
        ):
            rows.append(
                dict(
                    self._linkup_contact_values(user, highlighted),
                    position=position,
                    value=values[user.id],
                )
            )
        return {"kind": kind, "period": period, "rows": rows}

    # ------------------------------------------------------------------
    # Link card (LU-F-075)
    # ------------------------------------------------------------------

    @api.model
    @server_context
    def get_link_card(self, user_id, reflets_only=False, limit=20):
        """The card of the link between the current member and a contact.

        ``user_id`` must be a contact of the Network view; any other id,
        a member outside the scope, a ``pending`` or ``blocked`` link or an
        archived account, gives ``{"available": False}``, whatever the
        reason. The card gives the contact (``user_id``, ``partner_id``,
        ``name``), ``energy`` as the member received it (LU-F-071 RM2),
        ``first_link_date``, ``channel_id``, the direct conversation for the
        call, the video call and the conversation, ``highlight_sent`` and
        ``highlight_received``, and ``entries``: the thread of the pair,
        oldest first, at most ``limit`` (Q-26).

        The thread holds what both members read: the comments of their
        direct conversation, with ``reflets_only`` the carrier messages of
        their reflections only; a draft, a withdrawn reflection and a
        phantom one have no entry. Each entry gives ``message_id``,
        ``date``, ``mine``, ``reflet_id`` and ``text``, the plain text cut
        to ``CARD_TEXT_LENGTH``; the cards of the reflections are in
        ``store``, with the private part of the member.
        """
        self = self._linkup_network_reader()
        unavailable = {"available": False}
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return unavailable
        me = self.env.user
        link = self._linkup_network_contacts(me, user_ids={user_id}).get(
            user_id
        )
        if not link:
            return unavailable
        try:
            limit = min(max(int(limit), 1), CARD_THREAD_LIMIT)
        except (TypeError, ValueError):
            limit = CARD_THREAD_LIMIT
        other = self.env["res.users"].sudo().browse(user_id)
        channel = link.channel_id
        if me.partner_id not in channel.channel_member_ids.partner_id:
            channel = self.env["discuss.channel"]
        Highlight = self.env["linkup.highlight"].sudo()
        entries, reflets = self._linkup_card_thread(
            link, channel, bool(reflets_only), limit
        )
        store = Store(reflets)
        reflets._linkup_private_to_store(store, me)
        partner = other.partner_id
        return {
            "available": True,
            "user_id": other.id,
            "partner_id": partner.id,
            "name": partner.name or other.name,
            "energy": link._linkup_energy_for(me),
            "first_link_date": link.first_link_date or False,
            "channel_id": channel.id or False,
            "highlight_sent": bool(
                Highlight.search_count(
                    [("sender_id", "=", me.id), ("recipient_id", "=", user_id)]
                )
            ),
            "highlight_received": bool(
                self._linkup_highlighted_by(me, {user_id})
            ),
            "entries": entries,
            "store": store.get_result(),
        }

    @api.model
    def _linkup_card_thread(self, link, channel, reflets_only, limit):
        """The entries of the thread of a link card, oldest first, and the
        reflections they carry, under ``sudo``."""
        Reflet = self.env["linkup.reflet"].sudo()
        if not channel:
            return [], Reflet
        visible = Reflet.search(
            [
                ("link_id", "=", link.id),
                ("channel_id", "=", channel.id),
                ("state", "in", RECEIVED_STATES),
                ("phantom", "=", False),
                ("message_id", "!=", False),
            ]
        )
        reflet_of = {reflet.message_id.id: reflet for reflet in visible}
        domain = [
            ("model", "=", "discuss.channel"),
            ("res_id", "=", channel.id),
            ("message_type", "=", "comment"),
        ]
        if reflets_only:
            domain.append(("id", "in", list(reflet_of)))
        # sudo: mail.message - the member belongs to the conversation
        messages = (
            self.env["mail.message"]
            .sudo()
            .search(domain, order="id desc", limit=limit)
        )
        hidden = Reflet.search(
            [
                ("message_id", "in", messages.ids),
                ("id", "not in", visible.ids),
            ]
        ).message_id
        me = self.env.user.partner_id
        entries = []
        reflets = Reflet
        for message in reversed(messages - hidden):
            reflet = reflet_of.get(message.id, Reflet)
            reflets |= reflet
            text = html2plaintext(message.body or "").strip()
            entries.append(
                {
                    "message_id": message.id,
                    "date": message.date,
                    "mine": message.author_id == me,
                    "reflet_id": reflet.id or False,
                    "text": text[:CARD_TEXT_LENGTH],
                }
            )
        return entries, reflets
