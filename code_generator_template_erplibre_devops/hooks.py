import logging
import os

from odoo import SUPERUSER_ID, _, api, fields, models

_logger = logging.getLogger(__name__)

# TODO HUMAN: change my module_name to create a specific demo functionality
MODULE_NAME = "code_generator_erplibre_devops"


def post_init_hook(cr, e):
    with api.Environment.manage():
        env = api.Environment(cr, SUPERUSER_ID, {})

        # The path of the actual file
        path_module_generate = "./addons/ERPLibre_erplibre_addons"

        short_name = MODULE_NAME.replace("_", " ").title()

        # Add code generator
        categ_id = env["ir.module.category"].search(
            [("name", "=", "Uncategorized")], limit=1
        )
        value = {
            "shortdesc": short_name,
            "name": MODULE_NAME,
            "license": "AGPL-3",
            "category_id": categ_id.id,
            "summary": "",
            "author": "TechnoLibre",
            "website": "https://technolibre.ca",
            "application": True,
            "enable_sync_code": True,
            "path_sync_code": path_module_generate,
            "icon": os.path.join(
                os.path.dirname(__file__),
                "static",
                "description",
                "code_generator_icon.png",
            ),
        }

        # TODO HUMAN: enable your functionality to generate
        value["enable_template_code_generator_demo"] = False
        value["template_model_name"] = (
            "devops.cg; devops.cg.field; devops.cg.model; devops.cg.module;"
            " devops.cg.new_project; devops.cg.new_project.stage;"
            " devops.cg.test.case; devops.db.image; devops.exec;"
            " devops.exec.bundle; devops.exec.error; devops.ide.breakpoint;"
            " devops.ide.pycharm; devops.ide.pycharm.configuration;"
            " devops.log.error; devops.log.makefile.target;"
            " devops.log.warning; devops.plan.action.wizard; devops.plan.cg;"
            " devops.system; devops.test.case; devops.test.case.exec;"
            " devops.test.plan; devops.test.plan.exec; devops.test.result;"
            " devops.workspace; devops.workspace.docker;"
            " devops.workspace.terminal; erplibre.mode; erplibre.mode.env;"
            " erplibre.mode.exec; erplibre.mode.source;"
            " erplibre.mode.version.base; erplibre.mode.version.erplibre"
        )
        value["template_inherit_model_name"] = ""
        value[
            "template_module_path_generated_extension"
        ] = "./addons/ERPLibre_erplibre_addons"
        value["enable_template_wizard_view"] = True
        value["force_generic_template_wizard_view"] = False
        value["disable_generate_access"] = False
        value["enable_template_website_snippet_view"] = False
        value["template_auto_export_data"] = True
        value["template_auto_export_data_exclude_model"] = 'devops.db.image;devops.exec;devops.exec.bundle;devops.ide.pycharm;devops.log.makefile.target;devops.workspace.terminal;devops.workspace;devops.test.case;devops.test.plan;erplibre.mode;erplibre.mode.env;erplibre.mode.exec;erplibre.mode.source;erplibre.mode.version.base;erplibre.mode.version.erplibre'
        value["enable_sync_template"] = True
        value["ignore_fields"] = ""
        value["post_init_hook_show"] = True
        value["uninstall_hook_show"] = True
        value["post_init_hook_feature_code_generator"] = True
        value["uninstall_hook_feature_code_generator"] = True

        new_module_name = MODULE_NAME
        if (
            MODULE_NAME != "code_generator_demo"
            and "code_generator_" in MODULE_NAME
        ):
            if "code_generator_template" in MODULE_NAME:
                if value["enable_template_code_generator_demo"]:
                    new_module_name = f"code_generator_{MODULE_NAME[len('code_generator_template_'):]}"
                else:
                    new_module_name = MODULE_NAME[
                        len("code_generator_template_") :
                    ]
            else:
                new_module_name = MODULE_NAME[len("code_generator_") :]
            value["template_module_name"] = new_module_name
        value["hook_constant_code"] = f'MODULE_NAME = "{new_module_name}"'

        code_generator_id = env["code.generator.module"].create(value)

        # Add dependencies
        lst_depend_module = [
            "code_generator",
            "code_generator_hook",
            "mail",
            "multi_step_wizard",
        ]
        code_generator_id.add_module_dependency(lst_depend_module)
        # Generate module
        value = {"code_generator_ids": code_generator_id.ids}
        env["code.generator.writer"].create(value)


def uninstall_hook(cr, e):
    with api.Environment.manage():
        env = api.Environment(cr, SUPERUSER_ID, {})
        code_generator_id = env["code.generator.module"].search(
            [("name", "=", MODULE_NAME)]
        )
        if code_generator_id:
            code_generator_id.unlink()
