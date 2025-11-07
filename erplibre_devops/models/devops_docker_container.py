#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsDockerContainer(models.Model):
    _name = "devops.docker.container"
    _description = "devops_docker_container"

    name = fields.Char(readonly=True)

    system_id = fields.Many2one(
        comodel_name="devops.system",
        string="System",
        readonly=True,
    )

    active = fields.Boolean(default=True)

    command = fields.Char(readonly=True)

    create_at = fields.Char(readonly=True)

    id_container = fields.Char(readonly=True)

    id_short_container = fields.Char(readonly=True)

    label_full = fields.Text(readonly=True)

    mounts_full = fields.Text(readonly=True)

    image_id = fields.Many2one(
        comodel_name="devops.docker.image",
        string="Image",
        readonly=True,
    )

    network_id = fields.Many2one(
        comodel_name="devops.docker.network",
        string="Network",
        readonly=True,
    )

    compose_id = fields.Many2one(
        comodel_name="devops.docker.compose",
        string="Compose",
        readonly=True,
    )

    volume_ids = fields.Many2many(
        comodel_name="devops.docker.volume",
        string="Volumes",
        readonly=True,
    )

    ports_full = fields.Char(readonly=True)

    running_for = fields.Char(readonly=True)

    size_human = fields.Char(readonly=True)

    state_container = fields.Char(readonly=True)

    status_container = fields.Char(readonly=True)

    inspect_full = fields.Text(readonly=True)
