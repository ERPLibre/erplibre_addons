from odoo import _, api, fields, models


class DevopsPlanTypeLvl1(models.Model):
    _name = "devops.plan.type.lvl1"
    _description = "devops_plan_type_lvl1"

    name = fields.Char()
