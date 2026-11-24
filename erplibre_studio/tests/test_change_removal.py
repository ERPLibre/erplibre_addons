# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models.studio_pending import pending_view
from .common import StudioCase

MODULE = "studio_test_change_removal"
EMAIL = "//field[@name='email']"
VAT = "//field[@name='vat']"
PHONE = "//field[@name='phone']"
ITEM = "x_studio_test_removal_item"
ORDER = "x_studio_test_removal_order"
LINE = "x_studio_test_removal_line"
LEFT = "//group[@name='studio_left']"


@tagged("post_install", "-at_install")
class TestChangeRemoval(StudioCase):
    """Undo one change of the draft, whatever its place: what leaves with
    it, the confirmation it needs and the one removal it refuses."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project(MODULE)

    def removal(self, change):
        return self.Editor.get_change_removal(self.project.id, change.id)

    def remove(self, change, expected, view=None, model="res.partner", **kwargs):
        view = view or self.form
        return self.Editor.remove_change(
            self.project.id,
            change.id,
            expected,
            model,
            view.id,
            view.type,
            **kwargs,
        )

    def add_field(self, view, label, target=VAT, position="after", **field):
        return self.op(
            self.project,
            view,
            type="add_field",
            target=target,
            position=position,
            field={"ttype": "char", "field_description": label, **field},
        )

    def test_independent_change_leaves_alone(self):
        project = self.project
        email = self.op(project, self.list, type="relabel", target=EMAIL, value="Mail")
        vat = self.op(project, self.list, type="relabel", target=VAT, value="Tax ID")
        phone = self.op(project, self.list, type="required", target=PHONE, value=True)
        removal = self.removal(vat)
        self.assertEqual(removal["change"]["id"], vat.id)
        self.assertEqual(removal["change"]["view_type"], "list")
        self.assertTrue(removal["change"]["summary"])
        self.assertEqual(removal["items"], [])
        self.assertFalse(removal["refused"])
        self.assertFalse(removal["applied"])
        revision = project.draft_revision
        self.assertEqual(removal["revision"], revision)
        data = self.remove(vat, [vat.id], view=self.list, revision=revision)
        self.assertEqual(data["removed"], [vat.id])
        self.assertEqual(project.change_ids, email | phone)
        self.assertGreater(project.draft_revision, revision)
        arch = self.draft(project, self.list)
        self.assertEqual(arch.xpath(EMAIL)[0].get("string"), "Mail")
        self.assertEqual(arch.xpath(PHONE)[0].get("required"), "True")
        self.assertIsNone(arch.xpath(VAT)[0].get("string"))

    def test_new_field_leaves_with_its_changes(self):
        project = self.project
        added = self.add_field(self.form, "Studio nickname")
        name = added.field_name
        target = f"//field[@name='{name}']"
        required = self.op(
            project, self.form, type="required", target=target, value=True
        )
        move = self.op(
            project,
            self.form,
            type="move",
            source=target,
            target=VAT,
            position="before",
        )
        removal = self.removal(added)
        self.assertEqual(
            [item["id"] for item in removal["items"]], [required.id, move.id]
        )
        first = removal["items"][0]
        self.assertEqual(
            first["model_name"], self.env["ir.model"]._get("res.partner").name
        )
        self.assertEqual(
            (first["type"], first["kind"], first["attribute"]),
            ("required", "attribute", False),
        )
        self.assertEqual(first["subject"]["label"], "Studio nickname")
        self.assertIs(first["subject"]["value"], True)
        expected = [added.id, required.id, move.id]
        data = self.remove(added, expected)
        self.assertEqual(sorted(data["removed"]), sorted(expected))
        self.assertFalse(project.change_ids.filtered(lambda c: c.view_id == self.form))

    def test_stale_confirmation_is_refused(self):
        project = self.project
        added = self.add_field(self.form, "Studio nickname")
        self.op(
            project,
            self.form,
            type="required",
            target=f"//field[@name='{added.field_name}']",
            value=True,
        )
        with self.assertRaisesRegex(UserError, "changed since you confirmed"):
            with self.env.cr.savepoint():
                self.remove(added, [added.id])
        self.assertEqual(len(project.change_ids), 2)

    def test_revision_guard(self):
        change = self.op(
            self.project, self.list, type="relabel", target=EMAIL, value="Mail"
        )
        with self.assertRaisesRegex(UserError, "reload the editor"):
            with self.env.cr.savepoint():
                self.remove(
                    change,
                    [change.id],
                    view=self.list,
                    revision=self.project.draft_revision - 1,
                )
        self.assertEqual(self.project.change_ids, change)

    def test_field_of_a_model_not_created_yet(self):
        line = self.make_model(self.project, "Studio test item", model=ITEM)
        form = pending_view(line, "form")
        added = self.add_field(form, "Studio code", target=LEFT, position="inside")
        shown = self.op(
            self.project,
            pending_view(line, "list"),
            type="add_existing_field",
            target="//field[@name='x_name']",
            position="after",
            field_name=added.field_name,
        )
        removal = self.removal(added)
        self.assertEqual([item["id"] for item in removal["items"]], [shown.id])
        item = removal["items"][0]
        self.assertEqual(item["view_type"], "list")
        # What the editor builds the plain sentence of a change of another
        # view from, and the name of its model for a reader.
        self.assertEqual(item["model_name"], "Studio test item")
        self.assertEqual(item["type"], "add_existing_field")
        self.assertEqual(item["kind"], "new")
        self.assertEqual(item["subject"]["label"], "Studio code")
        self.assertEqual(removal["change"]["subject"]["label"], "Studio code")
        data = self.remove(added, [added.id, shown.id], view=form, model=ITEM)
        self.assertEqual(sorted(data["removed"]), sorted([added.id, shown.id]))
        self.assertFalse(self.project.change_ids)

    def test_inverse_taken_by_another_one2many_is_refused(self):
        project = self.project
        self.make_model(project, "Studio test order", model=ORDER)
        self.make_model(project, "Studio test line", model=LINE)
        project.action_apply()
        order_form = self.Editor._resolve_view(ORDER, False, "form", project)
        lines = self.add_field(
            order_form,
            "Lines",
            target=LEFT,
            position="inside",
            ttype="one2many",
            relation=LINE,
            inverse={"create": True},
        )
        inverse = lines._payload()["field"]["inverse_new"]["name"]
        self.add_field(
            order_form,
            "Other lines",
            target=LEFT,
            position="inside",
            ttype="one2many",
            relation=LINE,
            relation_field=inverse,
        )
        removal = self.removal(lines)
        self.assertIn("x_other_lines", removal["refused"])
        with self.assertRaisesRegex(UserError, "x_other_lines"):
            with self.env.cr.savepoint():
                self.remove(
                    lines,
                    [lines.id] + [item["id"] for item in removal["items"]],
                    view=order_form,
                    model=ORDER,
                )
        self.assertEqual(len(project.change_ids), 2)

    def test_many2one_taken_by_a_one2many_is_refused(self):
        # A many2one of a model not created yet, the inverse of a one2many
        # of another model: the one2many would name a field that is gone.
        project = self.project
        line = self.make_model(project, "Studio test item", model=ITEM)
        form = pending_view(line, "form")
        partner = self.add_field(
            form,
            "Partner ref",
            target=LEFT,
            position="inside",
            ttype="many2one",
            relation="res.partner",
        )
        things = self.add_field(
            self.form,
            "Things",
            ttype="one2many",
            relation=ITEM,
            relation_field=partner.field_name,
        )
        removal = self.removal(partner)
        self.assertIn(things.field_name, removal["refused"])
        with self.assertRaisesRegex(UserError, things.field_name):
            with self.env.cr.savepoint():
                self.remove(partner, [partner.id], view=form, model=ITEM)
        with self.assertRaisesRegex(UserError, things.field_name):
            with self.env.cr.savepoint():
                self.op(
                    project,
                    form,
                    type="remove",
                    target=f"//field[@name='{partner.field_name}']",
                )
        self.assertEqual(len(project.change_ids), 2)
        # The one2many first, then the many2one.
        self.remove(things, [things.id])
        self.remove(partner, [partner.id], view=form, model=ITEM)
        self.assertFalse(project.change_ids)

    def test_applied_change(self):
        project = self.project
        email = self.op(project, self.list, type="relabel", target=EMAIL, value="Mail")
        self.op(project, self.list, type="relabel", target=VAT, value="Tax ID")
        project.action_apply()
        self.assertEqual(project.state, "applied")
        removal = self.removal(email)
        self.assertTrue(removal["change"]["applied"])
        self.assertTrue(removal["applied"])
        self.remove(email, [email.id], view=self.list)
        self.assertEqual(project.state, "draft")

    def test_change_of_another_project(self):
        other = self.make_project("studio_test_change_removal_other")
        change = self.op(other, self.list, type="relabel", target=EMAIL, value="Mail")
        with self.assertRaisesRegex(UserError, "not in the draft"):
            self.removal(change)
        with self.assertRaisesRegex(UserError, "not in the draft"):
            with self.env.cr.savepoint():
                self.remove(change, None, view=self.list)
        self.assertEqual(other.change_ids, change)
