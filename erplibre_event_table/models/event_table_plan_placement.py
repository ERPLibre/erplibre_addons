# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import math

from odoo import _, models
from odoo.exceptions import UserError

from ..rotation import table_conflicts
from .event_table import (
    CONNECTOR_WIDTH,
    GRID_GAP_X,
    GRID_MARGIN,
    SEAT_RING,
    TABLE_SIZE,
    list_label_length,
    list_reserved_height,
    list_width,
    list_wraps_to_two_lines,
    visual_table_size,
)


class EventTablePlanPlacement(models.Model):
    """Where each person sits, and where the floor plan draws them.

    Split from event_table_plan.py, which holds the model itself. Here
    someone is moved, swapped or taken off a table, a seat is reserved
    before any combination exists, the payload the Owl component reads
    is assembled, and the tables are laid out on a grid wide enough for
    the name lists beside them. What decides WHO sits where in the first
    place is event_table_plan_generation.py.
    """

    _inherit = "event.table.plan"

    def _check_table_capacity(self, round_number, tables):
        """Replay the capacity rule once, after a move has finished.

        The ORM constraint on event.table.assignment stands down under the
        write flag, because Odoo validates a Python constraint at the end
        of every write and a swap needs two: this call is the single
        explicit check that replaces it once both writes are in.
        """
        self.ensure_one()
        for table in tables:
            occupancy = self.env["event.table.assignment"].search_count(
                [
                    ("plan_id", "=", self.id),
                    ("round_number", "=", round_number),
                    ("table_id", "=", table.id),
                ]
            )
            if occupancy > table.seat_count:
                raise UserError(
                    _(
                        "Table %(table)s is full in round %(round)s. Drop"
                        " the person onto someone to swap them.",
                        table=table.number,
                        round=round_number,
                    )
                )

    def _move_pinned_participant(
        self,
        round_number,
        participant_id,
        table_id,
        seat_number=False,
        swap_participant_id=False,
    ):
        """Place, or swap, one participant by hand before any generation.

        Reserves a seat rather than seating anyone: the pin constrains
        the generation to come and outlives it. The rules the operator
        already knows hold unchanged — a table takes no more people than
        it has seats, and dropping someone onto someone else trades the
        two places.

        The swap goes through THREE writes because a seat is claimed
        once per table and round: moving either pin onto the other's
        seat while that other still holds it breaks the rule. Seat 0
        means "no seat" and is the one value the rule skips, so parking
        the mover there first opens the road for both.
        """
        self.ensure_one()
        round_number = int(round_number)
        if not 1 <= round_number <= self.round_count:
            raise UserError(
                _(
                    "Round %(round)s does not exist in this plan.",
                    round=round_number,
                )
            )
        participant = self.participant_ids.filtered(
            lambda p: p.id == int(participant_id)
        )
        if not participant:
            raise UserError(
                _(
                    "%(name)s does not take part in this plan.",
                    name=participant_id,
                )
            )
        table = self.table_ids.filtered(lambda t: t.id == int(table_id))
        if not table:
            raise UserError(
                _(
                    "Table %(table)s is not part of this plan.",
                    table=table_id,
                )
            )

        pins = self.pin_ids.filtered(lambda p: p.round_number == round_number)
        pin = pins.filtered(lambda p: p.participant_id == participant)
        occupants = pins.filtered(lambda p: p.table_id == table) - pin
        full = _(
            "Table %(table)s is full in round %(round)s. Drop the person"
            " onto someone to swap them.",
            table=table.number,
            round=round_number,
        )

        swap_pin = pins.browse()
        if swap_participant_id:
            swap_pin = occupants.filtered(
                lambda p: p.participant_id.id == int(swap_participant_id)
            )
            if not swap_pin:
                other = self.participant_ids.browse(int(swap_participant_id))
                raise UserError(
                    _(
                        "%(name)s is not at table %(table)s in round"
                        " %(round)s.",
                        name=other.name,
                        table=table.number,
                        round=round_number,
                    )
                )
        elif len(occupants) >= table.seat_count:
            raise UserError(full)

        seat = int(seat_number or 0)
        if self.assign_seats and not swap_pin:
            taken = set(occupants.mapped("seat_number"))
            if not seat:
                free = [
                    number
                    for number in range(1, table.seat_count + 1)
                    if number not in taken
                ]
                if not free:
                    raise UserError(full)
                seat = free[0]
            elif not 1 <= seat <= table.seat_count:
                raise UserError(
                    _(
                        "Table %(table)s has no seat %(seat)s.",
                        table=table.number,
                        seat=seat,
                    )
                )
            elif seat in taken:
                occupant = occupants.filtered(lambda p: p.seat_number == seat)
                raise UserError(
                    _(
                        "Seat %(seat)s at table %(table)s is taken by"
                        " %(name)s. Drop the person onto them to swap.",
                        seat=seat,
                        table=table.number,
                        name=occupant.participant_id.name,
                    )
                )

        if swap_pin:
            target = {
                "table_id": swap_pin.table_id.id,
                "seat_number": swap_pin.seat_number,
            }
            if pin:
                vacated = {
                    "table_id": pin.table_id.id,
                    "seat_number": pin.seat_number,
                }
                pin.seat_number = 0
                swap_pin.write(vacated)
            else:
                # The mover holds no pin in this round, so the other
                # leaves it rather than taking a place that is not there.
                swap_pin.unlink()
        else:
            target = {"table_id": table.id, "seat_number": seat}

        if pin:
            pin.write(target)
        else:
            self.env["event.table.pin"].create(
                dict(
                    target,
                    plan_id=self.id,
                    round_number=round_number,
                    participant_id=participant.id,
                )
            )
        # No chatter line here, unlike a move on a seating already in
        # force: a pin is an input still being drafted, and placing
        # forty people by hand would bury the log it is meant to serve.
        return self.get_floor_plan_data()

    def _unseat_pinned_participant(self, round_number, participant_id):
        """Drop the reservation one participant holds for one round."""
        self.ensure_one()
        round_number = int(round_number)
        self.pin_ids.filtered(
            lambda p: p.round_number == round_number
            and p.participant_id.id == int(participant_id)
        ).unlink()
        return self.get_floor_plan_data()

    def action_retain_placement(self):
        """Turn a hand-made placement into a chosen combination.

        The pins say where some people must sit; the generator seats
        everyone else around them and the best candidate is chosen at
        once. It COMPLETES rather than refusing a partial placement:
        reserving three seats out of forty is the ordinary case, and
        the rest is precisely what a generator is for.
        """
        self.ensure_one()
        self._check_not_locked()
        if not self.pin_ids:
            raise UserError(
                _(
                    "Nobody is placed yet. Put at least one person at a"
                    " table before retaining the placement."
                )
            )
        known = set(self.combination_ids.ids)
        self.action_generate_combinations(honour_pins=True)
        fresh = self.combination_ids.filtered(lambda c: c.id not in known)
        if not fresh:
            raise UserError(
                _("The generation produced no combination to retain.")
            )
        fresh.sorted(key=lambda c: c.rank)[0].action_choose()

    def action_move_participant(
        self,
        round_number,
        participant_id,
        table_id,
        seat_number=False,
        swap_participant_id=False,
    ):
        """Move, or swap, one participant for one round.

        The move is computed from the assignment lines that stand now,
        never from what the floor plan component displays: two managers
        acting at once corrupt nothing, and the payload this returns
        corrects whichever screen was stale.

        With no assignment on the plan, the very same gesture reserves a
        seat instead. What the operator does is one thing; which record
        it writes depends only on whether a seating is already in force.
        """
        self.ensure_one()
        self._lock()
        self._check_not_locked()
        if not self.assignment_ids:
            return self._move_pinned_participant(
                round_number,
                participant_id,
                table_id,
                seat_number,
                swap_participant_id,
            )
        round_number = int(round_number)
        if not 1 <= round_number <= self.round_count:
            raise UserError(
                _(
                    "Round %(round)s does not exist in this plan.",
                    round=round_number,
                )
            )
        table_id = int(table_id)
        participant_id = int(participant_id)
        table = self.table_ids.filtered(lambda t: t.id == table_id)
        if not table:
            # The table may still exist, in another plan: show its own
            # number when it does, the raw id when it does not exist at
            # all. Either way this is a plain wrong id, not the stale
            # combination that action_choose guards against.
            other_table = self.env["event.table"].browse(table_id)
            raise UserError(
                _(
                    "Table %(table)s does not belong to this plan.",
                    table=(
                        other_table.number
                        if other_table.exists()
                        else table_id
                    ),
                )
            )
        participant = self.participant_ids.filtered(
            lambda p: p.id == participant_id and not p.excluded
        )
        if not participant:
            # Covers both an id foreign to this plan and one excluded from
            # it: excluded exists but does not take part either.
            other_participant = self.env["event.table.participant"].browse(
                participant_id
            )
            raise UserError(
                _(
                    "%(name)s does not take part in this plan.",
                    name=(
                        other_participant.name
                        if other_participant.exists()
                        else participant_id
                    ),
                )
            )
        lines = self.assignment_ids.with_context(
            event_table_assignment_write=True
        )
        line = lines.filtered(
            lambda a: a.round_number == round_number
            and a.participant_id == participant
        )
        occupants = lines.filtered(
            lambda a: a.round_number == round_number and a.table_id == table
        )
        swap_line = lines.browse()
        if swap_participant_id:
            swap_line = occupants.filtered(
                lambda a: a.participant_id.id == int(swap_participant_id)
            )
            if not swap_line:
                other = self.participant_ids.browse(int(swap_participant_id))
                raise UserError(
                    _(
                        "%(name)s is not at table %(table)s in round"
                        " %(round)s.",
                        name=other.name,
                        table=table.number,
                        round=round_number,
                    )
                )
        full = _(
            "Table %(table)s is full in round %(round)s. Drop the person"
            " onto someone to swap them.",
            table=table.number,
            round=round_number,
        )
        seat = int(seat_number or 0)
        if self.assign_seats and not swap_line:
            taken = set((occupants - line).mapped("seat_number"))
            if not seat:
                free = [
                    number
                    for number in range(1, table.seat_count + 1)
                    if number not in taken
                ]
                if not free:
                    raise UserError(full)
                seat = free[0]
            elif not 1 <= seat <= table.seat_count:
                raise UserError(
                    _(
                        "Table %(table)s has no seat %(seat)s.",
                        table=table.number,
                        seat=seat,
                    )
                )
            elif seat in taken:
                # The table itself may still have room: naming it "full"
                # would be false, and the taken seat's occupant is who
                # actually blocks this move.
                occupant = (occupants - line).filtered(
                    lambda a: a.seat_number == seat
                )
                raise UserError(
                    _(
                        "Seat %(seat)s at table %(table)s is taken by"
                        " %(name)s. Drop the person onto them to swap.",
                        seat=seat,
                        table=table.number,
                        name=occupant.participant_id.name,
                    )
                )
        if not swap_line and len(occupants - line) >= table.seat_count:
            raise UserError(full)
        origin_tables = table | line.table_id
        if swap_line and line:
            # Three writes so that two people never hold one seat: the
            # mover drops its seat, the other takes the freed place, then
            # the mover takes the place the other just left. The target
            # seat is read BEFORE the second write, which overwrites it.
            origin_table, origin_seat = line.table_id, line.seat_number
            target_seat = seat or swap_line.seat_number
            line.write({"seat_number": 0})
            swap_line.write(
                {"table_id": origin_table.id, "seat_number": origin_seat}
            )
            line.write({"table_id": table.id, "seat_number": target_seat})
            body = _(
                "Round %(round)s: %(name)s and %(other)s swapped places.",
                round=round_number,
                name=participant.name,
                other=swap_line.participant_id.name,
            )
        elif swap_line:
            # The mover comes from the tray: the occupant goes back to it,
            # nobody vanishes silently.
            freed_seat = swap_line.seat_number
            swap_other = swap_line.participant_id
            swap_line.unlink()
            lines.create(
                {
                    "plan_id": self.id,
                    "combination_id": self.chosen_combination_id.id,
                    "round_number": round_number,
                    "table_id": table.id,
                    "participant_id": participant.id,
                    "seat_number": freed_seat,
                }
            )
            body = _(
                "Round %(round)s: %(name)s and %(other)s swapped places.",
                round=round_number,
                name=participant.name,
                other=swap_other.name,
            )
        else:
            values = {"table_id": table.id, "seat_number": seat}
            if line:
                line.write(values)
            else:
                values.update(
                    {
                        "plan_id": self.id,
                        "combination_id": self.chosen_combination_id.id,
                        "round_number": round_number,
                        "participant_id": participant.id,
                    }
                )
                lines.create(values)
            body = _(
                "Round %(round)s: %(name)s now sits at table %(table)s.",
                round=round_number,
                name=participant.name,
                table=table.number,
            )
        # Capacity is replayed once, at the end: the ORM constraint stands
        # down for these writes, since a swap's intermediate state would
        # otherwise trip it on a table that ends up no fuller than before.
        self._check_table_capacity(round_number, origin_tables)
        self._recompute_chosen_indicators()
        self.message_post(body=body)
        return self.get_floor_plan_data()

    def action_unseat_participant(self, round_number, participant_id):
        """Take one person off a table for one round; the tray catches them."""
        self.ensure_one()
        self._lock()
        self._check_not_locked()
        if not self.assignment_ids:
            return self._unseat_pinned_participant(
                round_number, participant_id
            )
        round_number = int(round_number)
        if not 1 <= round_number <= self.round_count:
            raise UserError(
                _(
                    "Round %(round)s does not exist in this plan.",
                    round=round_number,
                )
            )
        participant_id = int(participant_id)
        participant = self.participant_ids.filtered(
            lambda p: p.id == participant_id and not p.excluded
        )
        if not participant:
            other_participant = self.env["event.table.participant"].browse(
                participant_id
            )
            raise UserError(
                _(
                    "%(name)s does not take part in this plan.",
                    name=(
                        other_participant.name
                        if other_participant.exists()
                        else participant_id
                    ),
                )
            )
        self.assignment_ids.with_context(
            event_table_assignment_write=True
        ).filtered(
            lambda a: a.round_number == round_number
            and a.participant_id == participant
        ).unlink()
        self._recompute_chosen_indicators()
        self.message_post(
            body=_(
                "Round %(round)s: %(name)s no longer sits at a table.",
                round=round_number,
                name=participant.name,
            )
        )
        return self.get_floor_plan_data()

    def _sync_assignments_after_change(self, message):
        """Keep the chosen combination in step with its participants.

        Adding someone, excluding them or deleting their line stays
        allowed after the choice: the person waits in the tray, or leaves
        every round. Only the exclusion case removes lines here; a plain
        addition has none yet, and a deletion already cascaded them.
        """
        self.ensure_one()
        if not self.assignment_ids:
            return
        excluded = self.participant_ids.filtered("excluded")
        if excluded:
            self.assignment_ids.with_context(
                event_table_assignment_write=True
            ).filtered(lambda a: a.participant_id in excluded).unlink()
        self._recompute_chosen_indicators()
        self.message_post(body=message)

    def _conflicts_by_round(self, placements):
        """Return round -> list of per-table conflict dicts, table ids used.

        company_pairs comes straight from table_conflicts: a company
        overlap at a table has no notion of before or after, so the
        library's value already matches what this round should show.
        repeated_pairs and table_returns are recomputed here instead: the
        library's own counters answer "does this pair ever meet twice
        anywhere on the plan", a question with a global answer, while a
        table conflict on the floor plan is read on the round being
        displayed, ignoring what happens in later rounds. Only the active
        options count, exactly as the library does: an inactive option is
        forced to 0 rather than left uncomputed.
        """
        self.ensure_one()
        options = self._rotation_options()
        company_pairs_by_group = {
            (conflict.round, conflict.table): conflict.company_pairs
            for conflict in table_conflicts(
                self._rotation_problem(), placements, options
            )
        }
        groups_by_round = {}
        for placement in placements:
            groups_by_round.setdefault(placement.round, {}).setdefault(
                placement.table, []
            ).append(placement.person)
        table_by_number = {table.number: table.id for table in self.table_ids}

        met_before = set()
        visited_before = {}
        conflicts_by_round = {}
        for round_number in range(1, self.round_count + 1):
            round_groups = groups_by_round.get(round_number, {})
            entries = []
            for table_number in sorted(round_groups):
                members = round_groups[table_number]
                company_pairs = company_pairs_by_group.get(
                    (round_number, table_number), 0
                )
                repeated_pairs = 0
                if options.avoid_repeat_neighbors:
                    for index, person in enumerate(members):
                        for other in members[index + 1 :]:
                            pair = (
                                (person, other)
                                if person < other
                                else (other, person)
                            )
                            if pair in met_before:
                                repeated_pairs += 1
                table_returns = 0
                if options.avoid_repeat_table:
                    table_returns = sum(
                        1
                        for person in members
                        if visited_before.get((person, table_number), 0)
                    )
                if company_pairs or repeated_pairs or table_returns:
                    entries.append(
                        {
                            "table_id": table_by_number[table_number],
                            "company_pairs": company_pairs,
                            "repeated_pairs": repeated_pairs,
                            "table_returns": table_returns,
                        }
                    )
            conflicts_by_round[round_number] = entries
            # A meeting or a table visit only weighs on a LATER round:
            # history updates after this round's conflicts are computed,
            # never before, so a round never counts against itself.
            for table_number, members in round_groups.items():
                for index, person in enumerate(members):
                    for other in members[index + 1 :]:
                        pair = (
                            (person, other)
                            if person < other
                            else (other, person)
                        )
                        met_before.add(pair)
                for person in members:
                    visited_before[(person, table_number)] = (
                        visited_before.get((person, table_number), 0) + 1
                    )
        return conflicts_by_round

    def get_floor_plan_data(self, combination_id=False):
        """Return everything the floor plan component draws, in one call.

        Seats come from the assignment lines whenever the requested
        combination is the chosen one, or when none is requested at all;
        they come from the combination's own placement_data only to
        preview a combination that was not chosen. A manual adjustment
        therefore stays visible everywhere, and no record is ever shown
        two different ways.
        """
        self.ensure_one()
        combination = (
            self.env["event.table.combination"].browse(combination_id)
            if combination_id
            else self.chosen_combination_id
        )
        is_preview = (
            bool(combination_id) and combination != self.chosen_combination_id
        )
        # With nothing assigned, the pins ARE the seating on screen:
        # hand placement has to be visible while it is being done, and
        # the same gesture that moves someone in a chosen plan reserves
        # a seat here.
        draws_pins = not is_preview and not self.assignment_ids
        if is_preview:
            placements = self._combination_placements(combination)
        elif draws_pins:
            placements = self._pin_placements()
        else:
            placements = self._assignment_placements()
        # A brand-new line has name = False, and comparing that to a string
        # raises the same TypeError as an unsorted NewId above; "" sorts
        # first among real names instead of failing.
        included = self._included_participants().sorted(
            key=lambda p: p.name or ""
        )
        # included.ids holds NewId objects before the plan is saved, same as
        # the two sorts above; p._origin.id keeps this comparable with the
        # placements' real participant ids in every case.
        included_ids = {p._origin.id for p in included}
        # A placement can still name an excluded participant through a
        # pre-existing assignment line: drop it so the payload never draws
        # someone the plan no longer seats.
        placements = tuple(p for p in placements if p.person in included_ids)
        table_by_number = {table.number: table.id for table in self.table_ids}

        # Every round is described, placements or none. Before a
        # combination is chosen there are no placements at all, and
        # returning no rounds left the screen with nothing to read: the
        # tray reads its people out of the CURRENT round, so it announced
        # "Not seated (0)" while every participant was waiting, and no
        # table could name anyone. An empty round states that plainly —
        # no seats taken, everyone included still waiting.
        rounds = []
        conflicts_by_round = (
            self._conflicts_by_round(placements) if placements else {}
        )
        for round_number in range(1, self.round_count + 1):
            seated_ids = set()
            seats = []
            for placement in placements:
                if placement.round != round_number:
                    continue
                seated_ids.add(placement.person)
                seats.append(
                    {
                        "participant_id": placement.person,
                        "table_id": table_by_number[placement.table],
                        "seat": (placement.seat if self.assign_seats else 0),
                    }
                )
            rounds.append(
                {
                    "round": round_number,
                    "seats": seats,
                    "unseated": sorted(included_ids - seated_ids),
                    "conflicts": conflicts_by_round.get(round_number, []),
                }
            )

        wrapping_counts = self._wrapping_label_counts(placements)

        can_edit_layout = self.env["event.table"].has_access("write")
        can_move_participants = (
            self.state != "locked"
            and not combination_id
            and self.env["event.table.assignment"].has_access("write")
        )

        return {
            "plan": {
                "id": self.id,
                "name": self.name,
                "state": self.state,
                "round_count": self.round_count,
                "assign_seats": self.assign_seats,
                "show_seat_number": self.show_seat_number,
                "show_company": self.show_company,
                "show_full_names": self.show_full_names,
                "visual_tables": self.visual_tables,
                "participant_count": self.participant_count,
                "seat_count": self.seat_count,
                "unseated_count": self.unseated_count,
                "capacity_message": self.capacity_message,
                "sync_message": self.sync_message or "",
                "can_edit_layout": can_edit_layout,
                "can_move_participants": can_move_participants,
                "draws_pins": draws_pins,
            },
            "combination": (
                {
                    "id": combination.id,
                    "name": combination.name,
                    "rank": combination.rank,
                    "is_chosen": combination.is_chosen,
                    "is_adjusted": combination.is_adjusted,
                }
                if combination
                else None
            ),
            "tables": [
                {
                    "id": table.id,
                    "number": table.number,
                    "seat_count": table.seat_count,
                    "shape": table.shape,
                    "x": float(table.position_h),
                    "y": float(table.position_v),
                    "width": float(table.width),
                    "height": float(table.height),
                    # What floorSize (geometry.js) reserves this table's
                    # list from, chip by chip. Counted from the SAME
                    # placements this payload draws, so a preview of
                    # another combination reserves for the names that
                    # preview seats and not for the chosen one's.
                    "wrapping_label_count": wrapping_counts.get(
                        table.number, 0
                    ),
                }
                for table in self.table_ids.sorted("number")
            ],
            "participants": [
                {
                    "id": participant.id,
                    "name": participant.name,
                    "company": participant.company_label or "",
                }
                for participant in included
            ],
            "rounds": rounds,
            "indicators": (
                {
                    "company_pairs": combination.company_pair_count,
                    "repeated_pairs": combination.repeated_pair_count,
                    "extra_meetings": combination.extra_meeting_count,
                    "max_pair_meetings": combination.max_pair_meetings,
                    "table_returns": combination.table_return_count,
                    "met_distinct_avg": combination.met_distinct_avg,
                    "met_distinct_min": combination.met_distinct_min,
                    "lower_bound": combination.lower_bound,
                    "is_proven_optimal": combination.is_proven_optimal,
                    "is_adjusted": combination.is_adjusted,
                }
                if combination
                else None
            ),
        }

    def _wrapping_label_counts(self, placements=None):
        """How many chips of each table's list wrap onto a second name
        line, by table NUMBER — the one figure both reservations add up
        chip by chip (list_reserved_height, and listReservedHeight in
        geometry.js).

        The MAXIMUM over the rounds, since a floor holds every round and
        people rotate between them: a table seating three long names in
        one round and none in another reserves for three. A plan hiding
        whole names wraps nothing at all, whatever its names, and gets
        an empty answer.

        A label's number is taken at the table's OWN seat_count, the
        largest a list of that table can print, where the drawn list
        numbers its lines 1..N. The count therefore errs toward a label
        longer than the one drawn, which reserves a line too many
        rather than one too few — the only direction a reservation may
        be wrong in.

        With no seating yet the answer is empty and every list is
        reserved at one line per seat, which is what an empty list
        draws. A plan generated after its tables were placed therefore
        needs Rearrange Tables before the floor holds its new lists,
        exactly as it does after any other change to what a list draws.

        get_floor_plan_data puts each table's count in the payload so
        that floorSize (geometry.js) reserves against these very
        numbers rather than counting a second time, in a second
        language, and from a rotation it would have to re-derive.
        """
        self.ensure_one()
        if not self.show_full_names:
            return {}
        if placements is None:
            # The branch get_floor_plan_data takes outside a preview:
            # pins while nothing is assigned, the assignment lines once
            # something is.
            placements = (
                self._assignment_placements()
                if self.assignment_ids
                else self._pin_placements()
            )
        names = {
            participant._origin.id: participant.name or ""
            for participant in self._included_participants()
        }
        seats_by_number = {
            table.number: table.seat_count for table in self.table_ids
        }
        per_round = {}
        for placement in placements:
            name = names.get(placement.person)
            seats = seats_by_number.get(placement.table)
            if name is None or seats is None:
                continue
            if not list_wraps_to_two_lines(
                self.show_full_names, list_label_length(seats, name)
            ):
                continue
            key = (placement.table, placement.round)
            per_round[key] = per_round.get(key, 0) + 1
        counts = {}
        for (number, _round), count in per_round.items():
            counts[number] = max(counts.get(number, 0), count)
        return counts

    def _grid_positions(self, start_index, count):
        self.ensure_one()
        total = start_index + count
        columns = max(1, math.ceil(math.sqrt(total)))
        wrapping_counts = self._wrapping_label_counts()
        if self.visual_tables:
            # The grid must space rows AND columns for the footprint
            # visual mode actually draws (visual_table_size, event_table.py)
            # — never TABLE_SIZE, which the browser stopped reading for
            # rendering the moment visual mode replaced it with the same
            # function. This is the THIRD twin of that footprint, after
            # floorSize and surfaceStyle (JS): leaving this one on the
            # fixed constant is what let tables overlap from about seven
            # seats up, since a table far bigger than TABLE_SIZE was
            # still spaced as if it were TABLE_SIZE. The busiest table
            # across every dimension a size depends on — shape and seat
            # count both — drives the spacing, since one grid pass
            # covers every table on the plan; the fallback (no tables
            # yet) matches the non-visual branch's own "8 seats" guess,
            # below, for the same empty case.
            sizes = [
                visual_table_size(
                    table.shape,
                    table.seat_count,
                    self.assign_seats,
                    self.show_company,
                )
                for table in self.table_ids
            ] or [
                visual_table_size(
                    "round", 8, self.assign_seats, self.show_company
                )
            ]
            table_width = max(size[0] for size in sizes)
            table_height = max(size[1] for size in sizes)
        else:
            table_width = TABLE_SIZE
            table_height = TABLE_SIZE
        # Every table carries its name list on its RIGHT, in both modes:
        # a column has to clear the seat ring, the connector and the list
        # itself before the next column starts. floorSize (geometry.js)
        # builds its own width term from these same four pieces; keep the
        # two in step, since this is that same arithmetic written a
        # second time, in a second language, and that duplication is
        # exactly how such a pair drifts apart later.
        step_x = (
            table_width
            + SEAT_RING
            + CONNECTOR_WIDTH
            + list_width(self.show_full_names)
            + GRID_GAP_X
        )
        # A row has to clear whichever of the table and its own list is
        # TALLER, never their sum: the two stand side by side. The list
        # is routinely the taller of the two — eight names stand 232 px
        # where their table stands 100 — so taking the table's height
        # alone would run the next row straight through the names.
        # Measured at seat_count CHIPS, the most a list can ever hold,
        # which is also all this method can know about a list's LENGTH:
        # it places tables before anyone is seated at all. The chips are
        # added up ONE BY ONE (list_reserved_height), each at its own
        # pitch, rather than multiplied by the tallest of them: a table
        # of eight where a single name wraps stands 21 px taller, not
        # 168. The busiest table drives the step, one grid pass covering
        # every table on the plan; the fallback matches the visual
        # branch's own "8 seats" guess for the same empty case.
        list_heights = [
            list_reserved_height(
                table.seat_count,
                wrapping_counts.get(table.number, 0),
                self.show_company,
            )
            for table in self.table_ids
        ] or [list_reserved_height(8, 0, self.show_company)]
        step_y = max(table_height + SEAT_RING, max(list_heights)) + 40.0
        return [
            (
                GRID_MARGIN + (index % columns) * step_x,
                GRID_MARGIN + (index // columns) * step_y,
            )
            for index in range(start_index, total)
        ]

    def action_rearrange_tables(self):
        for plan in self:
            tables = plan.table_ids.sorted("number")
            positions = plan._grid_positions(0, len(tables))
            for table, position in zip(tables, positions):
                table.write(
                    {"position_h": position[0], "position_v": position[1]}
                )
            plan.message_post(body=_("Tables rearranged on the floor plan."))
