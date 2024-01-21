import logging

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


class DevopsTestPlanExec(models.Model):
    _name = "devops.test.plan.exec"
    _description = "devops_test_plan_exec"

    name = fields.Char()

    execution_is_finished = fields.Boolean(
        help=(
            "Will be true when the test plan execution is finish to be"
            " execute."
        )
    )

    global_success = fields.Boolean(
        compute="_compute_global_success",
        store=True,
        help="Global result",
    )

    test_plan_id = fields.Many2one(
        comodel_name="devops.test.plan",
        string="Test plan",
    )

    exec_ids = fields.One2many(
        comodel_name="devops.test.case.exec",
        inverse_name="test_plan_exec_id",
        string="Execution",
    )

    @api.depends("exec_ids.is_pass")
    def _compute_global_success(self):
        for rec in self:
            if rec.exec_ids:
                rec.global_success = all([a.is_pass for a in rec.exec_ids])
            else:
                rec.global_success = False
