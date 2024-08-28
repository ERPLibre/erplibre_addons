#!/usr/bin/env python3
# © 2021-2024 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SurveyQuestion(models.Model):
    _inherit = "survey.question"

    matrix_type_selection = fields.Boolean(
        string="Force selection type",
        help="Will reduce matrix horizontal size to show only selection. Works only for 1 result to choose.",
    )
