from odoo import _, api, fields, models


class DevopsTestPlan(models.Model):
    _name = "devops.test.plan"
    _description = "General test plan -> will choose a plan"

    name = fields.Char()

    # run_all_test = fields.Boolean()
