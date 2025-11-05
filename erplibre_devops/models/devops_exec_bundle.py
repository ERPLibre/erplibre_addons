# Copyright 2023 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import timedelta

from odoo import _, api, exceptions, fields, models, tools

_logger = logging.getLogger(__name__)


class DevopsExecBundle(models.Model):
    _name = "devops.exec.bundle"
    _description = (
        "Bundle of execution process, package of multiple process to"
        " regroup it."
    )

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )

    description = fields.Char()

    parent_id = fields.Many2one(
        comodel_name="devops.exec.bundle",
        string="Parent bundle",
        index=True,
    )

    child_ids = fields.One2many(
        comodel_name="devops.exec.bundle",
        inverse_name="parent_id",
        string="Child bundle",
    )

    active = fields.Boolean(default=True)

    exec_start_date = fields.Datetime(
        string="Execution start date",
        readonly=True,
        default=fields.Datetime.now,
    )

    exec_stop_date = fields.Datetime(
        string="Execution stop date",
        readonly=True,
    )

    exec_time_duration = fields.Integer(
        string="Execution time duration",
        compute="_compute_exec_time_duration",
        store=True,
        help="Time in second, duration of execution",
    )

    time_duration_result = fields.Char(
        compute="_compute_time_duration_result",
        store=True,
    )

    execution_finish = fields.Boolean(
        compute="_compute_execution_finish",
        store=True,
    )

    devops_workspace = fields.Many2one(
        comodel_name="devops.workspace",
        readonly=True,
    )

    devops_exec_ids = fields.One2many(
        comodel_name="devops.exec",
        inverse_name="devops_exec_bundle_id",
        string="Executions",
        readonly=True,
    )

    devops_exec_error_ids = fields.One2many(
        comodel_name="devops.exec.error",
        inverse_name="devops_exec_bundle_id",
        string="Executions errors",
        readonly=True,
    )

    devops_exec_parent_error_ids = fields.One2many(
        comodel_name="devops.exec.error",
        inverse_name="parent_root_exec_bundle_id",
        string="Executions parent errors",
        readonly=True,
    )

    devops_new_project_ids = fields.One2many(
        comodel_name="devops.cg.new_project",
        inverse_name="devops_exec_bundle_id",
        string="New projects",
        readonly=True,
    )

    def get_last_exec(self):
        self.ensure_one()
        if self.devops_exec_ids:
            return self.devops_exec_ids[-1]

    @api.model
    def get_parent_root(self):
        rec = self
        while rec.parent_id:
            rec = rec.parent_id
        return rec

    @api.depends(
        "devops_workspace",
        "time_duration_result",
        "execution_finish",
        "description",
    )
    def _compute_name(self):
        for rec in self:
            if not isinstance(rec.id, models.NewId):
                rec.name = f"{rec.id:03d}"
            else:
                rec.name = ""
            # rec.name += f"workspace {rec.devops_workspace.id}"
            if rec.description:
                rec.name += f" '{rec.description}'"

    @api.depends("exec_start_date", "exec_stop_date")
    def _compute_exec_time_duration(self):
        for rec in self:
            if rec.exec_start_date and rec.exec_stop_date:
                rec.exec_time_duration = (
                    rec.exec_stop_date - rec.exec_start_date
                ).total_seconds()
            else:
                rec.exec_time_duration = False

    @api.depends("exec_stop_date")
    def _compute_execution_finish(self):
        for rec in self:
            rec.execution_finish = bool(rec.exec_stop_date)

    @api.depends("exec_time_duration")
    def _compute_time_duration_result(self):
        for rec in self:
            rec.time_duration_result = (
                f" {'{:0>8}'.format(str(timedelta(seconds=rec.exec_time_duration)))}"
            )
