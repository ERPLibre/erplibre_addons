# Copyright 2023 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import timedelta

from odoo import _, api, exceptions, fields, models, tools

_logger = logging.getLogger(__name__)


class DevopsExecError(models.Model):
    _name = "devops.exec.error"
    _inherit = ["mail.activity.mixin", "mail.thread"]
    _description = "Execution error"

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )

    description = fields.Char()

    escaped_tb = fields.Text(help="Traceback")

    active = fields.Boolean(default=True)

    devops_workspace = fields.Many2one(
        comodel_name="devops.workspace",
        readonly=True,
    )

    ide_breakpoint = fields.Many2one(
        comodel_name="devops.ide.breakpoint",
        help="Associate a breakpoint to this execution.",
    )

    exec_filename = fields.Char(
        string="Execution filename",
        help="Execution information, where it's called.",
    )

    exec_keyword = fields.Char(
        string="Execution keyword",
        help="Execution information, where it's called.",
    )

    exec_method = fields.Char(
        string="Execution method",
        help="Execution information, where it's called.",
    )

    exec_line_number = fields.Integer(
        string="Execution line number",
        help="Execution information, where it's called.",
    )

    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Partner",
    )

    # channel_ids = fields.Many2many(
    #     comodel_name="mail.channel",
    #     string="Channel",
    # )

    type_error = fields.Selection(
        selection=[("internal", "Internal"), ("execution", "Execution")]
    )

    line_file_tb_detected = fields.Text(
        help="Detected line to add breakpoint."
    )

    devops_exec_id = fields.Many2one(
        comodel_name="devops.exec",
        string="Devops Exec",
        readonly=True,
    )

    devops_exec_bundle_id = fields.Many2one(
        comodel_name="devops.exec.bundle",
        string="Devops Exec Bundle",
        readonly=True,
    )

    exception_name = fields.Char(string="Name of exception")

    stage_new_project_id = fields.Many2one(
        comodel_name="devops.cg.new_project.stage",
        string="Stage",
        readonly=True,
    )

    new_project_id = fields.Many2one(
        comodel_name="devops.cg.new_project",
        string="New projects",
        readonly=True,
    )

    parent_root_exec_bundle_id = fields.Many2one(
        comodel_name="devops.exec.bundle",
        string="Parent Root Exec Bundle",
        readonly=True,
    )

    find_resolution = fields.Selection(
        selection=[
            ("find", "Find"),
            ("error", "Error"),
            ("diagnostic", "Diagnostic"),
        ],
        help="If resolution to resolv the error was found.",
    )

    diagnostic_idea = fields.Text(help="Auto correction try to diagnostic.")

    @api.model_create_multi
    def create(self, vals_list):
        result = super().create(vals_list)
        for rec in result:
            # ERROR, cannot support error into error if generate error, each error will generate error
            # with rec.devops_workspace.devops_create_exec_bundle(
            #         "Create exec error"
            # ) as rec_ws:
            #     raise Exception("test error into error, no infinity")
            rec.message_post(  # pylint: disable=translation-required
                body="<p>%s</p><pre>%s</pre>"
                % (
                    _("devops.workspace '%s' failed.") % rec.description,
                    rec.escaped_tb,
                ),
                subtype_id=self.env.ref(
                    "erplibre_devops.mail_message_subtype_failure"
                ).id,
                author_id=self.env.ref("base.user_root").partner_id.id,
                # partner_ids=[(6, 0, rec.partner_ids.ids)],
                # channel_ids=[(6, 0, rec.channel_ids.ids)],
            )
            rec.devops_workspace.ide_pycharm.action_cg_setup_pycharm_debug(
                log=rec.escaped_tb.replace("&quot;", '"'), exec_error_id=rec
            )
        return result

    @api.depends("devops_workspace")
    def _compute_name(self):
        for rec in self:
            if not isinstance(rec.id, models.NewId):
                rec.name = f"{rec.id:03d}"
            else:
                rec.name = ""
            # rec.name += f"workspace {rec.devops_workspace.id}"
            if rec.description:
                rec.name += f" '{rec.description}'"

    def action_reboot_force_os_workspace(self):
        self.ensure_one()
        self.devops_workspace.with_context(
            default_exec_reboot_process=True
        ).action_reboot()

    def action_kill_workspace(self):
        self.ensure_one()
        self.devops_workspace.action_stop()

    def action_debug_new_project(self, ctx=None):
        for rec in self:
            np_ids = (
                rec.parent_root_exec_bundle_id.devops_new_project_ids.exists()
            )
            if np_ids:
                np_id = np_ids[0]
            for np_id in np_ids:
                np_id.stage_id = rec.stage_new_project_id.id
                np_id.action_new_project_debug(ctx=None)

    def action_kill_pycharm(self):
        self.ensure_one()
        self.devops_workspace.ide_pycharm.action_kill_pycharm()

    def action_start_pycharm(self, ctx=None):
        self.ensure_one()
        self.devops_workspace.ide_pycharm.action_start_pycharm(ctx=ctx)

    def action_set_breakpoint_pycharm(self):
        for rec_o in self:
            with rec_o.devops_workspace.devops_create_exec_bundle(
                "Set breakpoint on error"
            ) as rec:
                rec.ide_pycharm.action_cg_setup_pycharm_debug(
                    log=rec_o.escaped_tb.replace("&quot;", '"'),
                    exec_error_id=rec,
                )

    def open_file_ide(self):
        ws_id = self.env["devops.workspace"].search(
            [("is_me", "=", True)], limit=1
        )
        if not ws_id:
            return
        for o_rec in self:
            with ws_id.devops_create_exec_bundle("Open file IDE") as rec_ws:
                rec_ws.with_context(
                    breakpoint_id=o_rec.ide_breakpoint.id
                ).ide_pycharm.action_start_pycharm()
