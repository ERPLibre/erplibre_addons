import asyncio
import configparser
import os
import sys

# import git
# from colorama import Fore
import tempfile
import time
import uuid
from typing import Any, Coroutine, Tuple

import aioshutil

from odoo import _, api, fields, models

# TODO use system instead
# Get root of ERPLibre
new_path = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
sys.path.append(new_path)

from script import lib_asyncio

lst_ignore_warning = [
    "have the same label:",
    "odoo.addons.code_generator.extractor_module_file: Ignore next error about"
    " ALTER TABLE DROP CONSTRAINT.",
]

lst_ignore_error = [
    "fetchmail_notify_error_to_sender",
    'odoo.sql_db: bad query: ALTER TABLE "db_backup" DROP CONSTRAINT'
    ' "db_backup_db_backup_name_unique"',
    'ERROR: constraint "db_backup_db_backup_name_unique" of relation'
    ' "db_backup" does not exist',
    'odoo.sql_db: bad query: ALTER TABLE "db_backup" DROP CONSTRAINT'
    ' "db_backup_db_backup_days_to_keep_positive"',
    'ERROR: constraint "db_backup_db_backup_days_to_keep_positive" of relation'
    ' "db_backup" does not exist',
    "odoo.addons.code_generator.extractor_module_file: Ignore next error about"
    " ALTER TABLE DROP CONSTRAINT.",
]


class DevopsCgTestCase(models.Model):
    _name = "devops.cg.test.case"
    _description = "devops_cg_test_case"

    name = fields.Char()

    install_path = fields.Char()

    generated_path = fields.Char()

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

    path_meta = fields.Char()

    path_generated = fields.Char()

    search_class_module = fields.Char()

    restore_db_image_name = fields.Char(
        help="TODO use many2one from image db."
    )

    file_to_restore_origin = fields.Boolean()

    script_after_init_check = fields.Char()

    file_to_restore = fields.Char()

    test_name = fields.Char()

    script_path = fields.Char(help="For run_mode command")

    run_mode = fields.Selection(
        selection=[("command", "Run command"), ("test_exec", "Run test exec")],
        default="command",
        help=(
            "Option 'command' to run a script or 'test_exec' to run test"
            " script."
        ),
    )

    type_test = fields.Selection(
        selection=[
            ("gen_ucb", "Generate UcB"),
            ("gen_uca", "Generate UcA"),
            ("run_c", "Run module"),
        ],
        help=(
            "Type of test to run. "
            "gen_uca : Execute a template to generate a code generator module."
            "gen_ucb : Execute code generator to generate a module."
            "run_c : Run module to check to execution error."
        ),
        default="run_c",
    )

    sequence_test = fields.Integer(
        help="Can change sequence order to run test."
    )

    note = fields.Text()
