# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestEnableFastCreation(TransactionCase):
    def test_external_sync_field_present_in_wizard(self):
        # The bridge module is auto-installed because erplibre_devops now
        # depends on erplibre_sync_external_data; therefore the field exists
        # in the loaded wizard model (no mid-session install needed).
        self.assertIn(
            "model_fast_creation_field_enable_external_sync",
            self.env["devops.plan.action.wizard"]._fields,
        )

    def test_enable_button_only_flips_flag(self):
        # new() is an in-memory record: the wizard requires root_workspace_id
        # at the DB level, but this test only exercises the button's flag
        # logic, not persistence.
        wizard = self.env["devops.plan.action.wizard"].new({})
        self.assertFalse(wizard.model_fast_creation_enabled)
        action = wizard.action_enable_model_fast_creation()
        self.assertTrue(wizard.model_fast_creation_enabled)
        # Returns a reopen act_window of the same transient record.
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "devops.plan.action.wizard")

    def test_enable_button_does_not_install_modules(self):
        # Regression guard: the button must NOT install any module. The
        # mid-session button_immediate_install was removed; if it is ever
        # reintroduced, this mocked assertion fails.
        module_cls = type(self.env["ir.module.module"])
        wizard = self.env["devops.plan.action.wizard"].new({})
        with patch.object(
            module_cls, "button_immediate_install"
        ) as mocked_install:
            wizard.action_enable_model_fast_creation()
        mocked_install.assert_not_called()
