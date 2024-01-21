from odoo import _, api, fields, models


class DevopsTestResult(models.Model):
    _name = "devops.test.result"
    _description = "devops_test_result"

    name = fields.Char()

    log = fields.Text()

    is_finish = fields.Boolean()

    is_pass = fields.Boolean()

    test_case_exec_id = fields.Many2one(
        comodel_name="devops.test.case.exec",
    )

    test_plan_exec_id = fields.Many2one(
        comodel_name="devops.test.plan.exec",
        string="Plan",
        related="test_case_exec_id.test_plan_exec_id",
        readonly=True,
    )
