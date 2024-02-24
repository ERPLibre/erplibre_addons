import base64
import json
import logging
import os
import re
import subprocess

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)
try:
    import paramiko
except ImportError:  # pragma: no cover
    _logger.debug("Cannot import paramiko")

BASE_VERSION_SOFTWARE_NAME = "odoo"


class DevopsSystem(models.Model):
    _name = "devops.system"
    _description = "devops_system"

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )

    name_overwrite = fields.Char(
        string="Overwrite name",
        help="Overwrite existing name",
    )

    devops_workspace_ids = fields.One2many(
        comodel_name="devops.workspace",
        inverse_name="system_id",
        string="DevOps Workspace",
    )

    parent_system_id = fields.Many2one(
        comodel_name="devops.system",
        string="Parent system",
    )

    erplibre_config_path_home_ids = fields.Many2many(
        comodel_name="erplibre.config.path.home",
        string="List path home",
        default=lambda self: [
            (
                6,
                0,
                [
                    self.env.ref(
                        "erplibre_devops.erplibre_config_path_home_tmp"
                    ).id
                ],
            )
        ],
    )

    sub_system_ids = fields.One2many(
        comodel_name="devops.system",
        inverse_name="parent_system_id",
        string="Sub system",
    )

    method = fields.Selection(
        selection=[("local", "Local disk"), ("ssh", "SSH remote server")],
        required=True,
        default="local",
        help="Choose the communication method.",
    )

    ssh_connection_status = fields.Boolean(
        readonly=True,
        help="The state of the connexion.",
    )

    use_search_cmd = fields.Selection(
        # TODO support mdfind for OSX
        selection=[
            (
                "locate",
                "locate",
            ),
            ("find", "find"),
        ],
        default=lambda self: self.env["ir.config_parameter"]
        .sudo()
        .get_param("erplibre_devops.default_search_engine", False),
        help="find or locate, need sudo updatedb.",
    )

    terminal = fields.Selection(
        selection=[
            ("gnome-terminal", "Gnome-terminal"),
            (
                "osascript",
                "Execute AppleScripts and other OSA language scripts",
            ),
            ("xterm", "Xterm"),
        ],
        default=lambda self: self.env["ir.config_parameter"]
        .sudo()
        .get_param("erplibre_devops.default_terminal", False),
        help=(
            "xterm block the process, not gnome-terminal. xterm not work on"
            " osx, use osascript instead."
        ),
    )

    ssh_host = fields.Char(
        string="SSH Server",
        help=(
            "The host name or IP address from your remote server. For example"
            " 192.168.0.1"
        ),
    )

    ssh_password = fields.Char(
        string="SSH Password",
        help=(
            "The password for the SSH connection. If you specify a private key"
            " file, then this is the password to decrypt it."
        ),
    )

    ssh_port = fields.Integer(
        string="SSH Port",
        default=22,
        help="The port on the FTP server that accepts SSH calls.",
    )

    ssh_use_sshpass = fields.Boolean(
        string="SSH use SSHPass",
        help="This tool automatic add password to ssh connexion.",
    )

    keep_terminal_open = fields.Boolean(
        default=True,
        help="This will keep terminal open when close command.",
    )

    debug_command = fields.Boolean(
        help="This will show in log the command when execute it."
    )

    iterator_port_generator = fields.Integer(
        default=10000,
        help="Iterate to generate next port",
    )

    ssh_private_key = fields.Char(
        string="Private key location",
        help=(
            "Path to the private key file. Only the Odoo user should have read"
            " permissions for that file."
        ),
    )

    ssh_public_host_key = fields.Char(
        string="Public host key",
        help=(
            "Verify SSH server's identity using its public rsa-key. The host"
            " key verification protects you from man-in-the-middle attacks."
            " Can be generated with command 'ssh-keyscan -p PORT -H HOST/IP'"
            " and the right key is immediately after the words 'ssh-rsa'."
        ),
    )

    ssh_user = fields.Char(
        string="Username in the SSH Server",
        help=(
            "The username where the SSH connection should be made with. This"
            " is the user on the external server."
        ),
    )

    path_home = fields.Char()

    @api.model_create_multi
    def create(self, vals_list):
        result = super().create(vals_list)
        for rec in result:
            try:
                rec.path_home = rec.execute_with_result(
                    "echo $HOME", None
                ).strip()
            except Exception as e:
                # TODO catch AuthenticationException exception
                if rec.method == "ssh" and rec.ssh_user:
                    rec.path_home = f"/home/{rec.ssh_user}"
                else:
                    rec.path_home = "/home/"
                    _logger.warning(
                        f"Wrong path_home for create devops.system {rec.id}"
                    )
            if rec.path_home:
                # Display this home to plan action
                path_home_id = self.env[
                    "erplibre.config.path.home"
                ].get_path_home_id(rec.path_home)
                rec.erplibre_config_path_home_ids = [(4, path_home_id.id)]
        return result

    @api.multi
    @api.depends(
        "name_overwrite",
        "ssh_connection_status",
        "ssh_host",
        "ssh_port",
        "ssh_user",
    )
    def _compute_name(self):
        for rec in self:
            rec.name = ""
            if rec.name_overwrite:
                rec.name = rec.name_overwrite
            elif rec.method == "local":
                rec.name = "Local"
            if rec.method == "ssh":
                state = "UP" if rec.ssh_connection_status else "DOWN"
                if not rec.name:
                    addr = rec.get_ssh_address()
                    rec.name = f"SSH {addr}"
                # Add state if name_overwrite
                rec.name += f" {state}"

    def get_ssh_address(self):
        # TODO is unique
        s_port = "" if self.ssh_port == 22 else f":{self.ssh_port}"
        s_user = "" if self.ssh_user is False else f"{self.ssh_user}@"
        addr = f"{s_user}{self.ssh_host}{s_port}"
        return addr

    @api.model
    def _execute_process(
        self,
        cmd,
        add_stdin_log=False,
        add_stderr_log=True,
        return_status=False,
    ):
        # subprocess.Popen("date", stdout=subprocess.PIPE, shell=True)
        # (output, err) = p.communicate()
        p = subprocess.Popen(
            cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        # p = subprocess.Popen(
        #     cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, executable="/bin/bash"
        # )
        # TODO check https://www.cyberciti.biz/faq/python-run-external-command-and-get-output/
        # TODO support async update output
        # import subprocess, sys
        # ## command to run - tcp only ##
        # cmd = "/usr/sbin/netstat -p tcp -f inet"
        #
        # ## run it ##
        # p = subprocess.Popen(cmd, shell=True, stderr=subprocess.PIPE)
        #
        # ## But do not wait till netstat finish, start displaying output immediately ##
        # while True:
        #     out = p.stderr.read(1)
        #     if out == '' and p.poll() != None:
        #         break
        #     if out != '':
        #         sys.stdout.write(out)
        #         sys.stdout.flush()
        (output, err) = p.communicate()
        p_status = p.wait()
        result = output.decode()
        if add_stderr_log:
            result += err.decode()
        if not return_status:
            return result
        return result, p_status

    def execute_with_result(
        self,
        cmd,
        folder,
        add_stdin_log=False,
        add_stderr_log=True,
        engine="bash",
        delimiter_bash="'",
        return_status=False,
    ):
        """
        engine can be bash, python or sh
        """
        if folder:
            cmd = f"cd {folder};{cmd}"
        if engine == "python":
            cmd = f"python -c {delimiter_bash}{cmd}{delimiter_bash}"
        elif engine == "bash":
            cmd = f"bash -c {delimiter_bash}{cmd}{delimiter_bash}"
        lst_result = []
        cmd = cmd.strip()
        if self.debug_command:
            print(cmd)
        for rec in self.filtered(lambda r: r.method == "local"):
            if not return_status:
                result = rec._execute_process(cmd)
                status = None
            else:
                result, status = rec._execute_process(cmd, return_status=True)
            if len(self) == 1:
                if not return_status:
                    return result
                else:
                    return result, status
            lst_result.append(result)
        for rec in self.filtered(lambda r: r.method == "ssh"):
            with rec.ssh_connection() as ssh_client:
                status = 0
                cmd += ";echo $?"
                stdin, stdout, stderr = ssh_client.exec_command(cmd)
                if add_stdin_log:
                    result = stdin.read().decode("utf-8")
                else:
                    result = ""
                stdout_log = stdout.read().decode("utf-8")
                # Extract echo $?
                count_endline_log = stdout_log.count("\n")
                if count_endline_log:
                    # Minimum 1, we know we have a command output by echo $?
                    # output is only the status
                    try:
                        status = int(stdout_log.strip())
                    except Exception:
                        _logger.warning(
                            f"System id {rec.id} communicate by SSH cannot"
                            f" retrieve status of command {cmd}"
                        )
                    finally:
                        if count_endline_log == 1:
                            stdout_log = ""
                        else:
                            c = stdout_log
                            stdout_log = c[: c.rfind("\n", 0, c.rfind("\n"))]
                result += stdout_log
                if add_stderr_log:
                    result += stderr.read().decode("utf-8")
                if len(self) == 1:
                    if not return_status:
                        return result
                    else:
                        return result, status
                lst_result.append(result)
        return lst_result

    def execute_terminal_gui(
        self, folder="", cmd="", docker=False, force_no_sshpass_no_arg=False
    ):
        # TODO support argument return_status
        # TODO if folder not exist, cannot CD. don't execute the command if wrong directory
        for rec in self.filtered(lambda r: r.method == "local"):
            str_keep_open = ""
            if rec.keep_terminal_open and rec.terminal == "gnome-terminal":
                str_keep_open = ";bash"
            wrap_cmd = f"{cmd}{str_keep_open}"
            if folder:
                if wrap_cmd.startswith(";"):
                    wrap_cmd = f'cd "{folder}"{wrap_cmd}'
                else:
                    wrap_cmd = f'cd "{folder}";{wrap_cmd}'
            if docker:
                workspace = os.path.basename(folder)
                docker_name = f"{workspace}-ERPLibre-1"
                wrap_cmd = f"docker exec -u root -ti {docker_name} /bin/bash"
                if cmd:
                    wrap_cmd += f' -c "{cmd}{str_keep_open}"'
            if wrap_cmd:
                cmd_output = ""
                if rec.terminal == "xterm":
                    cmd_output = f"xterm -e bash -c '{wrap_cmd}'"
                elif rec.terminal == "gnome-terminal":
                    cmd_output = (
                        f"gnome-terminal --window -- bash -c '{wrap_cmd}'"
                    )
                elif rec.terminal == "osascript":
                    wrap_cmd = wrap_cmd.replace('"', '\\"')
                    cmd_output = (
                        'osascript -e \'tell app "Terminal" to do script'
                        f' "{wrap_cmd}"\''
                    )
            else:
                cmd_output = ""
                if rec.terminal == "xterm":
                    cmd_output = f"xterm"
                elif rec.terminal == "gnome-terminal":
                    cmd_output = f"gnome-terminal --window -- bash"
                elif rec.terminal == "osascript":
                    cmd_output = (
                        f'osascript -e \'tell app "Terminal" to do script'
                        f' "ls"\''
                    )
            if cmd_output:
                rec._execute_process(cmd_output)
            if rec.debug_command:
                print(cmd_output)
        for rec in self.filtered(lambda r: r.method == "ssh"):
            str_keep_open = ""
            if rec.keep_terminal_open and rec.terminal == "gnome-terminal":
                str_keep_open = ";bash"
            sshpass = ""
            if rec.ssh_use_sshpass and not force_no_sshpass_no_arg:
                if not rec.ssh_password:
                    raise exceptions.Warning(
                        "Please, configure your password, because you enable"
                        " the feature 'ssh_use_sshpass'"
                    )
                # TODO validate it exist before use it
                sshpass = f"sshpass -p {rec.ssh_password} "
            if cmd:
                wrap_cmd = f"{cmd}{str_keep_open}"
            else:
                wrap_cmd = ""
            if docker:
                workspace = os.path.basename(folder)
                docker_name = f"{workspace}-ERPLibre-1"
                wrap_cmd = f"docker exec -u root -ti {docker_name} /bin/bash"
                if cmd:
                    wrap_cmd += f' -c \\"{cmd}{str_keep_open}\\"'
            else:
                # force replace " to \"
                wrap_cmd = wrap_cmd.replace('"', '\\"')
            argument_ssh = ""
            if rec.ssh_public_host_key:
                # TODO use public host key instead of ignore it
                argument_ssh = (
                    ' -o "UserKnownHostsFile=/dev/null" -o'
                    ' "StrictHostKeyChecking=no"'
                )
            if folder:
                if wrap_cmd.startswith(";"):
                    wrap_cmd = f'cd "{folder}"{wrap_cmd}'
                else:
                    wrap_cmd = f'cd "{folder}";{wrap_cmd}'
            if not wrap_cmd:
                wrap_cmd = "bash --login"
            # TODO support other terminal
            addr = rec.get_ssh_address()
            rec.name = f"SSH {addr}"
            cmd_output = (
                "gnome-terminal --window -- bash -c"
                f" '{sshpass}ssh{argument_ssh} -t"
                f' {addr} "{wrap_cmd}"'
                + str_keep_open
                + "'"
            )
            rec._execute_process(cmd_output)
            if rec.debug_command:
                print(cmd_output)

    def exec_docker(self, cmd, folder, return_status=False):
        workspace = os.path.basename(folder)
        docker_name = f"{workspace}-ERPLibre-1"
        # for "docker exec", command line need "-ti", but "popen" no need
        # TODO catch error, stderr with stdout
        cmd_output = f'docker exec -u root {docker_name} /bin/bash -c "{cmd}"'
        if self.debug_command:
            print(cmd_output)
        return self.execute_with_result(
            cmd_output, folder, return_status=return_status
        )

    @api.multi
    def action_ssh_test_connection(self):
        """Check if the SSH settings are correct."""
        try:
            # Just open and close the connection
            with self.ssh_connection():
                raise exceptions.Warning(_("Connection Test Succeeded!"))
        except (
            paramiko.AuthenticationException,
            paramiko.PasswordRequiredException,
            paramiko.BadAuthenticationType,
            paramiko.SSHException,
        ):
            _logger.info("Connection Test Failed!", exc_info=True)
            raise exceptions.Warning(_("Connection Test Failed!"))

    @api.model
    def ssh_connection(self):
        """Return a new SSH connection with found parameters."""
        self.ensure_one()

        self.ssh_connection_status = False

        ssh_client = paramiko.SSHClient()
        ssh_client.load_system_host_keys()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if self.ssh_public_host_key:
            # add to host keys
            key = paramiko.RSAKey(
                data=base64.b64decode(self.ssh_public_host_key)
            )
            ssh_client.get_host_keys().add(
                hostname=self.ssh_host, keytype="ssh-rsa", key=key
            )
        ssh_client.connect(
            hostname=self.ssh_host,
            port=self.ssh_port,
            username=None if not self.ssh_user else self.ssh_user,
            password=None if not self.ssh_password else self.ssh_password,
            timeout=5,
        )
        # params = {
        #     "host": self.ssh_host,
        #     "username": self.ssh_user,
        #     "port": self.ssh_port,
        # }
        #
        # # not empty sftp_public_key means that we should verify sftp server with it
        # cnopts = pysftp.CnOpts()
        # if self.sftp_public_host_key:
        #     key = paramiko.RSAKey(
        #         data=base64.b64decode(self.sftp_public_host_key)
        #     )
        #     cnopts.hostkeys.add(self.sftp_host, "ssh-rsa", key)
        # else:
        #     cnopts.hostkeys = None
        #
        # _logger.debug(
        #     "Trying to connect to sftp://%(username)s@%(host)s:%(port)d",
        #     extra=params,
        # )
        # if self.sftp_private_key:
        #     params["private_key"] = self.sftp_private_key
        #     if self.sftp_password:
        #         params["private_key_pass"] = self.sftp_password
        # else:
        #     params["password"] = self.sftp_password
        #
        # return pysftp.Connection(**params, cnopts=cnopts)

        # Because, offline will raise an exception
        self.ssh_connection_status = True

        return ssh_client

    @api.multi
    def action_install_dev_system(self):
        for rec in self:
            # Need this to install ERPLibre for dev
            # Minimal
            # git make curl which parallel
            # Dev
            # plocate tig vim tree watch git-cola htop make curl build-essential
            # zlib1g-dev libreadline-dev libbz2-dev libffi-dev libssl-dev libldap2-dev wget
            out = rec.execute_terminal_gui(
                cmd=(
                    "sudo apt update;sudo apt install -y git make curl which"
                    " parallel  plocate vim tree watch git-cola htop tig"
                    " build-essential zlib1g-dev libreadline-dev libbz2-dev"
                    " libffi-dev libssl-dev libldap2-dev wget"
                ),
            )
            # Debian
            # libxslt-dev libzip-dev libsasl2-dev gdebi-core
            # TODO create link python for pyenv if not exist
            # sudo ln -s /usr/bin/python3 /usr/bin/python
            # print(out)
            # uname -m
            # uname -r
            # uname -s
            # uname -v
            # TODO autodetect missing git config --global
            # git config --global user.email "@"
            # git config --global user.name ""
            # git testing colorized enable color yes y
            # Dev desktop
            # vanille-gnome-desktop

    @api.multi
    def action_search_workspace(self):
        for rec in self:
            # TODO use mdfind on OSX
            # TODO need to do sometime «sudo updatedb»
            if not rec.use_search_cmd:
                return
            if rec.use_search_cmd not in (
                "locate",
                "find",
            ):
                # TODO add information about this missing command, a TODO action
                # raise ValueError(
                #     f"Cannot execute command search '{rec.use_search_cmd}'"
                # )
                _logger.error(
                    f"Cannot execute command search '{rec.use_search_cmd}'"
                )
                return
            if rec.use_search_cmd == "locate":
                # Validate word ERPLibre is into default.xml
                cmd = (
                    "locate -b -r '^default\.xml$'|grep -v "
                    '".repo"|grep -v'
                    ' "/var/lib/docker"| xargs -I {} sh -c "grep -l "ERPLibre"'
                    ' "{}" 2>/dev/null || true"'
                )
            elif rec.use_search_cmd == "find":
                # Validate word ERPLibre is into default.xml
                cmd = (
                    'find "/" -name "default.xml" -type f -print 2>/dev/null |'
                    " grep -v .repo | grep -v /var/lib/docker | xargs -I {} sh"
                    ' -c "grep -l "ERPLibre" "{}" 2>/dev/null || true"'
                )
            out_default_git = rec.execute_with_result(cmd, None).strip()
            if out_default_git:
                lst_dir_git = [
                    os.path.dirname(a) for a in out_default_git.split("\n")
                ]
            else:
                lst_dir_git = []
            if rec.use_search_cmd == "locate":
                # Validate word ERPLibre is into default.xml
                cmd = (
                    'locate -b -r "^docker-compose\.yml$"|grep -v .repo|grep'
                    ' -v /var/lib/docker|xargs -I {} sh -c "grep -l "ERPLibre"'
                    ' "{}" 2>/dev/null || true"'
                )
            elif rec.use_search_cmd == "find":
                # Validate word ERPLibre is into default.xml
                cmd = (
                    'find "/" -name "docker-compose.yml" -type f -print'
                    " 2>/dev/null | grep -v .repo | grep -v /var/lib/docker |"
                    ' xargs -I {} sh -c "grep -l "ERPLibre" "{}" 2>/dev/null'
                    ' || true"'
                )
            out_docker_compose = rec.execute_with_result(cmd, None).strip()
            if out_docker_compose:
                lst_dir_docker = [
                    os.path.dirname(a) for a in out_docker_compose.split("\n")
                ]
                lst_dir_docker = list(
                    set(lst_dir_docker).difference(set(lst_dir_git))
                )
            else:
                lst_dir_docker = []
            # if out:
            #     # TODO search live docker
            #     # TODO search all docker-compose.yml and check if support it
            #     # docker ps -q | xargs -I {} docker inspect {} --format '{{ .Id }}: Montages={{ range .Mounts }}{{ .Source }}:{{ .Destination }} {{ end }}
            #     """
            #     "com.docker.compose.project": "#",
            #     "com.docker.compose.project.config_files": "###/docker-compose.yml",
            #     "com.docker.compose.project.working_dir": "###",
            #     "com.docker.compose.service": "ERPLibre",
            #     """
            #     # docker inspect <container_id_or_name> --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}'
            # TODO detect is_me if not exist
            lst_ws_value = []
            for dir_name in lst_dir_git:
                # Check if already exist
                rec_ws = rec.devops_workspace_ids.filtered(
                    lambda r: r.folder == dir_name
                )
                if rec_ws:
                    continue
                # TODO do more validation it's a ERPLibre workspace
                # odoo_dir = os.path.join(dirname, BASE_VERSION_SOFTWARE_NAME)
                # out_odoo = rec.execute_with_result(f"ls {odoo_dir}", None)
                # if out_odoo.startswith("ls: cannot access"):
                #     # This is not a ERPLibre project
                #     continue
                git_dir = os.path.join(dir_name, ".git")
                out_git, status = rec.execute_with_result(
                    f"ls {git_dir}", None, return_status=True
                )
                if status:
                    continue
                value = {
                    "folder": dir_name,
                    "system_id": rec.id,
                }
                mode_env_id = self.env.ref(
                    "erplibre_devops.erplibre_mode_env_dev"
                )
                mode_exec_id = self.env.ref(
                    "erplibre_devops.erplibre_mode_exec_terminal"
                )
                mode_source_id = self.env.ref(
                    "erplibre_devops.erplibre_mode_source_git"
                )

                # Has git, get some information
                mode_version_erplibre = rec.execute_with_result(
                    "git branch --show-current", dir_name
                ).strip()

                mode_version_base = rec.execute_with_result(
                    "git branch --show-current",
                    os.path.join(dir_name, BASE_VERSION_SOFTWARE_NAME),
                ).strip()
                if not mode_version_base:
                    # Search somewhere else, because it's a commit!
                    mode_version_base_raw = rec.execute_with_result(
                        'grep "<default remote=" default.xml',
                        dir_name,
                    )
                    regex = r'revision="([^"]+)"'
                    result = re.search(regex, mode_version_base_raw)
                    mode_version_base = result.group(1) if result else None
                    _logger.debug(
                        f"Find mode version base {mode_version_base}"
                    )

                erplibre_mode = self.env["erplibre.mode"].get_mode(
                    mode_env_id,
                    mode_exec_id,
                    mode_source_id,
                    mode_version_base,
                    mode_version_erplibre,
                )
                value["erplibre_mode"] = erplibre_mode.id
                lst_ws_value.append(value)
            for dir_name in lst_dir_docker:
                # Check if already exist
                rec_ws = rec.devops_workspace_ids.filtered(
                    lambda r: r.folder == dir_name
                )
                if rec_ws:
                    continue
                value = {
                    "folder": dir_name,
                    "system_id": rec.id,
                }
                mode_exec_id = self.env.ref(
                    "erplibre_devops.erplibre_mode_exec_docker"
                )
                mode_source_id = self.env.ref(
                    "erplibre_devops.erplibre_mode_source_docker"
                )
                # TODO cannot find odoo version from a simple docker-compose, need more information from docker image
                mode_version_base = "12.0"
                key_version = "/erplibre:"
                cmd = (
                    f'grep "image:" ./docker-compose.yml |grep "{key_version}"'
                )
                out_docker_compose_file = rec.execute_with_result(
                    cmd, dir_name
                ).strip()
                if not out_docker_compose_file:
                    _logger.warning(
                        "Cannot find erplibre version into docker compose"
                        f" {dir_name}"
                    )
                    continue
                image_version = out_docker_compose_file[
                    out_docker_compose_file.find("image: ") + len("image: ") :
                ]
                docker_version = out_docker_compose_file[
                    out_docker_compose_file.find(key_version)
                    + len(key_version) :
                ]
                if "_" in docker_version:
                    mode_env_id = self.env.ref(
                        "erplibre_devops.erplibre_mode_env_dev"
                    )
                else:
                    mode_env_id = self.env.ref(
                        "erplibre_devops.erplibre_mode_env_prod"
                    )

                erplibre_mode = self.env["erplibre.mode"].get_mode(
                    mode_env_id,
                    mode_exec_id,
                    mode_source_id,
                    mode_version_base,
                    docker_version,
                )
                value["erplibre_mode"] = erplibre_mode.id
                lst_ws_value.append(value)

            if lst_ws_value:
                ws_ids = self.env["devops.workspace"].create(lst_ws_value)
                ws_ids.action_install_workspace()

    @api.model
    def action_refresh_db_image(self):
        path_image_db = os.path.join(os.getcwd(), "image_db")
        for file_name in os.listdir(path_image_db):
            if file_name.endswith(".zip"):
                file_path = os.path.join(path_image_db, file_name)
                image_name = file_name[:-4]
                image_db_id = self.env["devops.db.image"].search(
                    [("name", "=", image_name)]
                )
                if not image_db_id:
                    self.env["devops.db.image"].create(
                        {"name": image_name, "path": file_path}
                    )

    @api.multi
    def get_local_system_id_from_ssh_config(self):
        new_sub_system_id = self.env["devops.system"]
        for rec in self:
            config_path = os.path.join(self.path_home, ".ssh/config")
            config_path_exist = rec.os_path_exists(config_path)
            if not config_path_exist:
                continue
            out = rec.execute_with_result(f"cat {config_path}", None)
            out = out.strip()
            # config.parse(file)
            # config = paramiko.SSHConfig()
            # config.parse(out.split("\n"))
            config = paramiko.SSHConfig.from_text(out)
            # dev_config = config.lookup("martin")
            lst_host = [a for a in config.get_hostnames() if a != "*"]
            for host in lst_host:
                dev_config = config.lookup(host)
                system_id = self.env["devops.system"].search(
                    [("name", "=", dev_config.get("hostname"))], limit=1
                )
                if not system_id:
                    name = f"{host}[{dev_config.get('hostname')}]"
                    value = {
                        "method": "ssh",
                        "name_overwrite": name,
                        "ssh_host": dev_config.get("hostname"),
                        # "ssh_password": dev_config.get("password"),
                    }
                    if "port" in dev_config.keys():
                        value["ssh_port"] = dev_config.get("port")
                    if "user" in dev_config.keys():
                        value["ssh_user"] = dev_config.get("user")

                    value["parent_system_id"] = rec.id
                    system_id = self.env["devops.system"].create(value)
                if system_id:
                    new_sub_system_id += system_id
        return new_sub_system_id

    @api.model
    def os_path_exists(self, path):
        cmd = f'[ -e "{path}" ] && echo "true" || echo "false"'
        result = self.execute_with_result(cmd, None)
        return result.strip() == "true"
