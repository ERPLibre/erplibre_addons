import json
import logging
import os
import uuid

import pytz

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)

LST_CONSOLE_REPLACE_HTML = [
    ("\n", "<br />"),
    ("\033[0m", "</span>"),
    ("\033[0;30m", '<span style="color: black">'),
    ("\033[0;31m", '<span style="color: red">'),
    ("\033[0;32m", '<span style="color: green">'),
    ("\033[0;33m", '<span style="color: yellow">'),
    ("\033[0;34m", '<span style="color: blue">'),
    ("\033[0;35m", '<span style="color: purple">'),
    ("\033[0;36m", '<span style="color: cyan">'),
    ("\033[0;37m", '<span style="color: white">'),
    ("\033[1m", '<span style="font-weight: bold">'),
    ("\033[1;30m", '<span style="font-weight: bold;color: black">'),
    ("\033[1;31m", '<span style="font-weight: bold;color: red">'),
    ("\033[1;32m", '<span style="font-weight: bold;color: green">'),
    ("\033[1;33m", '<span style="font-weight: bold;color: yellow">'),
    ("\033[1;34m", '<span style="font-weight: bold;color: blue">'),
    ("\033[1;35m", '<span style="font-weight: bold;color: purple">'),
    ("\033[1;36m", '<span style="font-weight: bold;color: cyan">'),
    ("\033[1;37m", '<span style="font-weight: bold;color: white">'),
    ("\033[4;30m", '<span style="text-decoration: underline;color: black">'),
    ("\033[4;31m", '<span style="text-decoration: underline;color: red">'),
    ("\033[4;32m", '<span style="text-decoration: underline;color: green">'),
    ("\033[4;33m", '<span style="text-decoration: underline;color: yellow">'),
    ("\033[4;34m", '<span style="text-decoration: underline;color: blue">'),
    ("\033[4;35m", '<span style="text-decoration: underline;color: purple">'),
    ("\033[4;36m", '<span style="text-decoration: underline;color: cyan">'),
    ("\033[4;37m", '<span style="text-decoration: underline;color: white">'),
]


class DevopsTestPlanExec(models.Model):
    _name = "devops.test.plan.exec"
    _description = "devops_test_plan_exec"

    name = fields.Char()

    active = fields.Boolean(default=True)

    execution_is_finished = fields.Boolean(
        readonly=True,
        help=(
            "Will be true when the test plan execution is finish to be"
            " execute."
        ),
    )

    time_execution = fields.Float(
        help="Delay of execution, empty and execution is not finish."
    )

    execution_is_launched = fields.Boolean(
        readonly=True,
        help="True when start execution.",
    )

    global_success = fields.Boolean(
        compute="_compute_global_success",
        store=True,
        help="Global result",
    )

    test_plan_id = fields.Many2one(
        comodel_name="devops.test.plan",
        string="Test plan",
    )

    exec_id = fields.Many2one(
        comodel_name="devops.exec",
        string="Exec id",
        readonly=True,
    )

    test_case_ids = fields.Many2many(
        comodel_name="devops.test.case",
        string="Test case",
    )

    exec_ids = fields.One2many(
        comodel_name="devops.test.case.exec",
        inverse_name="test_plan_exec_id",
        string="Execution",
        readonly=True,
    )

    log = fields.Text()

    log_html = fields.Html(store=True, compute="_compute_log_html")

    result_ids = fields.One2many(
        comodel_name="devops.test.result",
        inverse_name="test_plan_exec_id",
        string="Results",
        readonly=True,
    )

    coverage = fields.Boolean(help="For CG test")

    keep_cache = fields.Boolean(help="For CG test")

    no_parallel = fields.Boolean(help="For CG test")

    debug = fields.Boolean(help="For CG test")

    has_configuration = fields.Boolean(
        compute="_compute_has_configuration",
        store=True,
    )

    ignore_init_check_git = fields.Boolean(help="For CG test")

    max_process = fields.Integer(help="For CG test")

    workspace_id = fields.Many2one(
        comodel_name="devops.workspace",
        string="Workspace",
        required=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name"):
                tzinfo = pytz.timezone(self.env.user.sudo().tz or "UTC")
                vals["name"] = (
                    "Test plan"
                    f" {fields.datetime.now(tzinfo).strftime('%Y-%m-%d %H:%M:%S')}"
                )
        result = super().create(vals_list)
        return result

    @api.multi
    @api.depends("log")
    def _compute_log_html(self):
        for rec in self:
            if rec.log:
                log_html = rec.log.strip()
                for rep_str_from, rep_str_to in LST_CONSOLE_REPLACE_HTML:
                    log_html = log_html.replace(rep_str_from, rep_str_to)
                rec.log_html = f"<p>{log_html}</p>"

    @api.depends("test_plan_id", "test_case_ids")
    def _compute_has_configuration(self):
        for rec in self:
            # Show configuration for test plan cg
            rec.has_configuration = False
            if rec.test_plan_id and rec.test_plan_id == self.env.ref(
                "erplibre_devops.devops_test_plan_cg"
            ):
                rec.has_configuration = True
            if rec.test_case_ids:
                for test_case_id in rec.test_case_ids:
                    if (
                        test_case_id.test_plan_id
                        and test_case_id.test_plan_id
                        == self.env.ref("erplibre_devops.devops_test_plan_cg")
                    ):
                        rec.has_configuration = True

    @api.depends("exec_ids", "exec_ids.is_pass")
    def _compute_global_success(self):
        for rec in self:
            if rec.exec_ids:
                rec.global_success = all([a.is_pass for a in rec.exec_ids])
            else:
                rec.global_success = False

    @api.multi
    def execute_test_action(self, ctx=None):
        lst_test_erplibre_async = []
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Execute - test plan exec", ctx=ctx
            ) as rec_ws:
                if rec.execution_is_launched:
                    continue
                if not rec.test_plan_id and not rec.test_case_ids:
                    raise exceptions.Warning(
                        "Missing test plan or test cases."
                    )
                rec.execution_is_launched = True
                test_case_ids = (
                    rec.test_plan_id.test_case_ids
                    if rec.test_plan_id
                    else rec.test_case_ids
                )
                for test_case_id in test_case_ids:
                    test_case_exec_id = self.env[
                        "devops.test.case.exec"
                    ].create(
                        {
                            "name": test_case_id.name,
                            "test_plan_exec_id": rec.id,
                            "workspace_id": rec_ws.id,
                            "test_case_id": test_case_id.id,
                        }
                    )
                    if test_case_id.test_cb_method_name and hasattr(
                        test_case_exec_id, test_case_id.test_cb_method_name
                    ):
                        cb_method = getattr(
                            test_case_exec_id, test_case_id.test_cb_method_name
                        )
                        cb_method(ctx=rec_ws._context)
                    elif test_case_id.test_cb_method_cg_id:
                        lst_test_erplibre_async.append(
                            (
                                test_case_exec_id,
                                test_case_id.test_cb_method_cg_id,
                            )
                        )
                    else:
                        self.env["devops.test.result"].create(
                            {
                                "name": f"Search method",
                                "log": (
                                    "Cannot find method"
                                    f" '{test_case_id.test_cb_method_name}'"
                                ),
                                "is_finish": True,
                                "is_pass": False,
                                "test_case_exec_id": test_case_exec_id.id,
                            }
                        )
                # TODO support better execution_is_finished for async, when execution is really finish
                rec.execution_is_finished = True
        # # Force compute result
        # self._compute_global_success()
        if lst_test_erplibre_async:
            lst_test = []
            test_plan_exec_id = None
            for test_case_exec_id, test_case_cg_id in lst_test_erplibre_async:
                test_name = (
                    test_case_exec_id.name.strip().replace(" ", "_").lower()
                )
                test_plan_exec_id = test_case_exec_id.test_plan_exec_id
                test_plan_id = test_case_exec_id.test_plan_exec_id.test_plan_id
                test_case_id = test_case_exec_id.test_case_id
                model_test = {
                    "test_name": test_name,
                }
                if test_case_cg_id.sequence_test:
                    model_test["sequence"] = test_case_cg_id.sequence_test
                if test_case_cg_id.note:
                    model_test["note"] = test_case_cg_id.note
                if test_case_cg_id.run_mode == "command":
                    model_test["run_command"] = True
                    if test_case_cg_id.script_path:
                        model_test["script"] = test_case_cg_id.script_path
                    else:
                        self.env["devops.test.result"].create(
                            {
                                "name": (
                                    "Missing field 'script_path' for test"
                                    f" {test_name}."
                                ),
                                "is_finish": False,
                                "is_pass": False,
                                "test_case_exec_id": test_case_exec_id.id,
                            }
                        )
                        continue
                else:
                    model_test["run_test_exec"] = True
                    model_test[
                        "path_module_check"
                    ] = test_case_cg_id.path_module_check
                    model_test[
                        "run_in_sandbox"
                    ] = test_case_cg_id.run_in_sandbox
                    if test_case_cg_id.search_class_module:
                        model_test[
                            "search_class_module"
                        ] = test_case_cg_id.search_class_module
                    if test_case_cg_id.file_to_restore:
                        model_test[
                            "file_to_restore"
                        ] = test_case_cg_id.file_to_restore
                    if test_case_cg_id.file_to_restore_origin:
                        model_test[
                            "file_to_restore_origin"
                        ] = test_case_cg_id.file_to_restore_origin
                    if test_case_cg_id.install_path:
                        model_test[
                            "install_path"
                        ] = test_case_cg_id.install_path
                    if test_case_cg_id.restore_db_image_name:
                        model_test[
                            "restore_db_image_name"
                        ] = test_case_cg_id.restore_db_image_name
                    if test_case_cg_id.generated_path:
                        model_test[
                            "generated_path"
                        ] = test_case_cg_id.generated_path
                    if test_case_cg_id.script_after_init_check:
                        model_test[
                            "script_after_init_check"
                        ] = test_case_cg_id.script_after_init_check
                    if test_case_cg_id.module_generated:
                        model_test["generated_module"] = ",".join(
                            [a.name for a in test_case_cg_id.module_generated]
                        )
                    if test_case_cg_id.module_init_ids:
                        model_test["init_module_name"] = ",".join(
                            [a.name for a in test_case_cg_id.module_init_ids]
                        )
                    if test_case_cg_id.module_tested:
                        model_test["tested_module"] = ",".join(
                            [a.name for a in test_case_cg_id.module_tested]
                        )
                lst_test.append(model_test)
            json_model = json.dumps({"lst_test": lst_test}).replace('"', '\\"')
            path_mkdir_log_external = os.path.join(
                "/",
                "tmp",
                f"erplibre_devops_testcase_cg_log_{uuid.uuid4()}",
            )
            # TODO store this variable into test plan execution information
            exec_id = rec_ws.execute(
                cmd=f"mkdir -p '{path_mkdir_log_external}'"
            )
            if exec_id.exec_status:
                # TODO test_case_exec_id is a wrong association, create a testcase for general execution (async)
                self.env["devops.test.result"].create(
                    {
                        "name": f"Cannot mkdir {path_mkdir_log_external}",
                        "log": exec_id.log_all.strip(),
                        "is_finish": True,
                        "is_pass": False,
                        "test_case_exec_id": test_case_exec_id.id,
                    }
                )
            pre_cmd_run_test = ""
            if test_plan_exec_id.coverage:
                pre_cmd_run_test += "--coverage "
            if test_plan_exec_id.keep_cache:
                pre_cmd_run_test += "--keep_cache "
            if test_plan_exec_id.no_parallel:
                pre_cmd_run_test += "--no_parallel "
            if test_plan_exec_id.ignore_init_check_git:
                pre_cmd_run_test += "--ignore_init_check_git "
            if test_plan_exec_id.max_process:
                pre_cmd_run_test += (
                    f"--max_process={test_plan_exec_id.max_process} "
                )
            if test_plan_exec_id.debug:
                pre_cmd_run_test += "--debug "
            cmd_run_test = (
                "./script/test/run_parallel_test.py --output_result_dir"
                f" {path_mkdir_log_external} {pre_cmd_run_test} --json_model"
                f' "{json_model}"'
            )
            # TODO associate execution per testcase exec and testplan exec
            exec_id = rec_ws.execute(
                cmd=cmd_run_test,
                to_instance=True,
            )
            if test_plan_exec_id:
                test_plan_exec_id.log = exec_id.log_all.strip()
                test_plan_exec_id.exec_id = exec_id.id
            if exec_id.exec_status:
                # Fail return error status
                self.env["devops.test.result"].create(
                    {
                        "name": f"Error execute run ERPLibre parallel test",
                        "log": exec_id.log_all.strip(),
                        "is_finish": True,
                        "is_pass": False,
                        "test_case_exec_id": test_case_exec_id.id,
                    }
                )
            for test_case_exec_id, test_case_cg_id in lst_test_erplibre_async:
                test_name = (
                    test_case_exec_id.name.strip().replace(" ", "_").lower()
                )
                path_log = os.path.join(path_mkdir_log_external, test_name)
                exec_id = rec_ws.execute(
                    cmd=f"cat {path_log}",
                )
                output = exec_id.log_all.strip()
                test_case_exec_id.log = output
                lst_output = output.split("\n")
                try:
                    status = int(lst_output[0])
                except Exception as e:
                    self.env["devops.test.result"].create(
                        {
                            "name": f"Log mal formatted - status",
                            "log": lst_output[0],
                            "is_finish": True,
                            "is_pass": False,
                            "test_case_exec_id": test_case_exec_id.id,
                        }
                    )
                    status = -1
                if status == -1:
                    continue
                test_name = lst_output[1]
                try:
                    time_exec_sec = int(float(lst_output[2]))
                except Exception as e:
                    self.env["devops.test.result"].create(
                        {
                            "name": f"Log mal formatted - time_exec_sec",
                            "log": lst_output[2],
                            "is_finish": True,
                            "is_pass": False,
                            "test_case_exec_id": test_case_exec_id.id,
                        }
                    )
                    time_exec_sec = 0
                date_log = lst_output[3]
                test_result = "PASS" if not status else "FAIL"
                self.env["devops.test.result"].create(
                    {
                        "name": (
                            f"Test result '{test_name}' - {time_exec_sec}s -"
                            f" {date_log} - {test_result}"
                        ),
                        "log": exec_id.log_all.strip(),
                        "is_finish": True,
                        "is_pass": not status,
                        "test_case_exec_id": test_case_exec_id.id,
                    }
                )
        pass
