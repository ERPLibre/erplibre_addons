import os
import time
import uuid

from odoo import _, api, exceptions, fields, models


class DevopsPlanActionWizard(models.TransientModel):
    _name = "devops.plan.action.wizard"
    _description = "Devops planification do an action with a specific workflow"
    _inherit = ["multi.step.wizard.mixin"]

    def _default_image_db_selection(self):
        return self.env["devops.db.image"].search(
            [("name", "like", "erplibre_base")], limit=1
        )

    name = fields.Char()

    root_workspace_id = fields.Many2one(
        comodel_name="devops.workspace",
        string="Root workspace",
        required=True,
        default=lambda self: self.env.context.get("active_id"),
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

    generated_new_project_id = fields.Many2one(
        comodel_name="devops.cg.new_project",
        string="Generated project",
    )

    plan_cg_id = fields.Many2one(
        comodel_name="devops.plan.cg",
        string="Generated plan CG",
    )

    working_module_id = fields.Many2one(
        comodel_name="ir.module.module",
        string="Working module",
    )

    working_module_name = fields.Char(
        help="working_module_id or working_module_name"
    )

    state = fields.Selection(default="init")

    has_next = fields.Boolean(compute="_compute_has_next")

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

    image_db_selection = fields.Many2one(
        comodel_name="devops.db.image",
        default=_default_image_db_selection,
    )

    # option_adding = fields.Selection([
    #     ('inherit', 'Inherit Model'),
    #     ('nomenclator', 'Nomenclator'),
    # ], required=True, default='nomenclator', help="Inherit to inherit a new model.\nNomenclator to export data.")

    # option_blacklist = fields.Selection([
    #     ('blacklist', 'Blacklist'),
    #     ('whitelist', 'Whitelist'),
    # ], required=True, default='whitelist', help="When whitelist, all selected fields will be added.\n"
    #                                             "When blacklist, all selected fields will be ignored.")

    # field_ids = fields.Many2many(
    #     comodel_name="ir.model.fields",
    #     string="Fields",
    #     help="Select the field you want to inherit or import data.",
    # )
    #
    # model_ids = fields.Many2many(
    #     comodel_name="ir.model",
    #     string="Models",
    #     help="Select the model you want to inherit or import data.",
    # )

    enable_package_srs = fields.Boolean()

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="User",
        required=True,
        default=lambda s: s.env.user.id,
    )

    def _compute_has_next(self):
        for record in self:
            record.has_next = getattr(
                record, "state_exit_%s" % record.state, False
            )

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
            ("c_existing_module", "Existing module"),
            ("c_a_model", "Model existing module"),
            ("d_import_data", "Import data"),
            ("e_migrate_from_external_ddb", "Migrate from external database"),
            ("f_new_project_society", "New society"),
            ("g_test_erplibre", "Test ERPLibre"),
            ("g_a_local", "Test ERPLibre local"),
            ("h_run_test", "Run test"),
            ("h_a_all", "Run all test"),
            ("h_b_cg", "Run test code generator"),
            ("not_supported", "Not supported"),
            ("final", "Final"),
        ]

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

    def state_goto_h_run_test(self):
        self.state = "h_run_test"
        return self._reopen_self()

    def state_goto_h_a_all(self):

        # finally
        self.state = "final"
        return self._reopen_self()

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

    def state_goto_c_existing_module(self):
        self.state = "c_existing_module"
        return self._reopen_self()

    def state_goto_c_a_model(self):
        self.state = "c_a_model"
        return self._reopen_self()

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

    def state_previous_a_c_action(self):
        self.state = "a_autopoiesis_devops"

    def state_previous_a_d_view(self):
        self.state = "a_autopoiesis_devops"

    def state_previous_a_f_devops_regen(self):
        self.state = "a_autopoiesis_devops"

    def state_previous_f_new_project_society(self):
        self.state = "init"

    def state_previous_g_test_erplibre(self):
        self.state = "init"

    def state_previous_g_a_local(self):
        self.state = "g_test_erplibre"

    def state_previous_h_run_test(self):
        self.state = "init"

    #
    # def state_previous_h_a_all(self):
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

    def state_exit_g_a_local(self):
        with self.root_workspace_id.devops_create_exec_bundle(
            "Plan g_a_local"
        ) as wp_id:
            # Create a workspace with same system of actual workspace, will be in test mode
            dct_wp = {
                "system_id": wp_id.system_id.id,
                "folder": f"/tmp/test_erplibre_{uuid.uuid4()}",
                "mode_source": "docker",
                "mode_exec": "docker",
                "image_db_selection": self.image_db_selection.id,
            }
            local_wp_id = self.env["devops.workspace"].create(dct_wp)
            self.create_workspace_id = local_wp_id.id
            local_wp_id.action_install_workspace()
            local_wp_id.action_start()
            # TODO implement detect when website is up or cancel state with error
            time.sleep(5)
            local_wp_id.action_restore_db_image()
            if self.enable_package_srs:
                local_wp_id.install_module("project_srs")
            wp_id.execute(
                cmd=(
                    "source"
                    " ./.venv/bin/activate;./script/selenium/web_login.py"
                    f" --url {local_wp_id.url_instance}"
                ),
                force_open_terminal=True,
                run_into_workspace=True,
            )
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

    def state_exit_a_f_devops_regen(self):
        with self.root_workspace_id.devops_create_exec_bundle(
            "Plan a_f_devops_regen"
        ) as wp_id:
            # TODO this is a bug, no need that in reality, but action_code_generator_generate_all loop into it
            # Project
            cg_id = self.env["devops.cg"].create(
                {
                    "name": "Autopoiesis regenerate",
                    "devops_workspace_ids": [(6, 0, wp_id.ids)],
                    "force_clean_before_generate": self.force_generate,
                }
            )
            # Module
            cg_module_id = self.env["devops.cg.module"].create(
                {
                    "name": "erplibre_devops",
                    "code_generator": cg_id.id,
                    "devops_workspace_ids": [(6, 0, wp_id.ids)],
                }
            )
            plan_cg_value = {
                "workspace_id": wp_id.id,
                "cg_self_add_config_cg": True,
                "path_working_erplibre": wp_id.folder,
                "code_mode_context_generator": "autopoiesis",
                "mode_view": "same_view",
                "devops_cg_ids": [(6, 0, cg_id.ids)],
                "devops_cg_module_ids": [(6, 0, cg_module_id.ids)],
                "devops_cg_model_ids": [(6, 0, [])],
                "devops_cg_field_ids": [(6, 0, [])],
                "stop_execution_if_env_not_clean": not self.force_generate,
            }
            plan_cg_id = self.env["devops.plan.cg"].create(plan_cg_value)
            # Generate
            plan_cg_id.action_code_generator_generate_all()
            self.generated_new_project_id = plan_cg_id.last_new_project_cg.id
            self.plan_cg_id = plan_cg_id.id
            # finally
            self.state = "final"

    def generate_new_model(
        self, wp_id, module_name, project_name, is_autopoiesis=False
    ):
        # Search relative path
        exec_id = wp_id.execute(
            cmd=(
                "./script/addons/check_addons_exist.py --output_path -m"
                f" {module_name}"
            ),
            run_into_workspace=True,
        )
        if exec_id.exec_status:
            raise exceptions.Warning(f"Cannot find module '{module_name}'")
        path_module = exec_id.log_all.strip()
        dir_name, basename = os.path.split(path_module)
        if dir_name.startswith(wp_id.folder):
            relative_path_module = dir_name[len(wp_id.folder) + 1 :]
        else:
            relative_path_module = dir_name
        # Project
        cg_id = self.env["devops.cg"].create(
            {
                "name": project_name,
                "devops_workspace_ids": [(6, 0, wp_id.ids)],
                "force_clean_before_generate": False,
            }
        )
        # Module
        cg_module_id = self.env["devops.cg.module"].create(
            {
                "name": module_name,
                "code_generator": cg_id.id,
                "devops_workspace_ids": [(6, 0, wp_id.ids)],
            }
        )
        # Model
        for cg_model_id in self.model_ids:
            cg_model_id.module_id = cg_module_id.id
            cg_model_id.devops_workspace_ids = [(6, 0, wp_id.ids)]
        for cg_model_id in self.model_to_remove_ids:
            cg_model_id.module_id = cg_module_id.id
            cg_model_id.devops_workspace_ids = [(6, 0, wp_id.ids)]
        lst_field_id = [b.id for a in self.model_ids for b in a.field_ids]
        # Field
        # cg_field_id = self.env[
        #     "devops.cg.field"
        # ].create(
        #     {
        #         "name": "size",
        #         "help": "Size of this example.",
        #         "type": "integer",
        #         "model_id": cg_model_id.id,
        #         "devops_workspace_ids": [(6, 0, wp_id.ids)],
        #     }
        # )
        plan_cg_value = {
            "workspace_id": wp_id.id,
            "mode_view": "new_view",
            "path_working_erplibre": wp_id.folder,
            "path_code_generator_to_generate": relative_path_module,
            "devops_cg_ids": [(6, 0, cg_id.ids)],
            "devops_cg_module_ids": [(6, 0, cg_module_id.ids)],
            "devops_cg_model_ids": [(6, 0, self.model_ids.ids)],
            "devops_cg_model_to_remove_ids": [
                (6, 0, self.model_to_remove_ids.ids)
            ],
            "devops_cg_field_ids": [(6, 0, lst_field_id)],
            "stop_execution_if_env_not_clean": not self.force_generate,
        }
        # Update configuration self-gen
        if is_autopoiesis:
            plan_cg_value["cg_self_add_config_cg"] = True
            plan_cg_value["code_mode_context_generator"] = "autopoiesis"
        # Generate
        plan_cg_id = self.env["devops.plan.cg"].create(plan_cg_value)
        plan_cg_id.action_code_generator_generate_all()
        self.generated_new_project_id = plan_cg_id.last_new_project_cg.id
        self.plan_cg_id = plan_cg_id.id
        # Git add
        lst_default_file = [
            f"{module_name}/__manifest__.py",
            f"{module_name}/security/ir.model.access.csv",
            f"{module_name}/views/menu.xml",
        ]
        if self.model_ids:
            lst_default_file.append(f"{module_name}/models/__init__.py")
            for cg_model_id in self.model_ids:
                model_file_name = cg_model_id.name.replace(".", "_")
                lst_default_file.append(
                    f"{module_name}/models/{model_file_name}.py"
                )
                lst_default_file.append(
                    f"{module_name}/views/{model_file_name}.xml"
                )
        cmd_git_add = ";".join([f"git add '{a}'" for a in lst_default_file])
        wp_id.execute(
            cmd=cmd_git_add,
            folder=relative_path_module,
            run_into_workspace=True,
            to_instance=True,
        )
        # finally
        self.state = "final"

    @api.multi
    def action_git_commit(self):
        for rec in self:
            if rec.plan_cg_id:
                rec.plan_cg_id.action_git_commit()
        return self._reopen_self()
