# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import random
import time
from dataclasses import replace

from odoo import _, api, models
from odoo.exceptions import UserError

from ..rotation import (
    Options,
    Person,
    Placement,
    Problem,
    Table,
    assign_seats,
    distance,
    evaluate,
    generate,
    precheck,
)
from .pin_reconcile import (
    PinReconcileError,
    PinRequest,
    improve,
    reconcile,
)


class EventTablePlanGeneration(models.Model):
    """The bridge to the pure rotation package, and what it produces.

    Split from event_table_plan.py, which holds the model itself. Here a
    plan is translated into the terms rotation/ works in — a Problem,
    Options, Persons and Tables — the search is run, and what comes back
    is turned into event.table.combination rows, ranked and diagnosed.
    Nothing here draws anything; where a person ends up on screen is
    event_table_plan_placement.py.
    """

    _inherit = "event.table.plan"

    def _rotation_problem(self):
        self.ensure_one()
        return Problem(
            persons=tuple(
                # Person.key is typed int: an unsaved onchange line has a
                # NewId here too, and the library sorts persons by this key
                # (rotation/bounds.py, _company_sizes). p._origin.id gives
                # the real id once the plan is saved, which is the only
                # time this key is reused as a participant id downstream;
                # before that, several unsaved lines sharing 0 only affect
                # the tie-break order of a live diagnostic preview.
                Person(key=p._origin.id, company=p.company_key or None)
                for p in self._included_participants()
            ),
            tables=tuple(
                Table(number=t.number, capacity=t.seat_count)
                for t in self.table_ids.sorted("number")
            ),
            rounds=self.round_count,
        )

    def _rotation_options(self):
        self.ensure_one()
        return Options(
            separate_companies=self.separate_companies,
            avoid_repeat_neighbors=self.avoid_repeat_neighbors,
            avoid_repeat_table=self.avoid_repeat_table,
            assign_seats=self.assign_seats,
        )

    def _combination_placements(self, combination):
        """Placements as the generator wrote them, for a preview or a choice."""
        self.ensure_one()
        return tuple(
            Placement(round=row[0], person=row[1], table=row[2], seat=row[3])
            for row in combination.placement_data or []
        )

    def _assignment_placements(self):
        """Placements as the assignment lines stand now, hand edits included."""
        self.ensure_one()
        return tuple(
            Placement(
                round=line.round_number,
                person=line.participant_id.id,
                table=line.table_number,
                seat=line.seat_number,
            )
            for line in self.assignment_ids
        )

    def _pin_placements(self):
        """Pins as placements, so hand work draws like a real seating.

        Before a combination exists the plan has no assignment, and the
        floor plan would show an empty room while the operator fills it.
        A pin carries the same four terms an assignment does, so the
        component draws one without knowing the difference; what differs
        is only which record the next gesture writes.
        """
        self.ensure_one()
        return tuple(
            Placement(
                round=pin.round_number,
                person=pin.participant_id.id,
                table=pin.table_id.number,
                seat=pin.seat_number or 0,
            )
            for pin in self.pin_ids
        )

    def _plan_pins(self):
        """The plan's pins in the terms the placements are written in.

        A pin names an event.table and an event.table.participant; the
        placements name a table NUMBER and a participant id, which is
        also Person.key in _rotation_problem.
        """
        self.ensure_one()
        return tuple(
            PinRequest(
                round=pin.round_number,
                person=pin.participant_id.id,
                table=pin.table_id.number,
            )
            for pin in self.pin_ids
        )

    def _pin_error_message(self, error):
        """One sentence for a pin no seating can hold.

        The reconciliation works on keys and numbers and raises a code;
        this is the layer that owns the wording and can read a
        participant's name back off the key.
        """
        self.ensure_one()
        params = dict(error.params)
        if "person" in params:
            params["name"] = (
                self.env["event.table.participant"]
                .browse(params["person"])
                .display_name
            )
        if error.code == "two_tables":
            return _(
                "%(name)s is pinned to two different tables in round"
                " %(round)s. Keep one of the two pins.",
                **params,
            )
        if error.code == "round_absent":
            return _(
                "%(name)s is pinned in round %(round)s, and this plan has"
                " %(count)s rounds. Remove that pin or add rounds.",
                count=self.round_count,
                **params,
            )
        if error.code == "person_absent":
            return _(
                "%(name)s is pinned in round %(round)s but is seated"
                " nowhere in it. Remove the pin, or put the participant"
                " back in the plan.",
                **params,
            )
        if error.code == "table_absent":
            return _(
                "Table %(table)s seats nobody in round %(round)s, so"
                " %(name)s cannot be pinned to it.",
                **params,
            )
        return _(
            "%(pinned)s people are pinned to table %(table)s in round"
            " %(round)s, which seats %(seats)s of them there. Remove"
            " pins, or make the table bigger.",
            **params,
        )

    def _honour_pins(self, problem, options, combination, pins):
        """Return this combination rearranged to hold every pin.

        Three passes over the generated placements: reconcile() puts
        each pinned person at their table by rearranging the occupants
        of that round, improve() wins back part of what that costs by
        swapping non-pinned people only, and evaluate() measures the
        result from scratch. Each pass conserves the number of people
        seated at every (round, table), so the seating pass still
        accepts the placements and lower_bound still bounds them -
        which is why it is carried over untouched while proven_optimal,
        a comparison against it, is decided again.

        A pin holds a TABLE. event.table.pin's seat_number states a
        wish the seating pass cannot be told to grant, and nothing here
        reads it.
        """
        self.ensure_one()
        placements = reconcile(combination.placements, pins)
        placements = improve(
            problem,
            placements,
            pins,
            options,
            # The budget bounds ONE candidate, and a generation repairs
            # combination_count of them, so it stays well under the
            # search budget the generator itself was given.
            time_budget=min(2.0, self._search_time_budget()),
        )
        if options.assign_seats:
            placements = assign_seats(
                problem, placements, options, seed=int(combination.seed)
            )
        indicators = evaluate(problem, placements, options)
        return replace(
            combination,
            placements=placements,
            indicators=indicators,
            proven_optimal=indicators.cost <= combination.lower_bound,
        )

    def _reconciled_combinations(self, problem, options, combinations, pins):
        """Hold the pins in every candidate, then re-measure diversity.

        distance_to_first compares a candidate to the FIRST one, so it
        is recomputed once all of them have been rearranged rather than
        candidate by candidate. close_variant is left as the draw set
        it: it records the verdict that CHOSE these candidates, and no
        selection is run again here.
        """
        self.ensure_one()
        held = [
            self._honour_pins(problem, options, combination, pins)
            for combination in combinations
        ]
        if not held:
            return tuple(held)
        first = held[0].placements
        return tuple(
            replace(
                combination,
                distance_to_first=(
                    0.0
                    if not index
                    else distance(first, combination.placements)
                ),
            )
            for index, combination in enumerate(held)
        )

    def _recompute_chosen_indicators(self):
        """Measure the chosen combination from the lines that stand now.

        A hand edit can break the even occupancy the generator produced,
        so every indicator is recomputed from scratch rather than patched
        incrementally, and placement_data is rewritten to match: the
        combination record always describes what is actually seated.
        """
        self.ensure_one()
        combination = self.chosen_combination_id
        if not combination:
            return
        placements = self._assignment_placements()
        indicators = evaluate(
            self._rotation_problem(), placements, self._rotation_options()
        )
        combination.write(
            {
                "placement_data": [
                    [p.round, p.person, p.table, p.seat]
                    for p in sorted(
                        placements,
                        key=lambda p: (p.round, p.table, p.seat, p.person),
                    )
                ],
                "company_pair_count": indicators.company_pairs,
                "repeated_pair_count": indicators.repeated_pairs,
                "extra_meeting_count": indicators.extra_meetings,
                "max_pair_meetings": indicators.max_pair_meetings,
                "table_return_count": indicators.table_returns,
                "met_distinct_min": indicators.met_distinct_min,
                "met_distinct_avg": indicators.met_distinct_avg,
                "cost": indicators.cost,
                "is_adjusted": True,
            }
        )

    def _company_labels(self):
        """Normalized company key -> first label met, to name a diagnostic."""
        self.ensure_one()
        labels = {}
        for participant in self._included_participants():
            key = participant.company_key
            if key and key not in labels:
                labels[key] = participant.company_label
        return labels

    def _diagnostic_message_text(self, diagnostic):
        self.ensure_one()
        params = dict(diagnostic.params, minimum=diagnostic.minimum)
        code = diagnostic.code
        if code == "no_tables":
            return _("Configure the tables first.")
        if code == "too_few_participants":
            return _("At least 2 participants are needed.")
        if code == "capacity_short":
            return "%s %s" % (
                _(
                    "Participants: %(persons)s. Seats: %(seats)s."
                    " Missing: %(missing)s.",
                    **params,
                ),
                _("Add tables or seats."),
            )
        if code == "company_exceeds_tables":
            # params["company"] is the normalized key; the manager reads the
            # label they typed.
            params["company"] = self._company_labels().get(
                params.get("company"), params.get("company")
            )
            return _(
                "%(company)s has %(members)s participants for %(tables)s open"
                " tables. Colleague pairs that cannot be avoided: %(minimum)s.",
                **params,
            )
        if code == "pairs_exhausted":
            return _(
                "Too many rounds for these table sizes. Repeated meetings"
                " that cannot be avoided: %(minimum)s.",
                **params,
            )
        if code == "tables_too_full":
            if self.avoid_repeat_table:
                return _(
                    "Tables too full for this number of tables. Repeated"
                    " meetings or table returns that cannot be avoided:"
                    " %(minimum)s.",
                    **params,
                )
            return _(
                "Tables too full for this number of tables. Repeated meetings"
                " that cannot be avoided: %(minimum)s.",
                **params,
            )
        if code == "rounds_exceed_tables":
            return _(
                "More rounds (%(rounds)s) than open tables (%(tables)s)."
                " Table returns that cannot be avoided: %(minimum)s.",
                **params,
            )
        if code == "tight":
            return _(
                "This configuration is tight: with %(suggested_tables)s"
                " tables an algebraic plan applies and usually avoids every"
                " conflict.",
                **params,
            )
        if code == "fewer_combinations":
            return _(
                "Distinct combinations found: %(count)s of %(requested)s"
                " requested.",
                **params,
            )
        return ""

    @api.depends(
        "round_count",
        "separate_companies",
        "avoid_repeat_neighbors",
        "avoid_repeat_table",
        "table_ids",
        "table_ids.seat_count",
        "participant_ids",
        "participant_ids.excluded",
        "participant_ids.company_key",
        "participant_ids.company_label",
    )
    def _compute_diagnostic_message(self):
        """Recompute the diagnostics on every read instead of storing them.

        A stored value would go stale the moment a table, a round or a
        participant changes without a new generation; recomputing keeps
        the banner honest at the cost of running precheck on every read.
        """
        for plan in self:
            # precheck returns (lower bound, diagnostics, targets).
            diagnostics = precheck(
                plan._rotation_problem(), plan._rotation_options()
            )[1]
            plan.diagnostic_message = "\n".join(
                plan._diagnostic_message_text(d) for d in diagnostics
            )

    def _rerank_combinations(self):
        """Number every combination of the plan on one scale, best first.

        Generations accumulate, so each run would otherwise hand out
        ranks that mean nothing next to the previous run's. Renumbering
        the whole set by cost after every change keeps rank comparable
        across runs, which is the only thing an operator reads it for.
        """
        self.ensure_one()
        ordered = self.combination_ids.sorted(key=lambda c: (c.cost, c.id))
        for position, combination in enumerate(ordered, start=1):
            if combination.rank != position:
                combination.rank = position

    def action_clear_combinations(self):
        """Delete every combination except the chosen one.

        Generations accumulate, so pruning the list is the operator's
        move. The chosen one survives: the assignments standing in the
        world were drawn from it, and its own unlink guard refuses to
        let it go while the plan still points at it.
        """
        self.ensure_one()
        self._check_not_locked()
        doomed = self.combination_ids - self.chosen_combination_id
        count = len(doomed)
        doomed.unlink()
        self._rerank_combinations()
        self.message_post(
            body=_("Combinations cleared: %(count)s deleted.", count=count)
        )

    def action_request_generation(self):
        """Ask what to do with the pins, or generate straight away.

        The question only exists when the plan carries pins; with none,
        this runs exactly the generation the button has always run.
        Returning a window action is confined to THIS method on purpose:
        action_generate_combinations stays callable from a data file and
        from any other code, where an action to display would be
        dropped and the generation silently skipped.
        """
        self.ensure_one()
        if not self.pin_ids:
            return self.action_generate_combinations()
        return {
            "type": "ir.actions.act_window",
            "res_model": "event.table.pin.generate.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_plan_id": self.id},
        }

    def action_generate_combinations(self, honour_pins=True):
        """Generate the combinations, holding the plan's pins by default.

        honour_pins False starts from zero: the pins are left on the
        plan and ignored for this generation, which is what "start over"
        means on the question action_request_generation asks. A plan
        without a pin takes the same path either way.
        """
        self.ensure_one()
        self._check_not_locked()
        self._lock()
        problem = self._rotation_problem()
        options = self._rotation_options()
        seed = random.SystemRandom().randrange(1, 2**31 - 1)
        started = time.monotonic()
        generation = generate(
            problem,
            options,
            count=self.combination_count,
            seed=seed,
            time_budget=self._search_time_budget(),
        )
        duration = time.monotonic() - started
        blocking = [
            d for d in generation.diagnostics if d.severity == "blocking"
        ]
        if blocking:
            raise UserError(
                "\n".join(self._diagnostic_message_text(d) for d in blocking)
            )
        pins = self._plan_pins() if honour_pins else ()
        if pins:
            try:
                candidates = self._reconciled_combinations(
                    problem, options, generation.combinations, pins
                )
            except PinReconcileError as error:
                raise UserError(self._pin_error_message(error)) from error
        else:
            candidates = generation.combinations
        # Generations ACCUMULATE: a run adds its candidates to the ones
        # already on the plan instead of replacing them, so an operator
        # can compare the fruit of several settings side by side. The
        # offset keeps the create from colliding with a rank already
        # handed out; _rerank_combinations then renumbers the whole set
        # on one scale. Pruning the list is action_clear_combinations.
        offset = len(self.combination_ids)
        self.env["event.table.combination"].create(
            [
                {
                    "plan_id": self.id,
                    "rank": rank,
                    "placement_data": [
                        [p.round, p.person, p.table, p.seat]
                        for p in sorted(
                            candidate.placements,
                            key=lambda p: (p.round, p.table, p.seat, p.person),
                        )
                    ],
                    "company_pair_count": candidate.indicators.company_pairs,
                    "repeated_pair_count": candidate.indicators.repeated_pairs,
                    "extra_meeting_count": candidate.indicators.extra_meetings,
                    "max_pair_meetings": candidate.indicators.max_pair_meetings,
                    "table_return_count": candidate.indicators.table_returns,
                    "met_distinct_min": candidate.indicators.met_distinct_min,
                    "met_distinct_avg": candidate.indicators.met_distinct_avg,
                    "cost": candidate.indicators.cost,
                    "lower_bound": candidate.lower_bound,
                    "seed": candidate.seed,
                    "distance_to_first": candidate.distance_to_first,
                    "is_proven_optimal": candidate.proven_optimal,
                    "is_close_variant": candidate.close_variant,
                    "is_adjusted": False,
                    "is_pin_constrained": bool(pins),
                    "method": candidate.method,
                    "stopped_by": candidate.stopped_by,
                }
                for rank, candidate in enumerate(candidates, start=offset + 1)
            ]
        )
        # A plan already running on a chosen combination keeps its
        # state: a further generation adds candidates beside the choice
        # rather than quietly undoing it.
        values = {
            "generation_seed": seed,
            "generation_duration": duration,
        }
        if not self.chosen_combination_id:
            values["state"] = "proposed"
        self._rerank_combinations()
        self.write(values)
        lines = [
            _(
                "Combinations generated: %(count)s, in %(seconds)s s.",
                count=len(candidates),
                seconds=round(duration, 1),
            )
        ]
        if pins:
            lines.append(
                _(
                    "%(count)s reserved places held. A pin reserves a"
                    " table, not a seat: seat numbers are recomputed for"
                    " the whole table.",
                    count=len(pins),
                )
            )
        lines += [
            self._diagnostic_message_text(d)
            for d in generation.diagnostics
            if d.code == "fewer_combinations"
        ]
        first = candidates[0]
        lines.append(
            _(
                "Seed: %(seed)s. Method: %(method)s. Stopped by: %(stopped)s.",
                seed=seed,
                method=first.method,
                stopped=first.stopped_by,
            )
        )
        self.message_post(body="<br/>".join(lines))
