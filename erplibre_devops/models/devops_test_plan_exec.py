from odoo import _, api, fields, models


class DevopsTestPlanExec(models.Model):
    _name = "devops.test.plan.exec"
    _description = "devops_test_plan_exec"

    name = fields.Char()
