from odoo import _, api, fields, models


class DevopsTestExec(models.Model):
    _name = "devops.test.exec"
    _description = "devops_test_exec"

    name = fields.Char()
