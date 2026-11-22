# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models.studio_pending import is_added_view
from .common import StudioCase

MODULE = "studio_test_added_views"
ITEM = "x_studio_test_added_item"
XML_NAME = "res_partner_view_pivot"


@tagged("post_install", "-at_install")
class TestAddedViews(StudioCase):
    """A view the project adds to a model that has none of its type: a line
    of the draft until Apply creates it, the default view of the model for
    its type; Revert, Discard and the removal report take it out."""

    def setUp(self):
        super().setUp()
        self.View = self.env["ir.ui.view"]
        if self.View.default_view("res.partner", "pivot"):
            self.skipTest("res.partner has a pivot view in this database")
        self.project = self.make_project(MODULE)

    def add_pivot(self):
        data = self.Editor.add_view(self.project.id, "res.partner", "pivot")
        return self.project.view_line_ids, data

    def add_measure(self, view):
        return self.op(
            self.project,
            view,
            type="add_existing_field",
            target="/pivot",
            position="inside",
            field_name="create_date",
            axis="col",
            interval="month",
        )

    def resolve(self):
        return self.Editor._resolve_view("res.partner", False, "pivot", self.project)

    def entry(self, data, view_type="pivot"):
        return next(e for e in data["view_list"] if e["type"] == view_type)

    def test_add_view_draft(self):
        line, data = self.add_pivot()
        self.assertEqual((line.model, line.view_type), ("res.partner", "pivot"))
        self.assertFalse(line.applied)
        self.assertEqual(etree.fromstring(line.arch).tag, "pivot")
        self.assertEqual(self.project.item_count, 1)
        self.assertEqual(self.project.state, "draft")
        # The editor opens the view, which exists in the draft only.
        self.assertEqual(data["view_type"], "pivot")
        self.assertFalse(data["view"]["id"])
        self.assertFalse(data["view"]["pending"])
        self.assertEqual(data["view"]["added"]["line_id"], line.id)
        self.assertFalse(data["view"]["added"]["applied"])
        self.assertEqual(data["view"]["added"]["xml_id"], f"{MODULE}.{XML_NAME}")
        entry = self.entry(data)
        self.assertTrue(entry["added"] and entry["pending"] and entry["editable"])
        self.assertFalse(entry["reason_code"])
        self.assertEqual(data["project"]["counts"]["views_added"], 1)
        self.assertEqual(data["project"]["added_views"][0]["view_type"], "pivot")
        # The project form opens the editor on it.
        params = self.project.action_open_editor()["params"]
        self.assertEqual((params["view_type"], params["view_id"]), ("pivot", False))
        # Its changes are bound to the line.
        view = self.resolve()
        self.assertTrue(is_added_view(view))
        change = self.add_measure(view)
        self.assertEqual(change.view_line_id, line)
        self.assertFalse(change.view_id)
        arch = self.draft(self.project, view)
        self.assertEqual(arch.xpath("/pivot/field/@name"), ["create_date"])
        data = self.Editor.get_editor_data(
            "res.partner", False, "pivot", self.project.id
        )
        self.assertEqual([c["id"] for c in data["changes"]], [change.id])
        self.assertEqual(self.entry(data)["changes"], 1)
        # The other types of the model keep their own entries.
        self.assertFalse(self.entry(data, "form")["added"])

    def test_add_view_refused(self):
        with self.assertRaises(UserError):
            # The contacts have a kanban view.
            self.Editor.add_view(self.project.id, "res.partner", "kanban")
        self.add_pivot()
        with self.assertRaises(UserError):
            self.Editor.add_view(self.project.id, "res.partner", "pivot")
        other = self.make_project("studio_test_added_views_other")
        with self.assertRaises(UserError):
            self.Editor.add_view(other.id, "res.partner", "pivot")
        self.make_model(self.project, "Studio test item", model=ITEM)
        with self.assertRaises(UserError):
            self.Editor.add_view(self.project.id, ITEM, "pivot")
        with self.assertRaises(UserError):
            self.Editor.add_view(self.project.id, "res.partner", "calendar")

    def test_apply_and_revert(self):
        line, _data = self.add_pivot()
        change = self.add_measure(self.resolve())
        self.project.action_apply()
        self.assertEqual(self.project.state, "applied")
        view = line.view_id
        self.assertTrue(line.applied)
        self.assertEqual(view.xml_id, f"{MODULE}.{XML_NAME}")
        self.assertEqual(
            (view.mode, view.type, view.priority), ("primary", "pivot", 16)
        )
        self.assertEqual(self.View.default_view("res.partner", "pivot"), view.id)
        self.assertIn(view, self.project.created_view_ids)
        # Its changes are bound to it, in an inherited view of the project.
        self.assertEqual(change.view_id, view)
        self.assertFalse(change.view_line_id)
        studio = self.project.studio_view_ids.filtered(lambda v: v.inherit_id == view)
        self.assertEqual(len(studio), 1)
        arch = etree.fromstring(
            self.env["res.partner"].get_view(view.id, "pivot")["arch"]
        )
        self.assertEqual(arch.xpath("/pivot/field/@name"), ["create_date"])
        data = self.Editor.get_editor_data(
            "res.partner", False, "pivot", self.project.id
        )
        self.assertEqual(data["view"]["id"], view.id)
        self.assertTrue(data["view"]["added"]["applied"])
        entry = self.entry(data)
        self.assertTrue(entry["added"])
        self.assertFalse(entry["pending"])
        # Applying again changes nothing.
        self.project.action_apply()
        self.assertEqual(line.view_id, view)
        # Revert removes the view; the line and its change stay in the draft.
        self.assertFalse(
            self.project._studio_revert_report()["report"]["changes_removed"]
        )
        self.assertTrue(self.project.action_revert())
        self.assertFalse(view.exists())
        self.assertFalse(studio.exists())
        line.invalidate_recordset(["applied", "view_id"])
        self.assertFalse(line.applied)
        self.assertEqual(change.view_line_id, line)
        self.assertFalse(change.view_id)
        self.assertEqual(self.project.state, "draft")
        self.assertFalse(self.module_records(MODULE, "ir.ui.view"))
        self.assertEqual(
            self.draft(self.project, self.resolve()).xpath("/pivot/field/@name"),
            ["create_date"],
        )

    def test_removal_report(self):
        line, _data = self.add_pivot()
        self.add_measure(self.resolve())
        self.project.action_apply()
        view = line.view_id
        data = self.Editor.remove_view(
            self.project.id, line.id, "res.partner", view.id, "pivot"
        )
        self.assertFalse(self.project.view_line_ids)
        self.assertFalse(self.project.change_ids)
        # The view stays in the database until the next Apply, which lists
        # it among what leaves.
        self.assertEqual(data["view"]["id"], view.id)
        self.assertFalse(data["view"]["added"])
        answer = self.project._studio_apply_report()
        self.assertEqual(
            answer["report"]["views"],
            [
                {"name": "res.partner.pivot.studio", "kind": "default"},
                {
                    "name": f"{MODULE}.{MODULE}_{XML_NAME}_studio",
                    "kind": "inherited",
                },
            ],
        )
        self.assertFalse(answer["confirm"])
        self.project.action_apply()
        self.assertFalse(view.exists())
        self.assertFalse(self.View.default_view("res.partner", "pivot"))

    def test_remove_pending_view(self):
        line, _data = self.add_pivot()
        self.add_measure(self.resolve())
        data = self.Editor.remove_view(
            self.project.id,
            line.id,
            "res.partner",
            False,
            "pivot",
            fallback=["res.partner", self.form.id, "form"],
        )
        self.assertFalse(line.exists())
        self.assertFalse(self.project.change_ids)
        self.assertTrue(data["view_changed"])
        self.assertEqual(data["view"]["id"], self.form.id)
        self.assertEqual(self.project.item_count, 0)

    def test_discard(self):
        line, _data = self.add_pivot()
        self.add_measure(self.resolve())
        self.project.action_apply()
        snapshot = self.project.applied_snapshot
        self.project._studio_remove_view(line)
        self.assertEqual(self.project.state, "draft")
        self.project.action_discard()
        self.assertEqual(self.project.state, "applied")
        self.assertEqual(self.project.applied_snapshot, snapshot)
        restored = self.project.view_line_ids
        self.assertEqual(restored.view_id.xml_id, f"{MODULE}.{XML_NAME}")
        self.assertEqual(len(self.project.change_ids), 1)
        self.assertEqual(self.project.change_ids.view_id, restored.view_id)

    def test_project_without_view_keeps_its_snapshot(self):
        """A project with lines and no view line keeps the snapshot form it
        had before the view lines."""
        self.make_model(self.project, "Studio test item", model=ITEM)
        self.assertNotIn('"views"', self.project._current_snapshot())
        self.add_pivot()
        self.assertIn('"views"', self.project._current_snapshot())

    def test_review(self):
        line, _data = self.add_pivot()
        change = self.add_measure(self.resolve())
        review = self.Editor.get_review(self.project.id)
        group = review["groups"][0]
        self.assertEqual(group["key"], f"added:{line.id}")
        self.assertEqual(group["ref"], f"{MODULE}.{XML_NAME}")
        self.assertEqual(
            [(i["type"], i["id"]) for i in group["items"]],
            [("view", line.id), ("change", change.id)],
        )
        item = group["items"][0]
        self.assertEqual(item["category"], "views")
        self.assertFalse(item["error"])
        self.assertEqual(
            item["target"],
            {
                "space": "view",
                "model": "res.partner",
                "view_id": False,
                "view_type": "pivot",
                "path": False,
            },
        )
        self.assertFalse(review["blocked"])
        self.project.action_apply()
        review = self.Editor.get_review(self.project.id)
        group = review["groups"][0]
        self.assertEqual(group["key"], f"added:{line.id}")
        self.assertTrue(all(i["applied"] for i in group["items"]))

    def test_check_apply(self):
        """Another view of the type made since the line was added blocks
        Apply."""
        self.add_pivot()
        self.make_view("pivot", "<pivot/>")
        review = self.Editor.get_review(self.project.id)
        self.assertTrue(review["blocked"])
        self.assertTrue(review["groups"][0]["items"][0]["error"])
        with self.assertRaises(UserError):
            self.project.action_apply()

    def test_view_of_an_own_model_after_revert(self):
        """A view added to a model the project creates applies again after
        Revert: Apply creates the model before the views added to it."""
        self.make_model(self.project, "Studio test item", model=ITEM)
        self.project.action_apply()
        self.Editor.add_view(self.project.id, ITEM, "pivot")
        line = self.project.view_line_ids
        self.project.action_apply()
        self.assertTrue(line.view_id)
        self.project.action_revert()
        self.assertNotIn(ITEM, self.env)
        line.invalidate_recordset(["applied", "view_id"])
        self.assertFalse(line.applied)
        self.assertFalse(self.Editor.get_review(self.project.id)["blocked"])
        self.project.action_apply()
        line.invalidate_recordset(["applied", "view_id"])
        self.assertEqual(self.View.default_view(ITEM, "pivot"), line.view_id.id)

    def test_preview(self):
        """get_views shows the draft of the view before Apply creates it,
        for the editor of the project only."""
        _line, _data = self.add_pivot()
        self.add_measure(self.resolve())
        context = self.preview_key(self.project)
        Partner = self.env["res.partner"]
        arch = etree.fromstring(
            Partner.with_context(**context).get_view(False, "pivot")["arch"]
        )
        self.assertEqual(arch.xpath("/pivot/field/@name"), ["create_date"])
        arch = etree.fromstring(Partner.get_view(False, "pivot")["arch"])
        self.assertFalse(arch.xpath("/pivot/field"))

    def test_timeline(self):
        if not self.timeline_available():
            self.skipTest("web_timeline is not installed")
        if self.View.default_view("res.partner", "timeline"):
            self.skipTest("res.partner has a timeline view in this database")
        self.Editor.add_view(self.project.id, "res.partner", "timeline")
        line = self.project.view_line_ids
        root = etree.fromstring(line.arch)
        self.assertEqual(
            (root.get("date_start"), root.get("default_group_by")),
            ("create_date", "create_uid"),
        )
        context = self.preview_key(self.project)
        arch = etree.fromstring(
            self.env["res.partner"]
            .with_context(**context)
            .get_view(False, "timeline")["arch"]
        )
        self.assertEqual(arch.get("date_start"), "create_date")
        self.project.action_apply()
        self.assertEqual(line.view_id.type, "timeline")

    def test_graph(self):
        if self.View.default_view("res.partner", "graph"):
            self.skipTest("res.partner has a graph view in this database")
        data = self.Editor.add_view(self.project.id, "res.partner", "graph")
        self.assertEqual(data["view_type"], "graph")
        line = self.project.view_line_ids
        root = etree.fromstring(line.arch)
        self.assertEqual((root.tag, root.get("type")), ("graph", "bar"))
        self.assertEqual(
            [(f.get("name"), f.get("type"), f.get("interval")) for f in root],
            [("create_date", "row", "month")],
        )
        context = self.preview_key(self.project)
        arch = etree.fromstring(
            self.env["res.partner"]
            .with_context(**context)
            .get_view(False, "graph")["arch"]
        )
        self.assertEqual(arch.xpath("/graph/field/@name"), ["create_date"])
        self.project.action_apply()
        view = line.view_id
        self.assertEqual((view.mode, view.type), ("primary", "graph"))
        self.assertEqual(self.View.default_view("res.partner", "graph"), view.id)
        self.project.action_revert()
        self.assertFalse(view.exists())
        self.assertFalse(self.View.default_view("res.partner", "graph"))
