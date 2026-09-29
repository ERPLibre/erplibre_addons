# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import models

# Invented names, paired by index by _demo_participant_values. The two
# lists have coprime lengths, so a pair comes back only after 20*21
# people: one plan can name 420 participants before two of them collide.
# Every value here is made up, and the domain is the one reserved for
# documentation.
_DEMO_GIVEN_NAMES = (
    "Anwen",
    "Bramwell",
    "Cordelia",
    "Dorian",
    "Eulalia",
    "Fenwick",
    "Gwendolen",
    "Hesper",
    "Isolde",
    "Jorvik",
    "Kerensa",
    "Lysander",
    "Marisol",
    "Nerys",
    "Orrin",
    "Perrine",
    "Quenby",
    "Rowan",
    "Sable",
    "Tamsin",
)
_DEMO_SURNAMES = (
    "Ashgrove",
    "Bellwater",
    "Coldharbour",
    "Dunmire",
    "Everly",
    "Farrowgate",
    "Glimmerton",
    "Havelock",
    "Ironwood",
    "Jessamine",
    "Kirkbride",
    "Larkspur",
    "Meadowvale",
    "Northgate",
    "Oysterly",
    "Pemberton",
    "Quarrington",
    "Ravensworth",
    "Saltmarsh",
    "Thornbury",
    "Umberfield",
)
# The ceiling on the company_count a caller may ask for: the builder
# reads this tuple from index 0 to company_count - 1.
_DEMO_COMPANIES = (
    "Amberline Foundry",
    "Briarstone Logistics",
    "Clearwater Ceramics",
    "Duskvale Systems",
    "Elmgrove Bakery",
    "Foxglove Optics",
    "Greyharbour Freight",
    "Hollowbrook Paper",
    "Ivywell Chemicals",
    "Juniper Ridge Mills",
    "Kelpstone Marine",
    "Larchfield Aviation",
    "Mosswood Timber",
    "Nettlebrook Glass",
    "Orchard Gate Foods",
    "Pinecrest Alloys",
)


class EventTablePlanDemo(models.Model):
    """Builders the demo file calls, and nothing else calls.

    data/event_table_demo.xml reaches these through <function>, because a
    plan of a hundred participants written as XML records costs hundreds
    of lines that say no more than the four numbers handed to
    _demo_fill_room. No production code path leads here.
    """

    _inherit = "event.table.plan"

    def _demo_fill_room(
        self,
        table_count,
        seat_count,
        participant_count,
        company_count,
        shape="round",
        name_offset=0,
    ):
        """Create the tables and the participants of a demo plan.

        Demo data only. Deterministic: a person's name, address and
        company follow from their index, never from a random draw, so
        every installation of the module holds the same rows.
        name_offset shifts the pairing so two plans do not list the same
        people.

        Companies are handed out round-robin over the first
        company_count entries of _DEMO_COMPANIES, which caps the largest
        one at ceil(participant_count / company_count): a company with
        more people than the room has tables cannot be spread over them,
        and precheck (rotation/bounds.py) reports that as a
        company_exceeds_tables diagnostic on every generation.

        Creating an event.table calls _check_not_locked, so this runs
        on any plan that is not locked.
        """
        self.ensure_one()
        self.env["event.table"].create(
            [
                {
                    "plan_id": self.id,
                    "number": index + 1,
                    "seat_count": seat_count,
                    "shape": shape,
                }
                for index in range(table_count)
            ]
        )
        # Positions come from the plan's own grid pass, run once the
        # tables exist: _grid_positions spaces the room for the shape and
        # the seat count it reads on them, and falls back to a round
        # eight-seat guess as long as the plan carries no table.
        self.action_rearrange_tables()
        self.env["event.table.participant"].create(
            [
                self._demo_participant_values(
                    name_offset + index, company_count
                )
                for index in range(participant_count)
            ]
        )

    def _demo_participant_values(self, index, company_count):
        """Values of one demo participant, drawn from their index alone."""
        self.ensure_one()
        given = _DEMO_GIVEN_NAMES[index % len(_DEMO_GIVEN_NAMES)]
        surname = _DEMO_SURNAMES[index % len(_DEMO_SURNAMES)]
        return {
            "plan_id": self.id,
            "name": f"{given} {surname}",
            "email": f"{given}.{surname}@example.com".lower(),
            "company_label": _DEMO_COMPANIES[index % company_count],
        }

    def _demo_seat_first_combination(self):
        """Generate the combinations, then choose the first. Demo only.

        Takes the two public actions rather than writing assignment rows
        by hand: action_choose is what opens the write with
        event_table_assignment_write, the context the assignment model
        demands, and what moves the plan to "chosen" against its own
        combination.
        """
        self.ensure_one()
        self.action_generate_combinations()
        self.combination_ids.filtered(
            lambda combination: combination.rank == 1
        ).action_choose()
