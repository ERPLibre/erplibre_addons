from odoo import _, api, fields, models


class DevopsTestCaseExec(models.Model):
    _name = "devops.test.case.exec"
    _description = "devops_test_case_exec"

    name = fields.Char()

    is_finish = fields.Boolean(help="Execution is finish")

    is_pass = fields.Boolean(help="True test pass, else test fail.")

    log = fields.Text(help="Log for the test")

    test_plan_exec_id = fields.Many2one(
        comodel_name="devops.test.plan.exec",
        string="Plan",
        ondelete="cascade",
    )
