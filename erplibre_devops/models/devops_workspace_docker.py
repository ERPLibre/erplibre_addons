# Copyright 2023 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import os
import time

import requests

from odoo import _, api, exceptions, fields, models, tools

_logger = logging.getLogger(__name__)


class DevopsWorkspaceDocker(models.Model):
    _name = "devops.workspace.docker"
    _description = "ERPLibre DevOps Workspace Docker"

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )

    workspace_id = fields.Many2one(
        comodel_name="devops.workspace",
        string="Workspace",
    )

    docker_is_running = fields.Boolean(
        readonly=True,
        default=True,
        help="When false, it's because not running docker.",
    )

    force_create_docker_compose = fields.Boolean(
        default=True,
        help="Recreate docker-compose from configuration.",
    )

    docker_compose_ps = fields.Text()

    docker_version = fields.Char(default="technolibre/erplibre:1.5.0_c0c6f23")

    docker_cmd_extra = fields.Char(
        help="Extra command to share to odoo executable"
    )

    docker_nb_proc = fields.Integer(
        help=(
            "Number of processor/thread, 0 if not behind a proxy, else 2 or"
            " more."
        )
    )

    docker_config_gen_cg = fields.Boolean(
        help="Will reduce config path to improve speed to code generator"
    )

    docker_config_cache = fields.Char(
        help="Fill when docker_config_gen_cg is True, will be erase after"
    )

    docker_is_behind_proxy = fields.Boolean(
        help="Longpolling need a proxy when workers > 1"
    )

    docker_initiate_succeed = fields.Boolean(help="Docker is ready to run")

    @api.multi
    @api.depends("workspace_id", "docker_is_running")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.workspace_id.name} - {rec.docker_is_running}"

    @api.multi
    def action_start_docker_compose(self):
        for rec in self:
            rec.docker_is_running = False

            file_docker_compose = os.path.join(
                rec.workspace_id.folder, "docker-compose.yml"
            )
            if rec.docker_cmd_extra:
                docker_cmd_extra = f" {rec.docker_cmd_extra}"
            else:
                docker_cmd_extra = ""
            if rec.docker_is_behind_proxy:
                docker_behind_proxy = f" --proxy-mode"
                workers = f"--workers {max(2, rec.docker_nb_proc)}"
            else:
                docker_behind_proxy = ""
                workers = f"--workers {rec.docker_nb_proc}"
            docker_compose_content = f"""version: "3.3"
services:
  ERPLibre:
    image: {rec.docker_version}
    ports:
      - {rec.workspace_id.port_http}:8069
      - {rec.workspace_id.port_longpolling}:8072
    environment:
      HOST: db
      PASSWORD: mysecretpassword
      USER: odoo
      POSTGRES_DB: postgres
      STOP_BEFORE_INIT: "False"
      DB_NAME: ""
      UPDATE_ALL_DB: "False"
    depends_on:
      - db
    # not behind a proxy
    #command: odoo --workers 0
    # behind a proxy
    #command: odoo --workers 2 --proxy-mode
    command: odoo {workers}{docker_behind_proxy}{docker_cmd_extra}
    volumes:
      # See the volume section at the end of the file
      - erplibre_data_dir:/home/odoo/.local/share/Odoo
      - erplibre_conf:/etc/odoo
{'      - ' + '''
- '''.join([f'./{path}:{rec.workspace_id.path_working_erplibre}/{path}' for path in rec.workspace_id.path_code_generator_to_generate.split(";")]) if rec.workspace_id.path_code_generator_to_generate else ''}
    restart: always

  db:
    image: postgis/postgis:12-3.1-alpine
    environment:
      POSTGRES_PASSWORD: mysecretpassword
      POSTGRES_USER: odoo
      POSTGRES_DB: postgres
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - erplibre-db-data:/var/lib/postgresql/data/pgdata
    restart: always

# We configure volume without specific destination to let docker manage it. To configure it through docker use (read related documentation before continuing) :
# - docker volume --help
# - docker-compose down --help
volumes:
  erplibre_data_dir:
  erplibre_conf:
  erplibre-db-data:"""
            if rec.force_create_docker_compose or not os.path.exists(
                file_docker_compose
            ):
                rec.workspace_id.execute(
                    cmd=(
                        f"echo '{docker_compose_content}' >"
                        f" {file_docker_compose}"
                    ),
                    engine="sh",
                )

            exec_id = rec.workspace_id.execute(
                cmd=f"cd {rec.workspace_id.folder};cat docker-compose.yml"
            )
            rec.docker_compose_ps = exec_id.log_all
            exec_id = rec.workspace_id.execute(
                cmd=f"cd {rec.workspace_id.folder};docker compose up -d"
            )
            result = exec_id.log_all

            if (
                "Cannot connect to the Docker daemon at"
                " unix:///var/run/docker.sock. Is the docker daemon"
                " running?"
                in result
            ):
                rec.docker_initiate_succeed = False

            rec.log_workspace = f"\n{result}"
            exec_id = rec.workspace_id.execute(
                cmd=f"cd {rec.workspace_id.folder};docker compose ps"
            )
            result = exec_id.log_all
            rec.log_workspace += f"\n{result}"
            rec.update_docker_compose_ps()

            exec_id = rec.workspace_id.execute(
                cmd="cat /etc/odoo/odoo.conf;", force_docker=True
            )
            result = exec_id.log_all
            has_change = False
            if "db_host" not in result:
                # TODO remove this information from executable of docker
                result += (
                    "db_host = db\ndb_port = 5432\ndb_user ="
                    " odoo\ndb_password = mysecretpassword\n"
                )
            if "admin_passwd" not in result:
                result += "admin_passwd = admin\n"
            # TODO remove repo OCA_connector-jira
            str_to_replace = f",{rec.workspace_id.path_working_erplibre}/addons/OCA_connector-jira"
            if str_to_replace in result:
                result = result.replace(str_to_replace, "")
                has_change = True

            if (
                rec.docker_config_gen_cg
                or not rec.docker_config_gen_cg
                and rec.docker_config_cache
            ):
                addons_path = None
                # TODO this is not good, need a script from manifest to rebuild this path
                if rec.docker_config_gen_cg:
                    if rec.workspace_id.path_code_generator_to_generate:
                        str_path_gen = ",".join(
                            [
                                os.path.join(
                                    rec.workspace_id.path_working_erplibre, a
                                )
                                for a in rec.workspace_id.path_code_generator_to_generate.strip().split(
                                    ";"
                                )
                            ]
                        )
                    else:
                        str_path_gen = ""
                    addons_path = (
                        "addons_path ="
                        f" {rec.workspace_id.path_working_erplibre}/odoo/addons,"
                        f"{str_path_gen},"
                        f"{rec.workspace_id.path_working_erplibre}/addons/OCA_web,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/ERPLibre_erplibre_addons,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/ERPLibre_erplibre_theme_addons,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/MathBenTech_development,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/MathBenTech_erplibre-family-management,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/MathBenTech_odoo-business-spending-management-quebec-canada,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/MathBenTech_scrummer,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/Numigi_odoo-partner-addons,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/Numigi_odoo-web-addons,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/OCA_contract,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/OCA_geospatial,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/OCA_helpdesk,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/OCA_server-auth,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/OCA_server-brand,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/OCA_server-tools,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/OCA_server-ux,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/OCA_social,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/OCA_website,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/TechnoLibre_odoo-code-generator,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/TechnoLibre_odoo-code-generator-template,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/ajepe_odoo-addons,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/muk-it_muk_base,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/muk-it_muk_misc,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/muk-it_muk_web,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/muk-it_muk_website,"
                        f"{rec.workspace_id.path_working_erplibre}/addons/odoo_design-themes"
                    )
                elif not rec.docker_config_gen_cg and rec.docker_config_cache:
                    addons_path = rec.docker_config_cache
                    rec.docker_config_cache = ""

                # TODO use configparser instead of string parsing
                if addons_path:
                    lst_result = result.split("\n")
                    for i, a_result in enumerate(lst_result):
                        if a_result.startswith("addons_path = "):
                            if (
                                rec.docker_config_gen_cg
                                and not rec.docker_config_cache
                            ):
                                rec.docker_config_cache = a_result
                            lst_result[i] = addons_path
                            break
                    result = "\n".join(lst_result)
                    has_change = True

            if has_change:
                # TODO rewrite conf file and reformat
                rec.workspace_id.execute(
                    cmd=f"echo -e '{result}' > /etc/odoo/odoo.conf",
                    force_docker=True,
                )
            # TODO support only one file, and remove /odoo.conf
            rec.workspace_id.execute(
                cmd=(
                    f"cd {rec.workspace_id.path_working_erplibre};cp"
                    " /etc/odoo/odoo.conf ./config.conf;"
                ),
                force_docker=True,
            )
            rec.action_docker_check_docker_ps()

    @api.multi
    def action_stop_docker_compose(self):
        for rec in self:
            rec.workspace_id.execute(
                cmd=f"cd {rec.workspace_id.folder};docker compose down"
            )
        self.update_docker_compose_ps()
        self.action_docker_check_docker_ps()

    def update_docker_compose_ps(self):
        for rec in self:
            exec_id = rec.workspace_id.execute(
                cmd=f"cd {rec.workspace_id.folder};docker compose ps"
            )
            result = exec_id.log_all
            rec.docker_compose_ps = f"\n{result}"

    @api.multi
    def action_docker_status(self):
        for rec in self:
            exec_id = rec.workspace_id.execute(
                cmd=f"cd {rec.workspace_id.folder};docker compose ps"
            )
            result = exec_id.log_all
            rec.docker_compose_ps = f"\n{result}"

    @api.multi
    def action_docker_check_docker_ps(self):
        for rec in self:
            exec_id = rec.workspace_id.execute(
                cmd=(
                    f"cd {rec.workspace_id.folder};docker compose ps --format"
                    " json"
                )
            )
            result = exec_id.log_all
            # rec.docker_compose_ps = f"\n{result}"
            rec.docker_is_running = bool(result)
            rec.workspace_id.is_running = rec.docker_is_running

    @api.multi
    def action_docker_logs(self):
        for rec in self:
            rec.workspace_id.execute(
                cmd="docker compose logs -f",
                force_open_terminal=True,
            )

    @api.multi
    def action_open_terminal_docker(self):
        for rec in self:
            workspace = os.path.basename(rec.workspace_id.folder)
            docker_name = f"{workspace}-ERPLibre-1"
            rec.workspace_id.execute(
                cmd=f"docker exec -u root -ti {docker_name} /bin/bash",
                force_open_terminal=True,
            )

    @api.multi
    def action_docker_install_dev_soft(self):
        for rec in self:
            rec.workspace_id.execute(
                cmd=f"apt update;apt install -y tig vim htop tree watch",
                force_docker=True,
            )

    @api.multi
    def action_os_user_permission_docker(self):
        for rec in self:
            rec.workspace_id.execute(
                cmd=(
                    "sudo groupadd docker;sudo usermod -aG docker"
                    f" {rec.workspace_id.system_id.ssh_user}"
                ),
                force_open_terminal=True,
            )
            rec.workspace_id.execute(
                cmd="sudo systemctl start docker.service",
                force_open_terminal=True,
            )
            # TODO check if all good
        self.docker_initiate_succeed = True

    @api.multi
    def action_analyse_docker_image(self):
        for rec in self:
            rec.workspace_id.execute(
                cmd=f"dive {rec.docker_version}", force_open_terminal=True
            )

    @api.multi
    def action_check(self):
        self.action_docker_status()
        self.action_docker_check_docker_ps()
