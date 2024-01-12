# Copyright 2023 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "ERPLibre DevOps",
    "category": "Tools",
    "summary": "ERPLibre DevOps manage workspace to create new ERPLibre",
    "version": "12.0.1.0.0",
    "author": "Mathieu Benoit",
    "license": "AGPL-3",
    "website": "https://erplibre.ca",
    "application": True,
    "depends": [
        "mail",
        "multi_step_wizard",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizards/devops_plan_action_wizard.xml",
        "data/mail_message_subtype.xml",
        "views/devops_cg_new_project.xml",
        "views/devops_cg_new_project_stage.xml",
        "views/devops_code_generator.xml",
        "views/devops_code_generator_module.xml",
        "views/devops_code_generator_module_model.xml",
        "views/devops_code_generator_module_model_field.xml",
        "views/devops_db_image.xml",
        "views/devops_exec.xml",
        "views/devops_exec_bundle.xml",
        "views/devops_exec_error.xml",
        "views/devops_ide_breakpoint.xml",
        "views/devops_ide_pycharm.xml",
        "views/devops_log_makefile_target.xml",
        "views/devops_plan_type.xml",
        "views/devops_plan_type_lvl1.xml",
        "views/devops_system.xml",
        "views/devops_test.xml",
        "views/res_config_settings.xml",
        "views/devops_workspace.xml",
        "views/devops_workspace_docker.xml",
        "views/devops_workspace_terminal.xml",
        "data/ir_cron.xml",
        "data/devops_cg_new_project_stage.xml",
        "data/devops_ide_breakpoint.xml",
        "data/devops_system.xml",
        "data/devops_workspace.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "post_init_hook": "post_init_hook",
}
