# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .common import StudioCase

ITEM = "x_studio_test_level_item"


@tagged("post_install", "-at_install")
class TestDisplayLevel(StudioCase):
    """The display level of the editor, remembered per user account, and
    the inherited views and field modules the Detailed level shows."""

    def setUp(self):
        super().setUp()
        self.editor_user, self.other_user = self.make_users()

    def data(self, user, view=None):
        view = view or self.form
        return self.Editor.with_user(user).get_editor_data(
            view.model, view.id, view.type, False, pick_project=False
        )

    def settings_of(self, user):
        return self.env["res.users.settings"].sudo().search([("user_id", "=", user.id)])

    def test_simple_by_default_without_a_settings_row(self):
        self.settings_of(self.editor_user).unlink()
        self.assertEqual(self.data(self.editor_user)["display_level"], "simple")
        self.assertFalse(self.settings_of(self.editor_user))

    def test_detailed_is_remembered_for_the_account(self):
        Editor = self.Editor.with_user(self.editor_user)
        self.assertEqual(Editor.set_display_level("detailed"), "detailed")
        self.assertEqual(
            self.settings_of(self.editor_user).erplibre_studio_display_level,
            "detailed",
        )
        self.assertEqual(self.data(self.editor_user)["display_level"], "detailed")
        # Another account keeps its own level.
        self.assertEqual(self.data(self.other_user)["display_level"], "simple")
        Editor.set_display_level("simple")
        self.assertEqual(self.data(self.editor_user)["display_level"], "simple")

    def test_refused_values_and_users(self):
        Editor = self.Editor.with_user(self.editor_user)
        for value in ("expert", "", None):
            with self.subTest(value=value), self.assertRaises(UserError):
                Editor.set_display_level(value)
        employee = new_test_user(
            self.env,
            login="studio_test_level_employee",
            groups="base.group_user",
        )
        with self.assertRaises(AccessError):
            self.Editor.with_user(employee).set_display_level("detailed")
        self.assertNotEqual(
            self.settings_of(employee)[:1].erplibre_studio_display_level,
            "detailed",
        )
        # Without the developer mode the editor stays closed too.
        self._debug = False
        with self.assertRaises(UserError):
            Editor.set_display_level("detailed")

    def extend(self, parent, xml_id=None):
        """An extension view of ``parent``; ``xml_id`` « module.name »
        gives it an external id."""
        view = self.env["ir.ui.view"].create(
            {
                "name": "erplibre_studio test level extension",
                "model": "res.partner",
                "inherit_id": parent.id,
                "arch": (
                    "<field name='email' position='attributes'>"
                    "<attribute name='placeholder'>Mail</attribute>"
                    "</field>"
                ),
            }
        )
        if xml_id:
            module, name = xml_id.split(".")
            self.env["ir.model.data"].create(
                {
                    "module": module,
                    "name": name,
                    "model": "ir.ui.view",
                    "res_id": view.id,
                }
            )
        return view

    def test_inherited_views_of_the_view(self):
        before = self.data(self.editor_user)["view"]["inherited"]
        self.assertLessEqual(before["modules"], before["views"])
        first = self.extend(self.form, "studio_test_level_a.view_one")
        # An extension of an extension extends the view too.
        self.extend(first, "studio_test_level_a.view_two")
        self.extend(self.form, "studio_test_level_b.view_three")
        # A view without external id counts as a view, not as a module.
        self.extend(self.form)
        inherited = self.data(self.editor_user)["view"]["inherited"]
        self.assertEqual(
            (inherited["views"], inherited["modules"]),
            (before["views"] + 4, before["modules"] + 2),
        )
        self.assertGreater(inherited["modules"], 0)

    def test_a_pending_view_inherits_nothing(self):
        project = self.make_project("studio_test_level")
        self.make_model(project, "Studio test level item", model=ITEM)
        data = self.Editor.get_editor_data(ITEM, False, "form", project.id)
        self.assertTrue(data["view"]["pending"])
        self.assertEqual(data["view"]["inherited"], {"views": 0, "modules": 0})

    def test_modules_of_the_fields(self):
        fields = self.data(self.editor_user)["fields"]
        self.assertIn("base", fields["name"]["modules"].split(", "))
