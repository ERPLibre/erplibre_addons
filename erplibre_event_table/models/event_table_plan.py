# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# A locked plan accepts these fields anyway: they carry the discussion
# attached to the record, not the record's own data. Locking freezes the
# seating, never the ability to write a note about it or to follow it.
MAIL_FIELDS = {
    "message_ids",
    "message_follower_ids",
    "message_main_attachment_id",
    "activity_ids",
}


class EventTablePlan(models.Model):
    _name = "event.table.plan"
    _description = "Rotating Table Plan"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(
        required=True,
        default=lambda self: _("Rotating Tables"),
        tracking=True,
    )
    event_id = fields.Many2one(
        "event.event",
        required=True,
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        related="event_id.company_id", store=True, index=True
    )
    # draft, proposed and chosen order the work without restricting it,
    # and the operator sets them by clicking the status bar. Only locked
    # has teeth. It is absent from the bar's always-visible list, so it
    # shows up solely when it is the current state, and the field turns
    # readonly then: the two buttons are the only way in and out.
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("proposed", "Proposed"),
            ("chosen", "Chosen"),
            ("locked", "Locked"),
        ],
        default="draft",
        required=True,
        copy=False,
        tracking=True,
    )
    round_count = fields.Integer(
        string="Rounds", default=3, required=True, tracking=True
    )
    combination_count = fields.Integer(
        string="Combinations to Propose", default=3, required=True
    )
    separate_companies = fields.Boolean(
        string="Separate Colleagues",
        default=True,
        tracking=True,
        help="Do not seat two people from the same company at the same"
        " table.",
    )
    avoid_repeat_neighbors = fields.Boolean(
        string="New Neighbours Each Round",
        default=True,
        tracking=True,
        help="Two people who already shared a table are not seated"
        " together again.",
    )
    avoid_repeat_table = fields.Boolean(
        string="New Table Each Round",
        default=False,
        tracking=True,
        help="A person does not return to a table where they already sat.",
    )
    assign_seats = fields.Boolean(
        string="Assign Seats",
        default=False,
        tracking=True,
        help="Give each person a seat number. Otherwise people choose"
        " where to sit at their table.",
    )
    show_seat_number = fields.Boolean(
        string="Show Seat Numbers", default=False
    )
    show_company = fields.Boolean(string="Show Company", default=False)
    show_full_names = fields.Boolean(
        string="Show Full Names",
        default=False,
        help="Let a long name wrap onto a second line in the list beside"
        " each table, instead of cutting it at the column's width. The"
        " column always widens; the extra height is reserved only where"
        " a name is long enough to need that second line. Rearranging"
        " the tables spaces them for whichever room the plan reserved.",
    )
    visual_tables = fields.Boolean(string="Visual Tables", default=False)
    table_ids = fields.One2many(
        "event.table", "plan_id", string="Tables", copy=True
    )
    participant_ids = fields.One2many(
        "event.table.participant", "plan_id", string="Participants", copy=True
    )
    combination_ids = fields.One2many(
        "event.table.combination", "plan_id", string="Combinations", copy=False
    )
    chosen_combination_id = fields.Many2one(
        "event.table.combination",
        string="Chosen Combination",
        readonly=True,
        copy=False,
    )
    assignment_ids = fields.One2many(
        "event.table.assignment", "plan_id", string="Assignments", copy=False
    )
    # copy=False, and copy() below repoints them instead: the ORM would
    # hand the duplicate rows still naming THIS plan's table and
    # participant, while the duplicate has clones of its own.
    pin_ids = fields.One2many(
        "event.table.pin", "plan_id", string="Pins", copy=False
    )
    table_count = fields.Integer(compute="_compute_capacity")
    seat_count = fields.Integer(compute="_compute_capacity")
    participant_count = fields.Integer(compute="_compute_capacity")
    seat_balance = fields.Integer(compute="_compute_capacity")
    unseated_count = fields.Integer(compute="_compute_capacity")
    capacity_message = fields.Char(compute="_compute_capacity")
    sync_message = fields.Char(compute="_compute_sync_message")
    placement_message = fields.Char(compute="_compute_placement_message")
    has_assignments = fields.Boolean(compute="_compute_has_assignments")
    unplaced_count = fields.Integer(compute="_compute_placement_message")
    pin_count = fields.Integer(compute="_compute_placement_message")
    diagnostic_message = fields.Text(compute="_compute_diagnostic_message")
    generation_seed = fields.Integer(readonly=True, copy=False)
    generation_duration = fields.Float(
        string="Generation Time (seconds)", readonly=True, copy=False
    )

    _sql_constraints = [
        (
            "round_count_range",
            "CHECK(round_count >= 1 AND round_count <= 50)",
            "A plan has between 1 and 50 rounds.",
        ),
        (
            "combination_count_range",
            "CHECK(combination_count >= 1 AND combination_count <= 10)",
            "A plan proposes between 1 and 10 combinations.",
        ),
    ]

    @api.depends(
        "table_ids",
        "table_ids.seat_count",
        "participant_ids",
        "participant_ids.excluded",
        "state",
        "assignment_ids",
        "assignment_ids.participant_id",
    )
    def _compute_capacity(self):
        for plan in self:
            plan.table_count = len(plan.table_ids)
            plan.seat_count = sum(plan.table_ids.mapped("seat_count"))
            included = plan._included_participants()
            plan.participant_count = len(included)
            # Counted in EVERY state, never only once a combination is
            # chosen. Assignments exist only from that point on, so before
            # it the count is simply everyone included — which is the
            # truth: nobody has a seat yet. Reporting 0 there said the
            # opposite, and contradicted the rounds the same record hands
            # the screen (get_floor_plan_data), where the very same people
            # are listed as waiting.
            seated = set(plan.assignment_ids.participant_id.ids)
            plan.unseated_count = len(
                [p for p in included if p.id not in seated]
            )
            plan.seat_balance = plan.seat_count - plan.participant_count
            if plan.seat_balance < 0:
                plan.capacity_message = _(
                    "Participants: %(persons)s. Seats: %(seats)s."
                    " Missing: %(missing)s.",
                    persons=plan.participant_count,
                    seats=plan.seat_count,
                    missing=-plan.seat_balance,
                )
            elif plan.seat_balance == 0:
                plan.capacity_message = _(
                    "Participants: %(persons)s. Seats: %(seats)s."
                    " Every seat is taken.",
                    persons=plan.participant_count,
                    seats=plan.seat_count,
                )
            else:
                plan.capacity_message = _(
                    "Participants: %(persons)s. Seats: %(seats)s."
                    " Free: %(free)s.",
                    persons=plan.participant_count,
                    seats=plan.seat_count,
                    free=plan.seat_balance,
                )

    @api.depends("assignment_ids", "unseated_count")
    def _compute_sync_message(self):
        # The warning hangs on the DATA, not on a state: a plan that
        # seats people and no longer covers all of them has drifted,
        # whichever label it currently wears. It never blocks; the
        # remedy is the operator's to choose.
        for plan in self:
            if plan.assignment_ids and plan.unseated_count:
                plan.sync_message = _(
                    "The plan no longer matches its participants. Not"
                    " seated: %(unseated)s.",
                    unseated=plan.unseated_count,
                )
            else:
                plan.sync_message = False

    @api.depends("assignment_ids")
    def _compute_has_assignments(self):
        # Printing, mailing and moving someone all hang on this rather
        # than on a state: a plan seats people once a combination is
        # chosen, and equally once they are placed by hand.
        for plan in self:
            plan.has_assignments = bool(plan.assignment_ids)

    @api.depends("participant_ids.excluded", "assignment_ids", "pin_ids")
    def _compute_placement_message(self):
        """Count who has no seat anywhere, by hand or by machine.

        A participant counts as placed once a pin or an assignment names
        them in any round. The figure is what the operator needs before
        turning a hand-made placement into a combination: it says how
        many people the generator would seat around the ones already
        set. It is stated in its own colour on the form, apart from the
        capacity and drift warnings, because it reports work left to do
        rather than something amiss.
        """
        for plan in self:
            placed = set(plan.assignment_ids.participant_id.ids) | set(
                plan.pin_ids.participant_id.ids
            )
            plan.pin_count = len(plan.pin_ids)
            plan.unplaced_count = len(
                [
                    p
                    for p in plan._included_participants()
                    if p.id not in placed
                ]
            )
            if plan.state != "locked" and plan.unplaced_count:
                plan.placement_message = _(
                    "%(count)s participant(s) still to place.",
                    count=plan.unplaced_count,
                )
            else:
                plan.placement_message = False

    def _included_participants(self):
        self.ensure_one()
        # During an onchange, a line never written to the database carries a
        # NewId, and Python cannot order two of them: sorting on p.id would
        # raise TypeError before the record is saved. p._origin.id falls
        # back to a saved line's real id, and to False for one that has
        # none yet, so every unsaved line compares equal and a stable sort
        # leaves them in the order the user added them.
        return self.participant_ids.filtered(lambda p: not p.excluded).sorted(
            key=lambda p: p._origin.id
        )

    def _add_registrations(self, registrations):
        self.ensure_one()
        seen = set()
        known_registration_ids = set()
        for participant in self.participant_ids:
            if participant.partner_id:
                seen.add(("p", participant.partner_id.id))
            elif (participant.email or "").strip():
                seen.add(("e", participant.email.strip().lower()))
            elif (participant.name or "").strip():
                seen.add(("n", participant.name.strip().lower()))
            if participant.registration_id:
                known_registration_ids.add(participant.registration_id.id)
        created = 0
        merged = 0
        vals_list = []
        for registration in registrations:
            if registration.id in known_registration_ids:
                continue
            stripped_email = (registration.email or "").strip().lower()
            stripped_name = (registration.name or "").strip().lower()
            if registration.partner_id:
                key = ("p", registration.partner_id.id)
            elif stripped_email:
                key = ("e", stripped_email)
            elif stripped_name:
                key = ("n", stripped_name)
            else:
                key = ("i", registration.id)
            if key in seen:
                merged += 1
                continue
            seen.add(key)
            created += 1
            vals_list.append(
                {
                    "plan_id": self.id,
                    "name": registration.name
                    or registration.partner_id.name
                    or _("Guest"),
                    "email": registration.email
                    or registration.partner_id.email
                    or False,
                    "partner_id": registration.partner_id.id or False,
                    "registration_id": registration.id,
                }
            )
        if vals_list:
            self.env["event.table.participant"].create(vals_list)
        return created, merged

    def _add_partners(self, partners):
        self.ensure_one()
        known_partner_ids = set(self.participant_ids.partner_id.ids)
        new_partners = partners.filtered(
            lambda p: p.id not in known_partner_ids
        )
        if new_partners:
            self.env["event.table.participant"].create(
                [
                    {
                        "plan_id": self.id,
                        "name": partner.name,
                        "email": partner.email or False,
                        "partner_id": partner.id,
                    }
                    for partner in new_partners
                ]
            )
        return len(new_partners)

    def _check_not_locked(self):
        """Refuse every change to a locked plan.

        Locking is the one state that forbids a write, and it forbids
        all of them: rounds, options, tables, participants and the
        position of a table on the screen alike. A locked plan is a
        document that has been printed and mailed, so a bad layout is
        cured by unlocking, arranging and locking again rather than by
        an exemption carved out here. Reading, printing and sending
        stay open, since none of them writes.

        This is the module's single write guard. event.table,
        event.table.participant and the configure wizard all call it
        rather than testing a state of their own, so the rule is stated
        once and cannot drift between models.
        """
        for plan in self:
            if plan.state == "locked":
                raise UserError(
                    _(
                        "This plan is locked. Unlock it before changing"
                        " anything."
                    )
                )

    def write(self, vals):
        # Unlocking is the one write a locked plan accepts, and a
        # context key marks it rather than the shape of vals: an
        # ordinary write that happens to carry the state field cannot
        # then pass for it.
        if not self.env.context.get("event_table_unlock") and (
            set(vals) - MAIL_FIELDS
        ):
            self._check_not_locked()
        return super().write(vals)

    def unlink(self):
        self._check_not_locked()
        return super().unlink()

    def action_lock(self):
        """Freeze the plan. The status bar cannot undo this; the button can."""
        self._check_not_locked()
        self.write({"state": "locked"})
        self.message_post(body=_("Plan locked: no change is accepted."))

    def action_unlock(self):
        """Thaw the plan, returning it to the state that fits its data."""
        for plan in self:
            if plan.state != "locked":
                continue
            if plan.chosen_combination_id or plan.assignment_ids:
                restored = "chosen"
            elif plan.combination_ids:
                restored = "proposed"
            else:
                restored = "draft"
            plan.with_context(event_table_unlock=True).write(
                {"state": restored}
            )
            plan.message_post(body=_("Plan unlocked."))

    def copy(self, default=None):
        """Duplicate the plan and carry its pins over, re-aimed.

        Tables and participants are copied fields, so every pin has a
        twin to point at in the duplicate. A pin whose participant
        cannot be told apart from a namesake is left behind, and the
        duplicate's chatter says how many, so a missing reservation is
        read rather than discovered at the door.

        The chatter of the duplicate also names the plan it comes from.
        It is posted here and not in an action so that every path that
        duplicates a plan carries it: the form's Duplicate menu item, a
        programmatic copy, a wizard.
        """
        duplicates = super().copy(default)
        pins = self.env["event.table.pin"]
        for source, duplicate in zip(self, duplicates):
            duplicate.message_post(
                body=_(
                    "Plan duplicated from %(plan_name)s.",
                    plan_name=source.display_name,
                )
            )
            carried, dropped = pins._clone_plan_pins(source, duplicate)
            if dropped:
                duplicate.message_post(
                    body=_(
                        "Pins carried over: %(carried)s. Left behind for"
                        " want of an identifiable participant:"
                        " %(dropped)s.",
                        carried=carried,
                        dropped=dropped,
                    )
                )
        return duplicates

    def _lock(self):
        self.ensure_one()
        self.env.cr.execute(
            "SELECT id FROM event_table_plan WHERE id = %s FOR UPDATE",
            [self.id],
        )
        self.invalidate_recordset()

    def _search_time_budget(self):
        self.ensure_one()
        parameter = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("erplibre_event_table.search_time_budget", "10")
        )
        try:
            budget = float(parameter)
        except (TypeError, ValueError):
            # A system parameter is typed by hand and can hold anything:
            # without this fallback, a mistyped value would fail generation
            # on an unreadable ValueError instead of using the default.
            budget = 10.0
        return min(45.0, max(1.0, budget))
