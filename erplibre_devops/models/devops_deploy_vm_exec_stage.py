#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsDeployVmExecStage(models.Model):
    _name = "devops.deploy.vm.exec.stage"
    _description = "devops_deploy_vm_exec_stage"

    name = fields.Char()
