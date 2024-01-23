from odoo import _, api, fields, models


class DevopsCgTestCase(models.Model):
    _name = "devops.cg.test.case"
    _description = "devops_cg_test_case"

    name = fields.Char()

    coverage = fields.Boolean()

    install_path = fields.Char()

    keep_cache = fields.Boolean()

    module_generated = fields.Many2many(
        comodel_name="devops.cg.module", relation="devops_module_generated_rel"
    )

    module_init_ids = fields.Many2many(
        comodel_name="devops.cg.module",
        string="Module Init",
        relation="devops_module_init_ids_rel",
    )

    module_search_class = fields.Many2many(
        comodel_name="devops.cg.module",
        relation="devops_module_search_class_rel",
    )

    module_tested = fields.Many2many(
        comodel_name="devops.cg.module", relation="devops_module_tested_rel"
    )

    path_module_check = fields.Char()

    restore_db_image_name = fields.Char()

    run_in_sandbox = fields.Boolean()

    script_after_init_check = fields.Char()

    test_name = fields.Char()
