from odoo import _, api, fields, models


class DevopsTestPlanCg(models.Model):
    _name = "devops.test.plan.cg"
    _description = "devops_test_plan_cg"

    name = fields.Char()
