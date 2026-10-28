# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""``runner.checkout_problem``: the message tells an ERPLibre too old for
the feature from a parameter that points nowhere. ``permission_warning``:
the clones the Odoo account cannot read, and the command that fixes it."""

import copy
import os
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests import tagged

from .. import runner
from .common import CROSS_VERSION, REPO, ErplibreInfoCase

PERMISSIONS = {
    "account": "service",
    "owner": "root",
    "count": 140,
    "path": "/srv/erplibre/.repo",
    "command": "chmod -R go+rX /srv/erplibre/.repo",
    "container": None,
}


@tagged("post_install", "-at_install")
class TestCheckoutProblem(ErplibreInfoCase):
    def setUp(self):
        super().setUp()
        self.old = tempfile.mkdtemp(prefix="erplibre_info_old_")
        self.addCleanup(shutil.rmtree, self.old, True)
        # An ERPLibre released before the scripts: its marker, no script/git.
        open(os.path.join(self.old, runner.CHECKOUT_MARKER), "w").close()

    def _set_root(self, value):
        self.env["ir.config_parameter"].sudo().set_param(runner.PARAM_ROOT, value)

    def _odoo_under(self, root):
        """``runner.odoo`` as if Odoo ran from ``<root>/odoo18.0/odoo``."""
        package = os.path.join(root, "odoo18.0", "odoo", "odoo")
        return patch.object(
            runner, "odoo", SimpleNamespace(__file__=os.path.join(package, "x.py"))
        )

    def test_complete_checkout_has_no_problem(self):
        self.assertFalse(runner.checkout_problem(self.env))

    def test_configured_checkout_without_the_script(self):
        self._set_root(self.old)
        problem = runner.checkout_problem(self.env)
        self.assertIn("missing this feature", problem)
        self.assertIn("does not exist in", problem)
        self.assertIn(runner.SCRIPT_STATE, problem)
        self.assertIn(os.path.realpath(self.old), problem)

    def test_configured_directory_that_does_not_exist(self):
        missing = os.path.join(self.old, "absent")
        self._set_root(missing)
        problem = runner.checkout_problem(self.env)
        self.assertIn(missing, problem)
        self.assertIn(runner.PARAM_ROOT, problem)
        self.assertNotIn("missing this feature", problem)

    def test_old_checkout_found_above_odoo(self):
        self._set_root(False)
        with self._odoo_under(self.old):
            problem = runner.checkout_problem(self.env)
        self.assertIn("missing this feature", problem)
        self.assertIn(runner.SCRIPT_STATE, problem)
        self.assertIn(os.path.realpath(self.old), problem)

    def test_no_checkout_at_all(self):
        self._set_root(False)
        nowhere = tempfile.mkdtemp(prefix="erplibre_info_none_")
        self.addCleanup(shutil.rmtree, nowhere, True)
        with self._odoo_under(nowhere):
            problem = runner.checkout_problem(self.env)
        self.assertIn("missing this feature", problem)
        self.assertIn(runner.PARAM_ROOT, problem)
        self.assertNotIn("does not exist in", problem)

    def test_script_missing_from_a_complete_checkout(self):
        script = "script/git/repo_absent.py"
        problem = runner.checkout_problem(self.env, script)
        self.assertIn("missing this feature", problem)
        self.assertIn(script, problem)
        self.assertIn(self.root, problem)

    def test_message_in_french(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        self.env["ir.module.module"]._load_module_terms(["erplibre_info"], ["fr_FR"])
        self._set_root(self.old)
        problem = runner.checkout_problem(self.env(context={"lang": "fr_FR"}))
        self.assertIn(
            "Il manque la fonctionnalité dans ERPLibre, êtes-vous sur la "
            "bonne version?",
            problem,
        )
        self.assertIn("n'existe pas dans", problem)


@tagged("post_install", "-at_install")
class TestPermissionWarning(ErplibreInfoCase):
    def test_nothing_to_report(self):
        self.assertFalse(runner.permission_warning(self.env, {}))
        self.assertFalse(runner.permission_warning(self.env, {"permissions": None}))

    def test_command_outside_and_inside_docker(self):
        text = runner.permission_warning(self.env, {"permissions": PERMISSIONS})
        self.assertIn("service", text)
        self.assertIn("140", text)
        self.assertIn("root", text)
        self.assertIn("chmod -R go+rX /srv/erplibre/.repo", text)
        self.assertNotIn("docker", text)
        advice = dict(PERMISSIONS, container="c0ffee")
        text = runner.permission_warning(self.env, {"permissions": advice})
        self.assertIn(
            "docker exec -u root c0ffee chmod -R go+rX /srv/erplibre/.repo", text
        )

    def test_no_command_outside_the_checkout(self):
        advice = dict(PERMISSIONS, path=None, command=None)
        text = runner.permission_warning(self.env, {"permissions": advice})
        self.assertIn("Missing permissions", text)
        self.assertNotIn("chmod", text)

    def test_snapshot_stores_and_shows_it(self):
        self.fake.snapshot["permissions"] = PERMISSIONS
        with self.assertLogs(
            "odoo.addons.erplibre_info.models.erplibre_code_snapshot", "WARNING"
        ):
            snap = self.Snapshot._capture("manual")
        self.assertIn("chmod -R go+rX", snap.permission_warning)
        self.fake.snapshot["permissions"] = None
        snap = self.Snapshot._capture("manual", force=True)
        self.assertFalse(snap.permission_warning)

    def test_cross_version_report_shows_it(self):
        data = copy.deepcopy(CROSS_VERSION)
        data["permissions"] = PERMISSIONS
        self.fake.answers[("repo_state.py", "cross-version")] = (0, data)
        rec = self.env["erplibre.code.cross.version"]._fetch(REPO)
        self.assertIn("alert-warning", rec.report_html)
        self.assertIn("chmod -R go+rX", rec.report_html)

    def test_in_french(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        self.env["ir.module.module"]._load_module_terms(["erplibre_info"], ["fr_FR"])
        advice = dict(PERMISSIONS, container="c0ffee")
        text = runner.permission_warning(
            self.env(context={"lang": "fr_FR"}), {"permissions": advice}
        )
        self.assertIn("Il manque des permissions", text)
        self.assertIn("Depuis l'hôte Docker", text)
