# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class EventType(models.Model):
    _inherit = "event.type"

    use_rotating_tables = fields.Boolean(
        string="Rotating Tables",
        help="Events created from this template start with rotating "
        "tables enabled.",
    )
