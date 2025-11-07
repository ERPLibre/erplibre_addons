#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

from odoo import _, api, exceptions, fields, models, tools

_logger = logging.getLogger(__name__)


class DevopsCgNewProjectStage(models.Model):
    _name = "devops.cg.new_project.stage"
    _description = "Stage new project for CG project"
    _order = "sequence, name, id"

    name = fields.Char()

    description = fields.Char()

    sequence = fields.Integer(
        default=10,
        help="Used to order new project stages. Lower is better.",
    )

    fold = fields.Boolean(
        string="Folded in Pipeline",
        help=(
            "This stage is folded in the kanban view when there are no records"
            " in that stage to display."
        ),
    )
