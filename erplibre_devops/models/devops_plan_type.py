from odoo import _, api, fields, models


class DevopsPlanType(models.Model):
    _name = "devops.plan.type"
    _description = "devops_plan_type"

    name = fields.Char()

    lvl1_id = fields.Many2one(
        comodel_name="devops.plan.type.lvl1", string="Lvl 1"
    )

    lvl2_id = fields.Many2one(
        comodel_name="devops.plan.type.lvl2", string="Lvl 2"
    )

    lvl3_id = fields.Many2one(
        comodel_name="devops.plan.type.lvl3", string="Lvl 3"
    )

    state_name = fields.Char(required=True, help="With this state name, will show wizard state associate to this plan type.")
