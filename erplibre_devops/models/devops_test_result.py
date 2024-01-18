from odoo import _, api, fields, models


class DevopsTestResult(models.Model):
    _name = "devops.test.result"
    _description = "devops_test_result"

    name = fields.Char()
