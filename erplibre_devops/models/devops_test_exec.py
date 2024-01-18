from odoo import _, api, fields, models


class DevopsTestExec(models.Model):
    _name = "devops.test.exec"
    _description = "devops_test_exec"

    name = fields.Char()

    is_finish = fields.Boolean(help="Execution is finish")

    is_pass = fields.Boolean(help="True test pass, else test fail.")

    log = fields.Text(help="Log for the test")

    test_plan_id = fields.Many2one(
        comodel_name="devops.test.plan",
        string="Plan",
        ondelete="cascade",
    )
