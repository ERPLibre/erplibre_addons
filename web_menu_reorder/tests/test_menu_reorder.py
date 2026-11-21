# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase

from odoo.addons.web_menu_reorder.models.res_config_settings import (
    menu_label_key,
)


class TestMenuReorder(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Menu = cls.env["ir.ui.menu"]
        # Only these top-level menus take part: the others are archived
        # for the test, so the order below is the whole order.
        Menu.search([("parent_id", "=", False)]).write({"active": False})
        # A menu without an action nor a visible child is hidden from
        # ir.ui.menu searches: each test menu opens an action.
        action = cls.env["ir.actions.act_window"].create(
            {"name": "Contacts", "res_model": "res.partner"}
        )
        names = ["Zèbre", "Ventes", "Événements", "eLearning", "Achats"]
        cls.menus = {
            name: Menu.create(
                {
                    "name": name,
                    "sequence": 5,
                    "action": f"ir.actions.act_window,{action.id}",
                }
            )
            for name in names
        }

    def _reorder(self, algorithm, labels=""):
        settings = self.env["res.config.settings"].create(
            {
                "menu_reorder_lang_to_order": "en_US",
                "menu_reorder_algorithm_lang_to_order": algorithm,
                "menu_order_labels": labels,
            }
        )
        settings.execute_menu_reorder()
        self.env["ir.ui.menu"].invalidate_model(["sequence"])
        return [
            menu.name
            for menu in sorted(
                self.menus.values(), key=lambda m: (m.sequence, m.id)
            )
        ]

    def test_label_key_ignores_case_and_accents(self):
        self.assertEqual(menu_label_key("Événements"), "evenements")
        self.assertEqual(menu_label_key("É"), menu_label_key("e"))
        self.assertEqual(menu_label_key("  Ventes "), "ventes")

    def test_alphabetical_order_ignores_case_and_accents(self):
        self.assertEqual(
            self._reorder("by_alphabetical"),
            ["Achats", "eLearning", "Événements", "Ventes", "Zèbre"],
        )

    def test_custom_labels_match_whatever_the_case_or_accents(self):
        self.assertEqual(
            self._reorder("by_label", "ventes\nEVENEMENTS"),
            ["Ventes", "Événements", "Achats", "eLearning", "Zèbre"],
        )
