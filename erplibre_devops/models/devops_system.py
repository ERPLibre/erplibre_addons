import base64
import json
import logging
import os
import re
import subprocess
import time

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

    active = fields.Boolean(default=True)

    name_overwrite = fields.Char(
        string="Overwrite name",
        help="Overwrite existing name",
    )

    devops_workspace_ids = fields.One2many(
        comodel_name="devops.workspace",
        inverse_name="system_id",
        string="DevOps Workspace",
    )

    devops_deploy_vm_id = fields.Many2one(
        comodel_name="devops.deploy.vm",
        string="Associate VM",
    )

    is_vm = fields.Boolean(
        compute="_compute_is_vm",
        store=True,
    )

    docker_has_check = fields.Boolean(
        readonly=True,
        help=(
            "Need to be False when system restart. Compare last time check"
            " with uptime machine."
        ),
    )

    docker_is_installed = fields.Boolean(readonly=True)

    docker_daemon_is_running = fields.Boolean(readonly=True)

    docker_version = fields.Text(readonly=True)

    docker_version_engine = fields.Char(readonly=True)

    docker_compose_version = fields.Char(readonly=True)

    docker_system_info = fields.Text(readonly=True)

    docker_system_df = fields.Text(readonly=True)

    docker_stats = fields.Text(readonly=True)

    docker_stats_total_ram_use = fields.Char(readonly=True)

    ssh_host_name = fields.Char()

    # devops_deploy_vm_ids = fields.One2many(
    # comodel_name="devops.deploy.vm",
    # inverse_name="system_id",
    # string="VMs",
    # )
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

    system_status = fields.Boolean(
        compute="_compute_system_status",
        store=True,
        help="Show up or down for system, depend local or ssh.",
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

    docker_compose_ids = fields.One2many(
        comodel_name="devops.deploy.docker.compose",
        inverse_name="system_id",
        string="Docker compose",
    )

    docker_compose_count = fields.Integer(
        string="Docker compose count",
        compute="_compute_docker_compose_count",
        store=True,
    )

    docker_volume_ids = fields.One2many(
        comodel_name="devops.deploy.docker.volume",
        inverse_name="system_id",
        string="Docker volume",
    )

    docker_volume_count = fields.Integer(
        string="Docker volume count",
        compute="_compute_docker_volume_count",
        store=True,
    )

    docker_image_ids = fields.Many2many(
        comodel_name="devops.deploy.docker.image",
        relation="deploy_docker_image_system_ids_rel",
        string="Docker image",
    )

    docker_image_count = fields.Integer(
        string="Docker image count",
        compute="_compute_docker_image_count",
        store=True,
    )

    docker_network_ids = fields.One2many(
        comodel_name="devops.deploy.docker.network",
        inverse_name="system_id",
        string="Docker network",
    )

    docker_network_count = fields.Integer(
        string="Docker network count",
        compute="_compute_docker_network_count",
        store=True,
    )

    docker_container_ids = fields.One2many(
        comodel_name="devops.deploy.docker.container",
        inverse_name="system_id",
        string="Docker container",
    )

    docker_container_count = fields.Integer(
        string="Docker container count",
        compute="_compute_docker_container_count",
        store=True,
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
    @api.depends("ssh_connection_status", "method")
    def _compute_system_status(self):
        for rec in self:
            rec.system_status = False
            if rec.method == "local":
                rec.system_status = True
            elif rec.method == "ssh":
                rec.system_status = rec.ssh_connection_status

    @api.multi
    @api.depends("devops_deploy_vm_id")
    def _compute_is_vm(self):
        for rec in self:
            rec.is_vm = bool(rec.devops_deploy_vm_id)

    @api.multi
    @api.depends(
        "name_overwrite",
        "ssh_connection_status",
        "ssh_host",
        "ssh_port",
        "ssh_user",
        "method",
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

    @api.multi
    @api.depends("docker_compose_ids", "docker_compose_ids.active")
    def _compute_docker_compose_count(self):
        for rec in self:
            rec.docker_compose_count = self.env[
                "devops.deploy.docker.compose"
            ].search_count([("system_id", "=", rec.id)])

    @api.multi
    @api.depends("docker_volume_ids", "docker_volume_ids.active")
    def _compute_docker_volume_count(self):
        for rec in self:
            rec.docker_volume_count = self.env[
                "devops.deploy.docker.volume"
            ].search_count([("system_id", "=", rec.id)])

    @api.multi
    @api.depends("docker_image_ids", "docker_image_ids.active")
    def _compute_docker_image_count(self):
        for rec in self:
            rec.docker_image_count = self.env[
                "devops.deploy.docker.image"
            ].search_count([("system_ids", "in", [rec.id])])

    @api.multi
    @api.depends("docker_network_ids", "docker_network_ids.active")
    def _compute_docker_network_count(self):
        for rec in self:
            rec.docker_network_count = self.env[
                "devops.deploy.docker.network"
            ].search_count([("system_id", "=", rec.id)])

    @api.multi
    @api.depends("docker_container_ids", "docker_container_ids.active")
    def _compute_docker_container_count(self):
        for rec in self:
            rec.docker_container_count = self.env[
                "devops.deploy.docker.container"
            ].search_count([("system_id", "=", rec.id)])

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
        result = ""
        status = None
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
        for rec in self.filtered(lambda r: r.method == "ssh"):
            with rec.ssh_connection() as ssh_client:
                if not rec.ssh_connection_status:
                    _logger.error(
                        "Ignore SSH command, ssh connection is down."
                    )
                    continue
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
            with self.ssh_connection(force_exception=True):
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
    def ssh_connection(self, timeout=5, force_exception=False):
        """Return a new SSH connection with found parameters."""
        self.ensure_one()

        has_error = False
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
        try:
            ssh_client.connect(
                hostname=self.ssh_host,
                port=self.ssh_port,
                username=None if not self.ssh_user else self.ssh_user,
                password=None if not self.ssh_password else self.ssh_password,
                timeout=timeout,
            )
        except paramiko.ssh_exception.NoValidConnectionsError as e:
            if force_exception:
                raise e
            has_error = True
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
        if not has_error:
            self.ssh_connection_status = True

        return ssh_client

    @api.multi
    def action_check_docker(self):
        for rec in self:
            # 1. Check if is installed
            cmd = "which docker"
            out, status = rec.execute_with_result(
                cmd, None, return_status=True
            )
            rec.docker_is_installed = status == 0
            if rec.docker_is_installed:
                # 2. Get version
                # Docker version
                cmd = "docker version"
                out, status = rec.execute_with_result(
                    cmd, None, return_status=True
                )
                if status == 0:
                    rec.docker_version = out
                cmd = "docker version -f json"
                out, status = rec.execute_with_result(
                    cmd, None, return_status=True
                )
                if status == 0:
                    try:
                        dct_docker_version = json.loads(out)
                        docker_client_version = dct_docker_version.get(
                            "Client"
                        ).get("Version")
                        docker_server_version = dct_docker_version.get(
                            "Server"
                        ).get("Version")
                        if docker_client_version != docker_server_version:
                            _logger.warning(
                                f"System {rec.name} has docker client version"
                                f" {docker_client_version} and docker serveur"
                                f" version {docker_server_version}"
                            )
                        rec.docker_version_engine = docker_server_version
                    except Exception as e:
                        # TODO need sudo to run docker or wrong version
                        #  system cannot support sudo command for now
                        _logger.warning(e)
                cmd = "docker compose version"
                out, status = rec.execute_with_result(
                    cmd, None, return_status=True
                )
                if status == 0:
                    rec.docker_compose_version = out
                # Docker system info
                # cmd = "docker system info"
                # out, status = rec.execute_with_result(
                #     cmd, None, return_status=True
                # )
                # 3. Check status, else force start it
                cmd = "docker info"
                out, status = rec.execute_with_result(
                    cmd, None, return_status=True
                )
                if status != 0:
                    # Suppose got error :
                    # Cannot connect to the Docker daemon at unix:///var/run/docker.sock.
                    # Is the docker daemon running?
                    out = rec.execute_terminal_gui(
                        cmd="sudo systemctl start docker"
                    )
                    time.sleep(5)
                    cmd = "docker info"
                    out, status = rec.execute_with_result(
                        cmd, None, return_status=True
                    )
                rec.docker_daemon_is_running = status == 0
                rec.docker_system_info = out
                # 4. Metric system
                # TODO maybe move this into action_check_docker_advance
                cmd = "docker system df"
                out, status = rec.execute_with_result(
                    cmd, None, return_status=True
                )
                if status == 0:
                    rec.docker_system_df = out
                cmd = "docker stats -a --no-stream"
                out, status = rec.execute_with_result(
                    cmd, None, return_status=True
                )
                if status == 0:
                    rec.docker_stats = out
                cmd = "docker stats -a --no-stream --format json"
                out, status = rec.execute_with_result(
                    cmd, None, return_status=True
                )
                if status == 0:
                    total_memory_usage = 0.0
                    for stat_line in out.splitlines():
                        dct_docker_stat = json.loads(stat_line)
                        mem_usage = (
                            dct_docker_stat.get("MemUsage")
                            .split("/")[0]
                            .strip()
                        )
                        if mem_usage == "0B":
                            # Ignore
                            pass
                        elif mem_usage.endswith("KiB"):
                            total_memory_usage += float(mem_usage[:-3]) * 1024
                        elif mem_usage.endswith("MiB"):
                            total_memory_usage += (
                                float(mem_usage[:-3]) * 1024 * 1024
                            )
                        elif mem_usage.endswith("GiB"):
                            total_memory_usage += (
                                float(mem_usage[:-3]) * 1024 * 1024 * 1024
                            )
                        elif mem_usage.endswith("B"):
                            total_memory_usage += float(mem_usage[:-1])
                        else:
                            _logger.error(
                                "Cannot support docker check MemUsage :"
                                f" {mem_usage}"
                            )
                    unit_count_kilo = 0
                    lst_unit_str = [
                        "B",
                        "KiB",
                        "MiB",
                        "GiB",
                        "TiB",
                        "PiB",
                        "EiB",
                    ]
                    while total_memory_usage > 1024:
                        unit_count_kilo += 1
                        total_memory_usage = total_memory_usage / 1024.0
                    unit_str = lst_unit_str[unit_count_kilo]
                    rec.docker_stats_total_ram_use = (
                        f"{total_memory_usage:.3f}{unit_str}"
                    )
            rec.docker_has_check = True

    @api.multi
    def action_search_docker(self):
        for rec in self:
            # Debug, force clean all before
            debug = True
            if debug:
                self.env["devops.deploy.docker.compose"].search(
                    [
                        ("system_id", "=", rec.id),
                    ],
                    limit=1,
                ).write({"active": False})
                self.env["devops.deploy.docker.volume"].search(
                    [
                        ("system_id", "=", rec.id),
                    ],
                    limit=1,
                ).write({"active": False})
                self.env["devops.deploy.docker.image"].search(
                    [
                        ("system_ids", "in", rec.ids),
                    ],
                    limit=1,
                ).write({"active": False})
                self.env["devops.deploy.docker.network"].search(
                    [
                        ("system_id", "=", rec.id),
                    ],
                    limit=1,
                ).write({"active": False})
                self.env["devops.deploy.docker.container"].search(
                    [
                        ("system_id", "=", rec.id),
                    ],
                    limit=1,
                ).write({"active": False})
            dct_compose_name_id = {}
            dct_volume_name_id = {}
            dct_image_name_id = {}
            dct_network_name_id = {}
            dct_container_name_id = {}

            # 1. Compose
            cmd = "docker compose ls --format json"
            out, status = rec.execute_with_result(
                cmd, None, return_status=True
            )
            if status != 0:
                continue
            lst_compose = json.loads(out)
            for dct_compose in lst_compose:
                compose_name = dct_compose.get("Name")
                deploy_docker_compose_id = self.env[
                    "devops.deploy.docker.compose"
                ].search(
                    [
                        ("name", "=", compose_name),
                        ("system_id", "=", rec.id),
                    ],
                    limit=1,
                )
                if not deploy_docker_compose_id:
                    is_running = dct_compose.get("Status") == "running(2)"
                    compose_value = {
                        "name": compose_name,
                        "system_id": rec.id,
                        "config_file_path": dct_compose.get("ConfigFiles"),
                        "is_running": is_running,
                    }
                    # # Show compose config
                    # cmd = f"docker compose config {id_image}"
                    # out, status = rec.execute_with_result(
                    #     cmd, None, return_status=True
                    # )
                    # if status == 0:
                    #     deploy_image_value["history_full"] = out
                    deploy_docker_compose_id = self.env[
                        "devops.deploy.docker.compose"
                    ].create(compose_value)
                dct_compose_name_id[compose_name] = deploy_docker_compose_id

            # 2. Volume
            cmd = "docker volume ls -q"
            out, status = rec.execute_with_result(
                cmd, None, return_status=True
            )
            if status != 0:
                continue
            lst_volume = out.splitlines()
            if lst_volume:
                str_volumes = " ".join(lst_volume)
                cmd = f"docker volume inspect {str_volumes}"
                out, status = rec.execute_with_result(
                    cmd, None, return_status=True
                )
                if status == 0:
                    lst_volume_inspect = json.loads(out)
                    for volume_inspect in lst_volume_inspect:
                        volume_name = volume_inspect.get("Name")
                        deploy_docker_volume_id = self.env[
                            "devops.deploy.docker.volume"
                        ].search(
                            [
                                ("name", "=", volume_name),
                                ("system_id", "=", rec.id),
                            ],
                            limit=1,
                        )
                        if not deploy_docker_volume_id:
                            deploy_volume_value = {
                                "name": volume_name,
                                "system_id": rec.id,
                                "mountpoint": volume_inspect.get("Mountpoint"),
                                "created_at_date": volume_inspect.get(
                                    "CreatedAt"
                                ),
                                "driver": volume_inspect.get("Driver"),
                            }
                            # Associate docker compose with docker volume
                            dct_labels = volume_inspect.get("Labels")
                            if dct_labels:
                                docker_compose_project_name = dct_labels.get(
                                    "com.docker.compose.project"
                                )
                                if (
                                    docker_compose_project_name
                                    and docker_compose_project_name
                                    in dct_compose_name_id.keys()
                                ):
                                    compose_id = dct_compose_name_id.get(
                                        docker_compose_project_name
                                    )
                                    deploy_volume_value[
                                        "compose_id"
                                    ] = compose_id.id
                            deploy_docker_volume_id = self.env[
                                "devops.deploy.docker.volume"
                            ].create(deploy_volume_value)
                        dct_volume_name_id[
                            volume_name
                        ] = deploy_docker_volume_id
            # 3. Image
            # cmd = "docker container ls --no-trunc -a --format json"
            cmd = "docker image ls -a --no-trunc --format json"
            out, status = rec.execute_with_result(
                cmd, None, return_status=True
            )
            # TODO cmd 1 : docker image history hash
            # cmd 2 : docker image inspect hash
            if status != 0:
                continue
            lst_json_image = out.splitlines()
            for json_image in lst_json_image:
                dct_image = json.loads(json_image)
                id_image = dct_image.get("ID")
                str_ignore_id_image = "sha256:"
                id_short_image = (
                    id_image[
                        len(str_ignore_id_image) : 12
                        + len(str_ignore_id_image)
                    ]
                    if id_image.startswith(str_ignore_id_image)
                    else id_image[:12]
                )
                deploy_docker_image_id = self.env[
                    "devops.deploy.docker.image"
                ].search(
                    [
                        ("id_image", "=", id_image),
                    ],
                    limit=1,
                )
                if not deploy_docker_image_id:
                    deploy_image_value = {
                        "system_ids": [(6, 0, rec.ids)],
                        "id_image": id_image,
                        "id_short_image": id_short_image,
                        "tag": dct_image.get("Tag"),
                        "size_human": dct_image.get("Size"),
                        "size_virtual_human": dct_image.get("VirtualSize"),
                        "created_at": dct_image.get("CreatedAt"),
                        "created_since": dct_image.get("CreatedSince"),
                        "repository": dct_image.get("Repository"),
                    }
                    cmd = f"docker image history {id_image}"
                    out, status = rec.execute_with_result(
                        cmd, None, return_status=True
                    )
                    if status == 0:
                        deploy_image_value["history_full"] = out
                    cmd = f"docker image inspect {id_image}"
                    out, status = rec.execute_with_result(
                        cmd, None, return_status=True
                    )
                    if status == 0:
                        deploy_image_value["inspect_full"] = out
                    deploy_docker_image_id = self.env[
                        "devops.deploy.docker.image"
                    ].create(deploy_image_value)
                elif (
                    not deploy_docker_image_id.system_ids
                    or rec.id not in deploy_docker_image_id.system_ids.ids
                ):
                    # Update image associate to this system
                    deploy_docker_image_id.system_ids = [(4, rec.id)]
                dct_image_name_id[
                    deploy_docker_image_id.name
                ] = deploy_docker_image_id
            # 4. Network
            cmd = "docker network ls --no-trunc --format json"
            out, status = rec.execute_with_result(
                cmd, None, return_status=True
            )
            if status != 0:
                continue
            lst_json_network = out.splitlines()
            for json_network in lst_json_network:
                dct_network = json.loads(json_network)
                id_network = dct_network.get("ID")
                id_short_network = id_network[:12]
                deploy_docker_network_id = self.env[
                    "devops.deploy.docker.network"
                ].search(
                    [
                        ("id_network", "=", id_network),
                        ("system_id", "=", rec.id),
                    ],
                    limit=1,
                )
                if not deploy_docker_network_id:
                    network_value = {
                        "name": dct_network.get("Name"),
                        "system_id": rec.id,
                        "created_at": dct_network.get("CreatedAt"),
                        "driver": dct_network.get("Driver"),
                        "id_network": id_network,
                        "id_short_network": id_short_network,
                        "ipv6": dct_network.get("IPv6"),
                        "internal": dct_network.get("Internal"),
                        "labels": dct_network.get("Labels"),
                        "scope": dct_network.get("Scope"),
                    }
                    cmd = f"docker network inspect {id_network} -v"
                    out, status = rec.execute_with_result(
                        cmd, None, return_status=True
                    )
                    if status == 0:
                        network_value["inspect_full"] = out
                    deploy_docker_network_id = self.env[
                        "devops.deploy.docker.network"
                    ].create(network_value)
                    dct_network_name_id[
                        deploy_docker_network_id.name
                    ] = deploy_docker_network_id
            # 5. Container
            cmd = "docker container ls --no-trunc -a --format json"
            out, status = rec.execute_with_result(
                cmd, None, return_status=True
            )
            if status != 0:
                continue
            lst_json_container = out.splitlines()
            for json_container in lst_json_container:
                dct_container = json.loads(json_container)
                id_container = dct_container.get("ID")
                deploy_docker_container_id = self.env[
                    "devops.deploy.docker.container"
                ].search(
                    [
                        ("id_container", "=", id_container),
                    ],
                    limit=1,
                )
                if not deploy_docker_container_id:
                    container_value = {
                        "name": dct_container.get("Names"),
                        "system_id": rec.id,
                        "command": dct_container.get("Command"),
                        "create_at": dct_container.get("CreatedAt"),
                        "id_container": id_container,
                        "id_short_container": id_container[:12],
                        "mounts_full": dct_container.get("Mounts"),
                        "ports_full": dct_container.get("Ports"),
                        "running_for": dct_container.get("RunningFor"),
                        "size_human": dct_container.get("Size"),
                        "state_container": dct_container.get("State"),
                        "status_container": dct_container.get("Status"),
                    }
                    # TODO interesting information into dct_labels for docker.compose, like his services to get with config
                    image_key = dct_container.get("Image")
                    image_id = dct_image_name_id.get(image_key, False)
                    if image_id:
                        container_value["image_id"] = image_id.id
                    # TODO networks, you means, multiple network?
                    network_key = dct_container.get("Networks")
                    network_id = dct_network_name_id.get(network_key, False)
                    if network_id:
                        container_value["network_id"] = network_id.id
                    volume_key = dct_container.get("Mounts")
                    lst_mount = volume_key.split(",")
                    if lst_mount:
                        lst_match_key = list(
                            set(dct_volume_name_id).intersection(
                                set(lst_mount)
                            )
                        )
                        lst_id_volume_ids = [
                            dct_volume_name_id.get(a).id for a in lst_match_key
                        ]
                        if lst_id_volume_ids:
                            container_value["volume_ids"] = [
                                (6, 0, lst_id_volume_ids)
                            ]
                    # TODO associate mount_id with workspace_id and with addons_path
                    # TODO create addons_path like erplibre_config_path_home_ids from system, but for workspace
                    # TODO long with diff/logs
                    cmd = f"docker container inspect {id_container}"
                    out, status = rec.execute_with_result(
                        cmd, None, return_status=True
                    )
                    if status == 0:
                        container_value["inspect_full"] = out
                        dct_container_inspect = json.loads(out)[0]
                        compose_key = (
                            dct_container_inspect.get("Config")
                            .get("Labels")
                            .get("com.docker.compose.project", False)
                        )
                        if compose_key:
                            compose_id = dct_compose_name_id.get(
                                compose_key, False
                            )
                            if compose_id:
                                container_value["compose_id"] = compose_id.id
                    # str_labels = dct_container.get("Labels")
                    # dct_labels = dict(
                    #     [a.split("=", 1) for a in str_labels.split(",")]
                    # )
                    # compose_key = dct_labels.get("com.docker.compose.project")
                    # compose_id = dct_compose_name_id.get(compose_key, False)
                    # if compose_id:
                    #     container_value["compose_id"] = compose_id.id

                    deploy_docker_container_id = self.env[
                        "devops.deploy.docker.container"
                    ].create(container_value)

                dct_container_name_id[
                    id_container
                ] = deploy_docker_container_id
            for compose_id in dct_compose_name_id.values():
                workspace_ids = rec.devops_workspace_ids.filtered(
                    lambda r: r.folder == compose_id.folder_root
                )
                if not workspace_ids:
                    continue
                for ws_id in workspace_ids:
                    mode_docker_id = self.env.ref(
                        "erplibre_devops.erplibre_mode_source_docker"
                    )
                    if (
                        ws_id.deploy_docker_compose_id
                        and ws_id.erplibre_mode.mode_source != mode_docker_id
                    ):
                        continue
                    ws_id.deploy_docker_compose_id = compose_id.id
                    if not ws_id.is_installed:
                        # Can install it!
                        ws_id.action_install_workspace()

    @api.multi
    def action_install_docker(self):
        for rec in self:
            if not rec.docker_has_check:
                continue
            # Install it
            cmd_dev = (
                "curl -fsSL https://get.docker.com | sudo sh && sudo apt-get"
                " install -y uidmap && dockerd-rootless-setuptool.sh install"
            )
            cmd_prod = "curl -fsSL https://get.docker.com | sudo sh"
            cmd = cmd_dev
            rec.execute_terminal_gui(cmd=cmd)

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
                    "sudo apt update;sudo apt install -y git make curl"
                    " parallel plocate vim tree watch git-cola htop tig"
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
    def action_show_security_ssh_keygen(self):
        for rec in self:
            cmd = (
                'for key in ~/.ssh/id_*; do ssh-keygen -l -f "${key}"; done |'
                " uniq"
            )
            log = rec.execute_with_result(cmd, None).strip()
            msg = (
                "Security good : 1. No DSA, 2. RSA key size >= 3072, 3. Better"
                " Ed25519\n"
                + log
            )
            raise exceptions.Warning(msg)

    @api.multi
    def action_search_vm(self):
        for rec in self:
            dct_vm_identifiant = {}
            cmd = "vboxmanage list runningvms"
            out, status = rec.execute_with_result(
                cmd, None, return_status=True
            )
            lst_identifiant_running = []
            out = out.strip()
            if not status and out:
                for vm_config_short in out.split("\n"):
                    # Expect "name" {key}
                    pattern = r'"([^"]*)" \{([^}]*)\}'
                    matches = re.match(pattern, vm_config_short)
                    if not matches:
                        _logger.warning(
                            'Cannot find regex to find "name" {key} to'
                            " extract vboxmanage list runningvms :"
                            f" '{vm_config_short}'."
                        )
                        continue
                    name = matches.group(1)
                    key = matches.group(2)
                    lst_identifiant_running.append(key)

            cmd = "vboxmanage list vms"
            out, status = rec.execute_with_result(
                cmd, None, return_status=True
            )
            out = out.strip()
            if not status and out:
                for vm_config_short in out.split("\n"):
                    # Expect "name" {key}
                    pattern = r'"([^"]*)" \{([^}]*)\}'
                    matches = re.match(pattern, vm_config_short)
                    if not matches:
                        _logger.warning(
                            'Cannot find regex to find "name" {key} to'
                            " extract vboxmanage list vms :"
                            f" '{vm_config_short}'."
                        )
                        continue
                    name = matches.group(1)
                    key = matches.group(2)
                    provider = "VirtualBox"
                    # Search if exist before create
                    vm_id = self.env["devops.deploy.vm"].search(
                        [
                            ("identifiant", "=", key),
                            ("system_id", "=", rec.id),
                            ("provider", "=", provider),
                        ],
                        limit=1,
                    )
                    if not vm_id:
                        value = {
                            "name": name,
                            "identifiant": key,
                            "provider": provider,
                            "system_id": rec.id,
                        }
                        vm_id = self.env["devops.deploy.vm"].create(value)
                    if vm_id and key in lst_identifiant_running:
                        # TODO need to be somewhere else to check status
                        value = {
                            "vm_id": vm_id.id,
                            "is_running": True,
                        }
                        vm_exec_id = self.env["devops.deploy.vm.exec"].create(
                            value
                        )
                        vm_id.vm_exec_last_id = vm_exec_id.id

                    cmd = f"VBoxManage showvminfo {vm_id.identifiant}"
                    out, status = rec.execute_with_result(
                        cmd, None, return_status=True
                    )
                    out = out.strip()
                    if not status and out:
                        # Extract Description
                        vm_id.vm_info = out
                        key_desc = "Description:"
                        key_guest = "Guest:"
                        idx_desc = out.find(key_desc)
                        idx_guest = out.find(key_guest)
                        if idx_desc >= 0 and idx_guest >= 0:
                            desc_str = out[
                                idx_desc + len(key_desc) : idx_guest
                            ].strip()
                            if desc_str:
                                vm_id.vm_description_json = desc_str
                                # Search datastructure {} from Description
                                key_first = "{"
                                key_last = "}"
                                idx_first = desc_str.find(key_first)
                                idx_last = desc_str.find(key_last)
                                if idx_first >= 0 and idx_last >= 0:
                                    datastructure = desc_str[
                                        idx_first : idx_last + len(key_last)
                                    ].strip()
                                    if datastructure:
                                        obj_vm_desc = json.loads(datastructure)
                                        ssh_host = obj_vm_desc.get("ssh_host")
                                        if ssh_host:
                                            vm_id.vm_ssh_host = ssh_host
                                            # Find an associate system
                                            system_vm_id = self.env[
                                                "devops.system"
                                            ].search(
                                                [
                                                    (
                                                        "ssh_host_name",
                                                        "=",
                                                        ssh_host,
                                                    )
                                                ],
                                                limit=1,
                                            )
                                            if system_vm_id:
                                                system_vm_id.devops_deploy_vm_id = (
                                                    vm_id.id
                                                )
                        # vm_id.vm_description_json = out
                    dct_vm_identifiant[key] = vm_id

            # cmd = "vboxmanage list bridgedifs"
            # out, status = rec.execute_with_result(
            #     cmd, None, return_status=True
            # )
            # out = out.strip()
            # if not status and out:
            #     dct_vm_net_info = {}
            #     for info_group in out.split("\n\n"):
            #         dct_net_info = {}
            #         for vm_net in info_group.split("\n"):
            #             key, value = vm_net.split(":", 1)
            #             dct_net_info[key.strip()] = value.strip()
            #         vm_uid = dct_net_info.get("GUID")
            #         if vm_uid:
            #             dct_vm_net_info[vm_uid] = dct_net_info
            #     for guid, dct_net in dct_vm_net_info.items():
            #         print("ok")

    @api.multi
    def action_search_all(self):
        self.action_search_workspace()
        # TODO maybe check system_status before continue
        if not all([a.system_status for a in self]):
            return
        self.action_refresh_db_image()
        self.get_local_system_id_from_ssh_config()
        self.action_search_vm()
        self.action_check_docker()
        self.action_search_docker()

    @api.multi
    def action_vm_power(self):
        for rec in self:
            if rec.devops_deploy_vm_id:
                if rec.devops_deploy_vm_id.has_vm_exec_running:
                    rec.devops_deploy_vm_id.action_stop_vm()
                else:
                    rec.devops_deploy_vm_id.action_start_vm()
            else:
                _logger.warning("Not action VM power.")

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
                hostname = dev_config.get("hostname")
                system_id = self.env["devops.system"].search(
                    [("ssh_host", "=", hostname)], limit=1
                )
                if not system_id:
                    name = f"{host}[{hostname}]"
                    value = {
                        "method": "ssh",
                        "name_overwrite": name,
                        "ssh_host": hostname,
                        "ssh_host_name": host,
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
