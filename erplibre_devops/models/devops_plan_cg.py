import json
import os

from odoo import _, api, exceptions, fields, models


class DevopsPlanCg(models.Model):
    _name = "devops.plan.cg"
    _description = "Planification to use Code Generator"

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )

    active = fields.Boolean(default=True)

    workspace_id = fields.Many2one(
        comodel_name="devops.workspace",
        string="Workspace",
        required=True,
    )

    use_external_cg = fields.Boolean(
        help=(
            "If internal, will use same database of devops for build code,"
            " this can interfere. If False, will generate external database"
            " with sandbox."
        )
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

    code_generator_name = fields.Char()

    template_name = fields.Char()

    use_existing_meta_module_ucb_only = fields.Boolean(
        help="Force UcB only from feature use_existing_meta_module"
    )

    code_mode_context_generator = fields.Selection(
        selection=[
            ("default", "Default"),
            ("autopoiesis", "Autopoiesis"),
            ("custom", "Custom"),
        ],
        default="default",
        help="Change context variable easy change.",
    )

    stop_execution_if_env_not_clean = fields.Boolean(default=True)

    devops_cg_erplibre_devops_error_log = fields.Text(
        string="Error CG erplibre_devops new_project",
        readonly=True,
        help=(
            "Will show code generator error for new project erplibre_devops,"
            " last execution"
        ),
    )

    devops_cg_diff = fields.Text(
        string="Diff addons",
        help="Will show diff git",
    )

    devops_cg_status = fields.Text(
        string="Status addons",
        help="Will show status git",
    )

    devops_cg_stat = fields.Text(
        string="Stat addons",
        help="Will show statistique code",
    )

    devops_cg_tree_addons = fields.Text(
        string="Tree addons",
        help="Will show generated files from code generator or humain",
    )

    devops_cg_log_addons = fields.Text(
        string="Log code generator",
        help="Will show code generator log, last execution",
    )

    devops_cg_erplibre_devops_log = fields.Text(
        string="Log CG erplibre_devops new_project",
        readonly=True,
        help=(
            "Will show code generator log for new project erplibre_devops,"
            " last execution"
        ),
    )

    devops_cg_ids = fields.Many2many(
        comodel_name="devops.cg",
        string="Project",
    )

    devops_cg_module_ids = fields.Many2many(
        comodel_name="devops.cg.module",
        string="Module",
    )

    devops_cg_model_ids = fields.Many2many(
        comodel_name="devops.cg.model",
        string="Model",
    )

    devops_cg_model_to_remove_ids = fields.Many2many(
        comodel_name="devops.cg.model",
        string="Model to remove",
        relation="devops_plan_cg_model_remove_rel",
    )

    devops_cg_field_ids = fields.Many2many(
        comodel_name="devops.cg.field",
        string="Field",
    )

    config_uca_enable_export_data = fields.Boolean(
        default=True,
        help=(
            "Will enable option nonmenclator in CG to export data associate to"
            " models."
        ),
    )

    has_re_execute_new_project = fields.Boolean(
        compute="_compute_has_re_execute_new_project",
        store=True,
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

    mode_view_portal = fields.Selection(
        selection=[
            ("no_portal", "No portal"),
            ("enable_portal", "Enable portal"),
        ],
        default="no_portal",
        help=(
            "Will active feature to generate portal interface, for variable"
            " enable_generate_portal"
        ),
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
        string="Portal Models",
        help="Separate models by ;",
    )

    mode_view_snippet = fields.Selection(
        selection=[
            ("no_snippet", "No snippet"),
            ("enable_snippet", "Enable snippet"),
        ],
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

    path_working_erplibre = fields.Char(default="/ERPLibre")

    cg_self_add_config_cg = fields.Boolean(
        help="Will use both feature of cg for self generate."
    )

    need_debugger_cg_erplibre_devops = fields.Boolean(
        help="CG erplibre_devops got error, detect can use the debugger"
    )

    cg_demo_type_data = fields.Selection(
        selection=[
            ("simple", "Simple"),
            ("ore", "ORE"),
            ("devops_example", "devops example"),
        ],
        required=True,
        default="simple",
        help="Generate a set of data depend of the type to generate.",
    )

    last_new_project_cg = fields.Many2one(
        comodel_name="devops.cg.new_project",
        string="Last new project cg",
    )

    last_code_generator_writer = fields.Many2one(
        comodel_name="code.generator.writer"
    )

    last_code_generator_module = fields.Many2one(
        comodel_name="code.generator.module"
    )

    path_code_generator_to_generate = fields.Char(default="addons/addons")

    path_code_generator_to_generate_cg = fields.Char(default="addons/addons")

    path_code_generator_to_generate_template = fields.Char(
        default="addons/addons"
    )

    is_clear_before_cg_demo = fields.Boolean(
        default=True,
        help=(
            "When generate data demo for code generator, delete all data"
            " before."
        ),
    )

    @api.multi
    def write(self, values):
        cg_before_ids_i = self.devops_cg_ids.ids

        status = super().write(values)
        if "devops_cg_ids" in values.keys():
            # Update all the list of code generator, associate to this plan
            for rec in self:
                cg_missing_ids_i = list(
                    set(cg_before_ids_i).difference(set(rec.devops_cg_ids.ids))
                )
                cg_missing_ids = self.env["devops.cg"].browse(cg_missing_ids_i)
                for cg_id in cg_missing_ids:
                    for module_id in cg_id.module_ids:
                        if rec in module_id.devops_workspace_ids:
                            module_id.devops_workspace_ids = [(3, rec.id)]
                        for model_id in module_id.model_ids:
                            if rec in model_id.devops_workspace_ids:
                                model_id.devops_workspace_ids = [(3, rec.id)]
                            for field_id in model_id.field_ids:
                                if rec in field_id.devops_workspace_ids:
                                    field_id.devops_workspace_ids = [
                                        (3, rec.id)
                                    ]
                cg_adding_ids_i = list(
                    set(rec.devops_cg_ids.ids).difference(set(cg_before_ids_i))
                )
                cg_adding_ids = self.env["devops.cg"].browse(cg_adding_ids_i)
                for cg_id in cg_adding_ids:
                    for module_id in cg_id.module_ids:
                        if rec not in module_id.devops_workspace_ids:
                            module_id.devops_workspace_ids = [(4, rec.id)]
                        for model_id in module_id.model_ids:
                            if rec not in model_id.devops_workspace_ids:
                                model_id.devops_workspace_ids = [(4, rec.id)]
                            for field_id in model_id.field_ids:
                                if rec not in field_id.devops_workspace_ids:
                                    field_id.devops_workspace_ids = [
                                        (4, rec.id)
                                    ]
        return status

    @api.depends("workspace_id")
    def _compute_name(self):
        for rec in self:
            if not isinstance(rec.id, models.NewId):
                rec.name = f"{rec.id}: "
            else:
                rec.name = ""
            rec.name += rec.workspace_id.name

    @api.multi
    def action_install_all_generated_module(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Install generated module"
            ) as rec_ws:
                module_list = ",".join(
                    [m.name for cg in rec.devops_cg_ids for m in cg.module_ids]
                )
                rec_ws.install_module(module_list)
                rec_ws.action_check()

    @api.multi
    def action_install_all_uca_generated_module(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Install all UcA"
            ) as rec_ws:
                module_list = ",".join(
                    [
                        f"code_generator_template_{m.name},{m.name}"
                        for cg in rec.devops_cg_ids
                        for m in cg.module_ids
                    ]
                )
                rec_ws.execute(
                    cmd=f"./script/database/db_restore.py --database cg_uca",
                    folder=rec.path_working_erplibre,
                    to_instance=True,
                )
                rec_ws.execute(
                    cmd=(
                        "./script/addons/install_addons_dev.sh"
                        f" cg_uca {module_list}"
                    ),
                    folder=rec.path_working_erplibre,
                    to_instance=True,
                )
                rec_ws.action_check()

    @api.multi
    def action_install_all_ucb_generated_module(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Install all UcB"
            ) as rec_ws:
                module_list = ",".join(
                    [
                        f"code_generator_{m.name}"
                        for cg in rec.devops_cg_ids
                        for m in cg.module_ids
                    ]
                )
                rec_ws.execute(
                    cmd=f"./script/database/db_restore.py --database cg_ucb",
                    folder=rec.path_working_erplibre,
                    to_instance=True,
                )
                rec_ws.execute(
                    cmd=(
                        "./script/addons/install_addons_dev.sh"
                        f" cg_ucb {module_list}"
                    ),
                    folder=rec.path_working_erplibre,
                    to_instance=True,
                )
                rec_ws.action_check()

    @api.multi
    def action_install_and_generate_all_generated_module(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Install and generate all"
            ) as rec_ws:
                rec.action_code_generator_generate_all()
                rec.action_git_commit_all_generated_module()
                rec.action_refresh_meta_cg_generated_module()
                rec.action_install_all_generated_module()

    @api.multi
    def action_code_generator_generate_all(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "CG generate module"
            ) as rec_ws:
                # TODO no where this variable are set at true, need hook
                rec.devops_cg_erplibre_devops_error_log = False
                rec.need_debugger_cg_erplibre_devops = False
                # TODO add try catch, add breakpoint, rerun loop. Careful when lose context
                # Start with local storage
                # Increase speed
                # TODO keep old configuration of config.conf and not overwrite all
                # rec_ws.execute(cmd=f"cd {rec.path_working_erplibre};make config_gen_code_generator", to_instance=True)
                if rec.devops_cg_ids and rec_ws.mode_exec.value in ["docker"]:
                    rec_ws.workspace_docker_id.docker_config_gen_cg = True
                    rec_ws.action_reboot()
                    rec_ws.workspace_docker_id.docker_config_gen_cg = False
                for rec_cg in rec.devops_cg_ids:
                    for module_id in rec_cg.module_ids:
                        devops_exec_bundle_parent_root_id = (
                            self.env["devops.exec.bundle"]
                            .browse(rec_ws._context.get("devops_exec_bundle"))
                            .get_parent_root()
                        )
                        if rec_cg.force_clean_before_generate:
                            rec.workspace_code_remove_module(module_id)
                        model_conf = None
                        if rec.code_mode_context_generator == "autopoiesis":
                            if rec.cg_self_add_config_cg:
                                model_conf = rec.get_cg_model_config(module_id)
                        else:
                            model_conf = rec.get_cg_model_config(module_id)
                        module = module_id.name
                        # TODO support portal into external
                        dct_new_project = {
                            "module": module,
                            "directory": rec.path_code_generator_to_generate,
                            "directory_cg": rec.path_code_generator_to_generate_cg,
                            "directory_template": rec.path_code_generator_to_generate_template,
                            "keep_bd_alive": True,
                            "use_existing_meta_module": rec.use_existing_meta_module,
                            "use_existing_meta_module_uca_only": rec.use_existing_meta_module_uca_only,
                            "uca_option_with_inherit": rec.uca_option_with_inherit,
                            "use_existing_meta_module_ucb_only": rec.use_existing_meta_module_ucb_only,
                            "devops_workspace": rec_ws.id,
                            "devops_exec_bundle_id": devops_exec_bundle_parent_root_id.id,
                            "stop_execution_if_env_not_clean": rec.stop_execution_if_env_not_clean,
                            "mode_view": rec.mode_view,
                            "mode_view_snippet": rec.mode_view_snippet,
                            "mode_view_snippet_enable_template_website_snippet_view": rec.mode_view_snippet_enable_template_website_snippet_view,
                            "mode_view_snippet_template_generate_website_snippet_generic_mdl": rec.mode_view_snippet_template_generate_website_snippet_generic_mdl,
                            "mode_view_snippet_template_generate_website_snippet_ctrl_featur": rec.mode_view_snippet_template_generate_website_snippet_ctrl_featur,
                            "mode_view_snippet_template_generate_website_enable_javascript": rec.mode_view_snippet_template_generate_website_enable_javascript,
                            "mode_view_snippet_template_generate_website_snippet_type": rec.mode_view_snippet_template_generate_website_snippet_type,
                            # "mode_view_portal": rec.mode_view_portal,
                            # "mode_view_portal_enable_create": rec.mode_view_portal_enable_create,
                            # "mode_view_portal_enable_read": rec.mode_view_portal_enable_read,
                            # "mode_view_portal_enable_update": rec.mode_view_portal_enable_update,
                            # "mode_view_portal_enable_delete": rec.mode_view_portal_enable_delete,
                            # "mode_view_portal_models": rec.mode_view_portal_models,
                            "config_uca_enable_export_data": rec.config_uca_enable_export_data,
                        }
                        if rec.code_generator_name:
                            dct_new_project[
                                "code_generator_name"
                            ] = rec.code_generator_name
                        if rec.template_name:
                            dct_new_project[
                                "template_name"
                            ] = rec.template_name
                        # extra_arg = ""
                        if model_conf:
                            dct_new_project["config"] = model_conf
                            # extra_arg = f" --config '{model_conf}'"
                        if rec.devops_cg_model_to_remove_ids:
                            dct_new_project["model_to_remove"] = ";".join(
                                [
                                    a.name
                                    for a in rec.devops_cg_model_to_remove_ids
                                ]
                            )
                        if rec.use_external_cg:
                            new_project_id = self.env[
                                "devops.cg.new_project"
                            ].create(dct_new_project)
                            if rec.last_new_project_cg:
                                new_project_id.last_new_project = (
                                    rec.last_new_project_cg.id
                                )
                            rec.last_new_project_cg = new_project_id.id
                            new_project_id.with_context(
                                rec_ws._context
                            ).action_new_project()
                        else:
                            rec.execute_internal_cg(rec_cg, module_id)
                        # cmd = (
                        #     f"cd {rec.path_working_erplibre};./script/code_generator/new_project.py"
                        #     f" --keep_bd_alive -m {module_name} -d"
                        #     f" {rec.path_code_generator_to_generate}{extra_arg}"
                        # )
                        # result = rec_ws.execute(cmd=cmd, to_instance=True)
                        # rec.devops_cg_log_addons = result
                        # OR
                        # result = rec_ws.execute(
                        #     cmd=f"cd {rec.folder};./script/code_generator/new_project.py"
                        #     f" -d {addons_path} -m {module_name}",
                        # )
                if rec.devops_cg_ids and rec_ws.mode_exec.value in ["docker"]:
                    rec_ws.action_reboot()
                # rec_ws.execute(cmd=f"cd {rec.path_working_erplibre};make config_gen_all", to_instance=True)

    @api.multi
    def execute_internal_cg(self, rec_cg, module_id):
        for rec in self:
            path_module_generate = os.path.join(
                ".", rec.path_code_generator_to_generate
            )
            short_name = module_id.name.replace("_", " ").title()

            # Add code generator
            value = {
                "shortdesc": short_name,
                "name": module_id.name,
                "license": "AGPL-3",
                "author": "TechnoLibre",
                "website": "https://technolibre.ca",
                "application": True,
                "enable_sync_code": True,
                "path_sync_code": path_module_generate,
            }

            value["enable_sync_template"] = True
            value["ignore_fields"] = ""
            value["post_init_hook_show"] = False
            value["uninstall_hook_show"] = False
            value["post_init_hook_feature_code_generator"] = False
            value["uninstall_hook_feature_code_generator"] = False

            value[
                "hook_constant_code"
            ] = f'module_id.name = "{module_id.name}"'

            code_generator_id = self.env["code.generator.module"].create(value)
            rec.last_code_generator_module = code_generator_id.id

            # lst_depend_module = ["mail", "portal", "website"]
            lst_depend_module = []
            if (
                rec.mode_view_snippet
                and rec.mode_view_snippet == "enable_snippet"
            ):
                lst_depend_module.append("website")
            if (
                rec.mode_view_portal
                and rec.mode_view_portal == "enable_portal"
            ):
                lst_depend_module.append("portal")
            if lst_depend_module:
                # Trim for unique item
                lst_depend_module = list(set(lst_depend_module))
                code_generator_id.add_module_dependency(lst_depend_module)

            # Add model
            if (
                rec.mode_view_portal
                and rec.mode_view_portal != "no_portal"
                and rec.mode_view_portal_models
            ):
                lst_portal_model = [
                    a.strip()
                    for a in rec.mode_view_portal_models.strip().split(";")
                ]
            else:
                lst_portal_model = []
            for model_model_id in rec.devops_cg_model_ids:
                lst_depend_model = None
                if (
                    lst_portal_model
                    and model_model_id.name in lst_portal_model
                ):
                    lst_depend_model = ["portal.mixin"]
                code_generator_id.add_update_model(
                    model_model_id.name,
                    dct_field=model_model_id.get_field_dct(),
                    lst_depend_model=lst_depend_model,
                )

            # Generate view
            # Action generate view
            value_view_wizard = {
                "code_generator_id": code_generator_id.id,
                "enable_generate_all": False,
            }
            if rec.mode_view == "same_view":
                value_view_wizard["disable_generate_menu"] = True
                value_view_wizard["disable_generate_access"] = True

            if rec.mode_view_portal and rec.mode_view_portal != "no_portal":
                value_view_wizard["enable_generate_portal"] = True
                value_view_wizard[
                    "mode_view_portal_enable_create"
                ] = rec.mode_view_portal_enable_create
                value_view_wizard[
                    "mode_view_portal_enable_read"
                ] = rec.mode_view_portal_enable_read
                value_view_wizard[
                    "mode_view_portal_enable_update"
                ] = rec.mode_view_portal_enable_update
                value_view_wizard[
                    "mode_view_portal_enable_delete"
                ] = rec.mode_view_portal_enable_delete

            wizard_view = self.env[
                "code.generator.generate.views.wizard"
            ].create(value_view_wizard)

            wizard_view.button_generate_views()

            if rec.mode_view_snippet and rec.mode_view_snippet != "no_snippet":
                # Generate snippet
                # TODO addons/TechnoLibre_odoo-code-generator-template/code_generator_demo_portal/hooks.py
                #  template_generate_website_snippet_controller_feature is not suppose to be here, this field
                #  is not into code.generator.snippet
                value_snippet = {
                    "code_generator_id": code_generator_id.id,
                    "controller_feature": rec.mode_view_snippet_template_generate_website_snippet_ctrl_featur,
                    "enable_javascript": rec.mode_view_snippet_template_generate_website_enable_javascript,
                    "snippet_type": rec.mode_view_snippet_template_generate_website_snippet_type,
                    "model_name": rec.mode_view_snippet_template_generate_website_snippet_generic_mdl,
                }
                self.env["code.generator.snippet"].create(value_snippet)

            # Generate module
            value = {"code_generator_ids": code_generator_id.ids}
            cg_writer = self.env["code.generator.writer"].create(value)
            rec.last_code_generator_writer = cg_writer.id
            # print(cg_writer_id)

    @api.multi
    def workspace_code_remove_module(self, module_id):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Workspace code remove module"
            ) as rec_ws:
                path_to_remove = os.path.join(
                    rec.path_working_erplibre,
                    rec.path_code_generator_to_generate,
                )
                rec.workspace_remove_module(module_id.name, path_to_remove)

    @api.multi
    def action_git_commit(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "CG git commit"
            ) as rec_ws:
                folder = os.path.join(
                    rec.path_working_erplibre,
                    rec.path_code_generator_to_generate,
                )
                rec_ws.execute(
                    cmd="git cola",
                    folder=folder,
                    force_open_terminal=True,
                    force_exit=True,
                )

    @api.multi
    def action_git_commit_remote(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "CG git commit remote"
            ) as rec_ws:
                module_name = rec.devops_cg_module_ids[0].exists().name
                dir1 = os.path.join(
                    rec.path_code_generator_to_generate,
                    module_name,
                )
                dir2 = os.path.join(
                    rec.path_code_generator_to_generate_cg,
                    module_name,
                )
                cmd = (
                    "./script/git/remote_code_generation_git_compare.py"
                    " --quiet --git_cola --clear --replace_directory"
                    f" --directory1 {dir1} --directory2 {dir2}"
                )
                rec_ws.execute(
                    cmd=cmd,
                    force_open_terminal=True,
                    force_exit=True,
                    to_instance=True,
                )

    @api.multi
    def action_git_meld_remote(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "CG git meld remote"
            ) as rec_ws:
                module_name = rec.devops_cg_module_ids[0].exists().name
                dir1 = os.path.join(
                    rec.path_code_generator_to_generate,
                    module_name,
                )
                dir2 = os.path.join(
                    rec.path_code_generator_to_generate_cg,
                    module_name,
                )
                cmd = f"meld {dir2} {dir1}"
                rec_ws.execute(
                    cmd=cmd,
                    force_open_terminal=True,
                    force_exit=True,
                    to_instance=True,
                )

    @api.multi
    def action_git_clean_remote(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "CG git clean remote"
            ) as rec_ws:
                module_name = rec.devops_cg_module_ids[0].exists().name
                dir2 = os.path.join(
                    rec.path_code_generator_to_generate_cg,
                    module_name,
                )
                cmd = f"rm -r {dir2}"
                rec_ws.execute(
                    cmd=cmd,
                    force_open_terminal=True,
                    force_exit=True,
                    to_instance=True,
                )

    @api.multi
    def action_git_commit_all_generated_module(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "CG commit all"
            ) as rec_ws:
                folder = os.path.join(
                    rec.path_working_erplibre,
                    rec.path_code_generator_to_generate,
                )
                # for cg in rec.devops_cg_ids:
                # Validate git directory exist
                exec_id = rec_ws.execute(
                    cmd=f"ls {folder}/.git",
                    to_instance=True,
                )
                result = exec_id.log_all
                if "No such file or directory" in result:
                    # Suppose git not exist
                    # This is not good if .git directory is in parent directory
                    rec_ws.execute(
                        cmd=(
                            "git"
                            " init;echo '*.pyc' > .gitignore;git add"
                            " .gitignore;git commit -m 'first commit'"
                        ),
                        folder=folder,
                        to_instance=True,
                    )
                    rec_ws.execute(
                        cmd="git init",
                        folder=folder,
                        to_instance=True,
                    )

                exec_id = rec_ws.execute(
                    cmd=f"git status -s",
                    folder=folder,
                    to_instance=True,
                )
                result = exec_id.log_all
                if result:
                    # TODO show result to log
                    # Force add file and commit
                    rec_ws.execute(
                        cmd=f"git add .",
                        folder=folder,
                        to_instance=True,
                    )
                    rec_ws.execute(
                        cmd=f"git commit -m 'Commit by RobotLibre'",
                        folder=folder,
                        to_instance=True,
                    )

    @api.multi
    def action_refresh_meta_cg_generated_module(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Refresh meta CG"
            ) as rec_ws:
                folder = os.path.join(
                    rec.path_working_erplibre,
                    rec.path_code_generator_to_generate_cg,
                )
                diff = ""
                status = ""
                stat = ""
                exec_id = rec_ws.execute(
                    cmd=f"ls {folder}/.git",
                    to_instance=True,
                )
                result = exec_id.log_all
                if result:
                    # Create diff
                    exec_id = rec_ws.execute(
                        cmd=f"git diff",
                        folder=folder,
                        to_instance=True,
                    )
                    diff += exec_id.log_all
                    # Create status
                    exec_id = rec_ws.execute(
                        cmd=f"git status",
                        folder=folder,
                        to_instance=True,
                    )
                    status += exec_id.log_all
                    for cg in rec.devops_cg_ids:
                        # Create statistic
                        for module_id in cg.module_ids:
                            exec_id = rec_ws.execute(
                                cmd=(
                                    "./script/statistic/code_count.sh"
                                    f" ./{rec.path_code_generator_to_generate}/{module_id.name};"
                                ),
                                folder=rec.path_working_erplibre,
                                to_instance=True,
                            )
                            result = exec_id.log_all
                            if result:
                                stat += f"./{rec.path_code_generator_to_generate}/{module_id.name}"
                                stat += result

                            exec_id = rec_ws.execute(
                                cmd=(
                                    "./script/statistic/code_count.sh"
                                    f" ./{rec.path_code_generator_to_generate}/code_generator_template_{module_id.name};"
                                ),
                                folder=rec.path_working_erplibre,
                                to_instance=True,
                            )
                            result = exec_id.log_all
                            if result:
                                stat += f"./{rec.path_code_generator_to_generate}/code_generator_template_{module_id.name}"
                                stat += result

                            exec_id = rec_ws.execute(
                                cmd=(
                                    "./script/statistic/code_count.sh"
                                    f" ./{rec.path_code_generator_to_generate}/code_generator_{module_id.name};"
                                ),
                                folder=rec.path_working_erplibre,
                                to_instance=True,
                            )
                            result = exec_id.log_all
                            if result:
                                stat += f"./{rec.path_code_generator_to_generate}/code_generator_{module_id.name}"
                                stat += result

                            # Autofix attached field to workspace
                            if rec not in module_id.devops_workspace_ids:
                                module_id.devops_workspace_ids = [(4, rec.id)]
                            for model_id in module_id.model_ids:
                                if rec not in model_id.devops_workspace_ids:
                                    model_id.devops_workspace_ids = [
                                        (4, rec.id)
                                    ]
                                for field_id in model_id.field_ids:
                                    if (
                                        rec
                                        not in field_id.devops_workspace_ids
                                    ):
                                        field_id.devops_workspace_ids = [
                                            (4, rec.id)
                                        ]

                rec.devops_cg_diff = diff
                rec.devops_cg_status = status
                rec.devops_cg_stat = stat

    @api.multi
    def workspace_remove_module(
        self, module_name, path_to_remove, remove_module=True
    ):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Workspace remove module"
            ) as rec_ws:
                if remove_module:
                    rec_ws.execute(
                        cmd=f"rm -rf ./{module_name};",
                        folder=path_to_remove,
                        to_instance=True,
                    )
                rec_ws.execute(
                    cmd=f"rm -rf ./code_generator_template_{module_name};",
                    folder=path_to_remove,
                    to_instance=True,
                )
                rec_ws.execute(
                    cmd=f"rm -rf ./code_generator_{module_name};",
                    folder=path_to_remove,
                    to_instance=True,
                )

    @api.multi
    def workspace_CG_remove_module(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Workspace CG remove module"
            ) as rec_ws:
                folder = os.path.join(
                    rec.path_working_erplibre,
                    rec.path_code_generator_to_generate_cg,
                )
                rec.workspace_remove_module(
                    "erplibre_devops", folder, remove_module=False
                )

    @api.multi
    def action_clear_all_generated_module(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Clear all generated module"
            ) as rec_ws:
                for cg in rec.devops_cg_ids:
                    for module_id in cg.module_ids:
                        rec.workspace_code_remove_module(module_id)
                rec_ws.action_check()

    @api.multi
    def action_cg_generate_demo(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Generate data demo"
            ) as rec_ws:
                if rec.cg_demo_type_data == "simple":
                    # Project
                    cg_id = self.env["devops.cg"].create(
                        {
                            "name": "Parc de voiture",
                            "devops_workspace_ids": [(6, 0, rec_ws.ids)],
                            "force_clean_before_generate": True,
                        }
                    )
                    # Module
                    cg_module_id = self.env["devops.cg.module"].create(
                        {
                            "name": "parc",
                            "code_generator": cg_id.id,
                            "devops_workspace_ids": [(6, 0, rec_ws.ids)],
                        }
                    )
                    # Model
                    cg_model_voiture_id = self.env["devops.cg.model"].create(
                        {
                            "name": "parc.voiture",
                            "description": "Ensemble de voiture dans le parc",
                            "module_id": cg_module_id.id,
                            "devops_workspace_ids": [(6, 0, rec_ws.ids)],
                        }
                    )
                    # Field
                    cg_field_voiture_couleur_id = self.env[
                        "devops.cg.field"
                    ].create(
                        {
                            "name": "couleur",
                            "help": "Couleur de la voiture.",
                            "type": "char",
                            "model_id": cg_model_voiture_id.id,
                            "devops_workspace_ids": [(6, 0, rec_ws.ids)],
                        }
                    )
                    if rec.is_clear_before_cg_demo:
                        rec.devops_cg_ids = [(6, 0, cg_id.ids)]
                        rec.devops_cg_module_ids = [(6, 0, cg_module_id.ids)]
                        rec.devops_cg_model_ids = [
                            (
                                6,
                                0,
                                [
                                    cg_model_voiture_id.id,
                                ],
                            )
                        ]
                        rec.devops_cg_field_ids = [
                            (
                                6,
                                0,
                                [
                                    cg_field_voiture_couleur_id.id,
                                ],
                            )
                        ]
                    else:
                        rec.devops_cg_ids = [(4, cg_id.id)]
                        rec.devops_cg_module_ids = [(4, cg_module_id.id)]
                        rec.devops_cg_model_ids = [
                            (4, cg_model_voiture_id.id),
                        ]
                        rec.devops_cg_field_ids = [
                            (4, cg_field_voiture_couleur_id.id),
                        ]
                elif rec.cg_demo_type_data == "devops_example":
                    # Project
                    cg_id = self.env["devops.cg"].create(
                        {
                            "name": "Projet exemple",
                            "devops_workspace_ids": [(6, 0, rec_ws.ids)],
                            "force_clean_before_generate": False,
                        }
                    )
                    # Module
                    cg_module_id = self.env["devops.cg.module"].create(
                        {
                            "name": "erplibre_devops",
                            "code_generator": cg_id.id,
                            "devops_workspace_ids": [(6, 0, rec_ws.ids)],
                        }
                    )
                    # Model
                    cg_model_example_id = self.env["devops.cg.model"].create(
                        {
                            "name": "devops.example",
                            "description": "Example feature to add to devops",
                            "module_id": cg_module_id.id,
                            "devops_workspace_ids": [(6, 0, rec_ws.ids)],
                        }
                    )
                    # Field
                    cg_field_size_id = self.env["devops.cg.field"].create(
                        {
                            "name": "size",
                            "help": "Size of this example.",
                            "type": "integer",
                            "model_id": cg_model_example_id.id,
                            "devops_workspace_ids": [(6, 0, rec_ws.ids)],
                        }
                    )
                    if rec.is_clear_before_cg_demo:
                        rec.devops_cg_ids = [(6, 0, cg_id.ids)]
                        rec.devops_cg_module_ids = [(6, 0, cg_module_id.ids)]
                        rec.devops_cg_model_ids = [
                            (
                                6,
                                0,
                                [
                                    cg_model_example_id.id,
                                ],
                            )
                        ]
                        rec.devops_cg_field_ids = [
                            (
                                6,
                                0,
                                [
                                    cg_field_size_id.id,
                                ],
                            )
                        ]
                    else:
                        rec.devops_cg_ids = [(4, cg_id.id)]
                        rec.devops_cg_module_ids = [(4, cg_module_id.id)]
                        rec.devops_cg_model_ids = [
                            (4, cg_model_example_id.id),
                        ]
                        rec.devops_cg_field_ids = [
                            (4, cg_field_size_id.id),
                        ]
                elif rec.cg_demo_type_data == "ore":
                    # Project
                    cg_id = self.env["devops.cg"].create(
                        {
                            "name": "Offrir Recevoir Échanger",
                            "devops_workspace_ids": [(6, 0, rec_ws.ids)],
                            "force_clean_before_generate": True,
                        }
                    )
                    # Module
                    cg_module_id = self.env["devops.cg.module"].create(
                        {
                            "name": "ore",
                            "code_generator": cg_id.id,
                            "devops_workspace_ids": [(6, 0, rec_ws.ids)],
                        }
                    )
                    # Model
                    cg_model_offre_id = self.env["devops.cg.model"].create(
                        {
                            "name": "ore.offre.service",
                            "description": (
                                "Permet de créer une offre de service"
                                " publiable dans la communauté."
                            ),
                            "module_id": cg_module_id.id,
                            "devops_workspace_ids": [(6, 0, rec_ws.ids)],
                        }
                    )
                    cg_model_demande_id = self.env["devops.cg.model"].create(
                        {
                            "name": "ore.demande.service",
                            "description": (
                                "Permet de créer une demande de service"
                                " publiable dans la communauté."
                            ),
                            "module_id": cg_module_id.id,
                            "devops_workspace_ids": [(6, 0, rec_ws.ids)],
                        }
                    )
                    # Field
                    cg_field_offre_date_afficher_id = self.env[
                        "devops.cg.field"
                    ].create(
                        {
                            "name": "date_service_afficher",
                            "help": (
                                "Date à laquelle l'offre de service sera"
                                " affiché."
                            ),
                            "type": "date",
                            "model_id": cg_model_offre_id.id,
                            "devops_workspace_ids": [(6, 0, rec_ws.ids)],
                        }
                    )
                    cg_field_offre_temps_estime_id = self.env[
                        "devops.cg.field"
                    ].create(
                        {
                            "name": "temp_estime",
                            "help": (
                                "Temps estimé pour effectuer le service à"
                                " offrir."
                            ),
                            "type": "float",
                            "model_id": cg_model_offre_id.id,
                            "devops_workspace_ids": [(6, 0, rec_ws.ids)],
                        }
                    )
                    cg_field_demande_date_afficher_id = self.env[
                        "devops.cg.field"
                    ].create(
                        {
                            "name": "date_service_afficher",
                            "help": (
                                "Date à laquelle la demande de service sera"
                                " affiché."
                            ),
                            "type": "date",
                            "model_id": cg_model_demande_id.id,
                            "devops_workspace_ids": [(6, 0, rec_ws.ids)],
                        }
                    )
                    cg_field_demande_condition_id = self.env[
                        "devops.cg.field"
                    ].create(
                        {
                            "name": "condition",
                            "help": "Condition sur la demande de service.",
                            "type": "text",
                            "model_id": cg_model_demande_id.id,
                            "devops_workspace_ids": [(6, 0, rec_ws.ids)],
                        }
                    )
                    if rec.is_clear_before_cg_demo:
                        rec.devops_cg_ids = [(6, 0, cg_id.ids)]
                        rec.devops_cg_module_ids = [(6, 0, cg_module_id.ids)]
                        rec.devops_cg_model_ids = [
                            (
                                6,
                                0,
                                [
                                    cg_model_offre_id.id,
                                    cg_model_demande_id.id,
                                ],
                            )
                        ]
                        rec.devops_cg_field_ids = [
                            (
                                6,
                                0,
                                [
                                    cg_field_offre_date_afficher_id.id,
                                    cg_field_offre_temps_estime_id.id,
                                    cg_field_demande_date_afficher_id.id,
                                    cg_field_demande_condition_id.id,
                                ],
                            )
                        ]
                    else:
                        rec.devops_cg_ids = [(4, cg_id.id)]
                        rec.devops_cg_module_ids = [(4, cg_module_id.id)]
                        rec.devops_cg_model_ids = [
                            (4, cg_model_offre_id.id),
                            (4, cg_model_demande_id.id),
                        ]
                        rec.devops_cg_field_ids = [
                            (4, cg_field_offre_date_afficher_id.id),
                            (4, cg_field_offre_temps_estime_id.id),
                            (4, cg_field_demande_date_afficher_id.id),
                            (4, cg_field_demande_condition_id.id),
                        ]

    @api.model
    def get_cg_model_config(self, module_id):
        # Support only 1, but can run in parallel multiple if no dependencies between
        lst_model = []
        dct_model_conf = {"model": lst_model}
        for model_id in module_id.model_ids:
            lst_field = []
            lst_model.append({"name": model_id.name, "fields": lst_field})
            for field_id in model_id.field_ids:
                dct_value_field = {
                    "name": field_id.name,
                    "help": field_id.help,
                    "type": field_id.type,
                }
                if field_id.type in [
                    "many2one",
                    "many2many",
                    "one2many",
                ]:
                    dct_value_field["relation"] = (
                        field_id.relation.name
                        if field_id.relation
                        else field_id.relation_manual
                    )
                    if not dct_value_field["relation"]:
                        msg_err = (
                            f"Model '{model_id.name}', field"
                            f" '{field_id.name}' need a"
                            " relation because type is"
                            f" '{field_id.type}'"
                        )
                        raise exceptions.Warning(msg_err)
                if field_id.type in [
                    "one2many",
                ]:
                    dct_value_field["relation_field"] = (
                        field_id.field_relation.name
                        if field_id.field_relation
                        else field_id.field_relation_manual
                    )
                    if not dct_value_field["relation_field"]:
                        msg_err = (
                            f"Model '{model_id.name}', field"
                            f" '{field_id.name}' need a"
                            " relation field because type is"
                            f" '{field_id.type}'"
                        )
                        raise exceptions.Warning(msg_err)
                if field_id.widget:
                    dct_value_field = field_id.widget
                lst_field.append(dct_value_field)
        model_conf = (
            json.dumps(dct_model_conf)
            # .replace('"', '\\"')
            # .replace("'", "")
        )
        return model_conf

    @api.multi
    def action_execute_last_stage_new_project(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Re-execute last new project"
            ) as rec_ws:
                if rec_ws._context.get("default_stage_Uc0"):
                    rec.last_new_project_cg.stage_id = self.env.ref(
                        "erplibre_devops.devops_cg_new_project_stage_generate_Uc0"
                    ).id
                # TODO create a copy of new project and not modify older version
                # TODO next sentence is not useful if made a copy
                rec.last_new_project_cg.devops_exec_bundle_id = (
                    rec_ws._context.get("devops_exec_bundle")
                )
                rec.last_new_project_cg.action_new_project()

    @api.multi
    def action_open_terminal_tig(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Open Terminal and tig"
            ) as rec_ws:
                if rec_ws.mode_exec.value in ["docker"]:
                    exec_id = rec_ws.execute(cmd="which tig", to_instance=True)
                    result = exec_id.log_all
                    if not result:
                        # TODO support OS and not only docker
                        rec_ws.workspace_docker_id.action_docker_install_dev_soft()
                dir_to_check = os.path.join(
                    rec.path_working_erplibre,
                    rec.path_code_generator_to_generate,
                    ".git",
                )
                exec_id = rec_ws.execute(cmd=f"ls {dir_to_check}")
                status_ls = exec_id.log_all
                if "No such file or directory" in status_ls:
                    raise exceptions.Warning(
                        "Cannot open command 'tig', cannot find directory"
                        f" '{dir_to_check}'."
                    )
                folder = os.path.join(
                    rec.path_working_erplibre,
                    rec.path_code_generator_to_generate,
                )
                cmd = f"tig"
                rec_ws.execute(
                    cmd=cmd,
                    force_open_terminal=True,
                    folder=folder,
                )

    @api.multi
    def action_open_terminal_addons(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Open Terminal addons"
            ) as rec_ws:
                folder = os.path.join(
                    rec.path_working_erplibre,
                    rec.path_code_generator_to_generate,
                )
                cmd = f"ls -l"
                rec_ws.execute(
                    cmd=cmd,
                    folder=folder,
                    force_open_terminal=True,
                )

    @api.multi
    def action_open_terminal_path_erplibre_devops(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Open terminal ERPLibre DevOps"
            ) as rec_ws:
                folder = os.path.join(
                    rec.path_working_erplibre,
                    rec.path_code_generator_to_generate,
                )
                rec_ws.execute(folder=folder, force_open_terminal=True)

    @api.multi
    def action_check_tree_addons(self):
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Check tree addons"
            ) as rec_ws:
                folder = os.path.join(
                    rec.path_working_erplibre,
                    rec.path_code_generator_to_generate,
                )
                exec_id = rec_ws.execute(
                    cmd=f"tree",
                    folder=folder,
                    to_instance=True,
                )
                rec.devops_cg_tree_addons = exec_id.log_all

    @api.multi
    @api.depends("last_new_project_cg", "last_new_project_cg.has_error")
    def _compute_has_re_execute_new_project(self):
        for rec in self:
            rec.has_re_execute_new_project = bool(
                rec.last_new_project_cg and rec.last_new_project_cg.has_error
            )
