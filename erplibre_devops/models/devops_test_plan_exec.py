import logging

import pytz

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


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
        readonly=True, help="True when start execution."
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
                    if hasattr(
                        test_case_exec_id, test_case_id.test_cb_method_name
                    ):
                        cb_method = getattr(
                            test_case_exec_id, test_case_id.test_cb_method_name
                        )
                        cb_method(ctx=rec_ws._context)
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
