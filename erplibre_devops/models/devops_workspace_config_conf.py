#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import configparser

from odoo import _, api, fields, models


class DevopsWorkspaceConfigConf(models.Model):
    _name = "devops.workspace.config.conf"
    _description = "devops_workspace_config_conf"

    name = fields.Char()

    config_workers = fields.Integer(
        compute="_compute_analyse",
        store=True,
    )

    file_content = fields.Text()

    workspace_id = fields.Many2one(
        comodel_name="devops.workspace",
        string="Workspace",
    )

    @api.depends("file_content")
    def _compute_analyse(self):
        for rec in self:
            if not rec.file_content:
                continue

            config = configparser.ConfigParser()
            config.read_string(rec.file_content)

            rec.config_workers = config.get("options", "workers")
