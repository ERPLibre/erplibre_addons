#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import os

from odoo import _, api, fields, models


class DevopsCodeTodo(models.Model):
    _name = "devops.code.todo"
    _description = "Associate to a TODO into a file code."

    name = fields.Char()

    active = fields.Boolean(default=True)

    filename = fields.Char()

    lineno = fields.Integer()

    module_id = fields.Many2one(
        comodel_name="devops.cg.module",
        string="Module",
    )

    path_absolute = fields.Char()

    path_module = fields.Char()

    sequence = fields.Integer(default=10)

    workspace_id = fields.Many2one(
        comodel_name="devops.workspace",
        string="Workspace",
    )

    ide_breakpoint = fields.Many2one(
        comodel_name="devops.ide.breakpoint",
        help="Associate a breakpoint to this execution.",
    )

    def open_file_ide(self):
        ws_id = self.env["devops.workspace"].search(
            [("is_me", "=", True)], limit=1
        )
        if not ws_id:
            return
        for o_rec in self:
            with ws_id.devops_create_exec_bundle("Open file IDE") as rec_ws:
                if o_rec.ide_breakpoint:
                    id_ide_breakpoint = o_rec.ide_breakpoint.id
                else:
                    bp_filename = os.path.join(
                        o_rec.path_module, o_rec.filename
                    )
                    bp_value = {
                        "name": "breakpoint_exec",
                        "description": "TODO",
                        "filename": bp_filename,
                        "no_line": o_rec.lineno,
                        "keyword": o_rec.name,
                        "ignore_test": True,
                        "generated_by_execution": True,
                    }
                    # TODO maybe check if already exist?
                    ide_breakpoint = self.env["devops.ide.breakpoint"].create(
                        [bp_value]
                    )
                    id_ide_breakpoint = ide_breakpoint.id

                rec_ws.with_context(
                    breakpoint_id=id_ide_breakpoint
                ).ide_pycharm.action_start_pycharm()

    def parse_workspace(self, wp_id):
        self.env["devops.code.todo"].search([]).write({"active": False})
        cg_module_ids = self.env["devops.cg.module"].search([])
        for cg_module in cg_module_ids:
            exec_id = wp_id.execute(
                cmd=(
                    "./script/addons/check_addons_exist.py --output_path -m"
                    f" {cg_module.name}"
                ),
                run_into_workspace=True,
            )
            path_absolute = exec_id.log_all.strip()
            path_module = (
                path_absolute[len(wp_id.folder_odoo_version) + 1 :]
                if path_absolute.startswith(wp_id.folder_odoo_version)
                else path_absolute
            )
            cmd = (
                'grep -IE "# ?TODO" --color=never -rn'
                ' --exclude-dir={.git,__pycache__} --exclude="*.pyc"'
                f' {path_absolute}|egrep -v "TODO HUMAN"'
            )
            exec_id = wp_id.execute(
                cmd=cmd,
                run_into_workspace=True,
                error_on_status=False,
            )
            if exec_id.exec_status == 2:
                raise Exception(exec_id.log_all)
            if exec_id.exec_status == 1:
                # Cannot found
                continue
            for todo_line in exec_id.log_all.strip().split("\n"):
                split_result = todo_line.split(":", maxsplit=2)
                if len(split_result) != 3:
                    raise Exception(
                        "Cannot extract filename and line number from todo"
                        f" log : {todo_line}"
                    )
                path_abs_file_name, lineno, name = split_result
                lineno = int(lineno)
                filename = (
                    path_abs_file_name[len(path_absolute) + 1 :]
                    if path_abs_file_name.startswith(path_absolute)
                    else todo_line
                )
                todo_value = {
                    "name": name,
                    "filename": filename,
                    "lineno": lineno,
                    "path_absolute": path_absolute,
                    "path_module": path_module,
                    "workspace_id": wp_id.id,
                    "module_id": cg_module.id,
                }
                todo_id = self.env["devops.code.todo"].create([todo_value])
