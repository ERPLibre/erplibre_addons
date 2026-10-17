# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os
import shutil
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo.addons.erplibre_developer.tests.common import DeveloperCase
from odoo.exceptions import UserError
from odoo.tests import tagged


class FakeWorkspace:
    """Stands for a « is_me » devops.workspace: records the PyCharm call
    instead of running it."""

    def __init__(self):
        self.ide_pycharm = MagicMock()
        self.bundles = []

    def __bool__(self):
        return True

    @contextmanager
    def devops_create_exec_bundle(self, description):
        self.bundles.append(description)
        yield self


class ShellWorkspace(FakeWorkspace):
    """Stands for a « is_me » devops.workspace that runs the real PyCharm
    command builder and the real terminal wrapper of erplibre_devops, as
    ``devops.workspace.execute`` chains them."""

    def __init__(self, env, folder):
        super().__init__()
        self.ide_pycharm = env["devops.ide.pycharm"]
        self.folder = folder
        self.system = env["devops.system"].new(
            {"method": "local", "terminal": "xterm", "keep_terminal_open": False}
        )

    def execute(self, cmd="", force_open_terminal=False, force_exit=False, **kw):
        if force_exit:
            cmd = f"{cmd};exit"
        if force_open_terminal:
            self.system.execute_terminal_gui(
                folder=self.folder, cmd=cmd, keep_open_terminal=True
            )


def _script(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)


@tagged("post_install", "-at_install")
class TestDevopsIde(DeveloperCase):
    def test_no_workspace_no_ide(self):
        self.env["devops.workspace"].search([("is_me", "=", True)]).write(
            {"is_me": False}
        )
        self.assertFalse(self.Dev._ide_available())
        info = self.Dev.get_view_info("res.partner", False, "form")
        self.assertFalse(info["ide_available"])
        with self.server_actions(), self.assertRaises(UserError):
            self.Dev.action_open_in_ide(__file__, 3)

    def test_open_in_pycharm(self):
        workspace = FakeWorkspace()
        Dev = type(self.Dev)
        with patch.object(Dev, "_ide_workspace", lambda self_: workspace):
            self.assertTrue(self.Dev._ide_available())
            # Opening the IDE is a server action: not offered without the flag.
            with self.server_actions(flag=False):
                info = self.Dev.get_view_info("res.partner", False, "form")
                self.assertFalse(info["ide_available"])
            with self.server_actions():
                info = self.Dev.get_view_info("res.partner", False, "form")
                self.assertTrue(info["ide_available"])
            with self.server_actions():
                self.assertTrue(self.Dev.action_open_in_ide(__file__, "12"))
                self.Dev.action_open_in_ide(__file__, 0)
            with self.server_actions(flag=False), self.assertRaises(UserError):
                self.Dev.action_open_in_ide(__file__, 1)
        self.assertEqual(workspace.bundles, ["Open in PyCharm", "Open in PyCharm"])
        first, second = workspace.ide_pycharm.action_pycharm_open.call_args_list
        self.assertEqual(first.args, (workspace,))
        self.assertTrue(first.kwargs["filename"].endswith("test_ide.py"))
        self.assertEqual(first.kwargs["pycharm_arg"], "--line 12")
        self.assertIsNone(second.kwargs["pycharm_arg"])

    def _shell_case(self):
        """A temporary directory with a fake PyCharm that records its
        arguments, a fake xterm that runs its command, and the workspace
        that drives them. Return (directory, workspace, commands, run):
        ``commands`` collects the terminal commands erplibre_devops builds,
        ``run`` executes the only one and returns the arguments PyCharm
        received, or None."""
        tmp = tempfile.mkdtemp(prefix="erplibre_developer_ide_")
        self.addCleanup(shutil.rmtree, tmp, True)
        home = os.path.join(tmp, "home")
        bindir = os.path.join(tmp, "bin")
        args_file = os.path.join(tmp, "pycharm_args")
        _script(
            os.path.join(home, ".local/share/JetBrains/Toolbox/scripts/pycharm"),
            '#!/bin/sh\nprintf "%s\\n" "$@" > "$ARGS_FILE"\n',
        )
        _script(
            os.path.join(bindir, "xterm"),
            '#!/bin/sh\n[ "$1" = "-e" ] && shift\nexec "$@"\n',
        )
        workspace = ShellWorkspace(self.env, tmp)
        commands = []

        def capture(system, cmd, *args, **kwargs):
            commands.append(cmd)

        patcher = patch.object(type(workspace.system), "_execute_process", capture)
        patcher.start()
        self.addCleanup(patcher.stop)

        def run():
            self.assertEqual(len(commands), 1)
            env = dict(
                os.environ,
                HOME=home,
                ARGS_FILE=args_file,
                PATH=f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            )
            subprocess.run(
                ["bash", "-c", commands[0]],
                env=env,
                check=False,
                capture_output=True,
                timeout=30,
            )
            if not os.path.exists(args_file):
                return None
            with open(args_file) as fh:
                return fh.read().splitlines()

        return tmp, workspace, commands, run

    def test_command_through_both_shells(self):
        """The command erplibre_devops builds, run through its two shells,
        gives PyCharm the line and the path unchanged."""
        tmp, workspace, _commands, run = self._shell_case()
        path = os.path.join(tmp, "src", "my_module", "models", "res_partner.py")
        os.makedirs(os.path.dirname(path))
        open(path, "w").close()
        Dev = type(self.Dev)
        with patch.object(Dev, "_ide_workspace", lambda self_: workspace):
            self.assertTrue(self.Dev._ide_open(path, 12))
        self.assertEqual(run(), ["--line", "12", path])

    def test_unsafe_path_is_refused(self):
        """A path that a shell would split or run is never passed to the
        command line: the error gives it to open by hand."""
        tmp, workspace, commands, _run = self._shell_case()
        marker = os.path.join(tmp, "injected")
        Dev = type(self.Dev)
        for name in (
            f"a;touch {marker};b.py",
            "it's.py",
            "a b.py",
            f"$(touch {marker}).py",
            f"a`touch {marker}`.py",
        ):
            path = os.path.join(tmp, "src", name)
            with self.subTest(name=name), patch.object(
                Dev, "_ide_workspace", lambda self_: workspace
            ):
                with self.assertRaises(UserError) as caught:
                    self.Dev._ide_open(path, 4)
                self.assertIn(f"{path}:4", str(caught.exception))
        self.assertEqual(commands, [])
        self.assertEqual(workspace.bundles, [])
        self.assertFalse(os.path.exists(marker))

    def test_workspace_lookup(self):
        workspace = self.Dev._ide_workspace()
        self.assertEqual(workspace._name, "devops.workspace")
