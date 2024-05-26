from odoo import _, api, fields, models


class DevopsPlanProjectPptx(models.Model):
    _name = "devops.plan.project.pptx"
    _description = "devops_plan_project_pptx"

    name = fields.Char()
