# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""``runner.checkout_problem``: the message tells an ERPLibre too old for
the feature from a parameter that points nowhere."""

import os
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests import tagged

from .. import runner
from .common import ErplibreInfoCase


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
