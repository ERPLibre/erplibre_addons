#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsSystemPostgresConf(models.Model):
    _name = "devops.system.postgres.conf"
    _description = "devops_system_postgres_conf"
    _order = "id"

    name = fields.Char()

    package_os = fields.Text()

    postgres_version = fields.Char()

    ps_config_version = fields.Char()

    psql_version = fields.Char()

    process_postgres = fields.Text()

    ss_postgres = fields.Text()

    system_id = fields.Many2one(
        comodel_name="devops.system",
        string="System",
    )
