import logging

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


class DevopsTestPlan(models.Model):
    _name = "devops.test.plan"
    _description = "General test plan -> will choose a plan"

    name = fields.Char()

    test_case_ids = fields.One2many(
        comodel_name="devops.test.case",
        inverse_name="test_plan_id",
        string="Test cases",
    )

    test_plan_exec_ids = fields.One2many(
        comodel_name="devops.test.plan.exec",
        inverse_name="test_plan_id",
        string="Test plan executions",
    )
