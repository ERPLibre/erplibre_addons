# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import _, api, fields, models


class EventTablePinGenerateWizard(models.TransientModel):
    """The question a plan carrying reserved places asks before generating.

    Placing someone by hand and then generating are two orders that
    contradict each other, and only the person can say which one wins.
    event.table.plan action_request_generation opens this wizard when,
    and only when, the plan carries at least one pin; the generation
    itself stays reachable without it.
    """

    _name = "event.table.pin.generate.wizard"
    _description = "Generate Combinations Around Pins"

    plan_id = fields.Many2one(
        "event.table.plan", required=True, ondelete="cascade"
    )
    mode = fields.Selection(
        [
            ("keep", "Reserve the pinned places and fill around them"),
            ("reset", "Start over from zero, ignoring the pins"),
        ],
        default="keep",
        required=True,
    )
    pin_count = fields.Integer(compute="_compute_pin_count")
    # One fully-formed sentence rather than a count between two text
    # nodes of the view: the plural differs per language and the two
    # fragments would be extracted as unrelated msgid.
    pin_summary = fields.Char(compute="_compute_pin_count")

    @api.depends("plan_id", "plan_id.pin_ids")
    def _compute_pin_count(self):
        for wizard in self:
            count = len(wizard.plan_id.pin_ids)
            wizard.pin_count = count
            if count == 1:
                wizard.pin_summary = _("One place is reserved by hand.")
            else:
                wizard.pin_summary = _(
                    "%(count)s places are reserved by hand.", count=count
                )

    def action_apply(self):
        """Generate, holding the reserved places or ignoring them.

        "reset" leaves the pins on the plan and only skips the pass that
        holds them: the person asked to start over from THIS generation,
        not to throw away what they placed by hand.
        """
        self.ensure_one()
        return self.plan_id.action_generate_combinations(
            honour_pins=self.mode == "keep"
        )
