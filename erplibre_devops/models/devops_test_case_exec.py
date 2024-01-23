import logging

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


class DevopsTestCaseExec(models.Model):
    _name = "devops.test.case.exec"
    _description = "devops_test_case_exec"

    name = fields.Char()

    is_finish = fields.Boolean(
        readonly=True,
        help="Execution is finish",
    )

    is_pass = fields.Boolean(
        compute="_compute_is_pass",
        store=True,
        help="True test pass, else test fail.",
    )

    log = fields.Text(help="Log for the test")

    test_plan_exec_id = fields.Many2one(
        comodel_name="devops.test.plan.exec",
        string="Plan",
        ondelete="cascade",
    )

    result_ids = fields.One2many(
        comodel_name="devops.test.result",
        inverse_name="test_case_exec_id",
        string="Results",
        readonly=True,
    )

    workspace_id = fields.Many2one(
        comodel_name="devops.workspace",
        string="Workspace",
        required=True,
    )

    @api.depends("result_ids", "result_ids.is_pass")
    def _compute_is_pass(self):
        for rec in self:
            if rec.result_ids:
                rec.is_pass = all([a.is_pass for a in rec.result_ids])
            else:
                rec.is_pass = False

    def test_breakpoint(self, ctx=None):
        lst_result_value = []
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Test plan DevOps run test",
                ctx=ctx,
            ) as rec_ws:
                bp_ids = self.env["devops.ide.breakpoint"].search([])
                if not bp_ids:
                    msg = f"List of breakpoint is empty."
                    _logger.error(msg)
                    raise exceptions.Warning(msg)
                for bp_id in bp_ids:
                    if bp_id.ignore_test:
                        continue

                    try:
                        lst_line = bp_id.get_breakpoint_info(rec_ws)
                    except Exception as e:
                        rec.is_finish = True
                        lst_result_value.append(
                            {
                                "name": f"Test breakpoint ID {bp_id.id}",
                                "log": (
                                    "Exception warning Breakpoint"
                                    f" '{bp_id.name}' : {e}"
                                ),
                                "is_finish": True,
                                "is_pass": False,
                                "test_case_exec_id": rec.id,
                            }
                        )
                        continue
                    if not lst_line:
                        msg = (
                            f"Cannot find breakpoint {bp_id.name} for file"
                            f" {bp_id.filename}, key : {bp_id.keyword}"
                        )
                        rec.is_finish = True
                        lst_result_value.append(
                            {
                                "name": f"Test breakpoint ID {bp_id.id}",
                                "log": msg,
                                "is_finish": True,
                                "is_pass": False,
                                "test_case_exec_id": rec.id,
                            }
                        )
                        continue
                    if not bp_id.is_multiple and (
                        len(lst_line) != 1 or len(lst_line[0][1]) > 1
                    ):
                        msg = (
                            f"Breakpoint {bp_id.name} is not suppose to find"
                            f" multiple line and got '{lst_line}' into file"
                            f" '{bp_id.filename}' with key '{bp_id.keyword}'"
                        )
                        rec.is_finish = True
                        lst_result_value.append(
                            {
                                "name": f"Test breakpoint ID {bp_id.id}",
                                "log": msg,
                                "is_finish": True,
                                "is_pass": False,
                                "test_case_exec_id": rec.id,
                            }
                        )
                        continue
                    rec.is_finish = True
                    lst_result_value.append(
                        {
                            "name": f"Test breakpoint ID {bp_id.id}",
                            "is_finish": True,
                            "is_pass": True,
                            "test_case_exec_id": rec.id,
                        }
                    )
        self.env["devops.test.result"].create(lst_result_value)
