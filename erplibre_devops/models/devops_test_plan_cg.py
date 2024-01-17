from odoo import _, api, fields, models


class DevopsTestPlanCg(models.Model):
    _name = "devops.test.plan.cg"
    _description = "Test plan CG -> choose devops.test.cg.exec to create"

    name = fields.Char()
