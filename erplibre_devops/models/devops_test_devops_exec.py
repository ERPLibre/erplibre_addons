from odoo import _, api, fields, models


class DevopsTestDevopsExec(models.Model):
    _name = "devops.test.devops.exec"
    _description = "execution devops test"

    name = fields.Char()

    is_finish = fields.Boolean(help="Execution is finish")

    is_pass = fields.Boolean(help="True test pass, else test fail.")

    log = fields.Text(help="Log for the test")

    test_plan_devops_id = fields.Many2one(
        comodel_name="devops.test.plan.devops",
        string="Plan",
        ondelete="cascade",
    )
