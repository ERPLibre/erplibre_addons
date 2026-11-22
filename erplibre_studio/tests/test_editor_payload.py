# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .. import arch as studio_arch
from ..models.erplibre_studio_access import PERMS
from ..models.erplibre_studio_editor import UNSUPPORTED_VIEW_TYPES
from .common import StudioCase

MODULE = "studio_test_payload_a2"
ITEM = "x_studio_test_payload_item"


@tagged("post_install", "-at_install")
class TestEditorPayload(StudioCase):
    """The parts of the editor payload the A2 layout reads: the list of the
    views, the change marks of the blocks, the counts and models of the
    project, the members of the groups."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project(MODULE)

    def data(self, view_type="list", model="res.partner"):
        return self.Editor.get_editor_data(model, False, view_type, self.project.id)

    def blocks(self, block):
        yield block
        for child in block.get("children", []):
            yield from self.blocks(child)

    def block_of(self, data, name):
        return next(b for b in self.blocks(data["blocks"]) if b.get("name") == name)

    # ── view_list ───────────────────────────────────────────────────────

    def test_view_list_of_a_model(self):
        self.op(
            self.project,
            self.list,
            type="relabel",
            target="//field[@name='email']",
            value="Mail",
        )
        data = self.data()
        entries = {entry["type"]: entry for entry in data["view_list"]}
        self.assertEqual(
            [entry["type"] for entry in data["view_list"]],
            list(studio_arch.VIEW_TYPES + UNSUPPORTED_VIEW_TYPES),
        )
        form, listed = entries["form"], entries["list"]
        self.assertEqual(
            (form["view_id"], form["xml_id"], form["exists"], form["editable"]),
            (self.form.id, "base.view_partner_form", True, True),
        )
        self.assertFalse(form["reason"])
        self.assertEqual(form["changes"], 0)
        self.assertEqual((listed["view_id"], listed["changes"]), (self.list.id, 1))
        View = self.env["ir.ui.view"]
        editable = self.Project._view_types()
        for entry in data["view_list"]:
            with self.subTest(view_type=entry["type"]):
                self.assertTrue(entry["label"])
                self.assertEqual(entry["editable"], not entry["reason_code"])
                self.assertEqual(bool(entry["reason"]), bool(entry["reason_code"]))
                if entry["type"] in editable and not entry["exists"]:
                    # An activity view needs a model with activities.
                    expected = (
                        "no_view"
                        if entry["type"] != "activity"
                        or self.Project._studio_has_activities("res.partner")
                        else "needs_activity"
                    )
                    self.assertEqual(entry["reason_code"], expected)
                if entry["type"] in UNSUPPORTED_VIEW_TYPES:
                    self.assertFalse(entry["editable"])
                    self.assertIn(
                        entry["reason_code"], ("not_editable", "not_installed")
                    )
                known = View._fields["type"].get_values(self.env)
                if entry["type"] in known:
                    default = View.default_view("res.partner", entry["type"])
                    self.assertEqual(entry["view_id"], default or False)
        # gantt is in no module of the Community edition.
        if "gantt" not in View._fields["type"].get_values(self.env):
            self.assertEqual(entries["gantt"]["reason_code"], "not_installed")
        if not self.timeline_available():
            self.assertEqual(entries["timeline"]["reason_code"], "needs_module")
            self.assertIn("web_timeline", entries["timeline"]["reason"])
        if not self.hierarchy_available():
            self.assertEqual(entries["hierarchy"]["reason_code"], "needs_module")
            self.assertIn("web_hierarchy", entries["hierarchy"]["reason"])
        if not self.activity_available():
            self.assertEqual(entries["activity"]["reason_code"], "needs_module")
            self.assertIn("mail", entries["activity"]["reason"])

    def test_view_list_names_a_type_without_a_view(self):
        """A studio type the model has no view of is listed, not editable."""
        model = "res.partner.category"
        View = self.env["ir.ui.view"]
        missing = [
            t for t in self.Project._view_types() if not View.default_view(model, t)
        ]
        self.assertTrue(missing)
        data = self.data("form", model)
        entries = {entry["type"]: entry for entry in data["view_list"]}
        for view_type in missing:
            with self.subTest(view_type=view_type):
                entry = entries[view_type]
                # The tags have no activities and no date_localization: no
                # activity view and no map to add.
                code = {
                    "activity": "needs_activity",
                    "leaflet_map": "needs_field",
                }.get(view_type, "no_view")
                self.assertEqual(
                    (entry["exists"], entry["editable"], entry["reason_code"]),
                    (False, False, code),
                )

    def test_view_list_of_a_model_not_created_yet(self):
        line = self.make_model(self.project, "Studio test payload item", model=ITEM)
        self.op(
            self.project,
            self.Editor._resolve_view(ITEM, False, "list", self.project),
            type="relabel",
            target="//field[@name='x_name']",
            value="Title",
        )
        data = self.data("form", ITEM)
        entries = {entry["type"]: entry for entry in data["view_list"]}
        for view_type in studio_arch.MODEL_VIEW_TYPES:
            with self.subTest(view_type=view_type):
                entry = entries[view_type]
                self.assertEqual(
                    (entry["view_id"], entry["exists"], entry["pending"]),
                    (False, True, True),
                )
                self.assertTrue(entry["editable"])
        self.assertEqual(entries["list"]["changes"], 1)
        self.assertEqual(entries["form"]["changes"], 0)
        self.assertEqual(entries["kanban"]["reason_code"], "apply_first")
        self.assertTrue(line.exists())

    # ── change marks ────────────────────────────────────────────────────

    def test_blocks_carry_the_changes_of_the_draft(self):
        project, view = self.project, self.list
        added = self.op(
            project,
            view,
            type="add_field",
            target="//field[@name='email']",
            position="after",
            field={"ttype": "char", "field_description": "Nickname"},
        )
        relabel = self.op(
            project, view, type="relabel", target="//field[@name='phone']", value="Tel"
        )
        hide = self.op(
            project, view, type="hide", target="//field[@name='city']", value=True
        )
        move = self.op(
            project,
            view,
            type="move",
            source="//field[@name='email']",
            target="//field[@name='complete_name']",
            position="before",
        )
        optional = self.op(
            project,
            view,
            type="optional",
            target="//field[@name='country_id']",
            value="hide",
        )
        # A relabel of a field of the project refines the change that adds
        # it, whose proposed name follows the label; a second change of
        # another node adds to its marks.
        self.op(
            project,
            view,
            type="relabel",
            target="//field[@name='x_nickname']",
            value="Alias",
        )
        relabel_country = self.op(
            project,
            view,
            type="relabel",
            target="//field[@name='country_id']",
            value="Land",
        )
        data = self.data()
        expected = {
            "x_alias": ([added.id], ["new"]),
            "phone": ([relabel.id], ["renamed"]),
            "city": ([hide.id], ["hidden"]),
            "email": ([move.id], ["moved"]),
            "country_id": (
                [optional.id, relabel_country.id],
                ["renamed", "attribute"],
            ),
        }
        for name, (changes, kinds) in expected.items():
            with self.subTest(name=name):
                block = self.block_of(data, name)
                self.assertEqual(block["changes"], changes)
                self.assertEqual(block["change_kinds"], kinds)
                self.assertTrue(block["changed"])
        untouched = self.block_of(data, "complete_name")
        self.assertEqual(
            (untouched["changes"], untouched["change_kinds"], untouched["changed"]),
            ([], [], False),
        )
        root = data["blocks"]
        self.assertEqual((root["changed"], root["changed_inside"]), (False, True))
        # Each change gives the path of the block it touches.
        by_path = {b["path"]: b for b in self.blocks(root)}
        kinds = {}
        for change in data["changes"]:
            with self.subTest(change=change["type"]):
                self.assertIn(change["id"], by_path[change["path"]]["changes"])
                kinds[change["id"]] = change["kind"]
        self.assertEqual(
            kinds,
            {
                added.id: "new",
                relabel.id: "renamed",
                hide.id: "hidden",
                move.id: "moved",
                optional.id: "attribute",
                relabel_country.id: "renamed",
            },
        )
        # The marks stay out of the payload and of the views.
        for block in by_path.values():
            self.assertNotIn(studio_arch.CHANGE_MARK, block["attrs"])
        project.action_apply()
        studio = project.studio_view_ids.filtered(lambda v: v.inherit_id == view)
        self.assertNotIn(studio_arch.CHANGE_MARK, studio.arch)
        self.assertNotIn(
            studio_arch.CHANGE_MARK, etree.tostring(self.view_arch(view), encoding=str)
        )
        data = self.data()
        self.assertEqual(self.block_of(data, "phone")["change_kinds"], ["renamed"])

    def test_containers_hold_the_marks_of_their_nodes(self):
        target = "//field[@name='vat']"
        change = self.op(
            self.project, self.form, type="required", target=target, value=True
        )
        data = self.data("form")
        vat = self.block_of(data, "vat")
        self.assertEqual(vat["change_kinds"], ["attribute"])
        ancestors = [
            b
            for b in self.blocks(data["blocks"])
            if b.get("children") and vat in list(self.blocks(b))[1:]
        ]
        self.assertTrue(ancestors)
        for block in ancestors:
            self.assertTrue(block["changed_inside"])
            self.assertFalse(block["changed"])
        self.assertEqual(data["changes"][0]["path"], vat["path"])
        self.assertEqual(data["changes"][0]["id"], change.id)
        # Only a « set_attribute » names the attribute it writes.
        self.assertFalse(data["changes"][0]["attribute"])

    def test_a_removed_or_failing_change_has_no_path(self):
        search = self.env.ref("base.view_res_partner_filter")
        target = "//filter[@name='type_company']"
        self.op(self.project, search, type="hide", target=target, value=True)
        data = self.data("search")
        (change,) = data["changes"]
        self.assertEqual((change["type"], change["kind"]), ("remove", "hidden"))
        self.assertFalse(change["path"])
        # A change whose node left the view reports its error, no path.
        broken = self.project._add_change(
            self.list,
            "relabel",
            "//field[@name='studio_test_missing']",
            "attributes",
            {"value": "Gone"},
        )
        data = self.data()
        entry = next(c for c in data["changes"] if c["id"] == broken.id)
        self.assertTrue(entry["error"])
        self.assertFalse(entry["path"])
        self.assertFalse(any(b["changed"] for b in self.blocks(data["blocks"])))

    def test_apply_changes_tracks_the_nodes(self):
        """``apply_changes(track=True)`` gives the same arch as without,
        once the marks are stripped."""
        root = etree.fromstring(
            "<list><field name='name'/><field name='email'/></list>"
        )
        changes = [
            {
                "key": 1,
                "type": "move",
                "xpath": "//field[@name='name']",
                "position": "before",
                "payload": {"source": "//field[@name='email']"},
            },
            {
                "key": 2,
                "type": "hide",
                "xpath": "//field[@name='name']",
                "payload": {"value": True},
            },
        ]
        plain, errors = studio_arch.apply_changes(root, changes, "list")
        tracked, tracked_errors = studio_arch.apply_changes(
            root, changes, "list", track=True
        )
        self.assertEqual((errors, tracked_errors), ({}, {}))
        self.assertEqual(
            studio_arch.change_paths(tracked),
            {"1": "//field[@name='email']", "2": "//field[@name='name']"},
        )
        self.assertEqual(studio_arch.change_marks(tracked[0]), [("1", "moved")])
        studio_arch.strip_change_marks(tracked)
        self.assertEqual(etree.tostring(tracked), etree.tostring(plain))
        self.assertNotIn(studio_arch.CHANGE_MARK, root.attrib)

    # ── project ─────────────────────────────────────────────────────────

    def test_project_counts_and_touched_models(self):
        project = self.project
        self.op(
            project,
            self.list,
            type="add_field",
            target="//field[@name='email']",
            position="after",
            field={"ttype": "char", "field_description": "Nickname"},
        )
        self.op(
            project, self.form, type="relabel", target="//field[@name='vat']", value="T"
        )
        self.make_model(project, "Studio test payload item", model=ITEM)
        payload = self.data()["project"]
        counts = payload["counts"]
        self.assertEqual(
            (counts["fields"], counts["views"], counts["models"], counts["groups"]),
            (1, 1, 1, 0),
        )
        self.assertEqual(counts["access"], len(project.access_line_ids))
        self.assertEqual(counts["rules"], 0)
        self.assertEqual(counts["edited_views"], 2)
        self.assertEqual(counts["total"], project.item_count)
        self.assertEqual(
            counts["total"],
            sum(
                counts[k]
                for k in ("fields", "views", "models", "access", "rules", "groups")
            )
            + counts["apps"],
        )
        self.assertFalse(payload["applied_date"])
        touched = {item["model"]: item for item in payload["touched_models"]}
        self.assertEqual(set(touched), {"res.partner", ITEM})
        partner = touched["res.partner"]
        self.assertEqual(
            (partner["new"], partner["pending"], partner["changes"]), (False, False, 2)
        )
        self.assertEqual(
            partner["fields"],
            [
                {
                    "name": "x_nickname",
                    "label": "Nickname",
                    "ttype": "char",
                    "relation": False,
                    "applied": False,
                }
            ],
        )
        # A model of the database: its module, its chatter, the default
        # views the studio edits.
        self.assertEqual(partner["module"], "base")
        IrModel = self.env["ir.model"]
        self.assertEqual(
            partner["chatter"],
            "is_mail_thread" in IrModel._fields
            and IrModel._get("res.partner").is_mail_thread,
        )
        views = {view["type"]: view for view in partner["views"]}
        self.assertEqual(views["form"]["view_id"], self.form.id)
        self.assertIn("list", views)
        self.assertTrue(views["form"]["label"])
        item = touched[ITEM]
        self.assertEqual(
            (item["name"], item["new"], item["pending"]),
            ("Studio test payload item", True, True),
        )
        # A model of the project: no module, its own chatter, its views
        # are those of its line.
        self.assertEqual(
            (item["module"], item["chatter"], item["views"]),
            (False, project.new_model_ids.chatter, []),
        )
        self.assertEqual(item["access"], len(project.access_line_ids))
        project.action_apply()
        payload = self.data()["project"]
        self.assertTrue(payload["applied_date"])
        touched = {item["model"]: item for item in payload["touched_models"]}
        self.assertTrue(touched["res.partner"]["fields"][0]["applied"])
        self.assertFalse(touched[ITEM]["pending"])

    def test_project_names_the_state_of_its_module(self):
        """``module_state``: False while no module has the name of the
        project, the state of that module once one has it."""
        self.assertFalse(self.data()["project"]["module_state"])
        self.env["ir.module.module"].create({"name": MODULE, "state": "installed"})
        self.project.invalidate_recordset(["module_id", "module_state"])
        self.assertEqual(self.data()["project"]["module_state"], "installed")

    def test_access_rows_carry_their_applied_rights(self):
        """An access row names the rights its ir.model.access got at the
        last Apply, False before: the grid marks what the draft changes."""
        project = self.project
        self.make_model(project, "Studio test payload item", model=ITEM)
        (row,) = self.data()["project"]["access"]
        self.assertFalse(row["applied"])
        project.action_apply()
        line = project.access_line_ids
        before = {perm: line[perm] for perm in PERMS}
        (row,) = self.data()["project"]["access"]
        self.assertEqual(row["applied"], before)
        project._studio_set_access(
            [
                {
                    "model": ITEM,
                    "group_id": line.group_id.id,
                    **before,
                    "perm_unlink": False,
                }
            ]
        )
        (row,) = self.data()["project"]["access"]
        self.assertFalse(row["perm_unlink"])
        self.assertEqual(row["applied"], before)

    def test_choices_name_the_category_of_a_group(self):
        groups = {
            g["xml_id"]: g
            for g in self.Editor.get_studio_choices(self.project.id)["groups"]
        }
        system = self.env.ref("base.group_system")
        self.assertEqual(
            groups["base.group_system"]["category"],
            [system.category_id.id, system.category_id.name],
        )

    # ── members of the groups ───────────────────────────────────────────

    def make_group_users(self):
        """(lead, member, Groups): a group implied by another, a user in
        the first one, a user in the second one only."""
        Groups = self.env["res.groups"]
        base = Groups.create({"name": "Studio test payload base"})
        top = Groups.create(
            {"name": "Studio test payload top", "implied_ids": [(4, base.id)]}
        )
        member = new_test_user(
            self.env, login="studio_test_payload_member", groups="base.group_user"
        )
        member.groups_id = [(4, base.id)]
        lead = new_test_user(
            self.env, login="studio_test_payload_lead", groups="base.group_user"
        )
        lead.groups_id = [(4, top.id)]
        return base, top, member, lead

    def test_group_members(self):
        base, top, member, lead = self.make_group_users()
        answer = self.Editor.get_group_members(group_ids=[base.id, top.id])
        self.assertFalse(answer["lines"])
        first, second = answer["groups"]
        self.assertEqual((first["id"], first["count"]), (base.id, 2))
        self.assertFalse(first["more"])
        direct = {item["id"]: item["direct"] for item in first["users"]}
        self.assertEqual(direct, {member.id: True, lead.id: False})
        self.assertEqual(
            [item["name"] for item in first["users"]],
            sorted((member.name, lead.name), key=str.lower),
        )
        self.assertEqual((second["count"], second["users"][0]["id"]), (1, lead.id))
        self.assertEqual(
            (second["name"], second["xml_id"], second["category"]),
            (top.full_name, False, False),
        )
        self.assertEqual(second["implied"], [[base.id, base.full_name]])
        system = self.env.ref("base.group_system")
        (admin,) = self.Editor.get_group_members(group_ids=[system.id])["groups"]
        self.assertEqual(admin["xml_id"], "base.group_system")
        self.assertEqual(admin["category"][0], system.category_id.id)
        capped = self.Editor.get_group_members(group_ids=[base.id], limit=1)
        (group,) = capped["groups"]
        self.assertEqual((group["count"], len(group["users"])), (2, 1))
        self.assertTrue(group["more"])

    def test_group_members_of_the_project(self):
        app = self.project._studio_save_app({"name": "Studio test payload app"})
        line = self.project._studio_save_group(
            {"name": "Studio test payload agent", "app_id": app.id}
        )
        answer = self.Editor.get_group_members(self.project.id, line_ids=[line.id])
        self.assertEqual(
            answer["lines"],
            [
                {
                    "line_id": line.id,
                    "applied": False,
                    "count": 0,
                    "users": [],
                    "more": False,
                }
            ],
        )
        with self.assertRaises(UserError):
            self.Editor.get_group_members(self.project.id, line_ids=[0])
        self.make_model(self.project, "Studio test payload item", model=ITEM)
        self.project.action_apply()
        record = line._studio_group_record()
        user = new_test_user(
            self.env, login="studio_test_payload_agent", groups="base.group_user"
        )
        user.groups_id = [(4, record.id)]
        (entry,) = self.Editor.get_group_members(self.project.id, line_ids=[line.id])[
            "lines"
        ]
        self.assertTrue(entry["applied"])
        self.assertEqual(entry["count"], len(record.users))
        self.assertIn(user.id, [item["id"] for item in entry["users"]])

    def test_group_losses(self):
        """The members Apply takes a group of the project from, when another
        group of the project stops implying it (``_studio_group_losses``)."""
        app = self.project._studio_save_app({"name": "Studio test payload app"})
        agent = self.project._studio_save_group(
            {"name": "Studio test agent", "app_id": app.id}
        )
        manager = self.project._studio_save_group(
            {
                "name": "Studio test manager",
                "app_id": app.id,
                "implied_line_ids": [agent.id],
            }
        )
        self.make_model(self.project, "Studio test payload item", model=ITEM)
        self.project.action_apply()
        self.assertEqual(self.Editor.get_group_losses(self.project.id), [])
        user = new_test_user(
            self.env, login="studio_test_payload_manager", groups="base.group_user"
        )
        user.groups_id = [(4, manager._studio_group_record().id)]
        self.project._studio_save_group(
            {"id": manager.id, "implied_line_ids": [], "implied_group_ids": []}
        )
        (loss,) = self.Editor.get_group_losses(self.project.id)
        agent_record = agent._studio_group_record()
        manager_record = manager._studio_group_record()
        self.assertEqual(
            loss,
            {
                "group": [agent_record.id, agent_record.full_name],
                "line_id": agent.id,
                "via": [manager_record.id, manager_record.full_name],
                "via_line_id": manager.id,
                "count": 1,
                "users": [{"id": user.id, "name": user.name}],
                "more": False,
            },
        )
        # The same members the Apply report counts.
        report = self.project._studio_apply_report()["report"]["members"]
        self.assertEqual([item["users"] for item in report], [loss["count"]])
