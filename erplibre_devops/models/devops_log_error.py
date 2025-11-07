#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

from odoo import _, api, exceptions, fields, models, tools

_logger = logging.getLogger(__name__)


class DevopsLogError(models.Model):
    _name = "devops.log.error"
    _description = "Log error"

    name = fields.Char()

    exec_id = fields.Many2one(
        comodel_name="devops.exec",
        string="Exec",
        readonly=True,
    )

    new_project_id = fields.Many2one(
        comodel_name="devops.cg.new_project",
        string="New Project",
    )
