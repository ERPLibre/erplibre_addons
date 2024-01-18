from odoo import _, api, fields, models


class DevopsTestCaseExec(models.Model):
    _name = "devops.test.case.exec"
    _description = "devops_test_case_exec"

    name = fields.Char()
