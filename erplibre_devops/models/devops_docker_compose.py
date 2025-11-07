# !/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import os

from odoo import _, api, fields, models


class DevopsDockerCompose(models.Model):
    _name = "devops.docker.compose"
    _inherit = ["mail.activity.mixin", "mail.thread"]
    _description = "devops_docker_compose"

    name = fields.Char(readonly=True)

    system_id = fields.Many2one(
        comodel_name="devops.system",
        string="System",
        readonly=True,
    )

    active = fields.Boolean(default=True)

    config_file_path = fields.Char(readonly=True)

    folder_root = fields.Char(
        compute="_compute_folder_root",
        store=True,
    )

    is_running = fields.Boolean(
        readonly=True,
        tracking=True,
    )

    @api.depends("config_file_path")
    def _compute_folder_root(self):
        for rec in self:
            if rec.config_file_path:
                rec.folder_root = os.path.dirname(rec.config_file_path)
            else:
                rec.folder_root = False
