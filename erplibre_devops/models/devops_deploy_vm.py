import logging
import time

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)
try:
    import paramiko
except ImportError:  # pragma: no cover
    _logger.debug("Cannot import paramiko")


class DevopsDeployVm(models.Model):
    _name = "devops.deploy.vm"
    _description = "devops_deploy_vm"

    name = fields.Char()

    identifiant = fields.Char()

    vm_ssh_host = fields.Char()

    vm_info = fields.Char()

    vm_description_json = fields.Char()

    os = fields.Char()

    provider = fields.Char()

    system_id = fields.Many2one(
        comodel_name="devops.system",
        string="System",
    )

    workspace_ids = fields.Many2many(
        comodel_name="devops.workspace",
        string="Workspaces",
    )

    has_vm_exec_running = fields.Boolean(
        compute="_compute_has_vm_exec_running",
        store=True,
    )

    vm_exec_last_id = fields.Many2one(
        comodel_name="devops.deploy.vm.exec",
        string="VM last exec",
    )

    @api.depends("vm_exec_last_id", "vm_exec_last_id.is_running")
    def _compute_has_vm_exec_running(self):
        for rec in self:
            rec.has_vm_exec_running = (
                rec.vm_exec_last_id and rec.vm_exec_last_id.is_running
            )

    def action_start_vm(self):
        for rec in self:
            # TODO use default workspace from system for contexte dev
            if not rec.system_id:
                _logger.warning(
                    f"Missing system_id into devops.deploy.vm id {rec.id}"
                )
                continue
            cmd = f"vboxmanage startvm {rec.identifiant} --type gui"
            out, status = rec.system_id.execute_with_result(
                cmd, None, return_status=True
            )
            if status != 0:
                # TODO raise error execution
                _logger.error(f"Problem to start vm {rec.identifiant} : {out}")
            else:
                _logger.info(f"VM start: {out}")
                value = {
                    "vm_id": rec.id,
                    "is_running": True,
                }
                vm_exec_id = self.env["devops.deploy.vm.exec"].create(value)
                rec.vm_exec_last_id = vm_exec_id.id
                # Find associate system if exist
                # TODO use one2many instead? Not existing, crash with CG
                system_vm_id = self.env["devops.system"].search(
                    [("devops_deploy_vm_id", "=", rec.id)], limit=1
                )
                if system_vm_id:
                    max_timeout_total = 60
                    max_timeout_system = 20
                    max_timeout = max_timeout_total - max_timeout_system
                    _logger.info(
                        "Waiting system ssh connection test, max"
                        f" {max_timeout_total} seconds."
                    )
                    # Sleep to give time to start network bridge
                    time.sleep(max_timeout_system)
                    # Start a SSH test
                    try:
                        # Just open and close the connection
                        with system_vm_id.ssh_connection(timeout=max_timeout):
                            _logger.info(
                                "Succeed to open system name"
                                f" {system_vm_id.name}"
                            )
                    except paramiko.AuthenticationException as e:
                        _logger.error(
                            f"Fail to open system name {system_vm_id.name},"
                            " need good authentification."
                        )
                        _logger.error(e)
                    except Exception as e:
                        _logger.error(
                            f"Fail to open system name {system_vm_id.name}"
                        )
                        _logger.error(e)

    def action_stop_vm(self):
        for rec in self:
            # TODO use default workspace from system for contexte dev
            if not rec.system_id:
                _logger.warning(
                    f"Missing system_id into devops.deploy.vm id {rec.id}"
                )
                continue
            cmd = f"vboxmanage controlvm {rec.identifiant} poweroff"
            out, status = rec.system_id.execute_with_result(
                cmd, None, return_status=True
            )
            if status != 0:
                # TODO raise error execution
                # TODO validate before status before launch poweroff
                # Since note validate before status, believe it's stopped
                if rec.vm_exec_last_id:
                    rec.vm_exec_last_id.is_running = False
                _logger.error(f"Problem to stop vm {rec.identifiant} : {out}")
            else:
                _logger.info(f"VM stop: {out}")
                if rec.vm_exec_last_id:
                    rec.vm_exec_last_id.is_running = False
                # Find associate system if exist
                # TODO use one2many instead? Not existing, crash with CG
                system_vm_id = self.env["devops.system"].search(
                    [("devops_deploy_vm_id", "=", rec.id)], limit=1
                )
                if system_vm_id:
                    system_vm_id.ssh_connection_status = False
