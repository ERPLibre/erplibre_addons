import logging

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


class DevopsTestPlan(models.Model):
    _name = "devops.test.plan"
    _description = "General test plan -> will choose a plan"

    name = fields.Char()

    # workspace_id = fields.Many2one(
    #     comodel_name="devops.workspace",
    #     string="Workspace",
    #     required=True,
    # )

