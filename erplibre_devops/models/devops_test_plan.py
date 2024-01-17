from odoo import _, api, fields, models


class DevopsTestPlan(models.Model):
    _name = "devops.test.plan"
    _description = "devops_test_plan"

    name = fields.Char()
