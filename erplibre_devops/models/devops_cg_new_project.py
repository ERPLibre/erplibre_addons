# Copyright 2023 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import configparser
import json
import logging
import os
import tempfile
import uuid

from git import Repo
from git.exc import InvalidGitRepositoryError, NoSuchPathError

from odoo import _, api, exceptions, fields, models, tools

CODE_GENERATOR_DIRECTORY = "./addons/TechnoLibre_odoo-code-generator-template/"
CODE_GENERATOR_DEMO_NAME = "code_generator_demo"
KEY_REPLACE_CODE_GENERATOR_DEMO = 'MODULE_NAME = "%s"'
_logger = logging.getLogger(__name__)


class DevopsCgNewProject(models.Model):
    _name = "devops.cg.new_project"
    _description = "Create new project for CG project"

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )

    active = fields.Boolean(default=True)

    has_error = fields.Boolean(
        readonly=True,
        help="Will be True if got error into execution of new project.",
    )

    has_warning = fields.Boolean(
        readonly=True,
        help="Will be True if got warning into execution of new project.",
    )

    stage_id = fields.Many2one(
        comodel_name="devops.cg.new_project.stage",
        string="Stage",
        default=lambda s: s.default_stage_id(),
    )

    project_type = fields.Selection(
        selection=[("self", "Self generate"), ("cg", "Code generator")]
    )

    mode_view = fields.Selection(
        selection=[
            ("no_view", "No view"),
            ("same_view", "Autopoiesis"),
            ("new_view", "New"),
        ],
        default="same_view",
        help="Mode view, enable rebuild same view or create new view.",
    )

    config_uca_enable_export_data = fields.Boolean(
        default=True,
        help=(
            "Will enable option nonmenclator in CG to export data associate to"
            " models."
        ),
    )

    mode_view_snippet = fields.Selection(
        selection=[
            ("no_snippet", "No snippet"),
            ("enable_snippet", "Enable snippet"),
        ],
        default="no_snippet",
        help="Will active feature to generate snippet",
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
            help="Feature for mode_view_snippet",
        )
    )

    mode_view_snippet_template_generate_website_enable_javascript = (
        fields.Boolean(
            default=True,
            help="Feature for mode_view_snippet",
        )
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
            help="Feature for mode_view_snippet",
        )
    )

    last_new_project = fields.Many2one(
        comodel_name="devops.cg.new_project",
        string="Last new project",
    )

    exec_start_date = fields.Datetime(string="Execution start date")

    exec_stop_date = fields.Datetime(string="Execution stop date")

    exec_time_duration = fields.Float(
        string="Execution time duration",
        compute="_compute_exec_time_duration",
        store=True,
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

    execution_finish = fields.Boolean(
        readonly=True,
        help="Will be True when execution finish correctly.",
    )

    is_pause = fields.Boolean(
        readonly=True,
        help=(
            "Is pause is True when debug is execute and set at pause to run"
            " outside."
        ),
    )

    module = fields.Char(required=True)

    directory = fields.Char(required=True)

    directory_cg = fields.Char(
        help="Specify cg generator directory, or use directory."
    )

    directory_template = fields.Char(
        help="Specify template directory, or use directory."
    )

    config = fields.Char()

    model_to_remove = fields.Char(help="Separate model by ; to remove to CG.")

    code_generator_name = fields.Char()

    template_name = fields.Char()

    odoo_config = fields.Char(default="./config.conf")

    stop_execution_if_env_not_clean = fields.Boolean(default=True)

    force = fields.Boolean()

    active_coverage = fields.Boolean(help="Will enable coverage output file.")

    keep_bd_alive = fields.Boolean()

    can_setup_ide = fields.Boolean(
        compute="_compute_can_setup_ide",
        store=True,
    )

    config_debug_Uc0 = fields.Boolean(help="Debug Uc0.")

    config_debug_UcA = fields.Boolean(help="Debug UcA.")

    config_debug_UcB = fields.Boolean(help="Debug UcB.")

    breakpoint_Uc0_first_line_hook = fields.Boolean(
        string="Uc0 First line hook",
        help="Breakpoint first line hook file uc0.",
    )

    breakpoint_all_write_hook_begin = fields.Boolean(
        string="ALL Write hook file at begin",
        help="Breakpoint general when write hook.",
    )

    breakpoint_all_write_hook_before_model = fields.Boolean(
        string="ALL Write hook before model",
        help=(
            "Breakpoint general when write hook before write model/fields into"
            " hook."
        ),
    )

    breakpoint_all_write_hook_model_write_field = fields.Boolean(
        string="ALL Write hook model write field",
        help=(
            "Breakpoint general when write hook while writing model, before"
            " write field."
        ),
    )

    breakpoint_condition_model_name = fields.Char(
        string="Model name",
        help="General breakpoint condition with model name.",
    )

    breakpoint_condition_field_name = fields.Char(
        string="Field name",
        help="General breakpoint condition with field name.",
    )

    breakpoint_condition_field_attribute_name = fields.Char(
        string="Field attribute name",
        help="General breakpoint condition with field attribute name.",
    )

    breakpoint_condition_method_name = fields.Char(
        string="Method name",
        help="General breakpoint condition to diagnostic method.",
    )

    breakpoint_condition_module_name = fields.Char(
        string="Module name",
        help=(
            "General breakpoint condition to diagnostic module. It's generally"
            " the name of the generated module."
        ),
    )

    breakpoint_condition_xml_id = fields.Char(
        string="Xml ID",
        help=(
            "View breakpoint condition to diagnostic module. XML_id is the"
            " identifiant of view."
        ),
    )

    breakpoint_condition_short_xml_id = fields.Char(
        string="Xml Short ID",
        help=(
            "View breakpoint condition to diagnostic module. XML_id is the"
            " identifiant of view, without the module name."
        ),
    )

    breakpoint_condition_value_label_view_item = fields.Char(
        string="String view item",
        help=(
            "View breakpoint condition to diagnostic module. The string of"
            " view item."
        ),
    )

    breakpoint_condition_name_view_item = fields.Char(
        string="Name view item",
        help=(
            "View breakpoint condition to diagnostic module. The name of view"
            " item."
        ),
    )

    breakpoint_condition_item_type_view_item = fields.Char(
        string="Item type view item",
        help=(
            "View breakpoint condition to diagnostic module. The item type of"
            " view item."
        ),
    )

    breakpoint_condition_view_name = fields.Char(
        string="View name",
        help=(
            "View breakpoint condition to diagnostic module. The id of the"
            " view."
        ),
    )

    breakpoint_UcA_first_line_hook = fields.Boolean(
        string="UcA First line hook",
        help="Breakpoint first line hook file ucA.",
    )

    breakpoint_UcB_first_line_hook = fields.Boolean(
        string="UcB First line hook",
        help="Breakpoint first line hook file ucB.",
    )

    breakpoint_Uc0_cg_Uc0 = fields.Boolean(
        string="Uc0 cg Uc0",
        help="Breakpoint dans la section génération de code du Uc0.",
    )

    breakpoint_all_begin_generate_file = fields.Boolean(
        string="ALL Begin generate file",
        help="Breakpoint dans la section génération de code.",
    )

    breakpoint_UcA_extract_python_controller_warning = fields.Boolean(
        string="UcA Extract Python controller WARNING",
        help=(
            "Breakpoint UcA to diagnostic warning when extract python"
            " controller."
        ),
    )

    breakpoint_UcA_extract_python_module_warning = fields.Boolean(
        string="UcA Extract Python module WARNING",
        help=(
            "Breakpoint UcA to diagnostic warning when extract python module."
        ),
    )

    breakpoint_UcA_extract_python_module_file_warning = fields.Boolean(
        string="UcA Extract Python module file WARNING",
        help=(
            "Breakpoint UcA to diagnostic warning when extract python module"
            " file."
        ),
    )

    breakpoint_UcA_extract_python_detect_field = fields.Boolean(
        string="UcA Extract Python detect field",
        help="Breakpoint UcA when extract Python field of model.",
    )

    breakpoint_all_prepare_data_before_write = fields.Boolean(
        string="ALL Prepare data before write",
        help="Breakpoint all prepare set of data before write code.",
    )

    breakpoint_all_before_sync_code = fields.Boolean(
        string="ALL Before sync module",
        help="Breakpoint before sync module in writing code.",
    )

    breakpoint_UcA_extract_view_warning = fields.Boolean(
        string="UcA Extract view WARNING",
        help="Breakpoint UcA to diagnostic warning when extract view.",
    )

    breakpoint_UcA_extract_view_first_line = fields.Boolean(
        string="UcA Extract view first line",
        help="Breakpoint UcA to diagnostic when extract view.",
    )

    breakpoint_UcA_extract_xml_button = fields.Boolean(
        string="UcA Extract XML button",
        help="Breakpoint UcA gc breakpoint extract xml button.",
    )

    breakpoint_UcA_extract_xml_header = fields.Boolean(
        string="UcA Extract XML header",
        help="Breakpoint UcA gc breakpoint extract xml header.",
    )

    breakpoint_UcA_extract_xml_title = fields.Boolean(
        string="UcA Extract XML title",
        help="Breakpoint UcA gc breakpoint extract xml title.",
    )

    breakpoint_UcA_extract_xml_view_item = fields.Boolean(
        string="UcA Extract XML view item",
        help="Breakpoint UcA gc breakpoint extract xml item.",
    )

    breakpoint_UcA_extract_xml_act_window = fields.Boolean(
        string="UcA Extract XML Act Window",
        help="Breakpoint UcA gc breakpoint extract xml act window.",
    )

    breakpoint_UcA_extract_xml_div_container = fields.Boolean(
        string="UcA Extract XML div container",
        help="Breakpoint UcA gc breakpoint extract xml div container.",
    )

    breakpoint_UcA_extract_module_create_cg_model_code = fields.Boolean(
        string="UcA Extract module create cg model code",
        help=(
            "Breakpoint UcA when extract module before create"
            " code.generator.model.code ."
        ),
    )

    breakpoint_UcA_write_hook_code = fields.Boolean(
        string="UcA Write hook code",
        help="Breakpoint UcA when write code into hooks.",
    )

    breakpoint_UcA_write_hook_model = fields.Boolean(
        string="UcA Write hook model",
        help="Breakpoint UcA when write model into hooks.",
    )

    breakpoint_UcB_write_code_with_cw = fields.Boolean(
        string="UcB Write code with CodeWriter",
        help="Breakpoint UcB when write code with code_writer.",
    )

    breakpoint_UcB_write_act_window = fields.Boolean(
        string="UcB Write act_window with xml_writer",
        help="Breakpoint UcB when write act_window with xml_writer.",
    )

    breakpoint_UcB_write_data = fields.Boolean(
        string="UcB Write xml data",
        help="Breakpoint UcB when generate data to xml_data.",
    )

    breakpoint_UcB_generate_view_warning = fields.Boolean(
        string="UcB Generate view WARNING",
        help="Breakpoint UcB to diagnostic warning when generate view.",
    )

    breakpoint_UcB_generate_view_specific_form_item = fields.Boolean(
        string="UcB Generate view specific form item",
        help="Breakpoint UcB to generate specific form view item.",
    )

    breakpoint_UcB_generate_xml_view_object = fields.Boolean(
        string="UcB Generate view xml view object",
        help="Breakpoint UcB to generate xml view object.",
    )

    breakpoint_UcB_write_code_model_field = fields.Boolean(
        string="UcB Write code model field",
        help="Breakpoint UcB generate code - write model field module.",
    )

    breakpoint_UcB_write_code_model_field_prepare_field = fields.Boolean(
        string="UcB Write code model field prepare field",
        help=(
            "Breakpoint UcB generate code - prepare set of data for field to"
            " generate field."
        ),
    )

    breakpoint_UcA_extract_module_get_min_max_crop = fields.Boolean(
        string="UcA Extract module get min/max crop",
        help="Breakpoint UcA to diagnostic warning when extract view.",
    )

    # TODO need to support related field
    # devops_exec_error_ids = fields.One2many(
    # related="devops_exec_bundle_id.devops_exec_parent_error_ids"
    # )
    cg_hooks_py = fields.Char(help="Path of hooks python file.")

    template_hooks_py = fields.Char(help="Path of template hooks python file.")

    template_manifest_py = fields.Char(
        help="Path of template manifest python file."
    )

    bd_name_demo = fields.Char(help="BD name for uc0")

    bd_name_template = fields.Char(help="BD name for ucA")

    bd_name_generator = fields.Char(help="BD name for ucB")

    code_generator_demo_hooks_py = fields.Char(
        help="Path of code_generator hooks python file."
    )

    code_generator_hooks_path_relative = fields.Char(
        help="Path of code_generator hooks python file relative path."
    )

    config_path = fields.Char(
        help="Path of temporary configuration file for execution."
    )

    module_path = fields.Char(help="Path of the module.")

    template_path = fields.Char(help="Path of the template.")

    cg_path = fields.Char(help="Path of the code generator.")

    code_generator_demo_path = fields.Char(help="Path of the uc0.")

    devops_exec_bundle_id = fields.Many2one(
        comodel_name="devops.exec.bundle",
        string="Devops Exec Bundle",
    )

    devops_workspace = fields.Many2one(comodel_name="devops.workspace")

    ide_pycharm_configuration_ids = fields.One2many(
        comodel_name="devops.ide.pycharm.configuration",
        inverse_name="devops_cg_new_project_id",
        string="Pycharm configurations",
    )

    devops_exec_ids = fields.One2many(
        comodel_name="devops.exec",
        inverse_name="new_project_id",
        string="Executions",
    )

    log_error_ids = fields.One2many(
        comodel_name="devops.log.error",
        inverse_name="new_project_id",
        string="Log errors",
        readonly=True,
    )

    log_warning_ids = fields.One2many(
        comodel_name="devops.log.warning",
        inverse_name="new_project_id",
        string="Log warnings",
        readonly=True,
    )

    new_project_with_code_generator = fields.Boolean(
        default=True,
        help=(
            "Need to enable this feature if the goal is to do new_project with"
            " the code generator. Because by default, it will be installed."
            " Not working how I assume, its take 40 seconds more. Stay it at"
            " default = True."
        ),
    )

    @api.model
    def default_stage_id(self):
        return self.env.ref("erplibre_devops.devops_cg_new_project_stage_init")

    @api.depends(
        "devops_workspace",
        "module",
        "exec_start_date",
        "exec_stop_date",
        "exec_time_duration",
    )
    def _compute_name(self):
        for rec in self:
            if not isinstance(rec.id, models.NewId):
                rec.name = f"{rec.id}: "
            else:
                rec.name = ""
            rec.name += f"{rec.devops_workspace.name} - {rec.module}"
            if rec.exec_stop_date:
                rec.name += (
                    f" - finish {rec.exec_stop_date} duration"
                    f" {rec.exec_time_duration}"
                )
            elif rec.exec_start_date:
                rec.name += f" - start {rec.exec_start_date}"

    @api.depends(
        "config_debug_Uc0",
        "config_debug_UcA",
        "config_debug_UcB",
        "breakpoint_all_write_hook_begin",
        "breakpoint_all_write_hook_before_model",
        "breakpoint_all_write_hook_model_write_field",
        "breakpoint_all_prepare_data_before_write",
        "breakpoint_all_before_sync_code",
        "breakpoint_Uc0_first_line_hook",
        "breakpoint_UcA_first_line_hook",
        "breakpoint_UcB_first_line_hook",
        "breakpoint_Uc0_cg_Uc0",
        "breakpoint_all_begin_generate_file",
        "breakpoint_UcA_extract_view_warning",
        "breakpoint_UcA_extract_python_controller_warning",
        "breakpoint_UcA_extract_python_module_warning",
        "breakpoint_UcA_extract_python_module_file_warning",
        "breakpoint_UcA_extract_python_detect_field",
        "breakpoint_UcA_extract_module_create_cg_model_code",
        "breakpoint_UcA_write_hook_code",
        "breakpoint_UcA_write_hook_model",
        "breakpoint_UcB_write_code_with_cw",
        "breakpoint_UcB_write_act_window",
        "breakpoint_UcB_write_data",
        "breakpoint_UcA_extract_module_get_min_max_crop",
        "breakpoint_UcA_extract_view_first_line",
        "breakpoint_UcA_extract_xml_button",
        "breakpoint_UcA_extract_xml_header",
        "breakpoint_UcA_extract_xml_title",
        "breakpoint_UcA_extract_xml_view_item",
        "breakpoint_UcA_extract_xml_act_window",
        "breakpoint_UcA_extract_xml_div_container",
        "breakpoint_UcB_generate_view_warning",
        "breakpoint_UcB_generate_view_specific_form_item",
        "breakpoint_UcB_generate_xml_view_object",
        "breakpoint_UcB_write_code_model_field",
    )
    def _compute_can_setup_ide(self):
        for rec in self:
            rec.can_setup_ide = (
                rec.config_debug_Uc0
                + rec.config_debug_UcA
                + rec.config_debug_UcB
                + rec.breakpoint_all_write_hook_begin
                + rec.breakpoint_all_write_hook_before_model
                + rec.breakpoint_all_write_hook_model_write_field
                + rec.breakpoint_all_prepare_data_before_write
                + rec.breakpoint_all_before_sync_code
                + rec.breakpoint_Uc0_first_line_hook
                + rec.breakpoint_UcA_first_line_hook
                + rec.breakpoint_UcB_first_line_hook
                + rec.breakpoint_Uc0_cg_Uc0
                + rec.breakpoint_all_begin_generate_file
                + rec.breakpoint_UcA_extract_view_warning
                + rec.breakpoint_UcA_extract_python_controller_warning
                + rec.breakpoint_UcA_extract_python_module_warning
                + rec.breakpoint_UcA_extract_python_module_file_warning
                + rec.breakpoint_UcA_extract_python_detect_field
                + rec.breakpoint_UcA_extract_module_create_cg_model_code
                + rec.breakpoint_UcA_write_hook_code
                + rec.breakpoint_UcA_write_hook_model
                + rec.breakpoint_UcB_write_code_with_cw
                + rec.breakpoint_UcB_write_act_window
                + rec.breakpoint_UcB_write_data
                + rec.breakpoint_UcA_extract_module_get_min_max_crop
                + rec.breakpoint_UcA_extract_view_first_line
                + rec.breakpoint_UcA_extract_xml_button
                + rec.breakpoint_UcA_extract_xml_header
                + rec.breakpoint_UcA_extract_xml_title
                + rec.breakpoint_UcA_extract_xml_view_item
                + rec.breakpoint_UcA_extract_xml_act_window
                + rec.breakpoint_UcA_extract_xml_div_container
                + rec.breakpoint_UcB_generate_view_warning
                + rec.breakpoint_UcB_generate_view_specific_form_item
                + rec.breakpoint_UcB_generate_xml_view_object
                + rec.breakpoint_UcB_write_code_model_field
            )

    def action_new_project_clear_pause(self, ctx=None):
        for rec in self:
            with rec.devops_workspace.devops_create_exec_bundle(
                "New project clear pause",
                devops_cg_new_project=rec.id,
                ctx=ctx,
            ) as rec_ws:
                rec.is_pause = False
                rec.config_debug_Uc0 = False
                rec.config_debug_UcA = False
                rec.config_debug_UcB = False
                rec.breakpoint_all_write_hook_begin = False
                rec.breakpoint_all_write_hook_before_model = False
                rec.breakpoint_all_write_hook_model_write_field = False
                rec.breakpoint_all_prepare_data_before_write = False
                rec.breakpoint_all_before_sync_code = False
                rec.breakpoint_Uc0_first_line_hook = False
                rec.breakpoint_UcA_first_line_hook = False
                rec.breakpoint_UcB_first_line_hook = False
                rec.breakpoint_Uc0_cg_Uc0 = False
                rec.breakpoint_all_begin_generate_file = False
                rec.breakpoint_UcA_extract_python_controller_warning = False
                rec.breakpoint_UcA_extract_python_module_warning = False
                rec.breakpoint_UcA_extract_python_module_file_warning = False
                rec.breakpoint_UcA_extract_python_detect_field = False
                rec.breakpoint_UcA_extract_module_create_cg_model_code = False
                rec.breakpoint_UcA_write_hook_code = False
                rec.breakpoint_UcA_write_hook_model = False
                rec.breakpoint_UcB_write_code_with_cw = False
                rec.breakpoint_UcB_write_act_window = False
                rec.breakpoint_UcB_write_data = False
                rec.breakpoint_UcA_extract_view_warning = False
                rec.breakpoint_UcA_extract_module_get_min_max_crop = False
                rec.breakpoint_UcA_extract_view_first_line = False
                rec.breakpoint_UcA_extract_xml_button = False
                rec.breakpoint_UcA_extract_xml_header = False
                rec.breakpoint_UcA_extract_xml_title = False
                rec.breakpoint_UcA_extract_xml_view_item = False
                rec.breakpoint_UcA_extract_xml_act_window = False
                rec.breakpoint_UcA_extract_xml_div_container = False
                rec.breakpoint_UcB_generate_view_warning = False
                rec.breakpoint_UcB_generate_view_specific_form_item = False
                rec.breakpoint_UcB_generate_xml_view_object = False
                rec.breakpoint_UcB_write_code_model_field = False

    @api.depends("exec_start_date", "exec_stop_date")
    def _compute_exec_time_duration(self):
        for rec in self:
            if rec.exec_start_date and rec.exec_stop_date:
                rec.exec_time_duration = (
                    rec.exec_stop_date - rec.exec_start_date
                ).total_seconds()
            else:
                rec.exec_time_duration = None

    @api.multi
    def action_new_project_debug(self, ctx=None):
        for rec in self:
            with rec.devops_workspace.devops_create_exec_bundle(
                "New project debug", devops_cg_new_project=rec.id, ctx=ctx
            ) as rec_ws:
                has_debug = False
                stage_Uc0 = self.env.ref(
                    "erplibre_devops.devops_cg_new_project_stage_generate_Uc0"
                )
                if rec.stage_id == stage_Uc0:
                    rec.config_debug_Uc0 = True
                    has_debug = True
                stage_uca = self.env.ref(
                    "erplibre_devops.devops_cg_new_project_stage_generate_uca"
                )
                if rec.stage_id == stage_uca:
                    rec.config_debug_UcA = True
                    has_debug = True
                stage_ucb = self.env.ref(
                    "erplibre_devops.devops_cg_new_project_stage_generate_ucb"
                )
                if rec.stage_id == stage_ucb:
                    rec.config_debug_UcB = True
                    has_debug = True
                if has_debug:
                    rec.with_context(rec_ws._context).action_new_project()
                else:
                    raise exceptions.Warning(
                        "Cannot support debug for this stage"
                    )

    @api.multi
    def action_new_project_setup_IDE(
        self,
        ctx=None,
        conf_add_mode=None,
        conf_add_db=None,
        conf_add_module=None,
        conf_add_config_path="config.conf",
    ):
        for rec in self:
            with rec.devops_workspace.devops_create_exec_bundle(
                "New project setup IDE", devops_cg_new_project=rec.id, ctx=ctx
            ) as rec_ws:
                if not rec.can_setup_ide:
                    continue
                has_bp = rec_ws._context.get(
                    "new_project_with_breakpoint", True
                )
                if has_bp:
                    lst_name = []
                    dct_condition = {}
                    # Create breakpoint data
                    for field_name, field_value in rec._fields.items():
                        if not (
                            field_name.startswith("breakpoint_")
                            and field_value.type == "boolean"
                        ):
                            continue
                        field_id = getattr(rec, field_name)
                        if not field_id:
                            continue
                        lst_name.append(field_name)
                    if lst_name:
                        bp_ids = (
                            self.env["devops.ide.breakpoint"]
                            .search([("name", "in", lst_name)])
                            .exists()
                        )
                        if len(bp_ids) != len(lst_name):
                            # error, missing breakpoint, search it
                            for name in lst_name:
                                find_it = bp_ids.filtered(
                                    lambda a: a.name == name
                                )
                                if not find_it:
                                    raise Exception(
                                        "Cannot find breakpoint name"
                                        f" '{name}'."
                                    )
                        if bp_ids:
                            rec.add_breakpoint(bp_ids=bp_ids)
                if conf_add_mode:
                    rec_ws.ide_pycharm.add_configuration(
                        conf_add_mode=conf_add_mode,
                        conf_add_db=conf_add_db,
                        conf_add_module=conf_add_module,
                        conf_add_config_path=conf_add_config_path,
                    )

    @api.multi
    def action_new_project(self, ctx=None):
        for rec in self:
            with rec.devops_workspace.devops_create_exec_bundle(
                "Generate new project with CG",
                devops_cg_new_project=rec.id,
                ctx=ctx,
            ) as rec_ws:
                rec.is_pause = False
                rec.exec_start_date = fields.Datetime.now(self)
                rec.has_error = False
                rec.has_warning = False
                stop_exec = False
                count_stage_execute = 0
                id_exec_bundle = rec_ws._context.get("devops_exec_bundle")
                one_stage_only = rec_ws._context.get("one_stage_only", False)
                exec_bundle_parent_id = self.env["devops.exec.bundle"].browse(
                    id_exec_bundle
                )
                stage_init_id = self.env.ref(
                    "erplibre_devops.devops_cg_new_project_stage_init"
                )
                stage_uc0_id = self.env.ref(
                    "erplibre_devops.devops_cg_new_project_stage_generate_Uc0"
                )
                stage_uca_id = self.env.ref(
                    "erplibre_devops.devops_cg_new_project_stage_generate_uca"
                )
                stage_ucb_id = self.env.ref(
                    "erplibre_devops.devops_cg_new_project_stage_generate_ucb"
                )
                # stage_terminate_id = self.env.ref(
                #     "erplibre_devops.devops_cg_new_project_stage_generate_terminate"
                # )

                # Stage INIT
                if rec.stage_id == stage_init_id:
                    rec.action_init(rec_ws=rec_ws)
                    count_stage_execute += 1

                if one_stage_only and count_stage_execute > 0:
                    stop_exec = True
                elif exec_bundle_parent_id.devops_exec_parent_error_ids:
                    rec.has_error = True
                    stop_exec = True

                # Check if create/update UcA or only run it
                if (
                    rec.use_existing_meta_module
                    and (
                        rec.use_existing_meta_module_uca_only
                        or rec.use_existing_meta_module_ucb_only
                    )
                    # and rec_ws.os_path_exists(
                    #     rec.template_path, to_instance=True
                    # )
                ):
                    if rec.use_existing_meta_module_uca_only:
                        rec.stage_id = self.env.ref(
                            "erplibre_devops.devops_cg_new_project_stage_generate_uca"
                        )
                    elif rec.use_existing_meta_module_ucb_only:
                        rec.stage_id = self.env.ref(
                            "erplibre_devops.devops_cg_new_project_stage_generate_ucb"
                        )

                # Stage Uc0
                # This stage will create a new UcA or update it
                if not stop_exec and rec.stage_id == stage_uc0_id:
                    rec.action_generate_Uc0(rec_ws=rec_ws)
                    count_stage_execute += 1

                if one_stage_only and count_stage_execute > 0:
                    stop_exec = True
                elif exec_bundle_parent_id.devops_exec_parent_error_ids:
                    rec.has_error = True
                    stop_exec = True

                # Stage UcA
                if not stop_exec and rec.stage_id == stage_uca_id:
                    rec.action_generate_uca(rec_ws=rec_ws)
                    count_stage_execute += 1

                if one_stage_only and count_stage_execute > 0:
                    stop_exec = True
                elif exec_bundle_parent_id.devops_exec_parent_error_ids:
                    rec.has_error = True
                    stop_exec = True

                # Stage UcB
                if (
                    not rec.use_existing_meta_module_uca_only
                    and not stop_exec
                    and rec.stage_id == stage_ucb_id
                ):
                    rec.action_generate_ucb(rec_ws=rec_ws)
                    count_stage_execute += 1

                rec.exec_stop_date = fields.Datetime.now(self)
                rec.execution_finish = True
                if rec.log_error_ids:
                    rec.has_error = True
                if rec.log_warning_ids:
                    rec.has_warning = True

    @api.multi
    def action_init(self, ctx=None, rec_ws=None):
        for rec in self:
            ws_param = rec_ws if rec_ws else rec.devops_workspace
            with ws_param.devops_create_exec_bundle(
                "New project generate 1.init", devops_cg_new_project=rec.id
            ) as ws:
                rec.stage_id = self.env.ref(
                    "erplibre_devops.devops_cg_new_project_stage_init"
                )
                if not ws.os_path_exists(rec.directory, to_instance=True):
                    msg_error = f"Path directory '{rec.directory}' not exist."
                    raise Exception(msg_error)

                if not rec.directory_cg:
                    rec.directory_cg = rec.directory
                if not ws.os_path_exists(rec.directory_cg, to_instance=True):
                    msg_error = (
                        f"Path cg directory '{rec.directory_cg}' not exist."
                    )
                    raise Exception(msg_error)

                if not rec.directory_template:
                    rec.directory_template = rec.directory
                if not ws.os_path_exists(
                    rec.directory_template, to_instance=True
                ):
                    msg_error = (
                        f"Path template directory '{rec.directory_template}'"
                        " not exist."
                    )
                    raise Exception(msg_error)

                if not rec.module:
                    msg_error = "Module name is missing."
                    raise Exception(msg_error)

                # Get code_generator name
                if not rec.code_generator_name:
                    rec.code_generator_name = f"code_generator_{rec.module}"

                # Get template name
                if not rec.template_name:
                    rec.template_name = f"code_generator_template_{rec.module}"

                # TODO copy directory in temp workspace file before update it
                rec.module_path = os.path.join(rec.directory, rec.module)
                is_over = rec.validate_path_ready_to_be_override(
                    rec.module, rec.directory, ws, path=rec.module_path
                )
                if not rec.force and not is_over:
                    msg_error = (
                        f"Cannot generate on module path '{rec.module_path}'"
                    )
                    raise Exception(msg_error)

                rec.cg_path = os.path.join(
                    rec.directory_cg, rec.code_generator_name
                )
                rec.cg_hooks_py = os.path.join(rec.cg_path, "hooks.py")
                if (
                    not rec.force
                    and not rec.validate_path_ready_to_be_override(
                        rec.code_generator_name,
                        rec.directory_cg,
                        ws,
                        path=rec.cg_path,
                    )
                ):
                    msg_error = f"Cannot generate on cg path '{rec.cg_path}'"
                    raise Exception(msg_error)

                rec.template_path = os.path.join(
                    rec.directory_template, rec.template_name
                )
                rec.template_hooks_py = os.path.join(
                    rec.template_path, "hooks.py"
                )
                rec.template_manifest_py = os.path.join(
                    rec.template_path, "__manifest__.py"
                )
                if (
                    not rec.force
                    and not rec.validate_path_ready_to_be_override(
                        rec.template_name,
                        rec.directory_template,
                        ws,
                        path=rec.template_path,
                    )
                ):
                    msg_error = (
                        "Cannot generate on template path"
                        f" '{rec.template_path}'"
                    )
                    raise Exception(msg_error)

                # Validate code_generator_demo
                rec.code_generator_demo_path = os.path.join(
                    CODE_GENERATOR_DIRECTORY, CODE_GENERATOR_DEMO_NAME
                )
                rec.code_generator_demo_hooks_py = os.path.join(
                    rec.code_generator_demo_path, "hooks.py"
                )
                rec.code_generator_hooks_path_relative = os.path.join(
                    CODE_GENERATOR_DEMO_NAME, "hooks.py"
                )
                if not ws.os_path_exists(
                    rec.code_generator_demo_path, to_instance=True
                ):
                    msg_error = (
                        "code_generator_demo is not accessible"
                        f" '{rec.code_generator_demo_path}'"
                    )
                    raise Exception(msg_error)

                # Update configuration
                config = configparser.ConfigParser()
                config.read(rec.odoo_config)
                addons_path = config.get("options", "addons_path")
                lst_addons_path = addons_path.split(",")
                lst_directory = list(
                    {
                        rec.directory_cg,
                        rec.directory,
                        rec.directory_template,
                    }
                )
                has_change = False
                for new_addons_path in lst_directory:
                    for actual_addons_path in lst_addons_path:
                        if not actual_addons_path:
                            continue
                        # Validate if not existing and valide is different path
                        relative_actual_addons_path = os.path.relpath(
                            actual_addons_path
                        )
                        relative_new_addons_path = os.path.relpath(
                            new_addons_path
                        )
                        if (
                            relative_actual_addons_path
                            == relative_new_addons_path
                        ):
                            break
                    else:
                        lst_addons_path.insert(0, new_addons_path)
                        has_change = True
                if has_change:
                    config.set(
                        "options", "addons_path", ",".join(lst_addons_path)
                    )
                temp_file = tempfile.mktemp()
                with open(temp_file, "w") as configfile:
                    config.write(configfile)
                _logger.info(f"Create temporary config file: {temp_file}")
                rec.config_path = temp_file

                rec.stage_id = self.env.ref(
                    "erplibre_devops.devops_cg_new_project_stage_generate_Uc0"
                )

    @api.multi
    def action_generate_Uc0(self, ctx=None, rec_ws=None):
        for rec in self:
            ws_param = rec_ws if rec_ws else rec.devops_workspace
            with ws_param.devops_create_exec_bundle(
                "New project generate 2.Uc0", devops_cg_new_project=rec.id
            ) as ws:
                rec.stage_id = self.env.ref(
                    "erplibre_devops.devops_cg_new_project_stage_generate_Uc0"
                )

                v_dct_log_error = {
                    "new_project_id": rec.id,
                }

                if not (
                    rec.validate_path_ready_to_be_override(
                        CODE_GENERATOR_DEMO_NAME, CODE_GENERATOR_DIRECTORY, ws
                    )
                    and self.search_and_replace_file(
                        rec.code_generator_demo_hooks_py,
                        [
                            (
                                KEY_REPLACE_CODE_GENERATOR_DEMO
                                % CODE_GENERATOR_DEMO_NAME,
                                KEY_REPLACE_CODE_GENERATOR_DEMO
                                % rec.template_name,
                            ),
                            (
                                'value["enable_sync_template"] = False',
                                'value["enable_sync_template"] = True',
                            ),
                            (
                                "# path_module_generate ="
                                " os.path.normpath(os.path.join(os.path.dirname(__file__),"
                                " '..'))",
                                "path_module_generate ="
                                f' "{rec.directory_template}"',
                            ),
                            (
                                '# "path_sync_code": path_module_generate,',
                                '"path_sync_code": path_module_generate,',
                            ),
                            (
                                '# value["template_module_path_generated_extension"]'
                                ' = "."',
                                'value["template_module_path_generated_extension"]'
                                f' = "{rec.directory_cg}"',
                            ),
                        ],
                        v_dct_log_error=v_dct_log_error,
                    )
                ):
                    # TODO create a variable in CG to change path of module generated from uc0
                    return False

                if not rec.bd_name_demo:
                    rec.bd_name_demo = (
                        f"new_project_code_generator_demo_{uuid.uuid4()}"[:63]
                    )

                if rec.new_project_with_code_generator:
                    cmd = (
                        "./script/database/db_restore.py --database"
                        f" {rec.bd_name_demo}"
                    )
                else:
                    cmd = (
                        "./script/database/db_restore.py --database"
                        f" {rec.bd_name_demo} --restore_image"
                        " addons_install_code_generator_basic"
                    )
                _logger.info(cmd)
                exec_id = ws.execute(cmd=cmd, to_instance=True)
                rec.has_error = bool(exec_id.devops_exec_error_ids.exists())
                if rec.has_error:
                    _logger.info("Exit new project")
                    continue

                # TODO need pause if ask? and continue if ask
                if rec.can_setup_ide:
                    _logger.info(
                        "========= Ask stop, setup pycharm and exit ========="
                    )
                    rec.is_pause = True
                    # rec.config_path is a temporary file, it will not work. Use default config instead
                    rec.action_new_project_setup_IDE(
                        conf_add_mode="install",
                        conf_add_db=rec.bd_name_demo,
                        conf_add_module="code_generator_demo",
                        # conf_add_config_path=rec.config_path,
                    )
                    continue

                _logger.info(
                    "========= GENERATE code_generator_demo ========="
                )

                if rec.active_coverage:
                    cmd = (
                        "./script/addons/coverage_install_addons_dev.sh"
                        f" {rec.bd_name_demo} code_generator_demo"
                        f" {rec.config_path}"
                    )
                else:
                    cmd = (
                        "./script/addons/install_addons_dev.sh"
                        f" {rec.bd_name_demo} code_generator_demo"
                        f" {rec.config_path}"
                    )
                exec_id = ws.with_context(
                    devops_cg_new_project=rec.id
                ).execute(cmd=cmd, to_instance=True)
                rec.has_error = bool(exec_id.devops_exec_error_ids.exists())
                if rec.has_error:
                    _logger.info("Exit new project")
                    continue

                if not self.keep_bd_alive:
                    cmd = (
                        "./.venv/bin/python3 ./odoo/odoo-bin db --drop"
                        f" --database {rec.bd_name_demo}"
                    )
                    _logger.info(cmd)
                    ws.execute(cmd=cmd, to_instance=True)

                # Revert code_generator_demo
                self.restore_git_code_generator_demo(
                    CODE_GENERATOR_DIRECTORY,
                    rec.code_generator_hooks_path_relative,
                )

                # Validate
                if not ws.os_path_exists(rec.template_path, to_instance=True):
                    raise Exception(
                        f"Module template not exists '{rec.template_path}'"
                    )
                else:
                    _logger.info(
                        f"Module template exists '{rec.template_path}'"
                    )
                if not rec.has_error:
                    rec.stage_id = self.env.ref(
                        "erplibre_devops.devops_cg_new_project_stage_generate_uca"
                    )

    @api.multi
    def action_generate_uca(self, ctx=None, rec_ws=None):
        for rec in self:
            ws_param = rec_ws if rec_ws else rec.devops_workspace
            with ws_param.devops_create_exec_bundle(
                "New project generate 3.UcA", devops_cg_new_project=rec.id
            ) as ws:
                rec.stage_id = self.env.ref(
                    "erplibre_devops.devops_cg_new_project_stage_generate_uca"
                )
                v_dct_log_error = {
                    "new_project_id": rec.id,
                }
                # Execute all
                if not rec.bd_name_template:
                    rec.bd_name_template = (
                        f"new_project_code_generator_template_{uuid.uuid4()}"[
                            :63
                        ]
                    )

                if rec.new_project_with_code_generator:
                    cmd = (
                        "./script/database/db_restore.py --database"
                        f" {rec.bd_name_template}"
                    )
                else:
                    cmd = (
                        "./script/database/db_restore.py --database"
                        f" {rec.bd_name_template} --restore_image"
                        " addons_install_code_generator_basic"
                    )
                exec_id = ws.with_context(
                    devops_cg_new_project=rec.id
                ).execute(cmd=cmd, to_instance=True)
                rec.has_error = bool(exec_id.devops_exec_error_ids.exists())
                if rec.has_error:
                    _logger.info("Exit new project")
                    continue
                _logger.info(cmd)
                _logger.info(
                    f"========= GENERATE {rec.template_name} ========="
                )
                # TODO maybe the module exist somewhere else
                if ws.os_path_exists(rec.module_path, to_instance=True):
                    # Install module before running code generator
                    cmd = (
                        "./script/code_generator/search_class_model.py"
                        f" --quiet -d {rec.module_path} -t {rec.template_path}"
                    )
                    if rec.uca_option_with_inherit:
                        cmd += " --with_inherit"
                    _logger.info(cmd)
                    exec_id = ws.with_context(
                        devops_cg_new_project=rec.id
                    ).execute(cmd=cmd, to_instance=True)
                    rec.has_error = bool(
                        exec_id.devops_exec_error_ids.exists()
                    )
                    if rec.has_error:
                        _logger.info("Exit new project")
                        continue

                lst_template_hooks_py_replace = []
                lst_template_manifest_py_replace = []
                # Extract module dependency
                # ir_module_id = self.env["ir.module.module"].search(
                #     [("name", "=", rec.module)], limit=1
                # )
                # if ir_module_id:
                #     lst_depend_module = [
                #         a.name for a in ir_module_id.dependencies_id
                #     ]
                # else:
                #     lst_depend_module = []
                lst_depend_module = []
                if rec.mode_view in ["same_view", "new_view"]:
                    lst_template_hooks_py_replace.append(
                        (
                            'value["enable_template_wizard_view"] = False',
                            'value["enable_template_wizard_view"] = True',
                        )
                    )
                    if rec.mode_view == "new_view":
                        lst_template_hooks_py_replace.append(
                            (
                                'value["force_generic_template_wizard_view"] ='
                                " False",
                                'value["force_generic_template_wizard_view"] ='
                                " True",
                            )
                        )
                if rec.config_uca_enable_export_data:
                    lst_template_hooks_py_replace.append(
                        (
                            'value["enable_template_website_snippet_view"] ='
                            " False",
                            f'value["enable_template_website_snippet_view"] ='
                            f" False\n"
                            f"       "
                            f' value["template_auto_export_data"]'
                            f" = True\n"
                            f"       "
                            f' value["template_auto_export_data_exclude_model"]'
                            f" = 'devops.db.image;devops.exec;devops.exec.bundle;devops.ide.pycharm;"
                            f"devops.log.makefile.target;devops.workspace.terminal;devops.workspace;"
                            f"devops.test.case;devops.test.plan;erplibre.mode;erplibre.mode.env;"
                            f"erplibre.mode.exec;erplibre.mode.source;erplibre.mode.version.base;"
                            f"erplibre.mode.version.erplibre'",
                        )
                    )
                if rec.mode_view_snippet in ["enable_snippet"]:
                    lst_template_hooks_py_replace.append(
                        (
                            'value["enable_template_website_snippet_view"] ='
                            " False",
                            'value["enable_template_website_snippet_view"] ='
                            f" {rec.mode_view_snippet_enable_template_website_snippet_view}\n"
                            "       "
                            ' value["template_generate_website_snippet_generic_model"]'
                            f' = "{rec.mode_view_snippet_template_generate_website_snippet_generic_mdl}"\n'
                            "       "
                            ' value["template_generate_website_snippet_controller_feature"]'
                            f' = "{rec.mode_view_snippet_template_generate_website_snippet_ctrl_featur}"\n'
                            "       "
                            ' value["template_generate_website_enable_javascript"]'
                            f" = {rec.mode_view_snippet_template_generate_website_enable_javascript}\n"
                            "       "
                            ' value["template_generate_website_snippet_type"]'
                            f' = "{rec.mode_view_snippet_template_generate_website_snippet_type}"',
                        )
                    )

                    lst_template_manifest_py_replace.append(
                        (
                            '"depends": [',
                            '"depends": [\n       '
                            ' "code_generator_website_snippet",',
                        )
                    )

                    lst_depend_module.append("code_generator_website_snippet")

                if lst_depend_module:
                    l_d = [f'"{a}"' for a in lst_depend_module]
                    lst_template_hooks_py_replace.append(
                        (
                            "code_generator_id.add_module_dependency(lst_depend_module)",
                            f'lst_depend_module.extend([{", ".join(l_d)}])\n'
                            "       "
                            " code_generator_id.add_module_dependency(lst_depend_module)",
                        )
                    )

                # Add model from config
                if self.config:
                    config = json.loads(self.config)
                    config_lst_model = config.get("model")
                    str_lst_model = "; ".join(
                        [a.get("name") for a in config_lst_model]
                    )

                    has_error = False
                    try:
                        self.env[
                            "devops.ide.breakpoint"
                        ].get_no_line_breakpoint(
                            'value\["template_model_name"\] =',
                            rec.template_hooks_py,
                            ws,
                        )
                    except Exception:
                        _logger.warning(
                            "Cannot find template_model_name"
                            f" configuration into {rec.template_hooks_py}"
                        )
                        has_error = True
                    if not has_error and str_lst_model:
                        old_str = 'value["template_model_name"] ='
                        new_str = (
                            'value["template_model_name"] ='
                            f' "{str_lst_model};"\n       '
                            ' value["template_model_name"] +='
                        )
                        lst_template_hooks_py_replace.append(
                            (old_str, new_str)
                        )
                    if not has_error and rec.model_to_remove:
                        for (
                            model_to_remove
                        ) in rec.model_to_remove.strip().split(";"):
                            old_str = f"{model_to_remove};"
                            new_str = ""
                            lst_template_hooks_py_replace.append(
                                (old_str, new_str)
                            )

                if lst_template_hooks_py_replace:
                    self.search_and_replace_file(
                        rec.template_hooks_py,
                        lst_template_hooks_py_replace,
                        v_dct_log_error=v_dct_log_error,
                    )
                if lst_template_manifest_py_replace:
                    self.search_and_replace_file(
                        rec.template_manifest_py,
                        lst_template_manifest_py_replace,
                        v_dct_log_error=v_dct_log_error,
                    )

                # TODO maybe the module exist somewhere else
                if ws.os_path_exists(rec.module_path, to_instance=True):
                    # TODO do we need to diagnostic installing module?

                    if rec.active_coverage:
                        cmd = (
                            "./script/addons/coverage_install_addons_dev.sh"
                            f" {rec.bd_name_template} {rec.module} {rec.config_path}"
                        )
                    else:
                        cmd = (
                            "./script/addons/install_addons_dev.sh"
                            f" {rec.bd_name_template} {rec.module} {rec.config_path}"
                        )
                    _logger.info(cmd)
                    exec_id = ws.with_context(
                        devops_cg_new_project=rec.id
                    ).execute(cmd=cmd, to_instance=True)
                    rec.has_error = bool(
                        exec_id.devops_exec_error_ids.exists()
                    )
                    if rec.has_error:
                        _logger.info("Exit new project")
                        continue

                # TODO need pause if ask? and continue if ask
                if rec.can_setup_ide:
                    _logger.info(
                        "========= Ask stop, setup pycharm and exit ========="
                    )
                    rec.is_pause = True
                    # rec.config_path is a temporary file, it will not work. Use default config instead
                    rec.action_new_project_setup_IDE(
                        conf_add_mode="install",
                        conf_add_db=rec.bd_name_template,
                        conf_add_module=rec.template_name,
                        # conf_add_config_path=rec.config_path,
                    )
                    continue

                if rec.active_coverage:
                    cmd = (
                        "./script/addons/coverage_install_addons_dev.sh"
                        f" {rec.bd_name_template} {rec.template_name} {rec.config_path}"
                    )
                else:
                    cmd = (
                        "./script/addons/install_addons_dev.sh"
                        f" {rec.bd_name_template}"
                        f" {rec.template_name} {rec.config_path}"
                    )
                _logger.info(cmd)
                exec_id = ws.with_context(
                    devops_cg_new_project=rec.id
                ).execute(cmd=cmd, to_instance=True)

                rec.has_error = bool(exec_id.devops_exec_error_ids.exists())

                if not self.keep_bd_alive:
                    cmd = (
                        "./.venv/bin/python3 ./odoo/odoo-bin db --drop"
                        f" --database {rec.bd_name_template}"
                    )
                    _logger.info(cmd)
                    ws.execute(cmd=cmd, to_instance=True)

                # Validate
                if not ws.os_path_exists(rec.cg_path, to_instance=True):
                    raise Exception(f"Module cg not exists '{rec.cg_path}'")
                else:
                    _logger.info(f"Module cg exists '{rec.cg_path}'")

                if not rec.has_error:
                    rec.stage_id = self.env.ref(
                        "erplibre_devops.devops_cg_new_project_stage_generate_ucb"
                    )

    @api.multi
    def action_generate_ucb(self, ctx=None, rec_ws=None):
        for rec in self:
            ws_param = rec_ws if rec_ws else rec.devops_workspace
            with ws_param.devops_create_exec_bundle(
                "New project generate 4.UcB", devops_cg_new_project=rec.id
            ) as ws:
                rec.stage_id = self.env.ref(
                    "erplibre_devops.devops_cg_new_project_stage_generate_ucb"
                )
                v_dct_log_error = {
                    "new_project_id": rec.id,
                }
                if not rec.bd_name_generator:
                    rec.bd_name_generator = (
                        f"new_project_code_generator_{uuid.uuid4()}"[:63]
                    )

                if rec.new_project_with_code_generator:
                    cmd = (
                        "./script/database/db_restore.py --database"
                        f" {rec.bd_name_generator}"
                    )
                else:
                    cmd = (
                        "./script/database/db_restore.py --database"
                        f" {rec.bd_name_generator} --restore_image"
                        " addons_install_code_generator_basic"
                    )
                _logger.info(cmd)
                exec_id = ws.with_context(
                    devops_cg_new_project=rec.id
                ).execute(cmd=cmd, to_instance=True)
                _logger.info(
                    f"========= GENERATE {rec.code_generator_name} ========="
                )

                rec.has_error = bool(exec_id.devops_exec_error_ids.exists())
                if rec.has_error:
                    _logger.info("Exit new project")
                    continue

                # Add field from config
                if self.config:
                    lst_update_cg = []
                    config = json.loads(self.config)
                    config_lst_model = config.get("model")
                    for model in config_lst_model:
                        model_name = model.get("name")
                        dct_field = {}
                        # TODO add here nomenclator to each model
                        for a in model.get("fields"):
                            dct_value = {"ttype": a.get("type")}
                            if "relation" in a.keys():
                                dct_value["relation"] = a["relation"]
                            if "relation_field" in a.keys():
                                dct_value["relation_field"] = a[
                                    "relation_field"
                                ]
                            if "description" in a.keys():
                                dct_value["field_description"] = a[
                                    "description"
                                ]
                            dct_field[a.get("name")] = dct_value
                        if "name" not in dct_field.keys():
                            dct_field["name"] = {"ttype": "char"}
                        old_str = (
                            f'model_model = "{model_name}"\n       '
                            " code_generator_id.add_update_model(model_model)"
                        )
                        new_str = (
                            f'model_model = "{model_name}"\n        dct_field'
                            f" = {dct_field}\n       "
                            " code_generator_id.add_update_model(model_model,"
                            " dct_field=dct_field)"
                        )
                        lst_update_cg.append((old_str, new_str))

                    # Force add menu and access
                    # if rec.mode_view in ["same_view", "new_view"]:
                    #     lst_update_cg.append(
                    #         ('"disable_generate_menu": True,', "")
                    #     )
                    # lst_update_cg.append(
                    #     ('"disable_generate_access": True,', "")
                    # )
                    #             # TODO add option nomenclature
                    #             if True:
                    #                 # Add option "nomenclature", this will export data from all generated model
                    #                 #  This is a mess when inherit another model
                    #                 txt_replace = 'env["code.generator.writer"].create(value)'
                    #                 txt_replace_to = f"""        values = {
                    #     "s_data2export": "nomenclator",
                    # }
                    # event_config = env["res.config.settings"].sudo().create(values)
                    # event_config.execute()\n        """ + txt_replace
                    #                 lst_update_cg.append((txt_replace, txt_replace_to))
                    self.search_and_replace_file(
                        rec.cg_hooks_py,
                        lst_update_cg,
                        v_dct_log_error=v_dct_log_error,
                    )

                # TODO need pause if ask? and continue if ask
                if rec.can_setup_ide:
                    _logger.info(
                        "========= Ask stop, setup pycharm and exit ========="
                    )
                    rec.is_pause = True
                    # rec.config_path is a temporary file, it will not work. Use default config instead
                    rec.action_new_project_setup_IDE(
                        conf_add_mode="install",
                        conf_add_db=rec.bd_name_generator,
                        conf_add_module=rec.code_generator_name,
                        # conf_add_config_path=rec.config_path,
                    )
                    continue

                if rec.active_coverage:
                    cmd = (
                        "./script/addons/coverage_install_addons_dev.sh"
                        f" {rec.bd_name_generator} {rec.code_generator_name} {rec.config_path}"
                    )
                else:
                    cmd = (
                        "./script/addons/install_addons_dev.sh"
                        f" {rec.bd_name_generator} {rec.code_generator_name} {rec.config_path}"
                    )
                _logger.info(cmd)
                exec_id = ws.with_context(
                    devops_cg_new_project=rec.id
                ).execute(
                    cmd=cmd,
                    to_instance=True,
                )

                rec.has_error = bool(exec_id.devops_exec_error_ids.exists())

                if not self.keep_bd_alive:
                    cmd = (
                        "./.venv/bin/python3 ./odoo/odoo-bin db --drop"
                        f" --database {rec.bd_name_generator}"
                    )
                    _logger.info(cmd)
                    ws.execute(cmd=cmd, to_instance=True)

                # Validate
                if not ws.os_path_exists(rec.module_path, to_instance=True):
                    raise Exception(f"Module not exists '{rec.module_path}'")
                else:
                    _logger.info(f"Module exists '{rec.module_path}'")

                if not rec.has_error:
                    rec.stage_id = rec.env.ref(
                        "erplibre_devops.devops_cg_new_project_stage_generate_terminate"
                    )

    @api.model
    def validate_path_ready_to_be_override(self, name, directory, ws, path=""):
        if not path:
            path = os.path.join(directory, name)
        if not ws.os_path_exists(path, to_instance=True):
            return True
        # Check if in git
        # TODO complete me, need to check into instance
        try:
            git_repo = Repo(directory)
        except NoSuchPathError:
            raise Exception(f"Directory not existing '{directory}'")
        except InvalidGitRepositoryError:
            raise Exception(
                f"The path '{path}' exist, but no git repo, use force to"
                " ignore it."
            )

        if self.stop_execution_if_env_not_clean:
            status = git_repo.git.status(name, porcelain=True)
            if status:
                msg = (
                    f"The directory '{path}' has git difference, use force to"
                    " ignore it."
                )
                raise Exception(msg)
        return True

    @staticmethod
    def restore_git_code_generator_demo(
        code_generator_demo_path, relative_path
    ):
        # TODO support to remote
        try:
            git_repo = Repo(code_generator_demo_path)
        except NoSuchPathError:
            raise Exception(
                f"Directory not existing '{code_generator_demo_path}'"
            )
        except InvalidGitRepositoryError:
            raise Exception(
                f"The path '{code_generator_demo_path}' exist, but no git repo"
            )

        git_repo.git.restore(relative_path)

    @api.multi
    def add_breakpoint(
        self,
        bp_id=None,
        bp_ids=None,
        lst_bp_id=None,
        file=None,
        key=None,
        no_line=None,
        condition=None,
    ):
        # lst_bp_id is deprecated
        # bp_id is deprecated, use instead bp_ids
        for rec in self:
            with rec.devops_workspace.devops_create_exec_bundle(
                "New project add breakpoint", devops_cg_new_project=rec.id
            ) as rec_ws:
                lst_no_line = []
                if bp_ids:
                    for rec_bp_id in bp_ids:
                        result = rec_bp_id.get_breakpoint_info(
                            rec_ws, new_project_id=rec, condition=condition
                        )
                        lst_no_line.extend(result)
                elif lst_bp_id:
                    for rec_bp_id, s_cond in lst_bp_id:
                        result = rec_bp_id.get_breakpoint_info(
                            rec_ws, new_project_id=rec, condition=s_cond
                        )
                        lst_no_line.extend(result)
                elif bp_id:
                    lst_no_line = bp_id.get_breakpoint_info(
                        rec_ws, new_project_id=rec, condition=condition
                    )
                elif file:
                    file_path = os.path.normpath(
                        os.path.join(
                            rec_ws.folder,
                            file,
                        )
                    )
                    if key:
                        lst_no_line = (
                            file_path,
                            self.env[
                                "devops.ide.breakpoint"
                            ].get_no_line_breakpoint(key, file_path, rec_ws),
                            condition,
                        )
                    elif no_line:
                        lst_no_line = [(file_path, int(no_line), condition)]

                if lst_no_line:
                    for filename, lst_line, s_cond in lst_no_line:
                        rec_ws.ide_pycharm.add_breakpoint(
                            filename,
                            lst_line,
                            condition=s_cond,
                            minus_1_line=True,
                        )
                else:
                    _logger.warning(
                        "Missing no_line to method add_breakpoint. Or specify"
                        " a key to research from file."
                    )

    def search_and_replace_file(
        self, filepath, lst_search_and_replace, v_dct_log_error
    ):
        """
        lst_search_and_replace is a list of tuple, first item is search, second is replace
        """
        # TODO open file from workspace and not from this execution
        # TODO validate file exist before try to open it
        with open(filepath, "r") as file:
            txt = file.read()
            for search, replace in lst_search_and_replace:
                if search not in txt:
                    msg_error = f"Cannot find '{search}' in file '{filepath}'"
                    v_dct_log_error["name"] = msg_error
                    self.env["devops.log.error"].create(v_dct_log_error)
                    continue
                    # raise Exception(msg_error)
                txt = txt.replace(search, replace)
        with open(filepath, "w") as file:
            file.write(txt)
        return True

    @api.multi
    def action_kill_pycharm(self):
        for rec in self:
            with rec.devops_workspace.devops_create_exec_bundle(
                "New project kill PyCharm", devops_cg_new_project=rec.id
            ) as rec_ws:
                rec_ws.ide_pycharm.action_kill_pycharm()

    @api.multi
    def action_start_pycharm(self, ctx=None):
        for rec in self:
            with rec.devops_workspace.devops_create_exec_bundle(
                "New project start PyCharm", devops_cg_new_project=rec.id
            ) as rec_ws:
                rec_ws.ide_pycharm.action_start_pycharm(
                    ctx=ctx, new_project_id=self
                )
