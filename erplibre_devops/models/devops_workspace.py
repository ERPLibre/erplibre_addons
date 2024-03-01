# Copyright 2023 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import os
import pathlib
import platform
import re
import subprocess
import time
import traceback
from contextlib import contextmanager

import requests

from odoo import _, api, exceptions, fields, models, service, tools

_logger = logging.getLogger(__name__)
# TODO move into configuration or erplibre_devops
SLEEP_KILL = 2
SLEEP_WAIT_KILL = 3
SLEEP_ERROR_RESTORE_KILL = 5


class DevopsWorkspace(models.Model):
    _name = "devops.workspace"
    _inherit = ["mail.activity.mixin", "mail.thread"]
    _description = "ERPLibre DevOps Workspace"

    def _default_image_db_selection(self):
        return self.env["devops.db.image"].search(
            [("name", "like", "erplibre_base")], limit=1
        )

    name = fields.Char(
        compute="_compute_name",
        store=True,
        help="Summary of this devops_workspace process",
    )

    active = fields.Boolean(default=True)

    sequence = fields.Integer(default=10)

    devops_exec_ids = fields.One2many(
        comodel_name="devops.exec",
        inverse_name="devops_workspace",
        string="Executions",
    )

    devops_test_plan_exec_count = fields.Integer(
        string="Test plan exec count",
        compute="_compute_devops_test_plan_exec_count",
        store=True,
    )

    devops_test_plan_exec_ids = fields.One2many(
        comodel_name="devops.test.plan.exec",
        inverse_name="workspace_id",
        string="Test plan exec",
    )

    devops_test_result_count = fields.Integer(
        string="Test result count",
        compute="_compute_devops_test_result_count",
        store=True,
    )

    devops_test_result_ids = fields.One2many(
        comodel_name="devops.test.result",
        inverse_name="workspace_id",
        string="Test result",
    )

    devops_exec_count = fields.Integer(
        string="Executions count",
        compute="_compute_devops_exec_count",
        store=True,
    )

    new_project_count = fields.Integer(
        string="New project count",
        compute="_compute_new_project_count",
        store=True,
    )

    devops_exec_error_count = fields.Integer(
        string="Executions error count",
        compute="_compute_devops_exec_error_count",
        store=True,
    )

    devops_exec_bundle_count = fields.Integer(
        string="Executions bundle count",
        compute="_compute_devops_exec_bundle_count",
        store=True,
    )

    devops_exec_bundle_root_count = fields.Integer(
        string="Executions bundle root count",
        compute="_compute_devops_exec_bundle_count",
        store=True,
    )

    devops_exec_bundle_ids = fields.One2many(
        comodel_name="devops.exec.bundle",
        inverse_name="devops_workspace",
        string="Executions bundle",
    )

    devops_exec_bundle_root_ids = fields.One2many(
        comodel_name="devops.exec.bundle",
        inverse_name="devops_workspace",
        string="Executions bundle root",
        domain=[("parent_id", "=", False)],
    )

    devops_exec_error_ids = fields.One2many(
        comodel_name="devops.exec.error",
        inverse_name="devops_workspace",
        string="Executions error",
    )

    devops_workspace_format = fields.Selection(
        selection=[
            ("zip", "zip (includes filestore)"),
            ("dump", "pg_dump custom format (without filestore)"),
        ],
        default="zip",
        help="Choose the format for this devops_workspace.",
    )

    log_workspace = fields.Text()

    show_error_chatter = fields.Boolean(help="Show error to chatter")

    log_makefile_target_ids = fields.One2many(
        comodel_name="devops.log.makefile.target",
        inverse_name="devops_workspace_id",
        string="Makefile Targets",
    )

    path_working_erplibre = fields.Char(default="/ERPLibre")

    is_installed = fields.Boolean(
        string="Installed",
        help="Need to install environnement before execute it.",
    )

    is_robot = fields.Boolean(
        string="Robot",
        help="The automated robot to manage ERPLibre.",
    )

    path_code_generator_to_generate = fields.Char(
        compute="_compute_path_code_generator_to_generate",
        store=True,
    )

    namespace = fields.Char(help="Specific name for this workspace")

    is_debug_log = fields.Boolean(help="Will print cmd to debug.")

    # TODO transform in in compute with devops_workspace_docker.is_running
    is_running = fields.Boolean(readonly=True)

    folder = fields.Char(
        required=True,
        default=lambda self: self._default_folder(),
        help="Absolute path for storing the devops_workspaces",
    )

    system_id = fields.Many2one(
        comodel_name="devops.system",
        string="System",
        required=True,
        default=lambda self: self.env.ref(
            "erplibre_devops.devops_system_local", raise_if_not_found=False
        ),
    )

    ide_pycharm = fields.Many2one(comodel_name="devops.ide.pycharm")

    # TODO backup button and restore button
    port_http = fields.Integer(
        string="port http",
        default=8069,
        help="The port of http odoo.",
    )

    port_longpolling = fields.Integer(
        string="port longpolling",
        default=8071,
        help="The port of longpolling odoo.",
    )

    db_name = fields.Char(
        string="DB instance name",
        default="test",
    )

    is_me = fields.Boolean(
        string="ME",
        readonly=True,
        help="Add more automatisation about manage itself.",
    )

    db_is_restored = fields.Boolean(
        readonly=True,
        help="When false, it's because actually restoring a DB.",
    )

    exec_reboot_process = fields.Boolean(
        help=(
            "Reboot means kill and reborn, but from operating system, where is"
            " the origin! False mean keep same parent process, reboot the ERP"
            " only. When False, a bug occur and the transaction cannot finish."
            " Only work with is_me."
        )
    )

    url_instance = fields.Char(
        compute="_compute_url_instance",
        store=True,
    )

    url_instance_database_manager = fields.Char(
        compute="_compute_url_instance",
        store=True,
    )

    erplibre_mode = fields.Many2one(
        comodel_name="erplibre.mode",
        string="Mode",
    )

    mode_exec = fields.Many2one(
        comodel_name="erplibre.mode.exec", related="erplibre_mode.mode_exec"
    )

    system_method = fields.Selection(
        related="system_id.method", string="Method"
    )

    # TODO move it to erplibre.mode
    is_conflict_mode_exec = fields.Boolean(
        compute="_compute_is_conflict_mode_exec",
        store=True,
    )

    git_branch = fields.Char(string="Git branch")

    git_url = fields.Char(
        string="Git URL",
        default="https://github.com/ERPLibre/ERPLibre",
    )

    workspace_docker_id = fields.Many2one(
        comodel_name="devops.workspace.docker",
        string="Workspace Docker",
    )

    workspace_terminal_id = fields.Many2one(
        comodel_name="devops.workspace.terminal",
        string="Workspace Terminal",
    )

    has_error_restore_db = fields.Boolean()

    plan_cg_ids = fields.One2many(
        comodel_name="devops.plan.cg",
        inverse_name="workspace_id",
        string="Plan CG",
        help="All plan code generator associate to this workspace",
    )

    plan_cg_count = fields.Integer(
        string="Plan CG count",
        compute="_compute_plan_cg_count",
        store=True,
    )

    new_project_ids = fields.One2many(
        comodel_name="devops.cg.new_project",
        inverse_name="devops_workspace",
        string="All new project associate with this workspace",
    )

    image_db_selection = fields.Many2one(
        comodel_name="devops.db.image",
        default=_default_image_db_selection,
    )

    @api.model_create_multi
    def create(self, vals_list):
        rec_ids = super().create(vals_list)
        for rec_id in rec_ids:
            if not rec_id.ide_pycharm:
                rec_id.ide_pycharm = self.env["devops.ide.pycharm"].create(
                    {"devops_workspace": rec_id.id}
                )
            rec_id.message_subscribe(
                partner_ids=[self.env.ref("base.partner_admin").id]
            )
            # help to find path.home of ERPLibre
            config_id = self.env["erplibre.config.path.home"].get_path_home_id(
                os.path.dirname(rec_id.folder)
            )
            rec_id.system_id.erplibre_config_path_home_ids = [
                (4, config_id.id)
            ]
        return rec_ids

    @api.model
    def _default_folder(self):
        return os.getcwd()

    @api.multi
    @api.depends("is_me", "is_robot", "folder", "namespace")
    def _compute_name(self):
        for rec in self:
            rec.name = ""
            if rec.is_me:
                rec.name += "💻"
            if rec.is_robot:
                rec.name += "🤖"
            if rec.name:
                rec.name += " "
            if rec.namespace:
                rec.name += rec.namespace
            elif rec.folder:
                rec.name += rec.folder

    @api.multi
    @api.depends("erplibre_mode.mode_source", "erplibre_mode.mode_exec")
    def _compute_is_conflict_mode_exec(self):
        for rec in self:
            if rec.erplibre_mode:
                rec.is_conflict_mode_exec = (
                    rec.erplibre_mode.mode_source
                    == self.env.ref(
                        "erplibre_devops.erplibre_mode_source_docker"
                    )
                    and rec.erplibre_mode.mode_exec
                    != self.env.ref(
                        "erplibre_devops.erplibre_mode_exec_docker"
                    )
                )

    @api.multi
    @api.depends("plan_cg_ids.path_code_generator_to_generate")
    def _compute_path_code_generator_to_generate(self):
        for rec in self:
            # Append unpack list with cg and template
            lst_path = ["addons/addons"] + [
                b
                for c in [
                    [
                        a.path_code_generator_to_generate,
                        a.path_code_generator_to_generate_cg,
                        a.path_code_generator_to_generate_template,
                    ]
                    for a in rec.plan_cg_ids
                ]
                for b in c
            ]
            rec.path_code_generator_to_generate = ";".join(set(lst_path))

    @api.multi
    @api.depends("system_id.ssh_host", "system_id.method", "port_http")
    def _compute_url_instance(self):
        for rec in self:
            # TODO create configuration
            # localhost = "127.0.0.1"
            localhost = "localhost"
            url_host = (
                rec.system_id.ssh_host
                if rec.system_id.method == "ssh"
                else localhost
            )
            rec.url_instance = f"http://{url_host}:{rec.port_http}"
            rec.url_instance_database_manager = (
                f"{rec.url_instance}/web/database/manager"
            )

    @api.multi
    @api.depends("devops_exec_ids", "devops_exec_ids.active")
    def _compute_devops_exec_count(self):
        for rec in self:
            rec.devops_exec_count = self.env["devops.exec"].search_count(
                [("devops_workspace", "=", rec.id)]
            )

    @api.multi
    @api.depends(
        "devops_test_plan_exec_ids", "devops_test_plan_exec_ids.active"
    )
    def _compute_devops_test_plan_exec_count(self):
        for rec in self:
            rec.devops_test_plan_exec_count = self.env[
                "devops.test.plan.exec"
            ].search_count([("workspace_id", "=", rec.id)])

    @api.multi
    @api.depends("devops_test_result_ids", "devops_test_result_ids.active")
    def _compute_devops_test_result_count(self):
        for rec in self:
            rec.devops_test_result_count = self.env[
                "devops.test.result"
            ].search_count([("workspace_id", "=", rec.id)])

    @api.multi
    @api.depends("plan_cg_ids", "plan_cg_ids.active")
    def _compute_plan_cg_count(self):
        for rec in self:
            rec.plan_cg_count = self.env["devops.plan.cg"].search_count(
                [("workspace_id", "=", rec.id)]
            )

    @api.multi
    @api.depends("devops_exec_error_ids", "devops_exec_error_ids.active")
    def _compute_devops_exec_error_count(self):
        for rec in self:
            rec.devops_exec_error_count = self.env[
                "devops.exec.error"
            ].search_count([("devops_workspace", "=", rec.id)])

    @api.multi
    @api.depends("devops_exec_bundle_ids", "devops_exec_bundle_ids.active")
    def _compute_devops_exec_bundle_count(self):
        for rec in self:
            rec.devops_exec_bundle_count = self.env[
                "devops.exec.bundle"
            ].search_count([("devops_workspace", "=", rec.id)])
            rec.devops_exec_bundle_root_count = self.env[
                "devops.exec.bundle"
            ].search_count(
                [("devops_workspace", "=", rec.id), ("parent_id", "=", False)]
            )

    @api.multi
    @api.depends("new_project_ids", "new_project_ids.active")
    def _compute_new_project_count(self):
        for rec in self:
            rec.new_project_count = self.env[
                "devops.cg.new_project"
            ].search_count([("devops_workspace", "=", rec.id)])

    @api.multi
    def action_open_workspace_pycharm(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle("Setup PyCharm debug") as rec:
                rec.ide_pycharm.action_pycharm_open(rec, folder=rec.folder)

    @api.multi
    def action_cg_setup_pycharm_debug(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle("Setup PyCharm debug") as rec:
                rec.ide_pycharm.action_cg_setup_pycharm_debug()

    @api.multi
    def action_clear_error_exec(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle("Clear error exec") as rec:
                for error in rec.devops_exec_error_ids:
                    error.active = False

    @api.multi
    def action_format_erplibre_devops(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle(
                "Format ERPLibre DevOps"
            ) as rec:
                rec.execute(
                    cmd=(
                        "./script/maintenance/format.sh"
                        " ./addons/ERPLibre_erplibre_addons/erplibre_devops"
                    )
                )

    @api.multi
    def action_update_erplibre_devops(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle(
                "Update ERPLibre DevOps"
            ) as rec:
                # TODO change db_name from this db
                rec.execute(
                    cmd=(
                        "./run.sh --limit-time-real 999999 --no-http"
                        f" --stop-after-init --dev cg -d {rec.db_name} -i"
                        " erplibre_devops -u erplibre_devops"
                    )
                )

    @api.multi
    def install_module(self, str_module_list):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle("Install module") as rec:
                # str_module_list is string separate module by ','
                if rec.erplibre_mode.mode_exec in [
                    self.env.ref("erplibre_devops.erplibre_mode_exec_docker")
                ]:
                    last_cmd = rec.workspace_docker_id.docker_cmd_extra
                    rec.workspace_docker_id.docker_cmd_extra = (
                        f"-d {rec.db_name} -i {str_module_list} -u"
                        f" {str_module_list}"
                    )
                    # TODO option install continuous or stop execution.
                    # TODO Use install continuous in production, else stop execution for dev
                    # TODO actually, it's continuous
                    # TODO maybe add an auto-update when detect installation finish
                    rec.action_reboot()
                    rec.workspace_docker_id.docker_cmd_extra = last_cmd
                elif rec.erplibre_mode.mode_exec in [
                    self.env.ref("erplibre_devops.erplibre_mode_exec_terminal")
                ]:
                    rec.execute(
                        "./script/addons/install_addons.sh"
                        f" {rec.db_name} {str_module_list}",
                        to_instance=True,
                    )
                    rec.action_reboot()

    @api.multi
    def action_open_terminal(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle("Open Terminal") as rec:
                rec.execute(force_open_terminal=True)

    @api.multi
    def action_open_directory(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle("Open directory") as rec:
                # TODO this need to use system
                if rec.is_me:
                    if platform.system() == "Windows":
                        os.startfile(rec.folder)
                    elif platform.system() == "Darwin":
                        subprocess.Popen(["open", rec.folder])
                    else:
                        subprocess.Popen(["xdg-open", rec.folder])
                else:
                    if rec.system_id.method == "ssh":
                        cmd = (
                            "nautilus"
                            f" ssh://{rec.system_id.ssh_user}@{rec.system_id.ssh_host}/{rec.folder}"
                        )
                    else:
                        cmd = f"nautilus {rec.folder}"
                    self.env.ref(
                        "erplibre_devops.devops_workspace_me"
                    ).execute(cmd=cmd)

    @api.model
    def action_check_all(self):
        """Run all scheduled check."""
        return self.search([]).action_check()

    @api.multi
    def action_check(self):
        for rec_o in self:
            # Track exception because it's run from cron
            with rec_o.devops_create_exec_bundle("Check all") as rec:
                # rec.docker_initiate_succeed = not rec.docker_initiate_succeed
                # TODO Check if project is installed, check script installation
                # exec_id = rec.execute(cmd=f"ls {rec.folder}")
                # lst_file = exec_id.log_all.strip().split("\n")
                # if any(
                #     [
                #         "No such file or directory" in str_file
                #         for str_file in lst_file
                #     ]
                # ):
                #     rec.is_installed = False
                if rec.erplibre_mode.mode_exec in [
                    self.env.ref("erplibre_devops.erplibre_mode_exec_docker")
                ]:
                    rec.is_running = rec.workspace_docker_id.docker_is_running
                    rec.workspace_docker_id.action_check()
                elif rec.erplibre_mode.mode_exec in [
                    self.env.ref("erplibre_devops.erplibre_mode_exec_terminal")
                ]:
                    exec_id = rec.execute(
                        f"lsof -i TCP:{rec.port_http} | grep python",
                        error_on_status=False,
                    )
                    rec.is_running = bool(exec_id.log_all)
                    rec.workspace_terminal_id.action_check()
                else:
                    _logger.warning(
                        "Support other mode_exec to detect is_running"
                        f" '{rec.mode_exec}'"
                    )

    @api.multi
    def action_install_me_workspace(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle(
                "Install ME workspace"
            ) as rec:
                # Set same BD of this instance
                rec.db_name = self.env.cr.dbname
                # Detect the mode exec of this instance
                exec_id = rec.execute(
                    cmd=f"ls {rec.folder}/.git", error_on_status=False
                )
                status_ls = exec_id.log_all
                if "No such file or directory" not in status_ls:
                    rec.erplibre_mode = self.env.ref(
                        "erplibre_devops.erplibre_mode_git_robot_libre"
                    ).id
                rec.action_install_workspace()
                rec.is_me = True
                rec.is_robot = True
                rec.port_http = 8069
                rec.port_longpolling = 8072
                rec.is_running = True

    @api.multi
    def action_restore_db_image(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle("Restore DB image") as rec:
                rec.has_error_restore_db = False
                if rec.erplibre_mode.mode_exec in [
                    self.env.ref("erplibre_devops.erplibre_mode_exec_terminal")
                ]:
                    image = ""
                    if rec.image_db_selection:
                        image = f" --image {rec.image_db_selection.name}"
                    cmd = (
                        "./script/database/db_restore.py --database"
                        f" {rec.db_name}{image};"
                    )
                    exec_id = rec.execute(
                        cmd=cmd, folder=rec.path_working_erplibre
                    )
                    rec.log_workspace = f"\n{exec_id.log_all}"
                elif rec.erplibre_mode.mode_exec in [
                    self.env.ref("erplibre_devops.erplibre_mode_exec_docker")
                ]:
                    # maybe send by network REST web/database/restore
                    url_list = f"{rec.url_instance}/web/database/list"
                    url_restore = f"{rec.url_instance}/web/database/restore"
                    url_drop = f"{rec.url_instance}/web/database/drop"
                    if not rec.image_db_selection:
                        # TODO create stage, need a stage ready to restore
                        raise exceptions.Warning(
                            _("Error, need field db_selection")
                        )
                    rec.db_is_restored = False
                    backup_file_path = rec.image_db_selection.path
                    session = requests.Session()
                    response = requests.get(
                        url_list,
                        data=json.dumps({}),
                        headers={
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                    )
                    if response.status_code == 200:
                        database_list = response.json()
                        _logger.info(database_list)
                    else:
                        _logger.error(
                            "Restore image response error"
                            f" {response.status_code}"
                        )
                        continue

                    # Delete first
                    # TODO cannot delete database if '-d database' argument -d is set
                    result_db_list = database_list.get("result")
                    if rec.db_name in result_db_list:
                        _logger.info(result_db_list)
                        files = {
                            "master_pwd": (None, "admin"),
                            "name": (None, rec.db_name),
                        }
                        response = session.post(url_drop, files=files)
                        if response.status_code == 200:
                            _logger.info("Le drop a été envoyé avec succès.")
                        else:
                            rec.workspace_docker_id.docker_cmd_extra = ""
                            # TODO detect "-d" in execution instead of force action_reboot
                            rec.action_reboot()
                            _logger.error(
                                "Une erreur s'est produite lors du drop, code"
                                f" '{response.status_code}'. Retry in"
                                f" {SLEEP_ERROR_RESTORE_KILL} seconds"
                            )
                            # Strange, retry for test
                            time.sleep(SLEEP_ERROR_RESTORE_KILL)
                            # response = requests.get(
                            #     url_list,
                            #     data=json.dumps({}),
                            #     headers={
                            #         "Content-Type": "application/json",
                            #         "Accept": "application/json",
                            #     },
                            # )
                            response = session.post(url_drop, files=files)
                            if response.status_code == 200:
                                # database_list = response.json()
                                # print(database_list)
                                _logger.info(
                                    "Seconde essaie, le drop a été envoyé avec"
                                    " succès."
                                )
                            else:
                                _logger.error(
                                    "Seconde essaie, une erreur s'est produite"
                                    " lors du drop, code"
                                    f" '{response.status_code}'."
                                )
                                rec.has_error_restore_db = True
                        if not rec.has_error_restore_db:
                            response = requests.get(
                                url_list,
                                data=json.dumps({}),
                                headers={
                                    "Content-Type": "application/json",
                                    "Accept": "application/json",
                                },
                            )
                            if response.status_code == 200:
                                database_list = response.json()
                                _logger.info(database_list)

                    if not rec.has_error_restore_db:
                        with open(backup_file_path, "rb") as backup_file:
                            files = {
                                "backup_file": (
                                    backup_file.name,
                                    backup_file,
                                    "application/octet-stream",
                                ),
                                "master_pwd": (None, "admin"),
                                "name": (None, rec.db_name),
                            }
                            response = session.post(url_restore, files=files)
                        if response.status_code == 200:
                            _logger.info(
                                "Le fichier de restauration a été envoyé avec"
                                " succès."
                            )
                            rec.db_is_restored = True
                        else:
                            _logger.error(
                                "Une erreur s'est produite lors de l'envoi du"
                                " fichier de restauration."
                            )

                    # f = {'file data': open(f'./image_db{rec.path_working_erplibre}_base.zip', 'rb')}
                    # res = requests.post(url_restore, files=f)
                    # print(res.text)

    @api.multi
    def check_devops_workspace(self):
        for rec in self:
            if rec.erplibre_mode.mode_exec in [
                self.env.ref("erplibre_devops.erplibre_mode_exec_docker")
            ]:
                if not rec.workspace_docker_id:
                    rec.workspace_docker_id = self.env[
                        "devops.workspace.docker"
                    ].create({"workspace_id": rec.id})
            elif rec.erplibre_mode.mode_exec in [
                self.env.ref("erplibre_devops.erplibre_mode_exec_terminal")
            ]:
                if not rec.workspace_terminal_id:
                    rec.workspace_terminal_id = self.env[
                        "devops.workspace.terminal"
                    ].create({"workspace_id": rec.id})
            else:
                raise exceptions.Warning(f"Cannot support '{rec.mode_exec}'")

    @api.multi
    def action_start(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle("Start") as rec:
                rec.check_devops_workspace()
                if rec.erplibre_mode.mode_exec in [
                    self.env.ref("erplibre_devops.erplibre_mode_exec_docker")
                ]:
                    rec.workspace_docker_id.action_start_docker_compose()
                elif rec.erplibre_mode.mode_exec in [
                    self.env.ref("erplibre_devops.erplibre_mode_exec_terminal")
                ]:
                    rec.execute(
                        cmd=(
                            "./run.sh -d"
                            f" {rec.db_name} --http-port={rec.port_http} --longpolling-port={rec.port_longpolling}"
                        ),
                        force_open_terminal=True,
                    )
                    # TODO validate output if execution conflict port to remove time.sleep
                    rec.is_running = True
                    # Time to start services, because action_check need time to detect port is open
                    time.sleep(SLEEP_KILL)

    @api.multi
    def action_stop(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle("Stop") as rec:
                rec.check_devops_workspace()
                if rec.erplibre_mode.mode_exec in [
                    self.env.ref("erplibre_devops.erplibre_mode_exec_docker")
                ]:
                    rec.workspace_docker_id.action_stop_docker_compose()
                    rec.action_check()
                elif rec.erplibre_mode.mode_exec in [
                    self.env.ref("erplibre_devops.erplibre_mode_exec_terminal")
                ]:
                    if rec.is_me:
                        pid = os.getpid()
                        rec.execute(
                            cmd=f"sleep {SLEEP_KILL};kill -9 {pid}",
                            force_open_terminal=True,
                            force_exit=True,
                            error_on_status=False,
                        )
                        rec_o.is_running = False
                    else:
                        rec.kill_process()
                        rec.action_check()

    @api.multi
    def action_update(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle("Update DevOps") as rec:
                rec.action_format_erplibre_devops()
                rec.action_update_erplibre_devops()
                rec.action_reboot()

    @api.multi
    def action_open_local_view(self, ctx=None, url_instance=None):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle("Open local view") as rec:
                str_url_instance = (
                    url_instance if url_instance else rec.url_instance
                )
                self.env.ref("erplibre_devops.devops_workspace_me").execute(
                    cmd=(
                        "source"
                        " ./.venv/bin/activate;./script/selenium/web_login.py"
                        f" --url {str_url_instance}"
                    ),
                    force_open_terminal=True,
                    run_into_workspace=True,
                )

    @api.multi
    def action_reboot(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle("Reboot") as rec:
                exec_reboot_process = rec._context.get(
                    "default_exec_reboot_process", rec.exec_reboot_process
                )
                if rec.is_me:
                    if not exec_reboot_process:
                        service.server.restart()
                    else:
                        # Expect already run ;-), no need to validate
                        pid = os.getpid()
                        rec.execute(
                            cmd=f"sleep {SLEEP_KILL};kill -9 {pid}",
                            force_open_terminal=True,
                            force_exit=True,
                            error_on_status=False,
                        )
                        rec.execute(
                            cmd=(
                                f"sleep {SLEEP_WAIT_KILL};./run.sh -d"
                                f" {rec.db_name} --http-port={rec.port_http} --longpolling-port={rec.port_longpolling}"
                            ),
                            force_open_terminal=True,
                            error_on_status=False,
                        )
                else:
                    rec.action_stop()
                    rec.action_start()

    @api.multi
    def kill_process(self, port=None, sleep_kill=0):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle("Kill process") as rec:
                if sleep_kill:
                    cmd = f"sleep {SLEEP_KILL};"
                else:
                    cmd = ""
                if not port:
                    port = rec.port_http
                exec_id = rec.execute(
                    f"lsof -FF -c python -i TCP:{port} -a",
                    error_on_status=False,
                )
                if exec_id.log_all:
                    lines = [
                        a
                        for a in exec_id.log_all.split("\n")
                        if a.startswith("p")
                    ]
                    if len(lines) > 1:
                        _logger.warning(
                            "What is the software for the port"
                            f" {port} : {exec_id.log_all}"
                        )
                    elif len(lines) == 1:
                        cmd += f"kill -9 {lines[0][1:]}"
                        rec.execute(
                            cmd=cmd,
                            force_open_terminal=True,
                            force_exit=True,
                            error_on_status=False,
                        )
                        rec_o.is_running = False

    @api.multi
    def action_install_workspace(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle("Install workspace") as rec:
                exec_id = rec.execute(
                    cmd=f"ls {rec.folder}", error_on_status=False
                )
                lst_file = exec_id.log_all.strip().split("\n")
                rec.namespace = os.path.basename(rec.folder)
                if rec.erplibre_mode.mode_source in [
                    self.env.ref("erplibre_devops.erplibre_mode_source_docker")
                ]:
                    if "docker-compose.yml" in lst_file:
                        # TODO try to reuse
                        _logger.info(
                            "detect docker-compose.yml, please read it"
                        )
                    rec.action_pre_install_workspace()
                    rec.path_working_erplibre = "/ERPLibre"
                elif rec.erplibre_mode.mode_source in [
                    self.env.ref("erplibre_devops.erplibre_mode_source_git")
                ]:
                    # TODO this can be move to erplibre_mode
                    if rec.erplibre_mode.mode_exec in [
                        self.env.ref(
                            "erplibre_devops.erplibre_mode_exec_docker"
                        )
                    ]:
                        rec.path_working_erplibre = "/ERPLibre"
                    else:
                        rec.path_working_erplibre = rec.folder
                    branch_str = ""
                    if rec.erplibre_mode.mode_version_erplibre:
                        branch_str = (
                            f" -b {rec.erplibre_mode.mode_version_erplibre.value}"
                        )
                    git_arg = f"{branch_str} {rec.folder}"

                    # TTODO bug if file has same key
                    # if any(["ls:cannot access " in str_file for str_file in lst_file]):
                    # if any(
                    #     [
                    #         "No such file or directory" in str_file
                    #         for str_file in lst_file
                    #     ]
                    # ):
                    is_first_install = False
                    if exec_id.exec_status:
                        dir_name = os.path.dirname(rec.folder)
                        # No such directory
                        exec_id = rec.execute(
                            cmd=f"git clone {rec.git_url}{git_arg}",
                            folder=dir_name,
                            error_on_status=False,
                        )
                        rec.log_workspace = exec_id.log_all
                        if exec_id.exec_status:
                            raise Exception(exec_id.log_all)
                        is_first_install = True
                    else:
                        _logger.info(
                            f'Git project already exist for "{rec.folder}"'
                        )
                        # Check branch
                        if self.env.context.get("force_reinstall_workspace"):
                            if (
                                rec.erplibre_mode
                                and rec.erplibre_mode.mode_version_erplibre
                            ):
                                branch_str = (
                                    rec.erplibre_mode.mode_version_erplibre.value
                                )
                            else:
                                branch_str = ""

                            exec_id = rec.execute(
                                cmd=(
                                    "git fetch --all;git checkout"
                                    f" {branch_str}"
                                ),
                                folder=rec.folder,
                                force_open_terminal=True,
                            )
                            if exec_id.exec_status:
                                raise Exception(exec_id.log_all)
                    if self.env.context.get("install_dev_workspace"):
                        exec_id = rec.execute(
                            cmd=f"./script/install/install_dev.sh",
                            folder=rec.folder,
                            force_open_terminal=True,
                        )
                        # print(exec_id)
                        # Force stop execution, async execution installation
                        return
                    if is_first_install or self.env.context.get(
                        "force_reinstall_workspace"
                    ):
                        # TODO implement debug with step and open with open-terminal async
                        exec_id = rec.execute(
                            cmd=f"./script/install/install_locally_dev.sh",
                            folder=rec.folder,
                            error_on_status=False,
                        )
                        rec.log_workspace = exec_id.log_all
                        if exec_id.exec_status:
                            raise Exception(exec_id.log_all)
                        # TODO fix this bug, but activate into install script
                        # TODO bug only for local, ssh is good
                        # Bug poetry thinks it's installed, so force it
                        # result = rec.system_id.execute_with_result(
                        #     f"cd {rec.folder};source"
                        #     " ./.venv/bin/activate;poetry install"
                        # )
                        # rec.log_workspace += result
                        rec.execute(
                            cmd=(
                                'bash -c "source'
                                ' ./.venv/bin/activate;poetry install"'
                            ),
                            force_open_terminal=True,
                        )
                        if exec_id.exec_status:
                            raise Exception(exec_id.log_all)
                    rec.update_makefile_from_git()

                    # lst_file = rec.execute(cmd=f"ls {rec.folder}").log_all.strip().split("\n")
                    # if "docker-compose.yml" in lst_file:
                    # if rec.mode_environnement in ["prod", "test"]:
                    #     result = rec.system_id.execute_with_result(
                    #         f"git clone https://github.com{rec.path_working_erplibre}{rec.path_working_erplibre}"
                    #         f"{branch_str}"
                    #     )
                    # else:
                rec.action_network_change_port_random()
                # TODO this "works" for source git, but source docker, need to check docker inspect
                folder_venv = os.path.join(rec.folder, ".venv")
                rec.is_installed = rec.os_path_exists(
                    rec.folder
                ) and rec.os_path_exists(folder_venv)
                # TODO now, robot is this branch, but find another way to identify it
                rec.is_robot = (
                    rec.erplibre_mode.mode_version_erplibre.id
                    == self.env.ref(
                        "erplibre_devops.erplibre_mode_version_erplibre_robot_libre"
                    ).id
                )

    @api.multi
    def update_makefile_from_git(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle("Update makefile") as rec:
                exec_mk_ref_id = rec.execute(
                    cmd=(
                        "git show"
                        f" {rec.erplibre_mode.mode_version_erplibre.value}:Makefile"
                    ),
                    to_instance=True,
                )
                ref_makefile_content = exec_mk_ref_id.log_all
                exec_mk_now_id = rec.execute(
                    cmd=f"cat Makefile", to_instance=True
                )
                now_makefile_content = exec_mk_now_id.log_all

                lst_ref = rec.get_lst_target_makefile(ref_makefile_content)
                lst_now = rec.get_lst_target_makefile(now_makefile_content)

                diff = set(lst_now).difference(set(lst_ref))
                lst_diff = list(diff)
                lst_ignore_target = ("PHONY",)
                for target in lst_diff:
                    if target in lst_ignore_target:
                        continue
                    self.env["devops.log.makefile.target"].create(
                        {"name": target, "devops_workspace_id": rec.id}
                    )

    @api.multi
    def execute(
        self,
        cmd="",
        folder="",
        force_open_terminal=False,
        force_exit=False,
        force_docker=False,
        add_stdin_log=False,
        add_stderr_log=True,
        run_into_workspace=False,
        to_instance=False,
        engine="bash",
        delimiter_bash="'",
        error_on_status=True,
    ):
        # TODO search into context if need to parallel or serial
        lst_result = []
        first_log_debug = True
        out = False
        # out = ""
        # err = ""
        # status = False
        if force_exit:
            cmd = f"{cmd};exit"
        for rec in self:
            rec_force_docker = force_docker
            if to_instance:
                rec.check_devops_workspace()
                if not folder:
                    folder = rec.path_working_erplibre
                if rec.erplibre_mode.mode_exec in [
                    self.env.ref("erplibre_devops.erplibre_mode_exec_docker")
                ]:
                    rec_force_docker = True

            if rec.is_debug_log and cmd:
                if first_log_debug:
                    _logger.info(cmd)
                    first_log_debug = False

            force_folder = folder if folder else rec.folder
            devops_exec_value = {
                "devops_workspace": rec.id,
                "cmd": cmd,
                "folder": force_folder,
            }
            devops_exec_bundle = self.env.context.get("devops_exec_bundle")
            devops_exec_bundle_id = None
            if devops_exec_bundle:
                devops_exec_bundle_id = (
                    self.env["devops.exec.bundle"]
                    .browse(devops_exec_bundle)
                    .exists()
                )
                devops_exec_value["devops_exec_bundle_id"] = devops_exec_bundle
            id_devops_cg_new_project = self.env.context.get(
                "devops_cg_new_project"
            )
            if id_devops_cg_new_project:
                devops_exec_value["new_project_id"] = id_devops_cg_new_project

            # ### Find who call us ###
            actual_file = str(pathlib.Path(__file__).resolve())
            is_found = False
            str_tb = None
            # When found it, the result is next one, extract filename and line
            for str_tb in traceback.format_stack()[::-1]:
                if is_found:
                    break
                if actual_file in str_tb:
                    is_found = True
            if is_found:
                # index 0, filename like «file "/home..."»
                # index 1, line number like «line 1234»
                # index 2, keyword
                lst_tb = [a.strip() for a in str_tb.split(",")]
                # Remove absolute path
                filename = lst_tb[0][6:-1][len(rec.folder) + 1 :]
                line_number = int(lst_tb[1][5:])
                keyword = lst_tb[2]
                bp_value = {
                    "name": "breakpoint_exec",
                    "description": (
                        "Breakpoint generate when create an execution."
                    ),
                    "filename": filename,
                    "no_line": line_number,
                    "keyword": keyword,
                    "ignore_test": True,
                    "generated_by_execution": True,
                }
                bp_id = self.env["devops.ide.breakpoint"].create(bp_value)
                devops_exec_value["ide_breakpoint"] = bp_id.id
                devops_exec_value["exec_filename"] = filename
                devops_exec_value["exec_line_number"] = line_number
                devops_exec_value["exec_keyword"] = keyword
            # ### END Find who call us ###

            devops_exec = self.env["devops.exec"].create(devops_exec_value)
            lst_result.append(devops_exec)
            status = None
            if force_open_terminal:
                rec.system_id.execute_terminal_gui(
                    folder=force_folder,
                    cmd=cmd,
                    docker=rec_force_docker,
                )
            elif rec_force_docker:
                out, status = rec.system_id.exec_docker(
                    cmd, force_folder, return_status=True
                )
            else:
                if run_into_workspace and not folder:
                    folder = force_folder
                out, status = rec.system_id.execute_with_result(
                    cmd,
                    folder,
                    add_stdin_log=add_stdin_log,
                    add_stderr_log=add_stderr_log,
                    engine=engine,
                    delimiter_bash=delimiter_bash,
                    return_status=True,
                )

            devops_exec.exec_stop_date = fields.Datetime.now()
            if out is not False and out.strip():
                devops_exec.log_stdout = out.strip()
                rec.find_exec_error_from_log(
                    out, devops_exec, devops_exec_bundle_id
                )
                devops_exec.compute_error()
            if status:
                devops_exec.exec_status = int(status)
                if error_on_status:
                    parent_root_id = devops_exec_bundle_id.get_parent_root()
                    rec.create_exec_error(
                        "Detect status > 0 on execution.",
                        devops_exec.log_stdout,
                        rec,
                        devops_exec_bundle_id,
                        devops_exec,
                        parent_root_id,
                        "internal",
                    )

        if len(self) == 1:
            return lst_result[0]
        return self.env["devops.exec"].browse([a.id for a in lst_result])

    @api.model
    def get_lst_target_makefile(self, content):
        regex = r"^\.PHONY:.*|([\w]+):\s"
        targets = re.findall(regex, content, re.MULTILINE)
        targets = list(set([target for target in targets if target]))
        return targets

    @api.model
    def os_path_exists(self, path, to_instance=False):
        cmd = f'[ -e "{path}" ] && echo "true" || echo "false"'
        result = self.execute(cmd=cmd, to_instance=to_instance)
        return result.log_all.strip() == "true"

    @api.model
    def os_read_file(self, path, to_instance=False):
        cmd = f'cat "{path}"'
        result = self.execute(cmd=cmd, to_instance=to_instance)
        return result.log_all

    @api.model
    def os_write_file(self, path, content, to_instance=False):
        cmd = f'echo "{content}" > "{path}"'
        result = self.execute(cmd=cmd, to_instance=to_instance)
        return result.log_all

    @api.model
    def find_exec_error_from_log(
        self, log, devops_exec, devops_exec_bundle_id
    ):
        # nb_error_estimate = log.count("During handling of the above exception, another exception occurred:")
        if not devops_exec_bundle_id:
            raise exceptions.Warning(
                f"Executable command {devops_exec.cmd} missing exec.bundle."
            )

        index_first_traceback = log.find("Traceback (most recent call last):")
        if index_first_traceback == -1:
            # cannot find exception
            return
        index_last_traceback = index_first_traceback

        lst_exception = (
            "odoo.exceptions.ValidationError:",
            "Exception:",
            "NameError:",
            "TypeError:",
            "AttributeError:",
            "ValueError:",
            "AssertionError:",
            "SyntaxError:",
            "KeyError:",
            "psycopg2.errors.UndefinedTable:",
            "UnboundLocalError:",
            "FileNotFoundError:",
            "RuntimeWarning:",
            "raise ValidationError",
            "odoo.exceptions.CacheMiss:",
            "json.decoder.JSONDecodeError:",
            "RuntimeError:",
        )
        # TODO move lst_exception into model devops.exec.exception
        for exception in lst_exception:
            index_error = log.rfind(exception)
            if index_last_traceback < index_error:
                index_last_traceback = index_error
            # index_endline_error = log.find("\n", index_error)

        if index_last_traceback <= index_first_traceback:
            raise Exception(
                "Cannot find exception, but an exception is detected. TODO"
                " debug it."
            )

        parent_root_id = devops_exec_bundle_id.get_parent_root()
        escaped_tb_all = log[index_first_traceback:index_last_traceback]
        lst_escaped_tb = escaped_tb_all.split(
            "During handling of the above exception, another exception"
            " occurred:"
        )
        for escaped_tb in lst_escaped_tb:
            escaped_tb = escaped_tb.strip()
            found_same_error_ids = self.env["devops.exec.error"].search(
                [
                    (
                        "parent_root_exec_bundle_id",
                        "=",
                        parent_root_id.id,
                    ),
                    (
                        "description",
                        "=",
                        devops_exec_bundle_id.description,
                    ),
                    ("escaped_tb", "=", escaped_tb),
                ]
            )
            if not found_same_error_ids:
                self.create_exec_error(
                    devops_exec_bundle_id.description,
                    escaped_tb,
                    self,
                    devops_exec_bundle_id,
                    devops_exec,
                    parent_root_id,
                    "execution",
                )

    @api.multi
    def action_poetry_install(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle("Poetry install") as rec:
                rec.execute(
                    cmd='bash -c "source ./.venv/bin/activate;poetry install"'
                )

    @api.multi
    def action_pre_install_workspace(self):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle(
                "Pre install workspace"
            ) as rec:
                # Directory must exist
                # TODO make test to validate if remove next line, permission root the project /tmp/project/addons root
                addons_path = os.path.join(rec.folder, "addons", "addons")
                rec.execute(f"mkdir -p '{addons_path}'")

    @api.multi
    @api.model
    def action_network_change_port_default(
        self, ctx=None, default_port_http=8069, default_port_longpolling=8072
    ):
        for rec_o in self:
            with rec_o.devops_create_exec_bundle(
                "Network change port default"
            ) as rec:
                rec.port_http = default_port_http
                rec.port_longpolling = default_port_longpolling

    @api.multi
    def action_network_change_port_random(
        self, ctx=None, min_port=10000, max_port=20000
    ):
        # Choose 2 sequence
        for rec_o in self:
            with rec_o.devops_create_exec_bundle(
                "Network change port random"
            ) as rec:
                # port_1
                while rec.check_port_is_open(
                    rec, rec.system_id.iterator_port_generator
                ):
                    rec.system_id.iterator_port_generator += 1
                rec.port_http = rec.system_id.iterator_port_generator
                rec.system_id.iterator_port_generator += 1
                # port_2
                while rec.check_port_is_open(
                    rec, rec.system_id.iterator_port_generator
                ):
                    rec.system_id.iterator_port_generator += 1
                rec.port_longpolling = rec.system_id.iterator_port_generator
                rec.system_id.iterator_port_generator += 1
                if rec.system_id.iterator_port_generator >= max_port:
                    rec.system_id.iterator_port_generator = min_port

    @staticmethod
    def check_port_is_open(rec, port):
        """
        Return False or the PID integer of the open port
        """
        # TODO move to devops_network

        # lsof need sudo when it's another process, like a docker run by root
        # exec_id = rec.execute(f"lsof -FF -i TCP:{port}")
        # if not exec_id.log_all:
        #     return False
        # return int(exec_id.log_all[1 : exec_id.log_all.find("\n")])

        script = f"""import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
result = sock.connect_ex(("127.0.0.1",{port}))
if result == 0:
   print("Port is open")
else:
   print("Port is not open")
sock.close()
"""
        if rec.system_id.debug_command:
            _logger.info(script)
        exec_id = rec.execute(
            cmd=script,
            engine="python",
        )
        return exec_id.log_all.strip() == "Port is open"

    @api.model
    def get_partner_channel(self):
        partner_ids = [
            (
                6,
                0,
                [
                    a.partner_id.id
                    for a in self.message_follower_ids
                    if a.partner_id
                ],
            )
        ]
        channel_ids = [
            (
                6,
                0,
                [
                    a.channel_id.id
                    for a in self.message_follower_ids
                    if a.channel_id
                ],
            )
        ]
        return partner_ids, channel_ids

    @api.multi
    def create_exec_error(
        self,
        description,
        escaped_tb,
        devops_workspace_id,
        devops_exec_bundle_id,
        devops_exec_id,
        parent_root_id,
        type_error,
    ):
        lst_result = []
        for rec in self:
            error_value = {
                "description": description,
                "escaped_tb": escaped_tb,
                "devops_workspace": devops_workspace_id.id,
                "devops_exec_bundle_id": devops_exec_bundle_id.id,
                "parent_root_exec_bundle_id": parent_root_id.id,
                "type_error": type_error,
            }
            if devops_exec_id:
                error_value["devops_exec_id"] = devops_exec_id.id
            if parent_root_id.devops_new_project_ids.exists():
                error_value[
                    "new_project_id"
                ] = parent_root_id.devops_new_project_ids[0].id
                error_value[
                    "stage_new_project_id"
                ] = parent_root_id.devops_new_project_ids[0].stage_id.id
            # this is not true, cannot associate exec_id to this error
            # exec_id = devops_exec_bundle_id.get_last_exec()
            # if exec_id:
            #     error_value["devops_exec_ids"] = exec_id.id
            partner_ids, channel_ids = rec.get_partner_channel()
            if partner_ids:
                error_value["partner_ids"] = partner_ids
            if channel_ids:
                error_value["channel_ids"] = channel_ids
            if rec._context.get("devops_workspace_create_exec_error"):
                exec_error_id = None
                _logger.warning(
                    "Detect infinite loop when create exec_error, stop it."
                )
            else:
                exec_error_id = (
                    self.env["devops.exec.error"]
                    .with_context(devops_workspace_create_exec_error=True)
                    .create(error_value)
                )
            lst_result.append(exec_error_id)
        if len(self) == 1:
            return lst_result[0]
        return self.env["devops.exec.error"].browse([a.id for a in lst_result])

    @api.multi
    @contextmanager
    def devops_create_exec_bundle(
        self,
        description,
        ignore_parent=False,
        succeed_msg=False,
        devops_cg_new_project=None,
        ctx=None,
    ):
        self.ensure_one()
        value_bundle = {
            "devops_workspace": self.id,
            "description": description,
        }
        if not ignore_parent:
            devops_exec_bundle_parent = self.env.context.get(
                "devops_exec_bundle"
            )
            if devops_exec_bundle_parent:
                value_bundle["parent_id"] = devops_exec_bundle_parent
        devops_exec_bundle_id = self.env["devops.exec.bundle"].create(
            value_bundle
        )
        rec = self.with_context(devops_exec_bundle=devops_exec_bundle_id.id)
        if ctx:
            rec = rec.with_context(**ctx)
        if devops_cg_new_project:
            rec = rec.with_context(devops_cg_new_project=devops_cg_new_project)
        try:
            yield rec
        except exceptions.Warning as e:
            raise e
        except Exception as e:
            _logger.exception(
                f"'{description}' it.exec.bundle id"
                f" '{devops_exec_bundle_id.id}' failed"
            )
            escaped_tb = tools.html_escape(traceback.format_exc()).replace(
                "&quot;", '"'
            )
            parent_root_id = devops_exec_bundle_id.get_parent_root()
            # detect is different to reduce recursion depth exceeded
            found_same_error_ids = self.env["devops.exec.error"].search(
                [
                    ("parent_root_exec_bundle_id", "=", parent_root_id.id),
                    ("description", "=", description),
                    ("escaped_tb", "=", escaped_tb),
                ]
            )
            if not found_same_error_ids:
                devops_exec = devops_exec_bundle_id.devops_exec_ids.exists()
                if devops_exec:
                    devops_exec = devops_exec[0]
                rec.create_exec_error(
                    description,
                    escaped_tb,
                    rec,
                    devops_exec_bundle_id,
                    devops_exec,
                    parent_root_id,
                    "internal",
                )
            if rec.show_error_chatter:
                partner_ids, channel_ids = rec.get_partner_channel()
                self.message_post(  # pylint: disable=translation-required
                    body="<p>%s</p><pre>%s</pre>"
                    % (
                        _("devops.workspace '%s' failed.") % description,
                        escaped_tb,
                    ),
                    subtype=self.env.ref(
                        "erplibre_devops.mail_message_subtype_failure"
                    ),
                    author_id=self.env.ref("base.user_root").partner_id.id,
                    partner_ids=partner_ids,
                    channel_ids=channel_ids,
                )
        else:
            if succeed_msg:
                _logger.info(
                    "devops_workspace succeeded '%s': %s",
                    self.name,
                    description,
                )

                partner_ids = [
                    (
                        6,
                        0,
                        [
                            a.partner_id.id
                            for a in rec.message_follower_ids
                            if a.partner_id
                        ],
                    )
                ]
                channel_ids = [
                    (
                        6,
                        0,
                        [
                            a.channel_id.id
                            for a in rec.message_follower_ids
                            if a.channel_id
                        ],
                    )
                ]

                self.message_post(
                    body=_("devops_workspace succeeded '%s': %s")
                    % (self.name, description),
                    subtype=self.env.ref(
                        "erplibre_devops.mail_message_subtype_success"
                    ),
                    author_id=self.env.ref("base.user_root").partner_id.id,
                    partner_ids=partner_ids,
                    channel_ids=channel_ids,
                )
        finally:
            # Finish bundle
            devops_exec_bundle_id.exec_stop_date = fields.Datetime.now()
