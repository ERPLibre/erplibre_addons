# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo.exceptions import UserError
from odoo.tests import tagged

from .. import arch as studio_arch
from .common import StudioCase

MODULE = "studio_test_field_properties"
VAT = "//field[@name='vat']"
COMPANION = "x_partner_properties"
# An invented property id, in the shape Odoo gives one.
PROPERTY = "a1b2c3d4e5f60708"
ITEM = "x_studio_test_item"
LEFT = "//group[@name='studio_left']"


@tagged("post_install", "-at_install")
class TestFieldProperties(StudioCase):
    """A new properties field (fields.Properties): it reads its definition
    through a many2one of its model, from a properties definition field of
    the comodel, existing or created by the project; a form only."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project(MODULE)
        self.Fields = self.env["ir.model.fields"]

    def add(self, view=None, target=VAT, position="after", **field):
        values = {
            "field_description": "Studio properties",
            "ttype": "properties",
            "definition_record": "country_id",
            "definition_new": {
                "name": COMPANION,
                "field_description": "Partner properties",
            },
        }
        values.update(field)
        return self.op(
            self.project,
            view or self.form,
            type="add_field",
            target=target,
            position=position,
            field=values,
        )

    def add_region(self):
        """A new many2one of the contacts to the countries, in the form."""
        return self.op(
            self.project,
            self.form,
            type="add_field",
            target=VAT,
            position="after",
            field={
                "field_description": "Studio region",
                "ttype": "many2one",
                "relation": "res.country",
            },
        )

    def form_arch(self, model="res.partner", view=None):
        view = view or self.form
        return etree.fromstring(self.env[model].get_view(view.id, "form")["arch"])

    def test_definition_creates_the_companion(self):
        change = self.add()
        payload = change._payload()
        definition = payload["field"]
        self.assertEqual(
            {
                key: definition[key]
                for key in ("relation", "definition_record", "definition_record_field")
            },
            {
                "relation": "res.country",
                "definition_record": "country_id",
                "definition_record_field": COMPANION,
            },
        )
        self.assertEqual(
            definition["definition_new"],
            {"name": COMPANION, "field_description": "Partner properties"},
        )
        # The form shows the country already: no container node.
        self.assertNotIn("container", payload)
        companion, owner = self.project._studio_field_definitions("res.country")[
            COMPANION
        ]
        self.assertEqual(companion["ttype"], "properties_definition")
        self.assertEqual(owner, change)
        self.assertIn(COMPANION, self.project._taken_field_names("res.country"))
        # Apply creates the many2one and the companion first.
        order = [
            definition["ttype"]
            for _model, _name, definition, _change in (
                self.project._studio_all_definitions()
            )
        ]
        self.assertEqual(order, ["properties_definition", "properties"])
        node = self.draft(self.project, self.form).xpath(
            f"//field[@name='{change.field_name}']"
        )
        self.assertTrue(node)

    def test_refusals(self):
        kanban = self.env.ref("base.res_partner_kanban_view")
        with self.assertRaisesRegex(UserError, "A properties field shows in a form"):
            self.add(kanban, target="//field[@name='email']")
        with self.assertRaisesRegex(UserError, "A properties field shows in a form"):
            self.add(self.list, target="//field[@name='email']")
        self.assertEqual(
            studio_arch.field_type_refusal("list", "properties").code,
            "properties_view",
        )
        self.assertIsNone(studio_arch.field_type_refusal("form", "properties"))
        with self.assertRaisesRegex(UserError, "vat is not a many2one"):
            self.add(definition_record="vat")
        with self.assertRaisesRegex(UserError, "does not add fields to res.users"):
            self.add(definition_record="user_id")
        with self.assertRaisesRegex(UserError, "not a properties definition field"):
            self.add(definition_new=False, definition_record_field="x_unknown")
        self.assertFalse(self.project.change_ids)
        change = self.add()
        with self.assertRaisesRegex(UserError, "relation of the field .* cannot"):
            self.op(
                self.project,
                self.form,
                type="update_field",
                field_name=change.field_name,
                field={"definition_record": "parent_id"},
            )
        # Its label still changes.
        self.op(
            self.project,
            self.form,
            type="update_field",
            field_name=change.field_name,
            field={"field_description": "Studio sizes"},
        )
        self.assertEqual(change._payload()["field"]["definition_record"], "country_id")

    def test_apply_reads_the_definition_of_the_country(self):
        change = self.add()
        name = change.field_name
        self.project.action_apply()
        companion = self.Fields._get("res.country", COMPANION)
        self.assertEqual(
            (companion.ttype, companion.state), ("properties_definition", "manual")
        )
        row = self.Fields._get("res.partner", name)
        self.assertEqual(row.ttype, "properties")
        self.assertEqual(
            row.erplibre_studio_properties_definition, f"country_id.{COMPANION}"
        )
        field = self.env["res.partner"]._fields[name]
        self.assertEqual(field.definition, f"country_id.{COMPANION}")
        self.assertEqual(self.project.field_ids, companion | row)
        country = self.env["res.country"].create(
            {"name": "Studio test land", "code": "QZ"}
        )
        country[COMPANION] = [{"name": PROPERTY, "string": "Size", "type": "char"}]
        partner = self.env["res.partner"].create(
            {"name": "Studio properties", "country_id": country.id}
        )
        partner.write({name: {PROPERTY: "L"}})
        partner.invalidate_recordset([name])
        self.assertEqual(partner[name], {PROPERTY: "L"})
        value = partner.read([name])[0][name]
        self.assertEqual(
            [(item["name"], item["string"], item["value"]) for item in value],
            [(PROPERTY, "Size", "L")],
        )
        self.assertTrue(self.form_arch().xpath(f"//field[@name='{name}']"))
        # The definition never changes once applied.
        self.assertFalse(
            self.project._field_differences(
                row,
                self.project._field_vals(
                    "res.partner", name, change._payload()["field"]
                ),
            )
        )

    def test_container_lands_before_the_field(self):
        container = "commercial_partner_id"
        self.assertFalse(self.form_arch().xpath(f"//field[@name='{container}']"))
        change = self.add(
            definition_record=container,
            definition_new={"name": "x_studio_definitions"},
        )
        payload = change._payload()
        self.assertEqual(payload["container"], container)
        self.assertEqual(payload["field"]["relation"], "res.partner")
        self.assertEqual(
            payload["field"]["definition_new"]["field_description"],
            "Contact properties",
        )
        name = change.field_name
        self.project.action_apply()
        studio_view = self.project.studio_view_ids.filtered(
            lambda v: v.inherit_id == self.form
        )
        spec = etree.fromstring(studio_view.arch)
        nodes = [node.get("name") for node in spec.iter("field")]
        self.assertEqual(nodes[nodes.index(container) + 1], name)
        arch = self.form_arch()
        names = [node.get("name") for node in arch.xpath(f"{VAT}/following::field")]
        self.assertEqual(names[:2], [container, name])

    def test_drop_in_a_sub_view_is_refused(self):
        form = self.make_view(
            "form",
            "<form><field name='name'/><field name='child_ids'>"
            "<form><group name='studio_child'><field name='name'/></group></form>"
            "</field></form>",
        )
        with self.assertRaisesRegex(UserError, "not in the sub-view of a relation"):
            self.add(
                form,
                target="//group[@name='studio_child']/field[@name='name']",
            )

    def test_definition_must_resolve_to_load(self):
        change = self.add()
        name = change.field_name
        self.project.action_apply()
        data = dict(self.Fields._get_manual_field_data("res.partner")[name])
        attrs = self.Fields._instanciate_attrs(data)
        self.assertEqual(attrs["definition"], f"country_id.{COMPANION}")
        for value in (None, "", "country_id", "a.b.c", "country_id.X-bad"):
            with self.subTest(value=value):
                data["erplibre_studio_properties_definition"] = value
                with self.assertLogs(
                    "odoo.addons.erplibre_studio.models.ir_model_fields", "WARNING"
                ):
                    self.assertIsNone(self.Fields._instanciate_attrs(data))
        # A definition well formed that names no field of the registry: the
        # field is left out, the model still loads.
        self.registry.registry_invalidated = True
        for value in ("vat.x_partner_properties", "country_id.x_studio_missing"):
            with self.subTest(value=value):
                self.env.cr.execute(
                    "UPDATE ir_model_fields "
                    "SET erplibre_studio_properties_definition = %s WHERE id = %s",
                    [value, self.Fields._get("res.partner", name).id],
                )
                self.registry.clear_cache()
                with self.assertLogs(
                    "odoo.addons.erplibre_studio.models.ir_model_fields", "WARNING"
                ):
                    self.registry.setup_models(self.env.cr)
                self.assertNotIn(name, self.env["res.partner"]._fields)
                self.env["res.partner"].search([], limit=1).read(["name"])

    def test_removal_follows_the_container(self):
        region = self.add_region()
        # Dropped beside the vat, not on the node the many2one adds: a node
        # dropped on it would leave with it.
        change = self.add(definition_record=region.field_name)
        self.assertNotIn("container", change._payload())
        with self.assertRaisesRegex(UserError, "reads its definition through"):
            with self.env.cr.savepoint():
                self.op(
                    self.project,
                    self.form,
                    type="remove",
                    target=f"//field[@name='{region.field_name}']",
                )
        with self.assertRaisesRegex(UserError, "reads its definition through"):
            with self.env.cr.savepoint():
                self.op(
                    self.project,
                    self.form,
                    type="rename_field",
                    field_name=region.field_name,
                    new_name="x_studio_area",
                )
        # The companion is renamed with the definition that names it.
        self.op(
            self.project,
            self.env.ref("base.view_country_form"),
            type="rename_field",
            field_name=COMPANION,
            new_name="x_studio_sizes",
        )
        definition = change._payload()["field"]
        self.assertEqual(
            (definition["definition_record_field"], definition["definition_new"]),
            (
                "x_studio_sizes",
                {"name": "x_studio_sizes", "field_description": "Partner properties"},
            ),
        )
        removed = self.project._studio_inverse_dependents(change)
        self.assertEqual(removed, change)
        self.op(
            self.project,
            self.form,
            type="remove",
            target=f"//field[@name='{change.field_name}']",
        )
        self.assertFalse(self.project._studio_field_definitions("res.country"))
        self.assertEqual(self.project._project_field_changes(), region)

    def test_revert_drops_both_fields(self):
        region = self.add_region()
        change = self.add(
            target=f"//field[@name='{region.field_name}']",
            definition_record=region.field_name,
        )
        name = change.field_name
        self.project.action_apply()
        self.assertEqual(
            self.env["res.partner"]._fields[name].definition,
            f"{region.field_name}.{COMPANION}",
        )
        # Odoo refuses to unlink the many2one with the field that depends on
        # it in one batch: Revert unlinks the properties field first.
        with self.assertRaisesRegex(UserError, "depends on it"):
            with self.env.cr.savepoint():
                (
                    self.Fields._get("res.partner", region.field_name)
                    | self.Fields._get("res.partner", name)
                ).unlink()
        report = self.project._studio_revert_report()
        listed = {(f["model"], f["name"]) for f in report["report"]["fields"]}
        self.assertTrue(
            {
                ("res.partner", name),
                ("res.partner", region.field_name),
                ("res.country", COMPANION),
            }
            <= listed
        )
        self.project.action_revert(digest=report["digest"])
        for model, field_name in (
            ("res.partner", name),
            ("res.partner", region.field_name),
            ("res.country", COMPANION),
        ):
            with self.subTest(field=field_name):
                self.assertFalse(self.Fields._get(model, field_name))
                self.assertNotIn(field_name, self.env[model]._fields)

    def test_choices(self):
        choices = self.Editor.get_properties_choices(self.project.id, "res.partner")
        containers = {item["name"]: item for item in choices["containers"]}
        country = containers["country_id"]
        self.assertEqual(
            (country["comodel"], country["pending"]), ("res.country", False)
        )
        self.assertEqual(
            country["proposed"],
            {"name": "x_contact_properties", "label": "Contact properties"},
        )
        self.assertEqual(country["definitions"], [])
        # The models the studio adds no field to are left out.
        for name in ("user_id", "company_id", "create_uid"):
            self.assertNotIn(name, containers)
        region = self.add_region()
        choices = self.Editor.get_properties_choices(self.project.id, "res.partner")
        containers = {item["name"]: item for item in choices["containers"]}
        self.assertTrue(containers[region.field_name]["pending"])

    def test_palette(self):
        change = self.add()
        name = change.field_name
        self.project.action_apply()
        country_form = self.env.ref("base.view_country_form")
        data = self.Editor.get_editor_data(
            "res.country", country_form.id, "form", self.project.id
        )
        palette = [item["name"] for item in data["palette"]]
        self.assertNotIn(COMPANION, palette)
        self.assertIn("properties", data["field_types"])
        data = self.Editor.get_editor_data(
            "res.partner", self.list.id, "list", self.project.id
        )
        self.assertNotIn(name, [item["name"] for item in data["palette"]])

    def test_simulation_shows_a_placeholder(self):
        line = self.make_model(self.project, "Studio test item", model=ITEM)
        self.Editor.apply_operation(
            self.project.id,
            ITEM,
            False,
            "form",
            {
                "type": "add_field",
                "target": LEFT,
                "position": "inside",
                "field": {
                    "field_description": "Country",
                    "ttype": "many2one",
                    "relation": "res.country",
                },
            },
            self.project.draft_revision,
        )
        self.Editor.apply_operation(
            self.project.id,
            ITEM,
            False,
            "form",
            {
                "type": "add_field",
                "target": LEFT,
                "position": "inside",
                "field": {
                    "field_description": "Item properties",
                    "ttype": "properties",
                    "definition_record": "x_country",
                    "definition_new": {"name": "x_studio_item_properties"},
                },
            },
            self.project.draft_revision,
        )
        data = self.project._studio_simulated_views(line)
        info = data["models"][ITEM]["fields"]["x_item_properties"]
        self.assertEqual(
            (info["type"], info["definition_record"]), ("properties", "x_country")
        )
        form = etree.fromstring(data["views"]["form"]["arch"])
        self.assertFalse(form.xpath("//field[@name='x_item_properties']"))
        placeholder = form.xpath(
            "//div[contains(@class, 'o_erplibre_studio_pending')]"
            "[strong='Item properties']"
        )
        self.assertIn("Country", placeholder[0].xpath("string(span)"))
