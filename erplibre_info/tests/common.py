# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import copy
import json
import os
import shutil
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from unittest.mock import patch

from odoo import release
from odoo.tests.common import TransactionCase
from odoo.tools import config

from .. import runner

SERIES = release.series
REPO = f"odoo{SERIES}/addons/Example_addons"
REPO_CORE = f"odoo{SERIES}/odoo"
REPO_OTHER = "odoo1.0/addons/Example_addons"

SNAPSHOT = {
    "schema": 1,
    "command": "snapshot",
    "generated_at": "2000-01-01T00:00:00+00:00",
    "root": "",
    "erplibre": {
        "version": f"odoo{SERIES}_python3.0.0",
        "commit": "v0.0.0-1-gaaaaaaa",
        "head": "a" * 40,
        "branch": "example",
        "dirty": None,
    },
    "odoo": {"version": SERIES, "python": "3.0.0"},
    "mode": "branches",
    "mode_detail": {"pinned": 0, "total": 3},
    "local_manifest": True,
    "dirty_checked": False,
    "repos": [
        {
            "path": REPO,
            "name": "addons.git",
            "remote": "Example",
            "url": "https://user:secret-token@git.example.invalid/addons.git",
            "revision": f"{SERIES}_dev",
            "manifest_branch": f"{SERIES}_dev",
            "freeze_revision": None,
            "upstream": {
                "remote": "Upstream",
                "name": "addons.git",
                "branch": SERIES,
                "freeze_revision": "b" * 40,
                "declared": True,
                "url": "https://git.example.invalid/upstream/addons.git",
            },
            "head": "1" * 40,
            "branch": None,
            "target": "1" * 40,
            "ahead": 0,
            "behind": 0,
            "alignment": "conforme",
            "state": "conforme",
            "dirty": None,
            "modules": [
                {
                    "name": "erplibre_info",
                    "version": f"{SERIES}.99.0.0",
                    "installable": True,
                    "path": f"{REPO}/erplibre_info",
                },
            ],
            "error": None,
        },
        {
            "path": REPO_CORE,
            "name": "odoo.git",
            "remote": "Example",
            "url": "https://git.example.invalid/odoo.git",
            "revision": SERIES,
            "manifest_branch": SERIES,
            "freeze_revision": None,
            "upstream": None,
            "head": "2" * 40,
            "branch": None,
            "target": "3" * 40,
            "ahead": 0,
            "behind": 2,
            "alignment": "decale",
            "state": "decale",
            "dirty": None,
            "modules": [
                {
                    "name": "base_setup",
                    "version": "1.0",
                    "installable": True,
                    "path": f"{REPO_CORE}/addons/base_setup",
                },
            ],
            "error": None,
        },
        {
            "path": REPO_OTHER,
            "name": "addons.git",
            "remote": "Example",
            "url": "https://git.example.invalid/addons.git",
            "revision": "1.0",
            "manifest_branch": "1.0",
            "freeze_revision": None,
            "upstream": None,
            "head": "4" * 40,
            "branch": None,
            "target": "4" * 40,
            "ahead": 0,
            "behind": 0,
            "alignment": "conforme",
            "state": "conforme",
            "dirty": None,
            "modules": [
                {
                    "name": "base_setup",
                    "version": "1.0.7",
                    "installable": True,
                    "path": f"{REPO_OTHER}/base_setup",
                },
            ],
            "error": None,
        },
    ],
    "counts": {
        "repos": 3,
        "modules": 3,
        "states": {"conforme": 2, "decale": 1},
    },
    "errors": [],
    "fingerprint": "f" * 64,
    "duration_ms": 5,
}

BETWEEN = {
    "schema": 1,
    "command": "between",
    "count": 2,
    "removed": 0,
    "ancestor": True,
    "old_known": True,
    "new_known": True,
    "truncated": False,
    "max": 200,
    "commits": [
        {
            "sha": "9" * 40,
            "author": "A",
            "date": "2000-01-02",
            "subject": "two",
        },
        {
            "sha": "8" * 40,
            "author": "A",
            "date": "2000-01-01",
            "subject": "one",
        },
    ],
    "error": None,
}

CROSS_VERSION = {
    "schema": 1,
    "command": "cross-version",
    "path": REPO,
    "version": SERIES,
    "module": "erplibre_info",
    "repo": {"path": REPO, "head": "1" * 40, "branch": None, "fork": True},
    "others": [
        {
            "version": "1.0",
            "path": REPO_OTHER,
            "present": True,
            "head": "4" * 40,
            "branch": None,
            "fork": True,
            "base": {"sha": "5" * 40, "source": "upstream_ref"},
            "modules": [
                {
                    "name": "erplibre_info",
                    "here": {"version": f"{SERIES}.99.0.0", "path": "x"},
                    "there": {"version": "1.0.1.0.0", "path": "y"},
                }
            ],
            "to_port": [
                {
                    "module": "erplibre_info",
                    "sha": "6" * 40,
                    "subject": "[ADD] something <b>bold</b>",
                    "author": "A",
                    "date": "2000-01-01",
                    "patch_id": "7" * 40,
                    "match": None,
                }
            ],
            "ported": [],
            "to_port_reason": None,
            "outside_modules": 0,
            "incomplete_modules": [],
            "truncated": False,
            "history": {
                "erplibre_info": {
                    "here": [{"sha": "1" * 40, "subject": "h", "date": "2000"}],
                    "there": [],
                }
            },
            "diff": {
                "from": "4" * 40,
                "to": "1" * 40,
                "modules": {
                    "erplibre_info": {
                        "files": 1,
                        "added": 2,
                        "removed": 1,
                        "paths": [{"path": "a.py", "added": 2, "removed": 1}],
                    }
                },
                "error": None,
            },
            "error": None,
        }
    ],
    "error": None,
}

DIAGNOSTIC = {
    "version": SERIES,
    "forks": [
        {
            "chemin": REPO,
            "verdict": "a_rebaser",
            "nos": 1,
            "amont_avance": 3,
            "cible_sha": "c" * 40,
            "head": "1" * 40,
        },
        {
            "chemin": "odooX/conflict",
            "verdict": "en_conflit",
            "conflits": ["a.py"],
        },
        {"chemin": "odooX/same", "verdict": "a_jour"},
    ],
}

REMOTES = {"version": SERIES, "remotes": []}

APPLY = {
    "version": SERIES,
    "horodatage": "20000101T0000",
    "dossier": "tasks/git_repo_upgrade/20000101T0000",
    "plan": [REPO],
    "attendus": [REPO],
    "laisses": ["odooX/conflict"],
    "resultats": [
        {
            "chemin": REPO,
            "etat": "rebase",
            "branche": f"{SERIES}_dev_maj_20000101",
            "depart": "1" * 40,
            "arrivee": "c" * 40,
        }
    ],
    "error": None,
}


class FakeScripts:
    """Stand-in for ``subprocess.run`` in the runner: answers each script
    call with a recorded JSON and keeps the argument lists."""

    def __init__(self):
        self.calls = []
        self.snapshot = copy.deepcopy(SNAPSHOT)
        self.answers = {}
        # The modules that « between --paths » finds changed.
        self.changed_modules = []

    def __call__(self, cmd, **kwargs):
        script = os.path.basename(cmd[1])
        args = list(cmd[2:])
        self.calls.append((script, args, kwargs))
        key = (script, args[0] if args else "")
        if key in self.answers:
            code, data = self.answers[key]
        elif script == "repo_state.py" and args[0] == "snapshot":
            code, data = 0, self.snapshot
        elif script == "repo_state.py" and args[0] == "between":
            code, data = 0, copy.deepcopy(BETWEEN)
            if "--paths" in args:
                data.update(
                    changed_modules=list(self.changed_modules),
                    paths=[f"{m}/x.xml" for m in self.changed_modules],
                    paths_count=len(self.changed_modules),
                    paths_truncated=False,
                )
        elif script == "repo_state.py" and args[0] == "cross-version":
            data = copy.deepcopy(CROSS_VERSION)
            if "--full" in args:
                # A later state than the cached report: nothing to port.
                data["others"][0]["diff"]["patch"] = "diff --git a/a.py b/a.py\n"
                data["others"][0]["to_port"] = []
            code = 0
        elif script == "repo_upgrade.py" and "--add-remotes" in args:
            code, data = 0, REMOTES
        elif script == "repo_upgrade.py" and "--diagnostic" in args:
            code, data = 0, DIAGNOSTIC
        elif script == "repo_apply.py":
            code, data = 0, APPLY
        else:
            raise AssertionError(f"unexpected script call {cmd}")
        return subprocess.CompletedProcess(cmd, code, json.dumps(data), "")

    def scripts(self):
        return [(script, args) for script, args, _kw in self.calls]


class ErplibreInfoCase(TransactionCase):
    """A fake ERPLibre checkout in a temporary directory, named by the
    ``erplibre_info.root`` parameter, and the fake scripts."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = tempfile.mkdtemp(prefix="erplibre_info_test_")
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        for rel in (
            runner.SCRIPT_STATE,
            runner.SCRIPT_UPGRADE,
            runner.SCRIPT_APPLY,
        ):
            os.makedirs(os.path.join(cls.root, os.path.dirname(rel)), exist_ok=True)
            with open(os.path.join(cls.root, rel), "w") as fh:
                fh.write("")
        python = os.path.join(cls.root, runner.PYTHON)
        os.makedirs(os.path.dirname(python), exist_ok=True)
        with open(python, "w") as fh:
            fh.write("#!/bin/false\n")
        os.chmod(python, os.stat(python).st_mode | stat.S_IXUSR)
        SNAPSHOT["root"] = cls.root

    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(runner.PARAM_ROOT, self.root)
        self.fake = FakeScripts()
        self.fake.snapshot["root"] = self.root
        patcher = patch.object(runner.subprocess, "run", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.Snapshot = self.env["erplibre.code.snapshot"]
        self.Run = self.env["erplibre.code.run"]
        self.cron = self.env.ref("erplibre_info.ir_cron_erplibre_code")

    @contextmanager
    def server_actions_allowed(self, flag=True, debug=True):
        with patch.dict(
            config.options,
            {"erplibre_info_allow_server_actions": str(flag)},
        ), patch.object(type(self.Run), "_is_debug_mode", lambda self_: debug):
            yield
