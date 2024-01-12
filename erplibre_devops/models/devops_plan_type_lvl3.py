from odoo import _, api, fields, models


class DevopsPlanTypeLvl3(models.Model):
    _name = "devops.plan.type.lvl3"
    _description = "devops_plan_type_lvl3"

    name = fields.Char()
