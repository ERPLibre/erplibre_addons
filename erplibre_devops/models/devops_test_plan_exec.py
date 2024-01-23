import asyncio
import logging
import os
import sys
from typing import Tuple

import pytz

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)
# TODO use system instead
# Get root of ERPLibre
new_path = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
sys.path.append(new_path)

from script import lib_asyncio


class DevopsTestPlanExec(models.Model):
    _name = "devops.test.plan.exec"
    _description = "devops_test_plan_exec"

    name = fields.Char()

    execution_is_finished = fields.Boolean(
        readonly=True,
        help=(
            "Will be true when the test plan execution is finish to be"
            " execute."
        ),
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

    result_ids = fields.One2many(
        comodel_name="devops.test.result",
        inverse_name="test_plan_exec_id",
        string="Results",
        readonly=True,
    )

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

    @api.depends("exec_ids", "exec_ids.is_pass")
    def _compute_global_success(self):
        for rec in self:
            if rec.exec_ids:
                rec.global_success = all([a.is_pass for a in rec.exec_ids])
            else:
                rec.global_success = False

    @api.multi
    def execute_test_action(self, ctx=None):
        lst_test_cb_method_cg_id = []
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
                        # lst_test_cb_method_cg_id.append(
                        #     (
                        #         test_case_id,
                        #         test_case_exec_id,
                        #         test_case_id.test_cb_method_cg_id.async_execute(),
                        #     )
                        # )
                        lst_test_cb_method_cg_id.append("True")
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
                rec.execution_is_finished = True
        # # Force compute result
        # self._compute_global_success()
        if lst_test_cb_method_cg_id:
            # Run in parallel prettier for more speed
            parallel = True
            try:
                if asyncio.get_event_loop().is_closed():
                    asyncio.set_event_loop(asyncio.new_event_loop())
            except Exception as e:
                _logger.error(e)
                # parallel = False
                asyncio.set_event_loop(asyncio.new_event_loop())
            if parallel:
                lst_cmd = ["ls /tmp", "tree /tmp"]
                loop = asyncio.get_event_loop()
                task_list = [execute_async_subprocess(a) for a in lst_cmd]
                try:
                    commands = asyncio.gather(*task_list)
                    tpl_result = loop.run_until_complete(commands)
                except RuntimeError as e:
                    print(e)
                finally:
                    loop.close()
                for result in tpl_result:
                    _logger.info("prettier " + result[0])
            else:
                print("oups")

            # lst_cb = [c for a, b, c in lst_test_cb_method_cg_id]
            # lib_asyncio.print_summary_task(lst_cb)
            # tpl_result, error_detected = lib_asyncio.execute_v2(lst_cb, debug=True)
            # # tpl_result = lib_asyncio.execute_v2(lst_test_cb_method_cg_id, use_uvloop=True)
            # if error_detected:
            #     for (
            #         test_case_id,
            #         test_case_exec_id,
            #         c,
            #     ) in lst_test_cb_method_cg_id:
            #         self.env["devops.test.result"].create(
            #             {
            #                 "name": f"Error detected execution asyncio",
            #                 "log": (
            #                     "Cannot execute asyncio, don't know why:"
            #                     f" '{test_case_id.name}'"
            #                 ),
            #                 "is_finish": True,
            #                 "is_pass": False,
            #                 "test_case_exec_id": test_case_exec_id.id,
            #             }
            #         )
            # if tpl_result:
            #     for i, (result_log, result_status) in enumerate(tpl_result):
            #         test_case_exec_id = lst_test_cb_method_cg_id[i][1]
            #         self.env["devops.test.result"].create(
            #             {
            #                 "name": f"Error detected execution asyncio",
            #                 "log": result_log,
            #                 "is_finish": True,
            #                 "is_pass": result_status == 0,
            #                 "test_case_exec_id": test_case_exec_id.id,
            #             }
            #         )
            # print("yeah")


async def execute_async_subprocess(cmd) -> Tuple[str, int]:
    process = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if stdout:
        result = stdout.decode()
    else:
        result = ""
    if stderr:
        result += stderr.decode()
    return result, 0
