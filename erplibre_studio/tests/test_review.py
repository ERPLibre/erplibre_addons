# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import tagged

from ..models.erplibre_studio_review import REVIEW_CATEGORIES
from .common import StudioCase

MODULE = "studio_test_review"
ITEM = "x_studio_test_review_item"
EMAIL = "//field[@name='email']"
VAT = "//field[@name='vat']"


@tagged("post_install", "-at_install")
class TestReview(StudioCase):
    """The review of a project before Apply: its items by view and by
    model, their errors, what the last Apply already wrote, and what Apply
    removes."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project(MODULE)

    def review(self):
        return self.Editor.get_review(self.project.id)

    def items(self, review):
        return {
            item["key"]: item for group in review["groups"] for item in group["items"]
        }

    def fill(self):
        """A relabel on the contact list, a new field on the contact form, a
        model with its access row, and a rule on the contacts."""
        self.op(self.project, self.list, type="relabel", target=EMAIL, value="Mail")
        self.op(
            self.project,
            self.form,
            type="add_field",
            target=VAT,
            position="after",
            field={"ttype": "char", "field_description": "Studio nickname"},
        )
        self.line = self.make_model(self.project, "Studio test item", model=ITEM)
        return self.project._studio_save_rule(
            {
                "name": "Studio test own contacts",
                "model": "res.partner",
                "domain": "[]",
                "group_ids": [self.env.ref("base.group_user").id],
                "perm_read": True,
            }
        )

    def test_groups_and_items(self):
        rule = self.fill()
        review = self.review()
        self.assertEqual(review["revision"], self.project.draft_revision)
        self.assertEqual(
            [(g["kind"], g["key"]) for g in review["groups"]],
            [
                ("view", f"view:{self.list.id}"),
                ("view", f"view:{self.form.id}"),
                ("model", f"model:{ITEM}"),
                ("security", "security:res.partner"),
                ("apps", "apps"),
            ],
        )
        views = {g["key"]: g for g in review["groups"]}
        self.assertEqual(views[f"view:{self.form.id}"]["ref"], "base.view_partner_form")
        self.assertEqual(views[f"model:{ITEM}"]["ref"], ITEM)
        items = self.items(review)
        relabel, new_field = self.project.change_ids.sorted("id")
        item = items[f"change:{relabel.id}"]
        self.assertEqual(item["category"], "views")
        self.assertEqual(item["text"], relabel.summary)
        self.assertFalse(item["error"])
        self.assertFalse(item["applied"])
        self.assertEqual(
            {k: item["target"][k] for k in ("space", "model", "view_id", "view_type")},
            {
                "space": "view",
                "model": "res.partner",
                "view_id": self.list.id,
                "view_type": "list",
            },
        )
        # The path of the block, as the editor payload names it.
        data = self.Editor.get_editor_data(
            "res.partner", self.list.id, "list", self.project.id
        )
        paths = {c["id"]: c["path"] for c in data["changes"]}
        self.assertTrue(item["target"]["path"])
        self.assertEqual(item["target"]["path"], paths[relabel.id])
        self.assertEqual(items[f"change:{new_field.id}"]["category"], "fields")
        model = items[f"model:{self.line.id}"]
        self.assertEqual(
            (model["category"], model["target"]),
            ("models", {"space": "models", "model": ITEM}),
        )
        self.assertIn("Studio test item", model["text"])
        access = self.project.access_line_ids
        self.assertEqual(len(access), 1)
        self.assertEqual(
            items[f"access:{access.id}"]["target"],
            {"space": "security", "tab": "access", "model": ITEM},
        )
        self.assertIn(
            f"access:{access.id}",
            [i["key"] for i in views[f"model:{ITEM}"]["items"]],
        )
        self.assertEqual(
            items[f"rule:{rule.id}"]["target"],
            {"space": "security", "tab": "rules", "model": "res.partner"},
        )
        for item in items.values():
            with self.subTest(item=item["key"]):
                self.assertIn(item["category"], REVIEW_CATEGORIES)
        # A first Apply removes nothing.
        self.assertFalse(review["removal"]["confirm"])
        self.assertEqual(
            review["removal"]["digest"],
            self.Editor.get_apply_report(self.project.id)["digest"],
        )
        self.assertFalse(review["blocked"])

    def test_errors(self):
        rule = self.fill()
        rule.group_ids = [(5,)]
        broken = self.env["erplibre.studio.change"].create(
            {
                "project_id": self.project.id,
                "change_type": "relabel",
                "model": "res.partner",
                "view_id": self.list.id,
                "view_type": "list",
                "xpath": "//field[@name='studio_test_nowhere']",
                "position": "attributes",
                "payload": '{"value": "Nowhere"}',
                "sequence": 1000,
            }
        )
        review = self.review()
        items = self.items(review)
        self.assertTrue(items[f"change:{broken.id}"]["error"])
        self.assertFalse(items[f"change:{broken.id}"]["target"]["path"])
        relabel = self.project.change_ids.sorted("id")[0]
        self.assertFalse(items[f"change:{relabel.id}"]["error"])
        self.assertIn("has no group", items[f"rule:{rule.id}"]["error"])
        # Apply refuses the draft for the same reason.
        self.assertIn("has no group", review["blocked"])
        # A model without access row.
        self.project.access_line_ids.unlink()
        items = self.items(self.review())
        self.assertIn(
            "needs at least one access right", items[f"model:{self.line.id}"]["error"]
        )

    def test_applied_items(self):
        self.fill()
        self.project.action_apply()
        review = self.review()
        self.assertTrue(all(item["applied"] for item in self.items(review).values()))
        self.assertEqual(review["groups"][2]["title"], "Model of the project")
        self.op(self.project, self.list, type="relabel", target=EMAIL, value="E-mail")
        items = self.items(self.review())
        pending = [key for key, item in items.items() if not item["applied"]]
        relabel = self.project.change_ids.sorted("id")[0]
        self.assertEqual(pending, [f"change:{relabel.id}"])

    def test_removal_report(self):
        """An applied field with values that leaves the draft: the review
        holds the report of Apply, its digest, and asks to confirm."""
        self.op(
            self.project,
            self.form,
            type="add_field",
            target=VAT,
            position="after",
            field={"ttype": "char", "field_description": "Studio nickname"},
        )
        self.project.action_apply()
        self.env["res.partner"].create(
            {"name": "Studio test review", "x_studio_nickname": "Nick"}
        )
        self.project.action_undo(self.form)
        review = self.review()
        removal = review["removal"]
        self.assertTrue(removal["confirm"])
        self.assertEqual(
            [(f["name"], f["filled"]) for f in removal["report"]["fields"]],
            [("x_studio_nickname", 1)],
        )
        self.assertEqual(
            removal["digest"], self.Editor.get_apply_report(self.project.id)["digest"]
        )
        self.assertEqual(review["groups"], [])

    def test_model_not_created_yet(self):
        """A change of a model not created yet is in the group of its pending
        default view; its target opens that view."""
        line = self.make_model(self.project, "Studio test item", model=ITEM)
        view = self.Editor._resolve_view(ITEM, False, "list", self.project)
        self.op(
            self.project,
            view,
            type="relabel",
            target="//field[@name='x_name']",
            value="Title",
        )
        review = self.review()
        group = review["groups"][0]
        self.assertEqual(
            (group["key"], group["ref"]),
            (
                f"pending:{line.id}:list",
                f"{MODULE}.view_x_studio_test_review_item_list",
            ),
        )
        change = self.project.change_ids
        item = group["items"][0]
        self.assertEqual(item["key"], f"change:{change.id}")
        self.assertEqual(
            (
                item["target"]["model"],
                item["target"]["view_id"],
                item["target"]["view_type"],
            ),
            (ITEM, False, "list"),
        )
        self.assertTrue(item["target"]["path"])
        self.assertEqual(review["groups"][1]["title"], "New model")
