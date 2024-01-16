# Copyright 2023 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import timedelta

from odoo import _, api, exceptions, fields, models, tools

_logger = logging.getLogger(__name__)


class DevopsExec(models.Model):
    _name = "devops.exec"
    _description = "Execution process"

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )

    active = fields.Boolean(default=True)

    cmd = fields.Char()

    exec_status = fields.Integer(help="Return status of execution. 0=success")

    exec_start_date = fields.Datetime(
        string="Execution start date",
        default=fields.Datetime.now,
    )

    exec_stop_date = fields.Datetime(string="Execution stop date")

    exec_time_duration = fields.Integer(
        string="Execution time duration",
        compute="_compute_exec_time_duration",
        store=True,
        help="Time in second, duration of execution",
    )

    exec_filename = fields.Char(
        string="Execution filename",
        help="Execution information, where it's called.",
    )

    exec_keyword = fields.Char(
        string="Execution keyword",
        help="Execution information, where it's called.",
    )

    exec_line_number = fields.Integer(
        string="Execution line number",
        help="Execution information, where it's called.",
    )

    folder = fields.Char()

    ide_breakpoint = fields.Many2one(
        comodel_name="devops.ide.breakpoint",
        help="Associate a breakpoint to this execution.",
    )

    time_duration_result = fields.Char(
        compute="_compute_time_duration_result",
        store=True,
    )

    execution_finish = fields.Boolean(
        compute="_compute_execution_finish",
        store=True,
    )

    module = fields.Char()

    new_project_id = fields.Many2one(
        comodel_name="devops.cg.new_project",
        string="New Project",
    )

    devops_workspace = fields.Many2one(comodel_name="devops.workspace")

    devops_exec_error_ids = fields.One2many(
        comodel_name="devops.exec.error",
        inverse_name="devops_exec_id",
        string="Executions errors",
    )

    log_error_ids = fields.One2many(
        comodel_name="devops.log.error",
        inverse_name="exec_id",
        string="Log errors",
    )

    log_warning_ids = fields.One2many(
        comodel_name="devops.log.warning",
        inverse_name="exec_id",
        string="Log warnings",
    )

    devops_exec_bundle_id = fields.Many2one(
        comodel_name="devops.exec.bundle",
        string="Devops Exec Bundle",
    )

    log_stdin = fields.Text()

    log_stdout = fields.Text()

    log_stderr = fields.Text()

    log_all = fields.Text(
        compute="_compute_log_all",
        store=True,
    )

    @api.depends(
        "devops_workspace",
        "module",
        "time_duration_result",
        "execution_finish",
    )
    def _compute_name(self):
        for rec in self:
            if not isinstance(rec.id, models.NewId):
                rec.name = f"{rec.id}: "
            else:
                rec.name = ""
            rec.name += f"workspace {rec.devops_workspace.id}"
            if rec.module:
                rec.name += f" - {rec.module}"

    @api.depends("exec_start_date", "exec_stop_date")
    def _compute_exec_time_duration(self):
        for rec in self:
            if rec.exec_start_date and rec.exec_stop_date:
                rec.exec_time_duration = (
                    rec.exec_stop_date - rec.exec_start_date
                ).total_seconds()
            else:
                rec.exec_time_duration = False

    @api.depends("log_stdout", "log_stderr")
    def _compute_log_all(self):
        for rec in self:
            rec.log_all = ""
            if rec.log_stdout:
                rec.log_all += rec.log_stdout
            if rec.log_stderr:
                rec.log_all += rec.log_stderr

    def compute_error(self):
        for rec in self:
            # extract error/warning
            # TODO maybe need to fix «has no access rules, consider adding one.»
            lst_item_ignore_error = [
                "fetchmail_notify_error_to_sender",
                'odoo.sql_db: bad query: ALTER TABLE "db_backup" DROP'
                ' CONSTRAINT "db_backup_db_backup_name_unique"',
                'ERROR: constraint "db_backup_db_backup_name_unique" of'
                ' relation "db_backup" does not exist',
                'odoo.sql_db: bad query: ALTER TABLE "db_backup" DROP'
                ' CONSTRAINT "db_backup_db_backup_days_to_keep_positive"',
                'ERROR: constraint "db_backup_db_backup_days_to_keep_positive"'
                ' of relation "db_backup" does not exist',
                "odoo.addons.code_generator.extractor_module_file: Ignore next"
                " error about ALTER TABLE DROP CONSTRAINT.",
                "has no access rules, consider adding one.",
                "Failed to load registry",
            ]
            keyword_error_to_remove = [
                "devops.cg.field.has_error",
                "devops.exec.error.name",
                "devops.workspace.devops_exec_error_count",
                "views/devops_exec_error.xml",
                "devops_exec_error.py",
                "devops_log_error.py",
            ]
            lst_item_ignore_warning = [
                "have the same label:",
                "odoo.addons.code_generator.extractor_module_file: Ignore next"
                " error about ALTER TABLE DROP CONSTRAINT.",
            ]
            keyword_warning_to_remove = [
                "devops_log_warning.py",
            ]
            lst_warning_key = [
                "WARNING",
                "warning:",
            ]
            lst_error_key = ["ERROR", "error:"]
            for line in rec.log_all.split("\n"):
                # line_fix = line.lower()
                line_fix = line
                for key_to_remove in keyword_error_to_remove:
                    line_fix = line_fix.replace(key_to_remove, "")
                for key_to_remove in keyword_warning_to_remove:
                    line_fix = line_fix.replace(key_to_remove, "")

                # Search error or warning
                for key in lst_error_key:
                    if key in line_fix:
                        has_error = True
                        break
                else:
                    has_error = False
                for key in lst_warning_key:
                    if key in line_fix:
                        has_warning = True
                        break
                else:
                    has_warning = False

                if has_error:
                    for ignore_item in lst_item_ignore_error:
                        if ignore_item in line:
                            break
                    else:
                        v = {
                            "name": line.strip(),
                            "exec_id": rec.id,
                        }
                        if rec.new_project_id:
                            v["new_project_id"] = rec.new_project_id.id
                        self.env["devops.log.error"].create(v)

                if has_warning:
                    for ignore_item in lst_item_ignore_warning:
                        if ignore_item in line:
                            break
                    else:
                        v = {
                            "name": line.strip(),
                            "exec_id": rec.id,
                        }
                        if rec.new_project_id:
                            v["new_project_id"] = rec.new_project_id.id
                        self.env["devops.log.warning"].create(v)

    @api.depends("exec_stop_date")
    def _compute_execution_finish(self):
        for rec in self:
            rec.execution_finish = bool(rec.exec_stop_date)

    @api.depends("exec_time_duration")
    def _compute_time_duration_result(self):
        for rec in self:
            rec.time_duration_result = (
                f" {'{:0>8}'.format(str(timedelta(seconds=rec.exec_time_duration)))}"
            )

    @api.multi
    def open_file_ide(self):
        ws_id = self.env["devops.workspace"].search(
            [("is_me", "=", True)], limit=1
        )
        if not ws_id:
            return
        for o_rec in self:
            with ws_id.devops_create_exec_bundle("Open file IDE") as rec_ws:
                rec_ws.with_context(
                    breakpoint_id=o_rec.ide_breakpoint.id
                ).ide_pycharm.action_start_pycharm()
