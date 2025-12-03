#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsInstanceExec(models.Model):
    _name = "devops.instance.exec"
    _description = "devops_instance_exec"

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )

    instance_name = fields.Char(help="Optional")

    docker_container_ids = fields.Many2many(
        comodel_name="devops.docker.container",
        string="Docker Container",
    )

    docker_image_ids = fields.Many2many(
        comodel_name="devops.docker.image",
        string="Docker Image",
    )

    docker_network_ids = fields.Many2many(
        comodel_name="devops.docker.network",
        string="Docker Network",
    )

    docker_volume_ids = fields.Many2many(
        comodel_name="devops.docker.volume",
        string="Docker Volume",
    )

    port = fields.Integer()

    system_id = fields.Many2one(
        comodel_name="devops.system",
        string="System",
    )

    type_ids = fields.Many2many(
        comodel_name="devops.instance.type",
        string="Types",
    )

    url = fields.Char()

    workspace_id = fields.Many2one(
        comodel_name="devops.workspace",
        string="Workspace",
    )

    working_dir_path = fields.Char()

    @api.depends("url", "type_ids", "instance_name")
    def _compute_name(self):
        for rec in self:
            str_type = "|".join([a.name for a in rec.type_ids])
            rec.name = f"{rec.instance_name} {str_type} {rec.url}".strip()

    def start(self):
        self.system_id.execute_terminal_gui(
            folder=self.working_dir_path,
            cmd=f"docker compose up",
        )
