# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging
from collections import defaultdict

from markupsafe import Markup
from odoo import _, api, fields, models
from odoo.addons.mail_linkup_reflet.client_context import server_context
from odoo.addons.mail_linkup_reflet.models.res_users import (
    ADMIN_GROUP,
    MEMBER_GROUP,
)
from odoo.exceptions import AccessError
from odoo.tools import SQL

from .linkup_points_rule import CAP_REASONS, INELIGIBLE_REASONS

_logger = logging.getLogger(__name__)

# Columns a ledger line is inserted with, besides the log columns.
LINE_COLUMNS = (
    "user_id",
    "partner_user_id",
    "rule_id",
    "points",
    "capped",
    "cap_reason",
    "date",
    "channel_id",
    "message_id",
    "reflet_id",
    "link_id",
    "event_key",
    "resets_decay",
    "decay_day",
)
# Badges given at the first line of a rule, by rule code.
FIRST_LINE_BADGES = {
    "reflect_sent": "badge_first_reflection",
    "reflect_confirmed": "badge_first_link",
    "theme_guessed": "badge_first_guess",
    "call_answered": "badge_first_call",
}
TEN_LINKS_BADGE = "badge_ten_links"
TEN_LINKS = 10
MY_POINTS_MAX_LIMIT = 200


class LinkupPointsLedger(models.Model):
    """The points ledger of LinkUp, one line per beneficiary of an event.

    The ledger is append-only: lines are inserted by
    ``_linkup_record`` and never written afterwards; only the superuser
    deletes them, with the account they belong to. It is never
    consolidated, unlike ``gamification.karma.tracking``, so the karma of a
    member always equals the sum of their lines (LU-NF-043), which
    ``_cron_check_karma`` controls every day.

    ``event_key`` makes an event idempotent: a rule pays a member once per
    key, whatever the number of times the event is reported. A line that a
    cap or the account of its member leaves at 0 is kept, ``capped``, with
    its ``cap_reason``. A member reads their own lines only.
    """

    _name = "linkup.points.ledger"
    _inherit = ["linkup.server.record"]
    _description = "LinkUp points ledger"
    _order = "date desc, id desc"
    _rec_name = "rule_id"

    user_id = fields.Many2one(
        "res.users",
        string="Beneficiary",
        required=True,
        index=True,
        ondelete="cascade",
        readonly=True,
    )
    partner_user_id = fields.Many2one(
        "res.users",
        string="Counterpart",
        index=True,
        ondelete="set null",
        readonly=True,
    )
    rule_id = fields.Many2one(
        "linkup.points.rule",
        required=True,
        index=True,
        ondelete="restrict",
        readonly=True,
    )
    points = fields.Integer(
        readonly=True, help="Points actually paid, 0 for a capped line."
    )
    capped = fields.Boolean(readonly=True, index=True)
    cap_reason = fields.Selection(
        CAP_REASONS, string="Cap reason", readonly=True
    )
    date = fields.Datetime(required=True, index=True, readonly=True)
    channel_id = fields.Many2one(
        "discuss.channel",
        string="Conversation",
        ondelete="set null",
        readonly=True,
    )
    message_id = fields.Many2one(
        "mail.message", ondelete="set null", readonly=True
    )
    reflet_id = fields.Many2one(
        "linkup.reflet",
        string="Reflection",
        index="btree_not_null",
        ondelete="set null",
        readonly=True,
    )
    link_id = fields.Many2one(
        "linkup.link", index=True, ondelete="set null", readonly=True
    )
    event_key = fields.Char(string="Event key", required=True, readonly=True)
    resets_decay = fields.Boolean(
        string="Resets the decay",
        readonly=True,
        help="The line starts the decreasing sequences of the pair again.",
    )
    decay_day = fields.Datetime(
        string="Day of the sequence",
        readonly=True,
        help="Midnight, in UTC, of the day of the decreasing sequence the"
        " line belongs to.",
    )
    karma_tracking_id = fields.Many2one(
        "gamification.karma.tracking",
        string="Karma change",
        ondelete="set null",
        readonly=True,
        help="Karma change of the event; consolidating the karma history"
        " deletes it, which leaves the line as it is.",
    )

    _sql_constraints = [
        (
            "event_unique",
            "UNIQUE(rule_id, user_id, event_key)",
            "A rule pays a member once per event.",
        ),
    ]

    def write(self, vals):
        raise AccessError(_("The points ledger cannot be modified."))

    def unlink(self):
        if not self.env.su:
            raise AccessError(_("The points ledger cannot be modified."))
        return super().unlink()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    @api.model
    def _linkup_lock_users(self, users):
        """Lock the rows of ``users`` in increasing id order.

        Two events of one member are serialized here, so the caps they
        count and the karma they add never interleave. ``NOWAIT`` makes a
        concurrent transaction fail at once with a lock error, which the RPC
        layer retries; the retry reads the karma and the lines written by
        the first one. The karma is read again after the lock.
        """
        self.env["res.users"].flush_model(["karma"])
        self.env.cr.execute(
            "SELECT id FROM res_users WHERE id IN %s"
            " ORDER BY id FOR NO KEY UPDATE NOWAIT",
            [tuple(users.ids)],
        )
        users.invalidate_recordset(["karma"])

    @api.model
    def _linkup_record(
        self, targets, event_key, link, reflet, channel, message
    ):
        """Write the lines of an event and credit their points.

        ``targets`` lists ``(rule, user)`` pairs. A pair already recorded
        for ``event_key`` is skipped; ``INSERT … ON CONFLICT DO NOTHING``
        also skips one that a concurrent transaction committed meanwhile.
        The points paid then go to the karma, to the energy of the link and
        to the badges, and each beneficiary hears of their line on the bus.
        Return the new lines.
        """
        users = self.env["res.users"].sudo()
        for _rule, user in targets:
            users |= user
        self._linkup_lock_users(users)
        now = fields.Datetime.now()
        known = {
            (line.rule_id.id, line.user_id.id)
            for line in self.search(
                [
                    ("event_key", "=", event_key),
                    ("user_id", "in", users.ids),
                ]
            )
        }
        lines = self.browse()
        for rule, user in targets:
            if (rule.id, user.id) in known:
                continue
            values = rule._linkup_line(user, link, now)
            counterpart = (
                link._linkup_other_user(user) if link else users - user
            )
            lines |= self._linkup_insert(
                {
                    "user_id": user.id,
                    "partner_user_id": counterpart[:1].id or None,
                    "rule_id": rule.id,
                    "points": values["points"],
                    "capped": bool(values["cap_reason"]),
                    "cap_reason": values["cap_reason"] or None,
                    "date": now,
                    "channel_id": channel.id or None,
                    "message_id": message.id or None,
                    "reflet_id": reflet.id or None,
                    "link_id": link.id or None,
                    "event_key": event_key,
                    "resets_decay": values["resets_decay"],
                    "decay_day": values["decay_day"] or None,
                }
            )
            known.add((rule.id, user.id))
        if lines:
            lines._linkup_credit_karma(reflet or link)
            lines._linkup_add_energy()
            lines._linkup_grant_badges()
            lines._linkup_notify()
        return lines

    @api.model
    def _linkup_insert(self, vals):
        """Insert one line in SQL; return it, or nothing on a conflict."""
        self.flush_model()
        values = [vals[column] for column in LINE_COLUMNS]
        self.env.cr.execute(
            SQL(
                "INSERT INTO linkup_points_ledger (%s, create_uid,"
                " create_date, write_uid, write_date)"
                " VALUES %s ON CONFLICT (rule_id, user_id, event_key)"
                " DO NOTHING RETURNING id",
                SQL(", ").join(SQL.identifier(c) for c in LINE_COLUMNS),
                tuple(values + [self.env.uid, vals["date"]] * 2),
            )
        )
        row = self.env.cr.fetchone()
        self.invalidate_model()
        return self.browse(row[0]) if row else self.browse()

    def _linkup_credit_karma(self, source):
        """Add the points of the lines to the karma of their members.

        One ``gamification.karma.tracking`` per member, created as
        ``res.users._add_karma_batch`` does, from the karma read after the
        lock; the native computation then sets ``res.users.karma`` to its
        ``new_value`` and moves the rank. The line keeps its tracking.
        """
        gains = defaultdict(int)
        names = defaultdict(list)
        for line in self:
            gains[line.user_id] += line.points
            names[line.user_id].append(line.rule_id.name)
        vals_list = []
        for user, gain in gains.items():
            if not gain:
                continue
            vals_list.append(
                {
                    "user_id": user.id,
                    "old_value": user.karma,
                    "new_value": user.karma + gain,
                    "origin_ref": f"{source._name},{source.id}",
                    "reason": _(
                        "LinkUp: %(rules)s", rules=", ".join(names[user])
                    ),
                }
            )
        if not vals_list:
            return
        trackings = (
            self.env["gamification.karma.tracking"].sudo().create(vals_list)
        )
        trackings.flush_recordset()
        for tracking in trackings:
            line_ids = tuple(
                self.filtered(
                    lambda line: line.user_id == tracking.user_id
                ).ids
            )
            self.env.cr.execute(
                "UPDATE linkup_points_ledger SET karma_tracking_id = %s"
                " WHERE id IN %s",
                [tracking.id, line_ids],
            )
        self.invalidate_recordset(["karma_tracking_id"])
        self.env["res.users"].flush_model(["karma", "rank_id"])

    def _linkup_add_energy(self):
        """Add the points of the lines to the energy of their link, on the
        side of the member who received them (LU-F-071 RM2)."""
        by_link = defaultdict(lambda: [0, 0])
        for line in self.filtered("link_id"):
            link = line.link_id
            side = 0 if line.user_id == link.user_a_id else 1
            by_link[link][side] += line.points
        Link = self.env["linkup.link"]
        Link.flush_model(["energy_a", "energy_b"])
        for link, (gain_a, gain_b) in by_link.items():
            if gain_a or gain_b:
                self.env.cr.execute(
                    "UPDATE linkup_link"
                    " SET energy_a = COALESCE(energy_a, 0) + %s,"
                    " energy_b = COALESCE(energy_b, 0) + %s WHERE id = %s",
                    [gain_a, gain_b, link.id],
                )
        Link.invalidate_model(["energy_a", "energy_b"])

    def _linkup_grant_badges(self):
        """Give the LinkUp badges that the lines earn, once per member.

        A line of an account that earns no points earns no badge either.
        The guess badge goes to the member who guessed, the recipient of
        the precision.
        """
        for line in self:
            if line.cap_reason in INELIGIBLE_REASONS:
                continue
            code = line.rule_id.code
            user = line.user_id
            guesser = code != "theme_guessed" or (
                line.reflet_id.recipient_id in (user, user.browse())
            )
            if code in FIRST_LINE_BADGES and guesser:
                self._linkup_grant_badge(user, FIRST_LINE_BADGES[code])
            if code == "reflect_confirmed":
                links = (
                    self.env["linkup.link"]
                    .sudo()
                    .search_count(
                        [
                            "|",
                            ("user_a_id", "=", user.id),
                            ("user_b_id", "=", user.id),
                            ("first_link_date", "!=", False),
                        ]
                    )
                )
                if links >= TEN_LINKS:
                    self._linkup_grant_badge(user, TEN_LINKS_BADGE)

    @api.model
    def _linkup_grant_badge(self, user, name):
        """Give the badge ``name`` of this module to ``user`` once.

        It is granted by the server under ``sudo``, the badges of LinkUp
        being granted by nobody; ``_send_badge`` announces it on the bus.
        """
        badge = self.env.ref(
            f"mail_linkup_gamification.{name}", raise_if_not_found=False
        )
        if not badge or not badge.active:
            return
        BadgeUser = self.env["gamification.badge.user"].sudo()
        if BadgeUser.search_count(
            [("user_id", "=", user.id), ("badge_id", "=", badge.id)], limit=1
        ):
            return
        BadgeUser.create(
            {"user_id": user.id, "badge_id": badge.id}
        )._send_badge()

    def _linkup_notify(self):
        """Send each line to its member on ``linkup.points/awarded``.

        A capped line carries the information code ``linkup.cap_reached``
        (LU-F-093): the action succeeded and paid nothing. A line that the
        account of its member left at 0 is not sent. The id of the line lets
        the web client tell a line it already showed, whether the bus or a
        reading of ``linkup_my_points`` brought it first.
        """
        for line in self:
            if line.cap_reason in INELIGIBLE_REASONS:
                continue
            payload = {
                "id": line.id,
                "points": line.points,
                "rule_code": line.rule_id.code,
                "counterpart_id": line.partner_user_id.partner_id.id or False,
                "reflet_id": line.reflet_id.id or False,
                "channel_id": line.channel_id.id or False,
                "capped": line.capped,
                "cap_reason": line.cap_reason or False,
                "karma": line.user_id.karma,
            }
            if line.capped:
                payload["linkup_code"] = "linkup.cap_reached"
            line.user_id.partner_id._bus_send("linkup.points/awarded", payload)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    @api.model
    @server_context
    def linkup_my_points(
        self,
        limit=50,
        offset=0,
        rule_code=False,
        counterpart_id=False,
        after_id=False,
    ):
        """The points of the current member (LU-F-103): their balance, rank,
        next rank and badges, the point scale, and a page of their own
        ledger lines, most recent first.

        ``rule_code`` keeps the lines of one rule, ``counterpart_id`` those
        shared with one user. ``after_id`` keeps the lines newer than that
        id, oldest first: the web client reads with it the points of an
        action it just ran, when the bus is late or down. ``total`` counts
        the lines the filters keep; ``counterparts`` lists the users the
        member shares lines with, for the filter, and ``last_id`` is the
        newest line of the member.

        The lines are searched with the rights of the member, whose record
        rule opens their own lines only. A counterpart is named only while
        the member still reads it.
        """
        self.env["linkup.reflet"]._linkup_check_member()
        user = self.env.user
        try:
            limit = max(1, min(int(limit), MY_POINTS_MAX_LIMIT))
            offset = max(0, int(offset))
            after_id = max(0, int(after_id or 0))
            counterpart_id = int(counterpart_id or 0)
        except (TypeError, ValueError):
            limit, offset, after_id, counterpart_id = 50, 0, 0, 0
        own = [("user_id", "=", user.id)]
        domain = list(own)
        if rule_code:
            domain.append(("rule_id.code", "=", str(rule_code)))
        if counterpart_id:
            domain.append(("partner_user_id", "=", counterpart_id))
        order = None
        if after_id:
            domain.append(("id", ">", after_id))
            order = "id"
        lines = self.search(domain, limit=limit, offset=offset, order=order)
        total = self.search_count(domain)
        last = self.search(own, limit=1, order="id desc")
        shared = self._read_group(own, ["partner_user_id"])
        readable = self.env["res.users"].search(
            [
                (
                    "id",
                    "in",
                    [partner.id for (partner,) in shared if partner],
                )
            ]
        )
        lines = lines.sudo()
        me = user.sudo()
        rules = (
            self.env["linkup.points.rule"]
            .sudo()
            .search([("beneficiaries", "!=", "none")])
        )
        return {
            "balance": me.karma,
            "total": total,
            "last_id": last.id or 0,
            "rank": (
                {
                    "id": me.rank_id.id,
                    "name": me.rank_id.name,
                    "karma_min": me.rank_id.karma_min,
                }
                if me.rank_id
                else False
            ),
            "next_rank": (
                {
                    "id": me.next_rank_id.id,
                    "name": me.next_rank_id.name,
                    "karma_min": me.next_rank_id.karma_min,
                }
                if me.next_rank_id
                else False
            ),
            "badges": [
                {
                    "id": badge_user.badge_id.id,
                    "name": badge_user.badge_id.name,
                    "description": badge_user.badge_id.description or "",
                    "level": badge_user.badge_id.level or False,
                }
                for badge_user in me.badge_ids
            ],
            "rules": [
                {"code": rule.code, "name": rule.name, "points": rule.points}
                for rule in rules
            ],
            "counterparts": [
                {"id": counterpart.id, "name": counterpart.name}
                for counterpart in readable.sorted("name")
            ],
            "lines": [
                {
                    "id": line.id,
                    "date": fields.Datetime.to_string(line.date),
                    "rule_code": line.rule_id.code,
                    "rule_name": line.rule_id.name,
                    "points": line.points,
                    "capped": line.capped,
                    "cap_reason": line.cap_reason or False,
                    "counterpart": (
                        {
                            "id": line.partner_user_id.id,
                            "name": line.partner_user_id.name,
                        }
                        if line.partner_user_id
                        and line.partner_user_id in readable
                        else False
                    ),
                    "reflet_id": line.reflet_id.id or False,
                }
                for line in lines
            ],
        }

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    @api.model
    def _linkup_remove_karma(self):
        """Take the points of the ledger out of the karma of their members,
        and return those members.

        The uninstallation of the module calls it before the ledger leaves:
        the karma it credited would otherwise outlive it, and a later
        installation would start from a karma that no line explains
        (LU-NF-043). A karma earned outside LinkUp stays.
        """
        self.flush_model()
        self.env.cr.execute(
            "SELECT user_id, SUM(points) FROM linkup_points_ledger"
            " GROUP BY user_id HAVING SUM(points) != 0 ORDER BY user_id"
        )
        totals = dict(self.env.cr.fetchall())
        users = self.env["res.users"].sudo().browse(list(totals))
        users._add_karma_batch(
            {
                user: {
                    "gain": -totals[user.id],
                    "reason": _("LinkUp: points of the removed ledger"),
                }
                for user in users
            }
        )
        users.flush_recordset(["karma", "rank_id"])
        return users

    @api.model
    def _cron_check_karma(self):
        """Compare the karma of each restricted member with the sum of their
        ledger lines (LU-NF-043).

        A difference means the karma moved outside the ledger, or the
        reverse: it is logged as an error, with the ids of the members, and
        each LinkUp administrator receives an activity about it
        (``_linkup_alert_karma``). Return those ids.
        """
        self.flush_model()
        self.env["res.users"].flush_model(["karma"])
        member = self.env.ref(MEMBER_GROUP)
        system = self.env.ref("base.group_system")
        self.env.cr.execute(
            """
            SELECT u.id
            FROM res_users u
            JOIN res_groups_users_rel m ON m.uid = u.id AND m.gid = %s
            LEFT JOIN (
                SELECT user_id, SUM(points) AS total
                FROM linkup_points_ledger GROUP BY user_id
            ) l ON l.user_id = u.id
            WHERE NOT EXISTS (
                SELECT 1 FROM res_groups_users_rel s
                WHERE s.uid = u.id AND s.gid = %s
            )
            AND COALESCE(u.karma, 0) != COALESCE(l.total, 0)
            ORDER BY u.id
            """,
            [member.id, system.id],
        )
        user_ids = [row[0] for row in self.env.cr.fetchall()]
        if user_ids:
            _logger.error(
                "LinkUp: the karma of %s members differs from their points"
                " ledger: %s",
                len(user_ids),
                user_ids,
            )
            self._linkup_alert_karma(user_ids)
        return user_ids

    @api.model
    def _linkup_alert_karma(self, user_ids):
        """Give each LinkUp administrator a to-do activity about the members
        ``user_ids``, whose karma differs from their ledger; return the
        activities created.

        The activity names the members by id only, in the language of the
        administrator, and sits on the partner of the administrator it is
        assigned to, so that no record of a member carries it. An
        administrator who holds an open activity for the same members gets
        no second one; once it is done, the next check that still finds the
        difference creates it again.
        """
        Activity = self.env["mail.activity"].sudo()
        admins = (
            self.env.ref(ADMIN_GROUP)
            .sudo()
            .users.filtered(lambda user: user.active and not user.share)
        )
        if not admins:
            return Activity
        todo = self.env.ref(
            "mail.mail_activity_data_todo", raise_if_not_found=False
        )
        ids = ", ".join(str(user_id) for user_id in sorted(user_ids))
        partner_model_id = self.env["ir.model"]._get_id("res.partner")
        vals_list = []
        for admin in admins:
            env = self.with_context(lang=admin.lang).env
            summary = env._(
                "LinkUp: check the karma of the members %(ids)s", ids=ids
            )
            domain = [
                ("res_model", "=", "res.partner"),
                ("res_id", "=", admin.partner_id.id),
                ("user_id", "=", admin.id),
                ("summary", "=", summary),
            ]
            if todo:
                domain.append(("activity_type_id", "=", todo.id))
            if Activity.search_count(domain, limit=1):
                continue
            note = env._(
                "Members whose karma differs from the sum of their LinkUp"
                " points ledger lines (LU-NF-043): %(count)s. Their ids:"
                " %(ids)s.",
                count=len(user_ids),
                ids=ids,
            )
            vals_list.append(
                {
                    "res_model_id": partner_model_id,
                    "res_id": admin.partner_id.id,
                    "user_id": admin.id,
                    "activity_type_id": todo.id if todo else False,
                    "summary": summary,
                    "note": Markup("<p>%s</p>") % note,
                }
            )
        return Activity.create(vals_list)
