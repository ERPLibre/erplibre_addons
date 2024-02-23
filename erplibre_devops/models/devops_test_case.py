import logging

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


class DevopsTestCase(models.Model):
    _name = "devops.test.case"
    _description = "devops_test_case"

    name = fields.Char()

    active = fields.Boolean(default=True)

    test_plan_id = fields.Many2one(
        comodel_name="devops.test.plan",
        string="Test plan",
    )

    test_cb_method_cg_id = fields.Many2one(
        comodel_name="devops.cg.test.case",
        string="Method CG test case",
    )

    test_cb_method_name = fields.Char(
        string="Method name",
        help="Will call this method name",
    )

    note = fields.Text()
