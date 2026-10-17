# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models.erplibre_studio_project import STUDIO_PRIORITY
from .common import StudioCase


@tagged("post_install", "-at_install")
class TestApply(StudioCase):
    def setUp(self):
        super().setUp()
        self.project = self.make_project("studio_test_apply")
        self.op(
            self.project,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            position="after",
            field={
                "ttype": "char",
                "field_description": "Nickname",
                "help": "Short name",
            },
        )
        self.op(
            self.project,
            self.list,
            type="add_existing_field",
            target="//field[@name='email']",
            position="after",
            field_name="ref",
        )
        self.op(
            self.project,
            self.list,
            type="relabel",
            target="//field[@name='phone']",
            value="Telephone",
        )

    def studio_views(self):
        data = self.env["ir.model.data"].search(
            [
                ("module", "=", "studio_test_apply"),
                ("model", "=", "ir.ui.view"),
            ]
        )
        return self.env["ir.ui.view"].browse(data.mapped("res_id"))

    def arch(self, view, view_type):
        return etree.fromstring(
            self.env["res.partner"].get_view(view.id, view_type)["arch"]
        )

    def test_apply_creates_and_reapply_updates(self):
        self.project.action_apply()
        self.assertEqual(self.project.state, "applied")
        field = self.env["ir.model.fields"]._get("res.partner", "x_nickname")
        self.assertEqual(
            (field.state, field.ttype, field.field_description, field.help),
            ("manual", "char", "Nickname", "Short name"),
        )
        self.assertEqual(self.project.field_ids, field)
        views = self.studio_views()
        self.assertEqual(len(views), 2)
        self.assertEqual(views, self.project.studio_view_ids)
        self.assertEqual(set(views.mapped("inherit_id")), {self.form, self.list})
        self.assertEqual(set(views.mapped("priority")), {STUDIO_PRIORITY})
        self.assertEqual(set(views.mapped("mode")), {"extension"})
        # Every user sees the applied views.
        form = self.arch(self.form, "form")
        self.assertEqual(
            form.xpath("//field[@name='x_nickname']")[0].getprevious().get("name"),
            "vat",
        )
        listing = self.arch(self.list, "list")
        self.assertEqual(
            listing.xpath("//field[@name='phone']")[0].get("string"),
            "Telephone",
        )
        columns = self.columns(listing)
        self.assertEqual(columns[columns.index("email") + 1], "ref")
        partner = self.env["res.partner"].create({"name": "Studio", "x_nickname": "S"})
        self.assertEqual(partner.x_nickname, "S")

        # Applying again changes nothing: no duplicate view nor field.
        arch_before = views.mapped("arch")
        self.project.action_apply()
        self.assertEqual(self.studio_views(), views)
        self.assertEqual(views.mapped("arch"), arch_before)
        self.assertEqual(
            self.env["ir.model.fields"]._get("res.partner", "x_nickname"),
            field,
        )

        # A refined draft updates the same records.
        self.op(
            self.project,
            self.list,
            type="relabel",
            target="//field[@name='phone']",
            value="Phone 2",
        )
        self.op(
            self.project,
            self.form,
            type="relabel",
            target="//field[@name='x_nickname']",
            value="Alias",
        )
        self.assertEqual(self.project.state, "draft")
        self.project.action_apply()
        self.assertEqual(self.studio_views(), views)
        self.assertEqual(field.field_description, "Alias")
        listing = self.arch(self.list, "list")
        self.assertEqual(
            listing.xpath("//field[@name='phone']")[0].get("string"), "Phone 2"
        )
        self.assertEqual(len(listing.xpath("//field[@name='phone']")), 1)

    def test_removed_field_and_view_leave_the_database(self):
        self.project.action_apply()
        list_view = self.project.studio_view_ids.filtered(
            lambda v: v.inherit_id == self.list
        )
        self.op(
            self.project,
            self.form,
            type="remove",
            target="//field[@name='x_nickname']",
        )
        self.project.change_ids.filtered(lambda c: c.view_id == self.list).unlink()
        self.project._touch()
        self.project.action_apply()
        self.assertFalse(self.env["ir.model.fields"]._get("res.partner", "x_nickname"))
        self.assertFalse(list_view.exists())
        self.assertFalse(self.project.studio_view_ids)
        self.assertEqual(self.project.state, "applied")

    def test_discard_and_revert(self):
        self.project.action_apply()
        snapshot = self.project.applied_snapshot
        self.op(
            self.project,
            self.list,
            type="hide",
            target="//field[@name='city']",
            value=True,
        )
        self.project.action_undo()
        self.op(
            self.project,
            self.list,
            type="relabel",
            target="//field[@name='phone']",
            value="Other",
        )
        self.assertEqual(self.project.state, "draft")
        self.project.action_discard()
        self.assertEqual(self.project.state, "applied")
        self.assertEqual(self.project._current_snapshot(), snapshot)
        views = self.project.studio_view_ids
        self.project.action_revert()
        self.assertFalse(views.exists())
        self.assertFalse(self.env["ir.model.fields"]._get("res.partner", "x_nickname"))
        self.assertEqual(self.project.state, "draft")
        self.assertEqual(len(self.project.change_ids), 3)
        listing = self.arch(self.list, "list")
        self.assertNotEqual(
            listing.xpath("//field[@name='phone']")[0].get("string"),
            "Telephone",
        )
        # The changes apply again after a revert.
        self.project.action_apply()
        self.assertEqual(len(self.studio_views()), 2)

    def test_unlink_needs_a_revert(self):
        self.project.action_apply()
        with self.assertRaises(UserError):
            with self.env.cr.savepoint():
                self.project.unlink()
        self.project.action_revert()
        self.project.unlink()
