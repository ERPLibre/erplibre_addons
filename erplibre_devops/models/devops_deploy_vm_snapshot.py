#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsDeployVmSnapshot(models.Model):
    _name = "devops.deploy.vm.snapshot"
    _description = "devops_deploy_vm_snapshot"

    name = fields.Char()

    vm_id = fields.Many2one(
        comodel_name="devops.deploy.vm",
        string="Vm",
    )

    time_creation = fields.Datetime()

    state = fields.Char()

    def action_vm_snapshot_restore(self):
        for rec in self:
            if not rec.vm_id:
                raise Exception("Need association with a Vm.")

            system_id = rec.vm_id.system_id
            if not system_id:
                raise Exception("The VM is not associate with a system.")

            if rec.vm_id.provider == "Qemu":
                cmd = f'virsh -c "{rec.vm_id.uri}" snapshot-revert "{rec.vm_id.name}" "{rec.name}"'
                out, status = system_id.execute_with_result(
                    cmd, None, return_status=True
                )
                if status:
                    raise Exception(f"Seems not working : {out}")
            else:
                raise Exception(
                    f"Not support snapshot restore from '{rec.vm_id.provider}'."
                )
