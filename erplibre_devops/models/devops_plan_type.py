from odoo import _, api, fields, models


class DevopsPlanType(models.Model):
    _name = "devops.plan.type"
    _description = "devops_plan_type"

    name = fields.Char()
