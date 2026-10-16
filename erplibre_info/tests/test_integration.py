# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os

import odoo
from odoo.tests import TransactionCase, tagged

from .. import runner


@tagged("post_install", "-at_install")
class TestRealCheckout(TransactionCase):
    """The real ``repo_state.py snapshot`` on the checkout that runs this
    Odoo, when there is one. The command only reads the clones."""

    def test_real_snapshot(self):
        root = runner.find_root(os.path.dirname(odoo.__file__))
        if not root or not os.access(os.path.join(root, runner.PYTHON), os.X_OK):
            self.skipTest("no ERPLibre checkout around this Odoo")
        self.env["ir.config_parameter"].sudo().set_param(runner.PARAM_ROOT, False)
        snap = self.env["erplibre.code.snapshot"]._capture("manual", force=True)
        self.assertTrue(snap.repo_count)
        self.assertEqual(snap.repo_count, len(snap.repo_ids))
        self.assertEqual(len(snap.code_fingerprint), 64)
        self.assertTrue(snap.erplibre_head)
        info = snap.module_ids.filtered(lambda m: m.name == "erplibre_info")
        self.assertTrue(info.found_in_code)
        self.assertTrue(info.repo_line_id.is_active_version)
        self.assertFalse(
            any(
                "@" in (u or "").split("://")[-1].split("/")[0]
                for u in snap.repo_ids.mapped("url")
            )
        )
