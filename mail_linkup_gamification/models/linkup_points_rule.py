# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import timedelta

from odoo import api, fields, models

# The rules that each scoring event of the core applies, in order; an
# event absent from the map applies the rule of its own code. The points
# of ``reflect_sent`` are paid with the confirmation (Q-01): a reflection
# rejected, withdrawn or expired has paid nothing to its author.
EVENT_RULES = {
    "reflect_sent": (),
    "reflect_confirmed": ("reflect_confirmed", "reflect_sent"),
}
# The answered call, which may wait for the end of the call to be paid.
CALL_CODE = "call_answered"
VIRTUAL_ROUND = "virtual_round"
VIRTUAL_ROUND_PARAM = "linkup.virtual_round_points"
# The caps of a rule, checked in this order: the field, the sliding window
# it counts, and whether it counts within the pair only.
CAPS = (
    ("pair_lifetime_cap", None, True),
    ("pair_weekly_cap", timedelta(days=7), True),
    ("pair_daily_cap", timedelta(days=1), True),
    ("weekly_cap", timedelta(days=7), False),
    ("daily_cap", timedelta(days=1), False),
)
# Why a ledger line pays nothing. The first two concern the account of the
# beneficiary, the others a cap of the rule.
CAP_REASONS = [
    ("new_account", "Account too recent"),
    ("unverified", "Account not verified"),
    ("pair_lifetime_cap", "Cap of the pair"),
    ("pair_weekly_cap", "Weekly cap of the pair"),
    ("pair_daily_cap", "Daily cap of the pair"),
    ("weekly_cap", "Weekly cap"),
    ("daily_cap", "Daily cap"),
    ("decay", "Sequence exhausted"),
]
INELIGIBLE_REASONS = ("new_account", "unverified")
# The shortest span between two midnights of one time zone, a change to
# daylight saving time included: a sequence starts again at a midnight
# that far from the start of its current day, at the soonest.
SHORTEST_DAY = timedelta(hours=23)


class LinkupPointsRule(models.Model):
    """A rule of the LinkUp point scale (§7.1), edited by the LinkUp
    administrators.

    A rule pays ``points`` to its ``beneficiaries`` for each event of its
    ``code``. A positive value is subject to the caps of the rule, counted
    over sliding windows of 24 hours and 7 days, so that a change of time
    zone never pays a day twice; beyond a cap the event still writes its
    ledger line, at 0 and ``capped``. Rules that share a ``cap_group`` count
    their lines together. A negative value, a penalty, has no cap.

    A rule with ``decay`` pays less for each repetition within a pair: the
    n-th line of the sequence of a member pays the value halved n − 1 times
    and rounded down, so that 100 gives 100, 50, 25, 12, 6, 3, 1, then 0. The
    sequence of a member starts again at midnight in their time zone, and
    after each line of the pair that ``resets_decay``.
    """

    _name = "linkup.points.rule"
    _description = "LinkUp points rule"
    _order = "sequence, id"

    code = fields.Char(
        required=True,
        help="Code of the event of LinkUp that applies the rule.",
    )
    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(
        default=True,
        help="An archived rule pays nothing and writes no ledger line.",
    )
    points = fields.Integer(
        help="Points of each beneficiary; a negative value is a penalty."
    )
    beneficiaries = fields.Selection(
        [
            ("both", "Both parties"),
            ("author", "Author of the reflection"),
            ("none", "Nobody"),
        ],
        required=True,
        default="both",
    )
    daily_cap = fields.Integer(
        string="Daily cap",
        help="Paid lines per member over 24 hours; 0 for no cap.",
    )
    weekly_cap = fields.Integer(
        string="Weekly cap",
        help="Paid lines per member over 7 days; 0 for no cap.",
    )
    pair_daily_cap = fields.Integer(
        string="Daily cap of the pair",
        help="Paid lines per member of a pair over 24 hours; 0 for no cap.",
    )
    pair_weekly_cap = fields.Integer(
        string="Weekly cap of the pair",
        help="Paid lines per member of a pair over 7 days; 0 for no cap.",
    )
    pair_lifetime_cap = fields.Integer(
        string="Lifetime cap of the pair",
        help="Paid lines per member of a pair, ever; 0 for no cap.",
    )
    cap_group = fields.Char(
        string="Cap group",
        help="Rules of the same group count their lines together against"
        " the caps.",
    )
    decay = fields.Boolean(
        help="Each repetition within a pair pays half of the previous one,"
        " until midnight of the member or a reset of the pair."
    )
    resets_decay = fields.Boolean(
        string="Resets the decay",
        help="A line of this rule starts the decreasing sequences of the"
        " pair again.",
    )

    _sql_constraints = [
        ("code_unique", "UNIQUE(code)", "A code names a single rule."),
        (
            "caps_positive",
            "CHECK(daily_cap >= 0 AND weekly_cap >= 0 AND pair_daily_cap >= 0"
            " AND pair_weekly_cap >= 0 AND pair_lifetime_cap >= 0)",
            "A cap is a number of lines, 0 meaning no cap.",
        ),
    ]

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    @api.model
    def _linkup_apply_event(
        self,
        code,
        users,
        link=None,
        reflet=None,
        channel=None,
        key=None,
        message=None,
    ):
        """Apply the rules of the event ``code`` to ``users``.

        ``reflet`` is the reflection that carries the event, or an empty
        recordset; ``key`` identifies an event that no reflection does, and
        defaults to ``reflet:<id>``. Return the ledger lines written, none
        for an event already recorded.
        """
        reflet = (reflet or self.env["linkup.reflet"]).sudo()
        link = (link or reflet.link_id).sudo()
        codes = EVENT_RULES.get(code, (code,))
        if not codes:
            return self.env["linkup.points.ledger"]
        # A rule archived by an administrator pays nothing, whatever the
        # context of the action that raises the event says.
        rules = (
            self.sudo()
            .with_context(active_test=True)
            .search([("code", "in", list(codes))])
        )
        targets = [
            (rule, user)
            for rule in rules.sorted(lambda rule: codes.index(rule.code))
            for user in rule._linkup_beneficiaries(users, reflet)
        ]
        if not targets:
            return self.env["linkup.points.ledger"]
        event_key = key or (reflet and f"reflet:{reflet.id}")
        if not event_key:
            raise ValueError(f"The event {code} has no key.")
        return (
            self.env["linkup.points.ledger"]
            .sudo()
            ._linkup_record(
                targets,
                event_key,
                link=link,
                reflet=reflet,
                channel=channel or reflet.channel_id,
                message=message or reflet.message_id,
            )
        )

    def _linkup_beneficiaries(self, users, reflet):
        """The members of ``users`` this rule pays."""
        self.ensure_one()
        if self.beneficiaries == "none":
            return users.browse()
        if self.beneficiaries == "author" and reflet:
            return users.filtered(lambda user: user == reflet.author_id)
        return users

    # ------------------------------------------------------------------
    # Value of a line
    # ------------------------------------------------------------------

    def _linkup_line(self, user, link, now):
        """The values of a new line of this rule for ``user`` in ``link``:
        its ``points``, the ``cap_reason`` that leaves it at 0 or
        ``False``, whether it ``resets_decay``, and the ``decay_day`` of
        its sequence for a rule with ``decay``.

        The caller holds the lock of ``user``, so the lines counted here do
        not change before the new one is written.

        A rule that resets the decay does so within its caps of 24 hours
        and 7 days, which count the lines that reset as they count the lines
        that pay; the lifetime cap of the pair bounds its points only. A
        confirmation after the first link of a pair thus pays nothing and
        still starts the sequences again, no more often than a paid one,
        and a call beyond the cap of the pair starts nothing again. An
        account that earns no points resets nothing either.
        """
        self.ensure_one()
        line = {
            "points": self.points,
            "cap_reason": False,
            "resets_decay": False,
            "decay_day": False,
        }
        if self.points <= 0:
            return line
        reason = user._linkup_points_ineligibility()
        if reason:
            return dict(line, points=0, cap_reason=reason)
        if self.decay and link:
            line["decay_day"] = self._linkup_decay_day(user, link, now)
        resets = bool(self.resets_decay and link)
        for field, window, by_pair in CAPS:
            cap = self[field]
            if not cap or (by_pair and not link):
                continue
            since = window and now - window
            scope = link if by_pair else None
            if not reason and self._linkup_count(user, since, scope) >= cap:
                reason = field
            if (
                resets
                and window
                and self._linkup_count(user, since, scope, resets=True) >= cap
            ):
                resets = False
        line["resets_decay"] = resets
        if reason:
            return dict(line, points=0, cap_reason=reason)
        if line["decay_day"]:
            index = self._linkup_decay_index(user, link, line["decay_day"])
            value = self._linkup_decay_value(index)
            if value <= 0:
                return dict(line, points=0, cap_reason="decay")
            line["points"] = value
        return line

    def _linkup_cap_rules(self):
        """This rule and the rules that share its caps."""
        self.ensure_one()
        if not self.cap_group:
            return self
        return self | self.with_context(active_test=False).search(
            [("cap_group", "=", self.cap_group)]
        )

    def _linkup_count(self, user, since=None, link=None, resets=False):
        """Lines of the caps of this rule that paid ``user``, or that reset
        the decay with ``resets``."""
        domain = [
            ("user_id", "=", user.id),
            ("rule_id", "in", self._linkup_cap_rules().ids),
            ("resets_decay", "=", True) if resets else ("capped", "=", False),
        ]
        if since:
            domain.append(("date", ">", since))
        if link:
            domain.append(("link_id", "=", link.id))
        return self.env["linkup.points.ledger"].sudo().search_count(domain)

    def _linkup_decay_day(self, user, link, now):
        """The day of the sequence of ``user`` in ``link`` that a line at
        ``now`` joins, as the naive UTC datetime of its midnight.

        It is midnight in the time zone of the member, unless the day of
        their last line of this rule started less than ``SHORTEST_DAY``
        before: that day goes on. A member who changes time zone thus
        starts no sequence again before the next midnight of the zone they
        left, give or take an hour.
        """
        day = user._linkup_day_start(now)
        last = (
            self.env["linkup.points.ledger"]
            .sudo()
            .search(
                [
                    ("user_id", "=", user.id),
                    ("link_id", "=", link.id),
                    ("rule_id", "=", self.id),
                    ("decay_day", "!=", False),
                ],
                order="id desc",
                limit=1,
            )
        )
        if last and day < last.decay_day + SHORTEST_DAY:
            return last.decay_day
        return day

    def _linkup_decay_index(self, user, link, day):
        """The rank, from 0, of the next action of the sequence of ``user``
        in ``link``: their lines of this rule of ``day``, after their last
        line of the pair that reset the decay."""
        Ledger = self.env["linkup.points.ledger"].sudo()
        reset = Ledger.search(
            [
                ("user_id", "=", user.id),
                ("link_id", "=", link.id),
                ("resets_decay", "=", True),
            ],
            order="id desc",
            limit=1,
        )
        domain = [
            ("user_id", "=", user.id),
            ("link_id", "=", link.id),
            ("rule_id", "=", self.id),
            ("decay_day", "=", day),
        ]
        if reset:
            domain.append(("id", ">", reset.id))
        return Ledger.search_count(domain)

    def _linkup_decay_value(self, index):
        """The value of the action at ``index`` (from 0) of a sequence.

        ``virtual_round`` reads its sequence from the parameter
        ``linkup.virtual_round_points``, a list of integers separated by
        commas, when it is set; past its end, a round pays 0.
        """
        self.ensure_one()
        if self.code == VIRTUAL_ROUND:
            sequence = self._linkup_round_sequence()
            if sequence:
                return sequence[index] if index < len(sequence) else 0
        value = self.points
        for _step in range(index):
            value //= 2
        return value

    @api.model
    def _linkup_round_sequence(self):
        """The integers of ``linkup.virtual_round_points``, or ``None``
        when it is unset or invalid."""
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(VIRTUAL_ROUND_PARAM)
        )
        try:
            sequence = [int(item) for item in (value or "").split(",")]
        except ValueError:
            return None
        return sequence if value and all(n >= 0 for n in sequence) else None
