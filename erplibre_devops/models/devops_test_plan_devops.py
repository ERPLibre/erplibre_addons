from odoo import _, api, fields, models


class DevopsTestPlanDevops(models.Model):
    _name = "devops.test.plan.devops"
    _description = "devops_test_plan_devops"

    name = fields.Char()
