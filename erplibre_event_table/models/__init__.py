# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
# The mixin is imported first because Odoo builds models in registration
# order and refuses a model whose _inherit parent is not in the registry
# yet. The isort marker below keeps the two statements from being merged
# back into one alphabetical list, which would place the mixin after its
# heirs.
from . import event_table_seat_claim

# isort: split
from . import (
    event_event,
    event_table,
    event_table_assignment,
    event_table_combination,
    event_table_participant,
    event_table_pin,
    event_table_plan,
    event_table_plan_demo,
    event_table_plan_generation,
    event_table_plan_output,
    event_table_plan_placement,
    event_type,
    res_partner,
)
