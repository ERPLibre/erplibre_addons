#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsDeployVmSnapshot(models.Model):
    _name = "devops.deploy.vm.snapshot"
    _description = "devops_deploy_vm_snapshot"

    name = fields.Char()
