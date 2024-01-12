from odoo import _, api, fields, models


class DevopsPlanTypeLvl2(models.Model):
    _name = "devops.plan.type.lvl2"
    _description = "devops_plan_type_lvl2"

    name = fields.Char()
