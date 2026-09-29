# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import _, api, fields, models

from ..rotation import normalize_company


class EventTableParticipant(models.Model):
    _name = "event.table.participant"
    _description = "Rotating Table Participant"
    _order = "name, id"

    plan_id = fields.Many2one(
        "event.table.plan", required=True, ondelete="cascade", index=True
    )
    event_id = fields.Many2one(
        related="plan_id.event_id", store=True, index=True
    )
    name = fields.Char(required=True)
    email = fields.Char()
    partner_id = fields.Many2one("res.partner", string="Contact", index=True)
    registration_id = fields.Many2one(
        "event.registration",
        string="Registration",
        ondelete="set null",
        index=True,
    )
    source = fields.Selection(
        [
            ("registration", "Registration"),
            ("partner", "Contact"),
            ("guest", "Guest"),
        ],
        compute="_compute_source",
        store=True,
    )
    company_label = fields.Char(
        string="Company",
        compute="_compute_company_label",
        precompute=True,
        store=True,
        readonly=False,
        help="People sharing this company are kept apart when colleagues"
        " are separated. Clear it to exempt this person.",
    )
    company_key = fields.Char(
        compute="_compute_company_key", store=True, index=True
    )
    excluded = fields.Boolean(
        default=False,
        help="Keep the person in the list without seating them.",
    )
    assignment_ids = fields.One2many(
        "event.table.assignment", "participant_id", string="Tables by Round"
    )
    assignment_summary = fields.Char(
        compute="_compute_assignment_summary", string="Tables"
    )

    _sql_constraints = [
        (
            "partner_unique",
            "UNIQUE(plan_id, partner_id)",
            "This contact already takes part in this plan.",
        ),
    ]

    @api.depends("registration_id", "partner_id")
    def _compute_source(self):
        for participant in self:
            if participant.registration_id:
                participant.source = "registration"
            elif participant.partner_id:
                participant.source = "partner"
            else:
                participant.source = "guest"

    @api.depends("partner_id", "registration_id")
    def _compute_company_label(self):
        for participant in self:
            partner = participant.partner_id
            commercial = partner.commercial_partner_id
            if partner and (partner.is_company or commercial != partner):
                participant.company_label = commercial.name
            else:
                participant.company_label = (
                    partner.company_name
                    or participant.registration_id.company_name
                    or False
                )

    @api.depends("company_label")
    def _compute_company_key(self):
        for participant in self:
            # A Char field reads back as False when empty, never None:
            # normalize_company expects the latter for "no company".
            participant.company_key = normalize_company(
                participant.company_label or None
            )

    @api.depends(
        "assignment_ids",
        "assignment_ids.round_number",
        "assignment_ids.table_number",
        "assignment_ids.seat_number",
    )
    def _compute_assignment_summary(self):
        for participant in self:
            parts = []
            for line in participant.assignment_ids:
                if line.seat_number:
                    parts.append(
                        _(
                            "Round %(round)s: table %(table)s, seat"
                            " %(seat)s",
                            round=line.round_number,
                            table=line.table_number,
                            seat=line.seat_number,
                        )
                    )
                else:
                    parts.append(
                        _(
                            "Round %(round)s: table %(table)s",
                            round=line.round_number,
                            table=line.table_number,
                        )
                    )
            participant.assignment_summary = " ; ".join(parts)

    def _report_rows(self):
        """Rows of the participant card, one per round where the person sits."""
        self.ensure_one()
        return [
            {
                "round": line.round_number,
                "table_number": line.table_number,
                "seat_number": line.seat_number,
            }
            for line in self.assignment_ids.sorted("round_number")
        ]

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        for participant in self:
            if participant.partner_id:
                if not participant.name:
                    participant.name = participant.partner_id.name
                if not participant.email:
                    participant.email = participant.partner_id.email

    @api.model_create_multi
    def create(self, vals_list):
        self.env["event.table.plan"].browse(
            [vals["plan_id"] for vals in vals_list if vals.get("plan_id")]
        )._check_not_locked()
        participants = super().create(vals_list)
        for participant in participants:
            participant.plan_id._sync_assignments_after_change(
                _("%(name)s added to the plan.", name=participant.name)
            )
        return participants

    def write(self, vals):
        self.plan_id._check_not_locked()
        was_excluded = {p.id: p.excluded for p in self}
        result = super().write(vals)
        for participant in self:
            plan = participant.plan_id
            if plan.state != "chosen":
                continue
            if (
                "excluded" in vals
                and was_excluded[participant.id] != participant.excluded
            ):
                plan._sync_assignments_after_change(
                    _(
                        "%(name)s excluded: removed from every round.",
                        name=participant.name,
                    )
                    if participant.excluded
                    else _(
                        "%(name)s is included again and waits to be seated.",
                        name=participant.name,
                    )
                )
            elif {"partner_id", "company_label"} & set(vals):
                # These change the company groupings, not who is seated:
                # the indicators follow, but no note is worth posting.
                plan._recompute_chosen_indicators()
        return result

    def unlink(self):
        self.plan_id._check_not_locked()
        # Read the names before the rows go: the message names the person.
        departures = [(p.plan_id, p.name) for p in self]
        result = super().unlink()
        for plan, name in departures:
            # A cascade from the plan's own deletion leaves nothing to
            # post to.
            if plan.exists():
                plan._sync_assignments_after_change(
                    _("%(name)s removed from the plan.", name=name)
                )
        return result
