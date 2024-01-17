from odoo import _, api, fields, models


class DevopsTestCgExec(models.Model):
    _name = "devops.test.cg.exec"
    _description = "devops_test_cg_exec"

    name = fields.Char()
