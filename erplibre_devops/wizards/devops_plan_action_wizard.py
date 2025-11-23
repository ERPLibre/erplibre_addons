#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import json
import logging
import os
import re
import time
import unicodedata
import uuid
from datetime import datetime

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


class DevopsPlanActionWizard(models.TransientModel):
    _name = "devops.plan.action.wizard"
    _description = "Devops planification do an action with a specific workflow"
    _inherit = ["multi.step.wizard.mixin"]

    def _default_image_db_selection(self):
        return self.env["devops.db.image"].search(
            [("name", "like", "erplibre_base")], limit=1
        )

    def _default_instance_path(self):
        workspace_id = self.env.ref("erplibre_devops.devops_workspace_me")
        return os.path.join(workspace_id.folder, ".venv.erplibre", "project")

    name = fields.Char()

    root_workspace_id = fields.Many2one(
        comodel_name="devops.workspace",
        string="Root workspace",
        required=True,
        default=lambda self: self.env.context.get("id"),
        ondelete="cascade",
        help="Workspace where to execute the action.",
    )

    create_workspace_id = fields.Many2one(
        comodel_name="devops.workspace",
        string="Created workspace",
        ondelete="cascade",
        help="Workspace generate by this wizard.",
    )

    root_workspace_id_is_me = fields.Boolean(related="root_workspace_id.is_me")

    # working_workspace_ids = fields.One2many(
    #     related="working_system_id.devops_workspace_ids"
    # )

    workspace_folder = fields.Char(
        compute="_compute_workspace_folder",
        store=True,
        help="Absolute path for storing the devops_workspaces",
    )

    erplibre_mode = fields.Many2one(
        comodel_name="erplibre.mode",
    )

    generated_new_project_id = fields.Many2one(
        comodel_name="devops.cg.new_project",
        string="Generated project",
    )

    plan_cg_id = fields.Many2one(
        comodel_name="devops.plan.cg",
        string="Generated plan CG",
    )

    code_generator_name = fields.Char()

    template_name = fields.Char()

    working_module_id = fields.Many2one(
        comodel_name="ir.module.module",
        string="Working module",
    )

    working_project_name = fields.Char()

    is_new_module = fields.Boolean(
        compute="_compute_is_new_module", store=True, readonly=False
    )

    has_configured_path = fields.Boolean(
        store=True, compute="_compute_has_configured_path"
    )

    working_compute_module_path = fields.Char(
        store=True, compute="_compute_has_configured_path"
    )

    working_compute_module_cg_path = fields.Char(
        store=True, compute="_compute_has_configured_path"
    )

    working_compute_module_template_path = fields.Char(
        store=True, compute="_compute_has_configured_path"
    )

    instance_exec_from_workspace_id = fields.Many2one(
        comodel_name="devops.instance.exec",
        help=(
            "Help to create a new instance_exec_id from this one, will be a"
            " copy to deploy."
        ),
    )

    instance_exec_text_id = fields.Many2one(
        comodel_name="devops.instance.exec"
    )

    instance_exec_image_id = fields.Many2one(
        comodel_name="devops.instance.exec"
    )

    force_show_final = fields.Boolean(
        help="Will show final view without being in this state."
    )

    enable_deploy_llm_into_project = fields.Boolean(
        help="Will show deploy information about LLM for project."
    )

    working_module_path_suggestion = fields.Selection(
        selection=[
            ("#", "Manual"),
            ("addons/addons", "Addons private"),
            ("addons/ERPLibre_erplibre_addons", "ERPLibre addons"),
            ("addons/TechnoLibre_odoo-code-generator", "Code generator"),
        ],
        default="addons/addons",
        required=True,
        help="Suggestion relative path",
    )

    working_module_cg_path_suggestion = fields.Selection(
        selection=[
            ("-", "Default"),
            ("#", "Manual"),
            (
                "addons/TechnoLibre_odoo-code-generator-template",
                "Code generator template",
            ),
        ],
        default="-",
        required=True,
        help="Suggestion relative path CG",
    )

    working_module_template_path_suggestion = fields.Selection(
        selection=[
            ("-", "Default"),
            ("#", "Manual"),
            (
                "addons/TechnoLibre_odoo-code-generator-template",
                "Code generator template",
            ),
        ],
        default="-",
        required=True,
        help="Suggestion relative path template",
    )

    # TODO select default context from configuration and export it in local environment home configuration
    mode_context = fields.Selection(
        selection=[
            ("dev", "Dev"),
            ("test", "Test"),
            ("stage", "Stage"),
            ("demo", "Demo"),
            ("prod", "Prod"),
        ],
        help="Context why you use DevOps",
        default="dev",
        required=True,
    )

    working_module_name = fields.Char(
        help="working_module_id or working_module_name"
    )

    working_module_path = fields.Char(
        help="Need it for new module, relative path from folder of workspace."
    )

    working_module_cg_path = fields.Char(
        help=(
            "Need it for new module CG, relative path from folder of"
            " workspace. If empty, will use working_module_path."
        )
    )

    working_module_template_path = fields.Char(
        help=(
            "Need it for new module template, relative path from folder of"
            " workspace. If empty, will use working_module_path."
        )
    )

    system_name = fields.Char(string="System name")

    system_method = fields.Selection(related="working_system_id.method")

    system_erplibre_config_path_home_ids = fields.Many2many(
        related="working_system_id.erplibre_config_path_home_ids"
    )

    working_erplibre_config_path_home_id = fields.Many2one(
        string="Root path",
        comodel_name="erplibre.config.path.home",
    )

    working_relative_folder = fields.Char(string="Relative folder")

    is_force_local_system = fields.Boolean(
        help="Help for view to force local component."
    )

    is_new_or_exist_ssh = fields.Boolean(
        compute="_compute_is_new_or_exist_ssh", store=True
    )

    # TODO compute it, detect when it's remote, when cg path is different working path
    is_remote_cg = fields.Boolean(
        help="When it's remote, need tool to copy code with the developers."
    )

    is_cg_temporary = fields.Boolean(
        help="When it's remote, need tool to copy code with the developers."
    )

    can_search_workspace = fields.Boolean(
        compute="_compute_can_search_workspace", store=True
    )

    ssh_user = fields.Char(
        string="SSH user", help="New remote system ssh_user."
    )

    ssh_password = fields.Char(
        string="SSH password", help="New remote system ssh_password."
    )

    ssh_host = fields.Char(
        string="SSH host/IP", help="New remote system ssh_host, like local ip."
    )

    ssh_port = fields.Integer(
        string="SSH Port",
        default=22,
        help="The port on the FTP server that accepts SSH calls.",
    )

    working_system_id = fields.Many2one(
        comodel_name="devops.system",
        string="New/Existing system",
    )

    working_system_can_be_power_on = fields.Boolean(
        related="working_system_id.is_vm"
    )

    working_system_status = fields.Boolean(
        related="working_system_id.system_status"
    )

    working_cg_module_id = fields.Many2one(
        comodel_name="code.generator.module",
        string="CG code builder",
    )

    working_cg_writer_id = fields.Many2one(
        comodel_name="code.generator.writer",
        string="CG code writer",
    )

    is_update_system = fields.Boolean(
        store=True,
        compute="_compute_is_update_system",
        help="True if editing an existing system or False to create a system",
    )

    has_error_model = fields.Boolean(
        compute="_compute_has_error",
        store=True,
    )

    has_error_msg_model = fields.Text(compute="_compute_has_error", store=True)

    has_last_generated = fields.Boolean(
        help="Can show button to restore last generated module."
    )

    mode_view_generator = fields.Selection(
        selection=[
            ("no_view", "Nothing"),
            ("same_view", "Update"),
            ("new_view", "Create"),
        ],
        default="same_view",
        required=True,
        help="Mode view, enable rebuild same view or create new view.",
    )

    mode_view_portal = fields.Selection(
        selection=[
            ("no_portal", "No portal"),
            ("enable_portal", "Enable portal"),
        ],
        default="no_portal",
        required=True,
        help="Will active feature to generate portal interface",
    )

    mode_view_portal_enable_create = fields.Boolean(
        default=True,
        help="Feature for portal_enable_create",
    )

    mode_view_portal_enable_read = fields.Boolean(
        default=True,
        help="Feature for portal_enable_read",
    )

    mode_view_portal_enable_update = fields.Boolean(
        default=True,
        help="Feature for portal_enable_update",
    )

    mode_view_portal_enable_delete = fields.Boolean(
        default=True,
        help="Feature for portal_enable_delete",
    )

    mode_view_portal_models = fields.Char(
        help="Separate models by ;",
    )

    mode_view_snippet = fields.Selection(
        selection=[
            ("no_snippet", "No snippet"),
            ("enable_snippet", "Enable snippet"),
        ],
        required=True,
        default="no_snippet",
        help="Will active feature to generate snippet on website interface",
    )

    mode_view_snippet_enable_template_website_snippet_view = fields.Boolean(
        default=True,
        help="Feature for mode_view_snippet",
    )

    mode_view_snippet_template_generate_website_snippet_generic_mdl = (
        fields.Char(help="Feature for mode_view_snippet")
    )

    mode_view_snippet_template_generate_website_snippet_ctrl_featur = (
        fields.Selection(
            selection=[
                ("helloworld", "helloworld"),
                ("model_show_item_individual", "Model show item individual"),
                ("model_show_item_list", "Model show item list"),
            ],
            default="model_show_item_individual",
            required=True,
            help="Feature for mode_view_snippet",
        )
    )

    config_uca_enable_export_data = fields.Boolean(
        default=False,
        help=(
            "Will enable option nonmenclator in CG to export data associate to"
            " models."
        ),
    )

    mode_view_snippet_template_generate_website_enable_javascript = (
        fields.Boolean(
            default=True,
            help="Feature for mode_view_snippet",
        )
    )

    instance_list_to_deploy = fields.Many2one(
        comodel_name="devops.docker.compose.template",
        default=lambda s: s.default_devops_docker_compose_template(),
        domain="[('is_generic_template', '=', True)]",
        help="Instance list, from project list.",
    )

    instance_gpu_mode = fields.Selection(
        selection=[
            ("no_gpu", "No GPU"),
            ("gpu_cuda_11", "GPU Cuda 11"),
            ("gpu_cuda_12", "GPU Cuda 12"),
        ],
        default="no_gpu",
        required=True,
        help="Choose a GPU mode.",
    )

    instance_is_support_gpu = fields.Boolean(
        related="instance_list_to_deploy.is_support_gpu"
    )

    with_mistra_openorca = fields.Boolean(
        help=(
            "If true, force to use mistra openorca for generate text in french"
        )
    )

    instance_yaml = fields.Text(compute="_compute_instance_yaml")

    instance_port_1 = fields.Integer(
        string="Port 1",
        help="Principal port",
        default=8080,
        readonly=False,
    )

    instance_name = fields.Char()

    instance_path = fields.Char(default=_default_instance_path)

    instance_last_exec_id = fields.Many2one(
        comodel_name="devops.instance.exec"
    )

    instance_type_ids = fields.Many2many(
        comodel_name="devops.instance.type",
        string="Types",
    )

    mode_view_snippet_template_generate_website_snippet_type = (
        fields.Selection(
            selection=[
                ("content", "Content"),
                ("effect", "Effect"),
                ("feature", "Feature"),
                ("structure", "Structure"),
            ],
            default="effect",
            required=True,
            help="Feature for mode_view_snippet",
        )
    )

    use_external_cg = fields.Boolean(
        help=(
            "If internal, will use same database of devops for build code,"
            " this can interfere. If False, will generate external database"
            " with sandbox."
        ),
    )

    use_existing_meta_module = fields.Boolean(
        help="If False, will create new meta file from uc0."
    )

    use_existing_meta_module_uca_only = fields.Boolean(
        help="Force UcA only from feature use_existing_meta_module"
    )

    uca_option_with_inherit = fields.Boolean(
        help="UCA configuration - with inherit"
    )

    use_existing_meta_module_ucb_only = fields.Boolean(
        help="Force UcB only from feature use_existing_meta_module"
    )

    system_ssh_connection_status = fields.Boolean(
        related="working_system_id.ssh_connection_status",
        help="Status of test remote working_system_id",
    )

    state = fields.Selection(default="init")

    has_next = fields.Boolean(compute="_compute_has_next", store=True)

    force_generate = fields.Boolean(
        help=(
            "Ignore secure file edited, can overwrite this file and lost data."
        )
    )

    model_ids = fields.Many2many(
        comodel_name="devops.cg.model",
        string="Model",
    )

    model_to_remove_ids = fields.Many2many(
        comodel_name="devops.cg.model",
        string="Model to remove",
        relation="devops_plan_action_model_remove_rel",
    )

    model_fast_creation_enabled = fields.Boolean(
        string="Enable fast creation feature",
    )

    model_fast_creation_model_name = fields.Char(
        string="Model name fast creation",
    )

    model_fast_creation_field_name = fields.Text(
        string="Field name fast creation", help="Separate field name by ;"
    )

    model_fast_creation_field_separator = fields.Selection(
        string="Field separator fast creation",
        default=";",
        selection=[
            ("\t", "tab"),
            (";", ";"),
            (",", ","),
            ("\n", "saut de ligne \\n"),
        ],
    )

    model_fast_creation_field_example_value = fields.Text(
        string="Field value fast creation",
        help="Separate field name by ;, need to be same column of model_fast_creation_field_name",
    )

    model_fast_creation_error = fields.Text(
        string="Fast creation error", readonly=True
    )

    image_db_selection = fields.Many2one(
        comodel_name="devops.db.image",
        default=_default_image_db_selection,
    )

    enable_package_srs = fields.Boolean()

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="User",
        required=True,
        default=lambda s: s.env.user.id,
    )

    @api.model_create_multi
    def create(self, vals_list):
        res = super(DevopsPlanActionWizard, self).create(vals_list)
        res.has_last_generated = bool(
            self.env["devops.plan.cg"].search_count([], limit=1)
        )
        return res

    def _compute_has_next(self):
        for record in self:
            record.has_next = getattr(
                record, "state_exit_%s" % record.state, False
            )

    @api.depends("working_system_id")
    def _compute_is_update_system(self):
        for rec in self:
            is_update_system = bool(rec.working_system_id)
            if is_update_system:
                rec.system_name = rec.working_system_id.name_overwrite
                rec.ssh_host = rec.working_system_id.ssh_host
                rec.ssh_user = rec.working_system_id.ssh_user
                rec.ssh_password = rec.working_system_id.ssh_password

    @api.depends(
        "instance_gpu_mode",
        "instance_port_1",
        "instance_list_to_deploy",
        "with_mistra_openorca",
    )
    def _compute_instance_yaml(self):
        for rec in self:
            rec.instance_yaml = ""
            if rec.instance_list_to_deploy:
                # TODO maybe don't need to store the value?
                copy_instance_template = rec.instance_list_to_deploy.copy(
                    default={
                        "gpu_mode": rec.instance_gpu_mode,
                        "port_1": rec.instance_port_1,
                        "with_mistra_openorca": rec.with_mistra_openorca,
                        "active": False,
                    }
                )
                rec.instance_yaml = copy_instance_template.yaml

    @api.depends(
        "working_module_path_suggestion",
        "working_module_path",
        "working_module_cg_path_suggestion",
        "working_module_cg_path",
        "working_module_template_path_suggestion",
        "working_module_template_path",
        "working_module_id",
        "working_module_name",
    )
    def _compute_has_configured_path(self):
        for rec in self:
            rec.has_configured_path = False
            with open(".odoo-version", "r") as f:
                odoo_version = f.readline().strip()
                str_odoo_version = f"odoo{odoo_version}"

            # Module
            if (
                rec.working_module_path_suggestion == "#"
                and rec.working_module_path
            ):
                rec.has_configured_path = True
                rec.working_compute_module_path = rec.working_module_path
            if rec.working_module_path_suggestion != "#":
                rec.has_configured_path = True
                rec.working_compute_module_path = os.path.join(
                    str_odoo_version, rec.working_module_path_suggestion
                )
            # CG
            if (
                rec.working_module_cg_path_suggestion == "#"
                and not rec.working_module_cg_path
            ):
                rec.has_configured_path = False
            elif (
                rec.working_module_cg_path_suggestion == "#"
                and rec.working_module_cg_path
            ):
                rec.working_compute_module_cg_path = rec.working_module_cg_path
            elif rec.working_module_cg_path_suggestion == "-":
                rec.working_compute_module_cg_path = False
            else:
                rec.working_compute_module_cg_path = (
                    rec.working_module_cg_path_suggestion
                )
            # Template
            if (
                rec.working_module_template_path_suggestion == "#"
                and not rec.working_module_template_path
            ):
                rec.has_configured_path = False
            elif (
                rec.working_module_template_path_suggestion == "#"
                and rec.working_module_template_path
            ):
                rec.working_compute_module_template_path = (
                    rec.working_module_template_path
                )
            elif rec.working_module_template_path_suggestion == "-":
                rec.working_compute_module_template_path = False
            else:
                rec.working_compute_module_template_path = (
                    rec.working_module_template_path_suggestion
                )
            # Module name
            if not rec.working_module_id and not rec.working_module_name:
                rec.has_configured_path = False

    @api.depends("working_module_id")
    def _compute_is_new_module(self):
        for rec in self:
            if rec.working_module_id:
                rec.set_mode_edit_module()

    @api.model
    def default_devops_docker_compose_template(self):
        return self.env.ref(
            "erplibre_devops.devops_docker_compose_template_default_erplibre"
        )

    @api.depends(
        "working_erplibre_config_path_home_id",
        "working_erplibre_config_path_home_id.name",
        "working_relative_folder",
    )
    def _compute_workspace_folder(self):
        for rec in self:
            rec.workspace_folder = ""
            if (
                rec.working_erplibre_config_path_home_id
                and rec.working_erplibre_config_path_home_id.name
            ):
                if rec.working_relative_folder:
                    rec.workspace_folder = os.path.join(
                        rec.working_erplibre_config_path_home_id.name,
                        rec.working_relative_folder,
                    )
                else:
                    rec.workspace_folder = (
                        rec.working_erplibre_config_path_home_id.name
                    )

    @api.depends("system_method", "working_system_id")
    def _compute_is_new_or_exist_ssh(self):
        for rec in self:
            rec.is_new_or_exist_ssh = (
                not rec.working_system_id
                or rec.working_system_id.method == "ssh"
            )

    @api.depends(
        "working_system_id", "system_ssh_connection_status", "system_method"
    )
    def _compute_can_search_workspace(self):
        for rec in self:
            rec.can_search_workspace = False
            if rec.working_system_id:
                if (
                    rec.system_method == "ssh"
                    and rec.system_ssh_connection_status
                ):
                    rec.can_search_workspace = True
                elif rec.system_method == "local":
                    rec.can_search_workspace = True

    @api.model
    def _selection_state(self):
        return [
            ("init", "Init"),
            ("a_autopoiesis_devops", "Autopoiesis DevOps"),
            ("a_a_model", "Model autopoiesis devops"),
            ("a_b_field", "Field"),
            ("a_c_action", "Action"),
            ("a_d_view", "View"),
            ("a_f_devops_regen", "DevOps regenerate"),
            ("b_new_module", "New module"),
            # ("c_existing_module", "Existing module"),
            # ("c_a_model", "Model existing module"),
            ("d_import_data", "Import data"),
            ("e_migrate_from_external_ddb", "Migrate from external database"),
            ("f_new_project_society", "New society"),
            ("g_test_erplibre", "Test ERPLibre"),
            ("plan_project", "Plan project"),
            ("code_module", "Code module"),
            ("code_shortcut", "Shortcut configuration code"),
            ("g_a_local", "Test ERPLibre local"),
            ("h_run_test", "Run test"),
            ("h_a_test_plan_exec", "Run test plan execution"),
            ("h_b_cg", "Run test code generator"),
            ("i_new_remote_system", "New remote system"),
            ("i_new_instance", "New instance"),
            ("not_supported", "Not supported"),
            ("final", "Final"),
        ]

    def working_system_id_power(self):
        if self.working_system_id:
            self.working_system_id.action_vm_power()
        return self._reopen_self()

    def clear_working_system_id(self):
        self.working_system_id = False
        return self._reopen_self()

    def state_goto_a_autopoiesis_devops(self):
        self.state = "a_autopoiesis_devops"
        return self._reopen_self()

    def state_goto_a_a_model(self):
        self.state = "a_a_model"
        return self._reopen_self()

    def state_goto_a_b_field(self):
        self.state = "a_b_field"
        return self._reopen_self()

    def state_goto_a_e_cg_regen(self):
        self.state = "a_e_cg_regen"
        return self._reopen_self()

    def state_goto_a_f_devops_regen(self):
        self.state = "a_f_devops_regen"
        return self._reopen_self()

    def state_goto_a_g_regen(self):
        self.state = "a_g_regen"
        return self._reopen_self()

    def state_goto_f_new_project_society(self):
        self.state = "f_new_project_society"
        return self._reopen_self()

    def state_goto_g_test_erplibre(self):
        self.state = "g_test_erplibre"
        return self._reopen_self()

    def state_goto_plan_project(self):
        self.state = "plan_project"
        self.working_system_id = self.env.ref(
            "erplibre_devops.devops_system_local"
        ).id
        return self._reopen_self()

    def state_goto_code_module(self):
        self.state = "code_module"
        return self._reopen_self()

    def state_goto_code_module_shortcut_autopoieses_devops(self, ctx=None):
        self.working_project_name = "Autopoieses - erplibre_devops"
        self.code_generator_name = "code_generator_erplibre_devops"
        self.template_name = "code_generator_template_erplibre_devops"
        return self.goto_autopoiese("erplibre_devops", ctx=ctx)

    def state_goto_code_module_shortcut_autopoieses_code_generator(
        self, ctx=None
    ):
        if ctx is None:
            ctx = {}
        self.working_project_name = "Autopoieses - code_generator"
        self.working_module_cg_path_suggestion = (
            "addons/TechnoLibre_odoo-code-generator-template"
        )
        self.working_module_template_path_suggestion = (
            "addons/TechnoLibre_odoo-code-generator-template"
        )
        self.code_generator_name = "code_generator_code_generator"
        self.template_name = "code_generator_template_code_generator"
        self.use_existing_meta_module_ucb_only = True
        self.is_remote_cg = True
        return self.goto_autopoiese("code_generator", ctx=ctx)

    def state_goto_code_module_shortcut_autopoieses_code_generator_code_generator(
        self, ctx=None
    ):
        if ctx is None:
            ctx = {}
        self.working_project_name = (
            "Autopoieses - code_generator_code_generator"
        )
        self.working_module_cg_path_suggestion = (
            "addons/TechnoLibre_odoo-code-generator-template"
        )
        self.working_module_template_path_suggestion = (
            "addons/TechnoLibre_odoo-code-generator-template"
        )
        self.code_generator_name = "code_generator_code_generator"
        self.template_name = "code_generator_template_code_generator"
        self.use_existing_meta_module_uca_only = True
        self.uca_option_with_inherit = True
        self.is_remote_cg = True
        return self.goto_autopoiese("code_generator", ctx=ctx)

    def goto_autopoiese(self, module_name, ctx=None):
        if ctx is None:
            ctx = {}
        if module_name:
            self.fill_working_module_name_or_id(module_name)
            if not ctx.get("ignore_uca_ucb", False):
                self.use_external_cg = True
                self.use_existing_meta_module = True
            self.is_cg_temporary = True
            # self.set_mode_edit_module()
            self.action_code_module_autocomplete_module_path(ctx=ctx)
            self.config_uca_enable_export_data = False
            if ctx.get("force_create_view"):
                self.mode_view_generator = "new_view"
        return self.state_goto_code_module()

    def state_goto_code_shortcut(self):
        self.state = "code_shortcut"
        return self._reopen_self()

    def state_goto_h_run_test(self):
        self.state = "h_run_test"
        return self._reopen_self()

    def state_goto_h_a_test_plan_exec(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "devops.test.plan.exec",
            "view_mode": "form",
            "target": "new",
            "context": {"default_workspace_id": self.root_workspace_id.id},
        }

    def state_goto_h_b_cg(self):
        self.state = "h_b_cg"
        return self._reopen_self()

    def state_goto_g_a_local(self):
        self.state = "g_a_local"
        return self._reopen_self()

    def state_goto_a_c_action(self):
        # self.state = "a_c_action"
        self.state = "not_supported"
        return self._reopen_self()

    def state_goto_a_d_view(self):
        # self.state = "a_d_view"
        self.state = "not_supported"
        return self._reopen_self()

    def state_goto_not_supported(self):
        self.state = "not_supported"
        return self._reopen_self()

    # def state_goto_c_existing_module(self):
    #     self.state = "c_existing_module"
    #     return self._reopen_self()

    def state_goto_i_new_instance(self):
        self.state = "i_new_instance"
        self.working_system_id = self.env.ref(
            "erplibre_devops.devops_system_local"
        ).id
        return self._reopen_self()

    def state_goto_i_new_remote_system(self):
        self.state = "i_new_remote_system"
        self.working_system_id = False
        self.is_force_local_system = False
        return self._reopen_self()

    def state_goto_i_local_system(self):
        self.state = "i_new_remote_system"
        self.working_system_id = self.env.ref(
            "erplibre_devops.devops_system_local"
        ).id
        self.is_force_local_system = True
        self.system_name = self.working_system_id.name_overwrite
        return self._reopen_self()

    # def state_goto_c_a_model(self):
    #     self.state = "c_a_model"
    #     return self._reopen_self()

    # def state_exit_configure(self):
    #     self.state = 'custom'

    def state_previous_not_supported(self):
        self.state = "init"

    def state_previous_a_autopoiesis_devops(self):
        self.state = "init"

    def state_previous_a_a_model(self):
        self.state = "a_autopoiesis_devops"

    def state_previous_a_b_field(self):
        self.state = "a_autopoiesis_devops"

    def state_previous_i_new_remote_system(self):
        self.state = "init"

    def state_previous_i_new_instance(self):
        self.state = "init"

    def state_previous_a_c_action(self):
        self.state = "a_autopoiesis_devops"

    def state_previous_a_d_view(self):
        self.state = "a_autopoiesis_devops"

    def state_previous_code_module(self):
        self.state = "init"

    def state_previous_code_shortcut(self):
        self.state = "init"

    def state_previous_a_f_devops_regen(self):
        self.state = "a_autopoiesis_devops"

    def state_previous_f_new_project_society(self):
        self.state = "init"

    def state_previous_g_test_erplibre(self):
        self.state = "init"

    def state_previous_plan_project(self):
        self.state = "init"

    def state_previous_g_a_local(self):
        self.state = "g_test_erplibre"

    def state_previous_g_b_TODODO(self):
        self.state = "code_module"

    def state_previous_h_run_test(self):
        self.state = "init"

    #
    # def state_previous_h_a_test_plan_exec(self):
    #     self.state = "h_run_test"

    def state_previous_h_b_cg(self):
        self.state = "h_run_test"

    def state_exit_c_a_model(self):
        with self.root_workspace_id.devops_create_exec_bundle(
            "Plan c_a_model"
        ) as wp_id:
            module_name = (
                self.working_module_id.name
                if self.working_module_id
                else self.working_module_name
            )
            self.generate_new_model(
                wp_id, module_name, "Existing module new model"
            )
            # finally
            self.state = "final"

    def state_exit_code_module(self):
        with self.root_workspace_id.devops_create_exec_bundle(
            "Plan code_module"
        ) as wp_id:
            # TODO this is a duplicate of action_code_module_generate
            module_name = (
                self.working_module_id.name
                if self.working_module_id
                else self.working_module_name
            )
            self.generate_new_model(
                wp_id,
                module_name,
                "New empty module",
                is_new_module=True,
                module_path=self.working_compute_module_path,
                module_cg_path=self.working_compute_module_cg_path,
                module_template_path=self.working_compute_module_template_path,
                is_relative_path=True,
            )
            # finally
            self.state = "final"

    def state_exit_g_a_local(self):
        with self.root_workspace_id.devops_create_exec_bundle(
            "Plan g_a_local"
        ) as wp_id:
            self.erplibre_mode = self.env.ref(
                "erplibre_devops.erplibre_mode_docker_test"
            ).id
            # Create a workspace with same system of actual workspace, will be in test mode
            dct_wp = {
                "system_id": wp_id.system_id.id,
                "folder": f"/tmp/test_erplibre_{uuid.uuid4()}",
                "erplibre_mode": self.erplibre_mode.id,
                "image_db_selection": self.image_db_selection.id,
            }
            local_wp_id = self.env["devops.workspace"].create([dct_wp])
            self.create_workspace_id = local_wp_id.id
            local_wp_id.action_install_workspace()
            local_wp_id.action_start()
            # TODO implement detect when website is up or cancel state with error
            time.sleep(5)
            local_wp_id.action_restore_db_image()
            if self.enable_package_srs:
                local_wp_id.install_module("project_srs")
            local_wp_id.action_open_local_view()
            # finally
            self.state = "final"

    def state_exit_a_a_model(self):
        with self.root_workspace_id.devops_create_exec_bundle(
            "Plan a_a_model"
        ) as wp_id:
            module_name = "erplibre_devops"
            self.generate_new_model(
                wp_id, module_name, "Autopoiesis", is_autopoiesis=True
            )
            # finally
            self.state = "final"

    def state_exit_a_f_devops_regen(self):
        with self.root_workspace_id.devops_create_exec_bundle(
            "Plan a_f_devops_regen"
        ) as wp_id:
            self.generate_new_model(
                wp_id,
                "erplibre_devops",
                "Autopoiesis regenerate",
                is_autopoiesis=True,
            )
            # finally
            self.state = "final"
            # # Project
            # cg_id = self.env["devops.cg"].create(
            #     [{
            #         "name": "Autopoiesis regenerate",
            #         "devops_workspace_ids": [(6, 0, wp_id.ids)],
            #         "force_clean_before_generate": self.force_generate,
            #     }]
            # )
            # Module
            # cg_module_id = self.env["devops.cg.module"].create(
            #     [{
            #         "name": "erplibre_devops",
            #         "code_generator": cg_id.id,
            #         "devops_workspace_ids": [(6, 0, wp_id.ids)],
            #     }]
            # )
            # plan_cg_value = {
            #     "workspace_id": wp_id.id,
            #     "cg_self_add_config_cg": True,
            #     "path_working_erplibre": wp_id.folder,
            #     "code_mode_context_generator": "autopoiesis",
            #     "mode_view": "same_view",
            #     "devops_cg_ids": [(6, 0, cg_id.ids)],
            #     "devops_cg_module_ids": [(6, 0, cg_module_id.ids)],
            #     "devops_cg_model_ids": [(6, 0, [])],
            #     "devops_cg_field_ids": [(6, 0, [])],
            #     "stop_execution_if_env_not_clean": not self.force_generate,
            #     "use_external_cg": self.use_external_cg,
            # }
            # plan_cg_id = self.env["devops.plan.cg"].create([plan_cg_value])
            # # Generate
            # plan_cg_id.action_code_generator_generate_all()
            # self.generated_new_project_id = plan_cg_id.last_new_project_cg.id
            # self.plan_cg_id = plan_cg_id.id
            # self.working_cg_module_id = (
            #     self.plan_cg_id.last_code_generator_module.id
            # )
            # self.working_cg_writer_id = (
            #     self.plan_cg_id.last_code_generator_writer.id
            # )
            # Format module
            # cmd_format = (
            #     f"./script/maintenance/format.sh"
            #     f" ./addons/ERPLibre_erplibre_addons/erplibre_devops"
            # )
            # wp_id.execute(
            #     cmd=cmd_format,
            #     run_into_workspace=True,
            #     to_instance=True,
            # )
            # # finally
            # self.state = "final"

    def action_purge_metadata(self):
        with self.root_workspace_id.devops_create_exec_bundle(
            "Code Module - purge metadata"
        ) as wp_id:
            self.env["devops.cg.module"].search([]).unlink()
            self.env["devops.cg.model"].search([]).unlink()
            self.env["devops.cg.field"].search([]).unlink()
            self.has_error_model = False
            self.has_error_msg_model = ""
        return self._reopen_self()

    def action_enable_model_fast_creation(self):
        for rec in self:
            rec.model_fast_creation_enabled = True
        return self._reopen_self()

    def action_model_fast_creation(self):
        for rec in self:
            rec.model_fast_creation_error = ""
            if not rec.model_fast_creation_model_name:
                rec.model_fast_creation_error = "Missing model name."
                continue
            if rec.model_fast_creation_field_name:
                lst_field_name = [
                    a.strip()
                    for a in rec.model_fast_creation_field_name.strip(
                        "\n"
                    ).split(rec.model_fast_creation_field_separator)
                    if a.strip()
                ]
                # Check doublon
                if len(set(lst_field_name)) != len(lst_field_name):
                    rec.model_fast_creation_error = "Detect doublon into field name, validate all is unique."
                    continue
                # Extract value
                lst_field_value = [
                    a.strip()
                    for a in rec.model_fast_creation_field_example_value.strip(
                        "\n"
                    ).split(rec.model_fast_creation_field_separator)
                ]
                if lst_field_value and len(lst_field_value) != len(
                    lst_field_name
                ):
                    msg = (
                        f"The number '{len(lst_field_value)}' of item value is incoherent "
                        f"with item number '{len(lst_field_name)}' of field name."
                    )
                    for index in range(len(lst_field_value)):
                        if index < len(lst_field_name) and index < len(
                            lst_field_value
                        ):
                            msg += f"\n[{lst_field_name[index]}:{lst_field_value[index]}]"
                    rec.model_fast_creation_error = msg
                    continue
            else:
                lst_field_name = []
                lst_field_value = []

            dct_field_json = {}
            for field_index, field_name in enumerate(lst_field_name):
                field_name_code = self.to_field_name(field_name)
                if lst_field_value:
                    field_value = lst_field_value[field_index]
                    # Try to detect date, try to detect number
                    value_type, value_transform = rec.detect_type_from_string(
                        field_value, field_name
                    )
                else:
                    value_type = "Char"
                # TODO if type float or int and got $ in name, it's monetary
                dct_field_json[field_name_code] = {
                    "name": field_name_code,
                    "sequence": field_index + 10,
                    "string": field_name,
                    "type": value_type,
                }

            dct_field = {
                rec.model_fast_creation_model_name: {
                    "fields": dct_field_json,
                    "is_inherit": False,
                    "model_name": rec.model_fast_creation_model_name,
                }
            }

            str_dct_model = json.dumps(dct_field)
            self.generate_from_json(str_dct_model)

            # Clean
            # rec.model_fast_creation_model_name = ""
            # rec.model_fast_creation_field_name = ""
            # rec.model_fast_creation_field_example_value = ""
            rec.model_fast_creation_error = ""
        return self._reopen_self()

    def action_open_last_generated(self, ctx=None):
        if ctx is None:
            ctx = {}
        with self.root_workspace_id.devops_create_exec_bundle(
            "Code Module - Open last generated module"
        ) as wp_id:
            plan_cg_id = self.env["devops.plan.cg"].search(
                [], limit=1, order="id desc"
            )
            self.working_module_name = plan_cg_id.devops_cg_module_ids[0].name
            if self.working_module_name:
                self.action_code_module_autocomplete_module_path(ctx=ctx)
        return self._reopen_self()

    def action_code_module_autocomplete_module_path(self, ctx=None):
        if ctx is None:
            ctx = {}
        with self.root_workspace_id.devops_create_exec_bundle(
            "Code Module - auto-complete module path"
        ) as wp_id:
            # TODO complete use_existing_meta_module from suggested cg path
            module_name = None
            if self.working_module_id:
                module_name = self.working_module_id.name
            elif self.working_module_name:
                module_name = self.working_module_name
            if not module_name:
                # TODO manage error into action wizard
                # raise exceptions.UserError(f"Module name is empty.")
                return self._reopen_self()
            # Search absolute path
            exec_id = wp_id.execute(
                cmd=(
                    "./script/addons/check_addons_exist.py --output_path -m"
                    f" {module_name}"
                ),
                run_into_workspace=True,
                error_on_status=False,
            )
            path_module = exec_id.log_all.strip()
            if exec_id.exec_status == 2:
                raise exceptions.UserError(
                    f"The module '{module_name}' is duplicated :"
                    f" \n{path_module}"
                )
            elif exec_id.exec_status:
                # raise exceptions.UserError(f"Cannot find module '{module_name}'")
                self.set_mode_new_module()
                return self._reopen_self()
            if not path_module:
                # raise exceptions.UserError(f"Cannot find module path.")
                self.set_mode_new_module()
                return self._reopen_self()
            # Extract relative path
            dir_name, basename = os.path.split(path_module)
            if dir_name.startswith(wp_id.folder):
                relative_path_module = dir_name[len(wp_id.folder) + 1 :]
            else:
                relative_path_module = dir_name
            # Check if exist in suggested path
            lst_suggest_path = [
                a
                for a, b in self._fields[
                    "working_module_path_suggestion"
                ].selection
                if a not in ["#"]
            ]
            if relative_path_module in lst_suggest_path:
                self.working_module_path_suggestion = relative_path_module
            else:
                self.working_module_path_suggestion = "#"
                self.working_module_path = relative_path_module

            if not ctx.get("ignore_autocomplete_model", False):
                self.set_mode_edit_module()
                exec_id = wp_id.execute(
                    cmd=(
                        "./script/code_generator/search_class_model.py -d"
                        f" {relative_path_module}/{module_name} --json"
                        " --with_inherit"
                    ),
                    run_into_workspace=True,
                    error_on_status=False,
                )
                str_dct_model = exec_id.log_all.strip()
                if exec_id.exec_status != 0:
                    _logger.error("TODO i crash and forgot to raise an error!")
                else:
                    dct_model_cg = {}
                    dct_model_cg_depend = {}
                    self.generate_from_json(
                        str_dct_model,
                        force_new=True,
                        dct_model_cg=dct_model_cg,
                        dct_model_cg_depend=dct_model_cg_depend,
                    )
                    # reorder from dependency
                    # TODO reorder from dependency list, change sequence
                    lst_model_delete = []
                    sequence_no = 10
                    max_loop = 1000
                    i = 0
                    lst_id_model_order = []
                    has_change = True
                    while i < max_loop and dct_model_cg_depend and has_change:
                        i += 1
                        has_change = False
                        for (
                            model_name,
                            lst_depend,
                        ) in dct_model_cg_depend.items():
                            model_id = dct_model_cg.get(model_name)
                            if not lst_depend:
                                model_id.sequence = sequence_no
                                sequence_no += 1
                                lst_model_delete.append(model_name)
                                lst_id_model_order.append(model_id.id)
                                has_change = True
                            else:
                                # delete dependency from lst_model_order
                                lst_diff = list(
                                    set(lst_id_model_order).intersection(
                                        set(lst_depend)
                                    )
                                )
                                if lst_diff:
                                    for i_diff in lst_diff:
                                        lst_depend.remove(i_diff)
                                        has_change = True

                        for model_to_delete in lst_model_delete:
                            del dct_model_cg_depend[model_to_delete]
                        lst_model_delete = []
                    if dct_model_cg_depend:
                        _logger.error(
                            "Cannot reorder dependency of models, debug:"
                            f" {dct_model_cg_depend}"
                        )
                        for (
                            model_name,
                            lst_depend,
                        ) in dct_model_cg_depend.items():
                            model_id = dct_model_cg.get(model_name)
                            model_id.sequence = sequence_no
                            sequence_no += 1

        return self._reopen_self()

    def action_refresh_error(self):
        return self._compute_has_error()

    @api.depends(
        "model_ids.has_error",
        "model_ids.has_error_msg",
        "model_ids.field_ids.has_error",
        "model_ids.field_ids.has_error_msg",
    )
    def _compute_has_error(self):
        # compute on many2many compute is not working, so implement button action_refresh_error
        for rec in self:
            lst_has_error_model = []
            lst_has_error_msg_model = []
            for model_id in rec.model_ids:
                if model_id.has_error:
                    lst_has_error_model.append(True)
                    lst_model_error = model_id.has_error_msg.split("\n")
                    if len(lst_model_error) > 1:
                        msg_model_error = f"Model '{model_id.name}': {'\n\t'.join(lst_model_error)}"
                    else:
                        msg_model_error = (
                            f"Model '{model_id.name}': {lst_model_error[0]}"
                        )
                    lst_has_error_msg_model.append(msg_model_error)
            rec.has_error_model = any(lst_has_error_model)
            if rec.has_error_model:
                rec.has_error_msg_model = "\n".join(lst_has_error_msg_model)
            else:
                rec.has_error_msg_model = ""
        return self._reopen_self()

    def instance_deploy(self):
        if self.instance_list_to_deploy and self.instance_yaml:
            # TODO move this into devops.instance.exec, this to create
            yaml = self.instance_yaml

            if self.instance_exec_from_workspace_id:
                working_dir_path = os.path.join(
                    self.instance_path,
                    self.instance_exec_from_workspace_id.instance_name,
                )
            else:
                working_dir_path = os.path.join(
                    self.instance_path, self.instance_name
                )
            file_docker_compose = os.path.join(
                working_dir_path, "docker-compose.yml"
            )
            self.working_system_id.execute_with_result(
                f"mkdir '{working_dir_path}'",
                None,
                engine="sh",
            )
            self.working_system_id.execute_with_result(
                f"echo '{yaml}' > '{file_docker_compose}'",
                None,
                engine="sh",
            )
            # TODO ne pas copier toute la liste de type_ids, sélectionner ce qui est nécessaire
            # Le copier dans la liste par défaut à la copie, l'utilisateur pour l'enlever.
            inst_exec_value = {
                "port": self.instance_port_1,
                "url": f"http://localhost:{self.instance_port_1}",
                "type_ids": [(6, 0, self.instance_type_ids.ids)],
                "system_id": self.working_system_id.id,
                "workspace_id": self.root_workspace_id.id,
                "working_dir_path": working_dir_path,
                "instance_name": self.instance_name,
            }
            self.instance_last_exec_id = self.env[
                "devops.instance.exec"
            ].create([inst_exec_value])
            self.instance_last_exec_id.start()
            if (
                self.env.ref(
                    "erplibre_devops.devops_instance_type_gen_text"
                ).id
                in self.instance_type_ids.ids
            ):
                self.instance_exec_text_id = self.instance_last_exec_id.id
            if (
                self.env.ref(
                    "erplibre_devops.devops_instance_type_gen_image"
                ).id
                in self.instance_type_ids.ids
            ):
                self.instance_exec_image_id = self.instance_last_exec_id.id
        return self._reopen_self()

    def instance_create_operate_localai(self):
        ctx = {
            "default_system_id": self.working_system_id.id,
            "default_instance_exec_id": self.instance_last_exec_id.id,
            "default_request_url": self.instance_last_exec_id.url,
        }
        return {
            "name": _("Create operation LocalAI."),
            "type": "ir.actions.act_window",
            "view_type": "form",
            "view_mode": "form",
            "res_model": "devops.operate.localai",
            "view_id": self.env.ref(
                "erplibre_devops.devops_operate_localai_view_form"
            ).id,
            "target": "_blank",
            "context": ctx,
        }

    def instance_create_plan_project(self):
        ctx = {}
        if self.instance_exec_image_id:
            ctx["default_instance_exec_image_id"] = (
                self.instance_exec_image_id.id
            )
        if self.instance_exec_text_id:
            ctx["default_instance_exec_text_id"] = (
                self.instance_exec_text_id.id
            )
        return {
            "name": _("Create plan project."),
            "type": "ir.actions.act_window",
            "view_type": "form",
            "view_mode": "form",
            "res_model": "devops.plan.project",
            "view_id": self.env.ref(
                "erplibre_devops.devops_plan_project_view_form"
            ).id,
            "target": "_blank",
            "context": ctx,
        }

    def set_mode_new_module(self):
        self.is_new_module = True
        self.mode_view_generator = "new_view"
        self.config_uca_enable_export_data = False

    def set_mode_edit_module(self):
        self.is_new_module = False
        self.mode_view_generator = "same_view"
        self.config_uca_enable_export_data = True

    def generate_new_model(
        self,
        wp_id,
        module_name,
        project_name,
        is_autopoiesis=False,
        module_path=None,
        module_cg_path=None,
        module_template_path=None,
        is_relative_path=False,
        is_new_module=False,
    ):
        path_module = ""
        # if not is_new_module:
        #     # Search relative path
        #     exec_id = wp_id.execute(
        #         cmd=(
        #             "./script/addons/check_addons_exist.py --output_path -m"
        #             f" {module_name}"
        #         ),
        #         run_into_workspace=True,
        #     )
        #     if exec_id.exec_status:
        #         raise exceptions.UserError(f"Cannot find module '{module_name}'")
        #     path_module = exec_id.log_all.strip()
        if module_path:
            # Overwrite it
            path_module = module_path
        if not path_module:
            raise exceptions.UserError(f"Cannot find module path.")
        if not is_relative_path:
            dir_name, basename = os.path.split(path_module)
            if dir_name.startswith(wp_id.folder):
                relative_path_module = dir_name[len(wp_id.folder) + 1 :]
            else:
                relative_path_module = dir_name
        else:
            relative_path_module = path_module
        if not module_cg_path:
            relative_path_module_cg = relative_path_module
        else:
            if module_cg_path.startswith(wp_id.folder):
                relative_path_module_cg = module_cg_path[
                    len(wp_id.folder) + 1 :
                ]
            else:
                relative_path_module_cg = module_cg_path
        if not module_template_path:
            relative_path_module_template = relative_path_module
        else:
            if module_template_path.startswith(wp_id.folder):
                relative_path_module_template = module_template_path[
                    len(wp_id.folder) + 1 :
                ]
            else:
                relative_path_module_template = module_template_path

        # TODO this is a bug, no need that in reality, but action_code_generator_generate_all loop into it
        #  Remove action_code_generator_generate_all
        # Project
        cg_id = self.env["devops.cg"].create(
            [
                {
                    "name": project_name,
                    "devops_workspace_ids": [(6, 0, wp_id.ids)],
                    "force_clean_before_generate": self.force_generate,
                }
            ]
        )
        # Module
        cg_module_id = self.env["devops.cg.module"].create(
            [
                {
                    "name": module_name,
                    "code_generator": cg_id.id,
                    "devops_workspace_ids": [(6, 0, wp_id.ids)],
                }
            ]
        )
        # Model
        for cg_model_id in self.model_ids:
            cg_model_id.module_id = cg_module_id.id
            cg_model_id.devops_workspace_ids = [(6, 0, wp_id.ids)]
        lst_field_id = [b.id for a in self.model_ids for b in a.field_ids]
        # Complete plan to code_generator
        # TODO the code_generator has path_code_generator_to_generate_cg and path_code_generator_to_generate_template
        #  into template directory
        plan_cg_value = {
            "workspace_id": wp_id.id,
            "mode_view": self.mode_view_generator,
            "path_working_erplibre": wp_id.folder,
            "path_code_generator_to_generate": relative_path_module,
            "path_code_generator_to_generate_cg": relative_path_module_cg,
            "path_code_generator_to_generate_template": relative_path_module_template,
            "devops_cg_ids": [(6, 0, cg_id.ids)],
            "devops_cg_module_ids": [(6, 0, cg_module_id.ids)],
            "devops_cg_model_ids": [(6, 0, self.model_ids.ids)],
            "devops_cg_field_ids": [(6, 0, lst_field_id)],
            "stop_execution_if_env_not_clean": not self.force_generate,
            "use_external_cg": self.use_external_cg,
            "use_existing_meta_module": self.use_existing_meta_module,
            "use_existing_meta_module_uca_only": self.use_existing_meta_module_uca_only,
            "uca_option_with_inherit": self.uca_option_with_inherit,
            "use_existing_meta_module_ucb_only": self.use_existing_meta_module_ucb_only,
        }
        # Update configuration self-gen
        if is_autopoiesis:
            plan_cg_value["cg_self_add_config_cg"] = True
            plan_cg_value["code_mode_context_generator"] = "autopoiesis"
        # Support data
        plan_cg_value["config_uca_enable_export_data"] = (
            self.config_uca_enable_export_data
        )

        # Support snippet
        if self.mode_view_snippet and self.mode_view_snippet != "no_snippet":
            plan_cg_value["mode_view_snippet"] = self.mode_view_snippet
            plan_cg_value[
                "mode_view_snippet_enable_template_website_snippet_view"
            ] = self.mode_view_snippet_enable_template_website_snippet_view
            plan_cg_value[
                "mode_view_snippet_template_generate_website_snippet_generic_mdl"
            ] = (
                self.mode_view_snippet_template_generate_website_snippet_generic_mdl
            )
            plan_cg_value[
                "mode_view_snippet_template_generate_website_snippet_ctrl_featur"
            ] = (
                self.mode_view_snippet_template_generate_website_snippet_ctrl_featur
            )
            plan_cg_value[
                "mode_view_snippet_template_generate_website_enable_javascript"
            ] = (
                self.mode_view_snippet_template_generate_website_enable_javascript
            )
            plan_cg_value[
                "mode_view_snippet_template_generate_website_snippet_type"
            ] = self.mode_view_snippet_template_generate_website_snippet_type
        if self.mode_view_portal and self.mode_view_portal != "no_portal":
            plan_cg_value["mode_view_portal"] = self.mode_view_portal
            plan_cg_value["mode_view_portal_enable_create"] = (
                self.mode_view_portal_enable_create
            )
            plan_cg_value["mode_view_portal_enable_read"] = (
                self.mode_view_portal_enable_read
            )
            plan_cg_value["mode_view_portal_enable_update"] = (
                self.mode_view_portal_enable_update
            )
            plan_cg_value["mode_view_portal_enable_delete"] = (
                self.mode_view_portal_enable_delete
            )
            plan_cg_value["mode_view_portal_models"] = (
                self.mode_view_portal_models
            )
        if self.code_generator_name:
            plan_cg_value["code_generator_name"] = self.code_generator_name
        if self.template_name:
            plan_cg_value["template_name"] = self.template_name
        # Before generate, clean if necessary
        cg_module_id = self.env["code.generator.module"].search(
            [("name", "=", module_name)]
        )
        if cg_module_id:
            cg_module_id.unlink()
        # Generate
        plan_cg_id = self.env["devops.plan.cg"].create([plan_cg_value])
        plan_cg_id.action_code_generator_generate_all()
        self.generated_new_project_id = plan_cg_id.last_new_project_cg.id
        self.plan_cg_id = plan_cg_id.id
        self.working_cg_module_id = plan_cg_id.last_code_generator_module.id
        self.working_cg_writer_id = plan_cg_id.last_code_generator_writer.id
        # Format module
        cmd_format = (
            "./script/maintenance/format.sh"
            f" {relative_path_module}/{module_name}"
        )
        wp_id.execute(
            cmd=cmd_format,
            run_into_workspace=True,
            to_instance=True,
        )
        # Git add
        if is_new_module:
            lst_default_file = [module_name]
        else:
            lst_default_file = [
                f"{module_name}/__manifest__.py",
                f"{module_name}/security/ir.model.access.csv",
                f"{module_name}/views/menu.xml",
            ]
            model_ids = self.model_ids.filtered(lambda r: not r.is_to_remove)
            if model_ids:
                lst_default_file.append(f"{module_name}/models/__init__.py")
                for cg_model_id in model_ids:
                    model_file_name = cg_model_id.name.replace(".", "_")
                    lst_default_file.append(
                        f"{module_name}/models/{model_file_name}.py"
                    )
                    lst_default_file.append(
                        f"{module_name}/views/{model_file_name}.xml"
                    )
        cmd_git_add = ";".join([f"git add '{a}'" for a in lst_default_file])
        # Git remove
        lst_default_file_rm = []
        model_to_remove_ids = self.model_ids.filtered(lambda r: r.is_to_remove)
        if model_to_remove_ids:
            for cg_model_id in model_to_remove_ids:
                model_file_name = cg_model_id.name.replace(".", "_")
                lst_default_file_rm.append(
                    f"{module_name}/models/{model_file_name}.py"
                )
                lst_default_file_rm.append(
                    f"{module_name}/views/{model_file_name}.xml"
                )
        cmd_git_rm = ";".join([f"git rm '{a}'" for a in lst_default_file_rm])
        cmd_git = ";".join([cmd_git_add, cmd_git_rm])
        if cmd_git:
            wp_id.execute(
                cmd=cmd_git,
                folder=relative_path_module,
                run_into_workspace=True,
                to_instance=True,
            )

    def generate_from_json(
        self,
        str_dct_model,
        force_new=False,
        dct_model_cg={},
        dct_model_cg_depend={},
    ):
        # The file need to finish by }, or cut it and remove output execution
        last_pos_char = str_dct_model.rfind("}")
        if last_pos_char == -1:
            _logger.error(
                "Cannot detect JSON dict when searching class" " model."
            )
            # TODO You can stop execution here, but let crash later
            str_dct_model_complete = str_dct_model
            lst_logs_model = []
        else:
            str_dct_model_complete = str_dct_model[: last_pos_char + 1]
            lst_logs_model = (
                str_dct_model[last_pos_char + 1 :].strip().split("\n")
            )
            # TODO show this log to action view
            lst_logs_model = [a.strip() for a in lst_logs_model if a.strip()]
            if lst_logs_model:
                _logger.warning("\n".join(lst_logs_model))
        # Create cg.model
        dct_model = json.loads(str_dct_model_complete)
        lst_model_to_add = []
        lst_model_field = []
        for model_name, v in dct_model.items():
            model_id = self.env["devops.cg.model"].search(
                [("name", "=", model_name)]
            )
            if not model_id:
                model_value = {
                    "name": model_name,
                    "is_inherit": v.get("is_inherit", False),
                }
                model_id = self.env["devops.cg.model"].create([model_value])
            lst_model_to_add.append(model_id.id)
            lst_model_field.append((model_id, v))
            dct_model_cg[model_name] = model_id
            dct_model_cg_depend[model_name] = []
        # Create cg.field
        for model_id, v in lst_model_field:
            if "fields" in v.keys():
                # This algorithm only works when the module is working and formatted
                for dct_field in v.get("fields").values():
                    ttype = dct_field.get("type").lower()
                    field_name = dct_field.get("name")
                    value_value = {
                        "name": field_name,
                        "type": ttype,
                        "model_id": model_id.id,
                    }
                    model_name = model_id.name
                    # Check if exist
                    field_id = self.env["devops.cg.field"].search(
                        [
                            ("name", "=", field_name),
                            ("model_id", "=", model_id.id),
                        ]
                    )
                    if field_id:
                        continue
                    if "comodel_name" in dct_field.keys():
                        comodel_name = dct_field.get("comodel_name")
                        model_id_searched = dct_model_cg.get(comodel_name)
                        if model_id_searched:
                            value_value["relation"] = model_id_searched.id
                            if (
                                model_id_searched.id
                                not in dct_model_cg_depend[model_name]
                                and ttype not in ["one2many"]
                                and model_id_searched.id != model_id.id
                            ):
                                # Ignore one2many and depend on itself
                                # Keep cache on depend model
                                dct_model_cg_depend[model_name].append(
                                    model_id_searched.id
                                )
                        else:
                            value_value["relation_manual"] = comodel_name
                        if "inverse_name" in dct_field.keys():
                            inverse_name = dct_field.get("inverse_name")
                            # TODO detect field_relation, need to reorder the field model
                            value_value["field_relation_manual"] = inverse_name
                        if "relation" in dct_field.keys():
                            relation_ref = dct_field.get("relation")
                            value_value["relation_ref"] = relation_ref
                    if "currency_field" in dct_field.keys():
                        value_value["currency_field"] = dct_field.get(
                            "currency_field"
                        )
                    if "compute_method" in dct_field.keys():
                        value_value["compute"] = dct_field.get(
                            "compute_method"
                        )
                    if "help" in dct_field.keys():
                        value_value["help"] = dct_field.get("help")
                    if "string" in dct_field.keys():
                        value_value["string"] = dct_field.get("string")
                    if "related" in dct_field.keys():
                        value_value["related_manual"] = dct_field.get(
                            "related"
                        )

                    field_id = self.env["devops.cg.field"].create(
                        [value_value]
                    )

        if force_new:
            # Replace all
            self.model_ids = [(6, 0, lst_model_to_add)]
        else:
            # TODO support update and not append
            # Append
            self.model_ids = [(4, a) for a in lst_model_to_add]

    def fill_working_module_name_or_id(self, module_name):
        if not module_name:
            return
        module_id = self.env["ir.module.module"].search(
            [("name", "=", module_name)], limit=1
        )
        if module_id:
            self.working_module_id = module_id.id
        else:
            self.working_module_name = module_name

    def ssh_system_open_terminal(self):
        if not self.working_system_id:
            # TODO manage this error
            return
        self.working_system_id.execute_terminal_gui(
            force_no_sshpass_no_arg=True
        )
        return self._reopen_self()

    def search_workspace_from_system(self):
        if not self.working_system_id:
            # TODO manage this error
            return
        self.working_system_id.action_search_workspace()
        return self._reopen_self()

    def ssh_system_install_ntp(self):
        if not self.working_system_id:
            # TODO manage this error
            return
        self.working_system_id.configure_ntp()
        return self._reopen_self()

    def ssh_system_install_docker(self):
        if not self.working_system_id:
            # TODO manage this error
            return
        self.working_system_id.action_check_docker()
        self.working_system_id.action_install_docker()
        return self._reopen_self()

    def ssh_system_install_dev(self):
        if not self.working_system_id:
            # TODO manage this error
            return
        self.working_system_id.action_install_dev_system()
        return self._reopen_self()

    def ssh_system_install_starship(self):
        if not self.working_system_id:
            # TODO manage this error
            return
        self.working_system_id.configure_starship()
        return self._reopen_self()

    #
    # def ssh_system_install_all(self):
    #     if not self.working_system_id:
    #         # TODO manage this error
    #         return
    #     self.working_system_id.action_install_dev_system()
    #     return self._reopen_self()

    def ssh_system_install_robotlibre(self):
        if not self.working_system_id:
            # TODO manage this error
            return
        self.working_system_id.action_install_robotlibre()
        return self._reopen_self()

    def ssh_system_create_workspace(self):
        if not self.working_system_id:
            # TODO manage this error
            return
        ws_value = {
            "system_id": self.working_system_id.id,
            "folder": self.workspace_folder,
            "erplibre_mode": self.erplibre_mode.id,
            "image_db_selection": self.image_db_selection.id,
        }
        ws_id = self.env["devops.workspace"].create([ws_value])
        self.create_workspace_id = ws_id.id
        # TODO missing check status before continue
        # TODO missing with workspace me to catch error
        ws_id.action_install_workspace()
        ws_id.action_start()
        # TODO implement detect when website is up or cancel state with error
        time.sleep(5)
        ws_id.action_restore_db_image()
        ws_id.action_open_local_view()
        return self._reopen_self()

    def search_subsystem_workspace(self):
        system_ids = (
            self.root_workspace_id.system_id.get_local_system_id_from_ssh_config()
        )
        for system_id in system_ids:
            if system_id.ssh_connection_status:
                # TODO the connection status is never activate for new remote system
                system_id.action_search_workspace()
        return self._reopen_self()

    def ssh_create_and_test(self):
        system_name = self.system_name
        if not system_name:
            system_name = "New remote system " + uuid.uuid4().hex[:6]
        system_value = {
            "name_overwrite": system_name,
            "parent_system_id": self.root_workspace_id.system_id.id,
            "method": "ssh",
            "ssh_use_sshpass": True,
            "ssh_host": self.ssh_host,
            "ssh_user": self.ssh_user,
            "ssh_password": self.ssh_password,
        }
        system_id = self.env["devops.system"].create([system_value])
        self.working_system_id = system_id
        try:
            # Just open and close the connection
            with self.working_system_id.ssh_connection():
                pass
        except Exception:
            pass
        return self._reopen_self()

    def ssh_test_system_exist(self):
        if not self.working_system_id:
            raise exceptions.UserError(
                "Missing SSH system id from plan Wizard, wrong configuration,"
                " please contact your administrator."
            )
        if self.system_name:
            self.working_system_id.name_overwrite = self.system_name
        self.working_system_id.ssh_host = self.ssh_host
        self.working_system_id.ssh_user = self.ssh_user
        self.working_system_id.ssh_password = self.ssh_password
        self.working_system_id.ssh_use_sshpass = True
        try:
            # Just open and close the connection
            with self.working_system_id.ssh_connection():
                pass
        except Exception:
            pass
        return self._reopen_self()

    def action_git_commit(self):
        for rec in self:
            if rec.plan_cg_id:
                if not rec.is_remote_cg:
                    rec.plan_cg_id.action_git_commit()
                else:
                    rec.plan_cg_id.action_git_commit_remote()
        return self._reopen_self()

    def action_git_meld_remote(self):
        for rec in self:
            if rec.plan_cg_id:
                rec.plan_cg_id.action_git_meld_remote()
        return self._reopen_self()

    def action_git_clean_remote(self):
        for rec in self:
            if rec.plan_cg_id:
                rec.plan_cg_id.action_git_clean_remote()
        return self._reopen_self()

    def action_code_module_generate(self):
        with self.root_workspace_id.devops_create_exec_bundle(
            "Action Code Module - Generate"
        ) as wp_id:
            module_name = (
                self.working_module_id.name
                if self.working_module_id
                else self.working_module_name
            )
            self.generate_new_model(
                wp_id,
                module_name,
                self.working_project_name,
                module_path=self.working_compute_module_path,
                module_cg_path=self.working_compute_module_cg_path,
                module_template_path=self.working_compute_module_template_path,
                is_new_module=self.is_new_module,
                is_relative_path=True,
            )
        self.force_show_final = True
        return self._reopen_self()

    def detect_type_from_string(self, value: str, name: str) -> (str, object):
        datetime_formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
        ]

        # 4. DATETIME ?
        for fmt in datetime_formats:
            try:
                dt = datetime.strptime(value, fmt)
                return "Datetime", dt
            except ValueError:
                pass

        date_formats = [
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
        ]

        # 3. DATE ?
        for fmt in date_formats:
            try:
                d = datetime.strptime(value, fmt).date()
                return "Date", d
            except ValueError:
                pass

        if "$" in name:
            try:
                fv = float(value)
                return "Monetary", fv
            except ValueError:
                pass

        if "," in value:
            try:
                fv = float(value)
                return "Float", fv
            except ValueError:
                pass

        try:
            fv = int(value)
            return "Integer", fv
        except ValueError:
            pass

        return "Char", value

    def to_field_name(self, label: str) -> str:
        # 1) Normaliser les accents → é => e, ç => c, etc.
        label = unicodedata.normalize("NFKD", label)
        label = label.encode("ascii", "ignore").decode("ascii")

        # 2) tout en minuscule
        label = label.lower()

        # 3) remplacer tout ce qui n'est pas lettre ou chiffre par des underscores
        label = re.sub(r"[^a-z0-9]+", "_", label)

        # 4) enlever les underscores en trop au début/fin
        label = label.strip("_")

        # 5) éviter un nom vide
        if not label:
            label = "field"

        # 6) éviter un début par chiffre (pas valide pour un identifiant Python)
        if label[0].isdigit():
            label = "no_" + label

        return label

    def action_auto_complete_monetary(self, ctx=None):
        if ctx is None:
            ctx = {}
        with self.root_workspace_id.devops_create_exec_bundle(
            "Code Module - Auto complete monetary"
        ) as wp_id:
            for cg_model_id in self.model_ids:
                has_monetary_to_fix = [
                    a
                    for a in cg_model_id.field_ids
                    if a.type == "monetary" and not a.currency_field
                ]
                if not has_monetary_to_fix:
                    continue
                # Detect company_currency_id or first Many2one with comodel_name == res.currency
                lst_company_currency_id_field = [
                    a
                    for a in cg_model_id.field_ids
                    if a.type == "many2one"
                    and a.relation_manual == "res.currency"
                ]
                if not lst_company_currency_id_field:
                    company_currency_id = self.env["devops.cg.field"].create(
                        [
                            {
                                "name": "company_currency_id",
                                "help": "Company currency",
                                "type": "many2one",
                                "relation_manual": "res.currency",
                                "model_id": cg_model_id.id,
                                "compute_method": "_compute_company_currency_id",
                                "devops_workspace_ids": [
                                    (
                                        6,
                                        0,
                                        cg_model_id.devops_workspace_ids.ids,
                                    )
                                ],
                            }
                        ]
                    )
                    lst_company_currency_id_field = [company_currency_id]
                elif len(lst_company_currency_id_field) > 1:
                    lst_company_currency_id_field_if_find = [
                        a
                        for a in lst_company_currency_id_field
                        if a.name == "company_currency_id"
                    ]
                    if lst_company_currency_id_field_if_find:
                        lst_company_currency_id_field = (
                            lst_company_currency_id_field_if_find[0]
                        )
                    else:
                        lst_company_currency_id_field = (
                            lst_company_currency_id_field[0]
                        )
                company_currency_id = lst_company_currency_id_field[0]
                for field_id in cg_model_id.field_ids:
                    if (
                        field_id.type == "monetary"
                        and not field_id.currency_field
                    ):
                        field_id.currency_field = company_currency_id.name
                cg_model_id.is_method_compute_company_currency_id = True
            self.action_refresh_error()
        return self._reopen_self()
