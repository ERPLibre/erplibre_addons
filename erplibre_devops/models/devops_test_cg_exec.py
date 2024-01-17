from odoo import _, api, fields, models


class DevopsTestCgExec(models.Model):
    _name = "devops.test.cg.exec"
    _description = "Execution test CG"

    name = fields.Char()
