from odoo import _, api, fields, models


class DevopsTestCase(models.Model):
    _name = "devops.test.case"
    _description = "devops_test_case"

    name = fields.Char()
