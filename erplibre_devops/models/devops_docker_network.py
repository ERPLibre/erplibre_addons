#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsDockerNetwork(models.Model):
    _name = "devops.docker.network"
    _description = "devops_docker_network"

    name = fields.Char(readonly=True)

    system_id = fields.Many2one(
        comodel_name="devops.system",
        string="System",
    )

    active = fields.Boolean(default=True)

    created_at = fields.Char(readonly=True)

    driver = fields.Char(readonly=True)

    id_network = fields.Char(readonly=True)

    id_short_network = fields.Char(readonly=True)

    ipv6 = fields.Char(readonly=True)

    internal = fields.Char(readonly=True)

    labels = fields.Text(readonly=True)

    inspect_full = fields.Text(readonly=True)

    scope = fields.Char(readonly=True)
