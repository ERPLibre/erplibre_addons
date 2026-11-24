# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from lxml import etree
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .. import arch as studio_arch
from ..models.erplibre_studio_access import PERMS
from ..models.erplibre_studio_editor import (
    SAMPLE_TAGS,
    SAMPLE_TEXT_LENGTH,
    UNSUPPORTED_VIEW_TYPES,
)
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
                    # An activity view needs a model with activities, a
                    # GeoEngine view a model with a geo field.
                    expected = "no_view"
                    if entry["type"] == "activity" and not (
                        self.Project._studio_has_activities("res.partner")
                    ):
                        expected = "needs_activity"
                    if entry["type"] == "geoengine" and not (
                        self.Project._studio_geo_fields("res.partner")
                    ):
                        expected = "needs_geo_field"
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
        if "geoengine" not in editable:
            self.assertEqual(entries["geoengine"]["reason_code"], "needs_module")
            self.assertIn("base_geoengine", entries["geoengine"]["reason"])

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
                # The tags have no activities, no date_localization and no
                # geo field: no activity view and no map to add.
                code = {
                    "activity": "needs_activity",
                    "leaflet_map": "needs_field",
                    "geoengine": "needs_geo_field",
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

    def test_a_form_or_list_removal_stays_on_the_canvas(self):
        """« Remove from the view » keeps the node of a form or a list in
        the arch, hidden: its change is of kind « hidden » and carries the
        path of the block the editor draws as a removed line, which the
        palette does not offer again."""
        for view, view_type, attribute in (
            (self.form, "form", "invisible"),
            (self.list, "list", "column_invisible"),
        ):
            with self.subTest(view_type=view_type):
                self.project.change_ids.unlink()
                self.op(
                    self.project, view, type="remove", target="//field[@name='vat']"
                )
                data = self.data(view_type)
                (change,) = data["changes"]
                self.assertEqual((change["type"], change["kind"]), ("hide", "hidden"))
                vat = self.block_of(data, "vat")
                self.assertEqual(change["path"], vat["path"])
                self.assertEqual(vat["change_kinds"], ["hidden"])
                self.assertEqual(vat["attrs"].get(attribute), "True")
                self.assertNotIn("vat", [item["name"] for item in data["palette"]])

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

    # ── groups of the nodes ─────────────────────────────────────────────

    def test_groups_access_answers_each_expression(self):
        """Each « groups » of the arch, with whether the user passes it; a
        group the database does not hold passes, the editor draws its node."""
        view = self.make_view(
            "form",
            """<form><sheet><group>
                <field name="name" groups="base.group_portal"/>
                <field name="email" groups="!base.group_portal"/>
                <field name="phone" groups="base.group_public,base.group_portal"/>
                <field name="vat" groups="studio_invented.group_desk"/>
                <field name="website"/>
            </group></sheet></form>""",
        )
        data = self.Editor.get_editor_data(
            "res.partner", view.id, "form", self.project.id
        )
        self.assertEqual(
            data["groups_access"],
            {
                "base.group_portal": False,
                "!base.group_portal": True,
                "base.group_public,base.group_portal": False,
                "studio_invented.group_desk": True,
            },
        )

    # ── sample values ───────────────────────────────────────────────────

    SAMPLE_FORM = """<form>
        <sheet>
            <div class="oe_title"><h1><field name="name"/></h1></div>
            <group>
                <field name="ref"/>
                <field name="parent_id"/>
                <field name="type"/>
                <field name="is_company"/>
                <field name="contact_address"/>
                <field name="comment"/>
            </group>
            <notebook>
                <page name="contacts"><field name="child_ids"/></page>
            </notebook>
        </sheet>
    </form>"""

    def sample_partner(self):
        """An invented company with two contacts, and a contact of it."""
        company = self.env["res.partner"].create(
            {
                "name": "Studio sample company",
                "is_company": True,
                "ref": "S" * (SAMPLE_TEXT_LENGTH + 20),
                "comment": "<p>Sample <b>note</b></p>",
            }
        )
        contact = self.env["res.partner"].create(
            {
                "name": "Studio sample contact",
                "parent_id": company.id,
                "type": "invoice",
            }
        )
        self.env["res.partner"].create(
            {"name": "Studio sample other", "parent_id": company.id}
        )
        return company, contact

    def sample_values(self, record, names, fields_info=None):
        return self.Editor._sample_values(record, names, fields_info or {})

    def test_sample_values_of_a_known_record(self):
        """A char, an html as text, a many2one by its name, a selection by
        its label, a boolean, an x2many as its count; a long text cut."""
        company, contact = self.sample_partner()
        names = ["name", "ref", "comment", "parent_id", "type", "is_company"]
        values = self.sample_values(contact, names + ["child_ids"])
        label = dict(contact._fields["type"]._description_selection(self.env))
        self.assertEqual(values["name"], "Studio sample contact")
        self.assertEqual(values["parent_id"], company.display_name)
        self.assertEqual(values["type"], label["invoice"])
        self.assertIs(values["is_company"], False)
        self.assertEqual(values["child_ids"], {"count": 0})
        # The contact has no reference nor note: no entry, a placeholder.
        self.assertNotIn("ref", values)
        self.assertNotIn("comment", values)
        values = self.sample_values(company, names + ["child_ids"])
        self.assertIs(values["is_company"], True)
        self.assertEqual(values["child_ids"], {"count": 2})
        self.assertEqual(len(values["ref"]), SAMPLE_TEXT_LENGTH)
        self.assertTrue(values["ref"].endswith("…"))
        self.assertNotIn("<", values["comment"])
        self.assertIn("Sample", values["comment"])
        self.assertNotIn("parent_id", values)

    def test_sample_values_leave_out_what_the_user_may_not_read(self):
        """A field of a group the user lacks, a field not stored (no compute
        runs), a new field the project has not created yet: no entry. A
        record gone gives {}."""
        company, contact = self.sample_partner()
        editor, _other = self.make_users()
        Partner = type(self.env["res.partner"])

        def no_compute(records):
            raise AssertionError("a non-stored field was computed")

        with (
            patch.object(contact._fields["ref"], "groups", "base.group_portal"),
            patch.object(Partner, "_compute_contact_address", no_compute),
        ):
            values = self.Editor.with_user(editor)._sample_values(
                company.with_user(editor),
                ["name", "ref", "contact_address", "x_studio_new"],
                {"x_studio_new": {"pending": True}},
            )
        self.assertEqual(list(values), ["name"])
        # A pending field of the project that bears a name of the model.
        self.assertEqual(
            self.sample_values(company, ["name"], {"name": {"pending": True}}),
            {},
        )
        gone = self.env["res.partner"].browse(contact.id)
        contact.unlink()
        self.assertEqual(self.sample_values(gone, ["name"]), {})

    def test_sample_values_of_the_payload(self):
        """The form gives the values of its sample record for the fields its
        blocks show, without computing a non-stored one; a list gives
        none."""
        self.sample_partner()
        view = self.make_view("form", self.SAMPLE_FORM)
        Partner = type(self.env["res.partner"])

        def no_compute(records):
            raise AssertionError("a non-stored field was computed")

        with patch.object(Partner, "_compute_contact_address", no_compute):
            data = self.Editor.get_editor_data(
                "res.partner", view.id, "form", self.project.id
            )
        sample = self.env["res.partner"].browse(data["sample_res_id"])
        self.assertTrue(sample)
        names = self.Editor._block_field_names(data["blocks"])
        self.assertEqual(
            names,
            [
                "name",
                "ref",
                "parent_id",
                "type",
                "is_company",
                "contact_address",
                "comment",
                "child_ids",
            ],
        )
        values = data["sample_values"]
        self.assertEqual(values, self.sample_values(sample, names, data["fields"]))
        self.assertEqual(values["name"], sample.name[:SAMPLE_TEXT_LENGTH])
        self.assertEqual(values["child_ids"], {"count": len(sample.child_ids)})
        self.assertNotIn("contact_address", values)
        self.assertEqual(self.data("list")["sample_values"], {})
        self.assertEqual(self.data("kanban")["sample_values"], {})

    def test_sample_values_of_tags(self):
        """A many2many gives its count and the names of its first
        SAMPLE_TAGS records."""
        company, _contact = self.sample_partner()
        tags = self.env["res.partner.category"].create(
            [{"name": f"Studio sample tag {index}"} for index in range(SAMPLE_TAGS + 2)]
        )
        company.category_id = tags
        values = self.sample_values(company, ["category_id"])
        self.assertEqual(values["category_id"]["count"], SAMPLE_TAGS + 2)
        self.assertEqual(len(values["category_id"]["names"]), SAMPLE_TAGS)
        self.assertTrue(
            set(values["category_id"]["names"]) <= set(tags.mapped("display_name"))
        )

    def test_record_field_names(self):
        """The names the invisible conditions of the blocks read and the
        fields of a radio, each once: none of a constant, of the parent
        record, or of an expression that does not parse."""
        blocks = {
            "attrs": {},
            "children": [
                {"attrs": {"invisible": "not is_company"}, "children": []},
                {"attrs": {"invisible": "1"}},
                {"attrs": {"invisible": "parent.type == 'x' or type == 'contact'"}},
                {"attrs": {"invisible": "is_company and ("}},
                {"attrs": {"required": "ref"}},
                {"kind": "field", "name": "lang", "attrs": {"widget": "radio"}},
            ],
        }
        self.assertEqual(
            self.Editor._record_field_names(blocks), ["is_company", "type", "lang"]
        )

    def test_sample_record_as_the_context_of_an_expression(self):
        """The raw values an expression reads: a many2one its id, an x2many
        its ids, a selection its key, False for an empty value; a field not
        stored is computed, a new field not created yet leaves out."""
        company, contact = self.sample_partner()
        names = ["parent_id", "child_ids", "type", "is_company", "ref"]
        values = self.Editor._sample_record(
            contact,
            names + ["contact_address", "image_1920", "x_studio_new"],
            {"x_studio_new": {"pending": True}},
        )
        self.assertEqual(values["parent_id"], company.id)
        self.assertEqual(values["child_ids"], [])
        self.assertEqual(values["type"], "invoice")
        self.assertIs(values["is_company"], False)
        self.assertIs(values["ref"], False)
        self.assertIs(values["image_1920"], False)
        self.assertIsInstance(values["contact_address"], str)
        self.assertNotIn("x_studio_new", values)
        values = self.Editor._sample_record(company, ["child_ids", "parent_id"], {})
        self.assertEqual(sorted(values["child_ids"]), sorted(company.child_ids.ids))
        self.assertIs(values["parent_id"], False)
        gone = self.env["res.partner"].browse(contact.id)
        contact.unlink()
        self.assertEqual(self.Editor._sample_record(gone, ["name"], {}), {})

    def test_sample_record_of_the_payload(self):
        """A form gives the values its invisible conditions read on its
        sample record; a list gives none."""
        self.sample_partner()
        view = self.make_view(
            "form",
            """<form><sheet><group>
                <field name="name"/>
                <field name="ref" invisible="not is_company"/>
                <field name="is_company"/>
            </group></sheet></form>""",
        )
        data = self.Editor.get_editor_data(
            "res.partner", view.id, "form", self.project.id
        )
        sample = self.env["res.partner"].browse(data["sample_res_id"])
        self.assertEqual(data["sample_record"], {"is_company": sample.is_company})
        self.assertEqual(self.data("list")["sample_record"], {})

    def test_sample_values_of_a_model_without_record(self):
        """A model the project creates: before Apply, a pending form without
        sample; after, a form of a model without record, {}."""
        self.make_model(self.project, "Studio test payload item", model=ITEM)
        data = self.data("form", ITEM)
        self.assertEqual((data["sample_res_id"], data["sample_values"]), (False, {}))
        self.project.action_apply()
        data = self.data("form", ITEM)
        self.assertFalse(data["view"]["pending"])
        self.assertEqual((data["sample_res_id"], data["sample_values"]), (False, {}))
