# Copyright 2023 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import os
import time

import requests

from odoo import _, api, exceptions, fields, models, tools

_logger = logging.getLogger(__name__)


class DevopsWorkspaceTerminal(models.Model):
    _name = "devops.workspace.terminal"
    _description = "ERPLibre DevOps Workspace Terminal"

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )

    workspace_id = fields.Many2one(
        comodel_name="devops.workspace",
        string="Workspace",
    )

    terminal_is_running = fields.Boolean(
        readonly=True,
        default=True,
        help="When false, it's because not running terminal.",
    )

    @api.depends("workspace_id", "terminal_is_running")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.workspace_id.name} - {rec.terminal_is_running}"

    def action_check(self):
        pass
