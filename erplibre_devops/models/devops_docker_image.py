#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsDockerImage(models.Model):
    _name = "devops.docker.image"
    _description = "devops_docker_image"

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )

    system_ids = fields.Many2many(
        comodel_name="devops.system",
        relation="docker_image_system_ids_rel",
        string="Systems",
        readonly=True,
    )

    active = fields.Boolean(default=True)

    id_image = fields.Char(readonly=True)

    id_short_image = fields.Char(readonly=True)

    tag = fields.Char(readonly=True)

    size_human = fields.Char(readonly=True)

    size_virtual_human = fields.Char(readonly=True)

    created_at = fields.Char(readonly=True)

    created_since = fields.Char(readonly=True)

    repository = fields.Char(readonly=True)

    history_full = fields.Text(readonly=True)

    inspect_full = fields.Text(readonly=True)

    @api.depends("tag", "repository")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.repository}:{rec.tag}"
