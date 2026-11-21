# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models.studio_pending import pending_view
from .common import StudioCase

MODULE = "studio_test_fname"
PARTNER = "res.partner"
ORDER = "x_studio_test_fname_order"
LINE = "x_studio_test_fname_line"
LEFT = "//group[@name='studio_left']"
VAT = "//field[@name='vat']"


@tagged("post_install", "-at_install")
class TestFieldName(StudioCase):
    """The technical name of a new field: proposed after its label, checked
    against the rule of the database, the ORM, the model and the projects,
    renamed with the changes that name it until Apply creates it."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project(MODULE)

    def add(self, label, view=None, target=VAT, position="after", project=None, **f):
        return self.op(
            project or self.project,
            view or self.form,
            type="add_field",
            target=target,
            position=position,
            field={"ttype": "char", "field_description": label, **f},
        )

    def rename(self, change, new_name=None, auto=False, view=None):
        return self.op(
            self.project,
            view or self.form,
            type="rename_field",
            field_name=change.field_name,
            new_name=new_name,
            auto=auto,
        )

    def relabel_field(self, change, label, view=None):
        return self.op(
            self.project,
            view or self.form,
            type="update_field",
            field_name=change.field_name,
            field={"field_description": label},
        )

    def code(self, name, own="x_texte", model=PARTNER):
        problem = self.project._studio_field_name_problem(model, name, own=own)
        return problem and problem["code"]

    def test_proposed_names_are_deduplicated(self):
        first = self.add("Texte")
        second = self.add("Texte")
        self.assertEqual(
            (first.field_name, second.field_name), ("x_texte", "x_texte_2")
        )
        self.assertTrue(first._payload()["name_auto"])
        other = self.make_project("studio_test_fname_other")
        third = self.add("Texte", project=other)
        self.assertEqual(third.field_name, "x_texte_3")

    def test_given_name_is_kept(self):
        change = self.add("Texte", name="x_mon_code")
        self.assertEqual(change.field_name, "x_mon_code")
        self.assertFalse(change._payload()["name_auto"])
        with self.assertRaises(UserError):
            self.add("Texte", name="x_mon_code")
        with self.assertRaises(UserError):
            self.add("Texte", name="mon_code")

    def test_rename_rewrites_the_changes_that_name_it(self):
        change = self.add("Texte", view=self.list, target="//field[@name='email']")
        target = "//field[@name='x_texte']"
        required = self.op(
            self.project, self.list, type="required", target=target, value=True
        )
        move = self.op(
            self.project,
            self.list,
            type="move",
            source="//field[@name='email']",
            target=target,
            position="after",
        )
        self.rename(change, "x_note", view=self.list)
        self.assertEqual(change.field_name, "x_note")
        self.assertFalse(change._payload()["name_auto"])
        self.assertIn("x_note", change.summary)
        self.assertEqual(required.xpath, "//field[@name='x_note']")
        self.assertEqual(move.xpath, "//field[@name='x_note']")
        self.assertEqual(move._payload()["source"], "//field[@name='email']")
        self.assertNotIn("x_texte", required.summary + move.summary)
        columns = self.columns(self.draft(self.project, self.list))
        self.assertEqual(columns[columns.index("x_note") + 1], "email")
        self.assertNotIn("x_texte", columns)

    def test_rename_leaves_a_longer_name_alone(self):
        change = self.add("Texte")
        longer = self.add("Texte suite")
        target = "//field[@name='x_texte_suite']"
        required = self.op(
            self.project, self.form, type="required", target=target, value=True
        )
        self.rename(change, "x_note")
        self.assertEqual(required.xpath, target)
        self.assertEqual(longer.field_name, "x_texte_suite")
        self.draft(self.project, self.form)

    def test_rename_refused_once_applied(self):
        change = self.add("Texte")
        self.project.action_apply()
        with self.assertRaisesRegex(UserError, "once applied"):
            self.rename(change, "x_note")
        self.assertEqual(change.field_name, "x_texte")

    def test_rename_refusals(self):
        change = self.add("Texte")
        self.add("Autre")
        applied = self.make_project("studio_test_fname_applied")
        self.add("Existant", project=applied)
        applied.action_apply()
        drafted = self.make_project("studio_test_fname_drafted")
        self.add("Brouillon", project=drafted)
        cases = {
            "Texte": ("format", None),
            "texte": ("prefix", None),
            "x_": ("prefix", None),
            "write": ("reserved", None),
            "_foo": ("reserved", None),
            "x_existant": ("unique", "model"),
            "x_brouillon": ("unique", "other"),
            "x_autre": ("unique", "project"),
        }
        for name, (code, kind) in cases.items():
            with self.subTest(name=name):
                problem = self.project._studio_field_name_problem(
                    PARTNER, name, own="x_texte"
                )
                self.assertEqual(problem["code"], code)
                if kind:
                    self.assertEqual(problem["owner"]["kind"], kind)
                with self.assertRaises(UserError):
                    self.rename(change, name)
                self.assertEqual(change.field_name, "x_texte")
        self.assertIsNone(self.code("x_libre"))
        # The own name, and the applied field of the project, are no conflict.
        self.assertIsNone(self.code("x_texte"))
        self.assertIsNone(
            applied._studio_field_name_problem(PARTNER, "x_existant", own="x_existant")
        )

    def test_name_follows_the_label_until_renamed(self):
        change = self.add("Texte")
        self.relabel_field(change, "Texte long")
        self.assertEqual(change.field_name, "x_texte_long")
        self.rename(change, "x_mon_nom")
        self.assertFalse(change._payload()["name_auto"])
        self.relabel_field(change, "Autre libellé")
        self.assertEqual(change.field_name, "x_mon_nom")
        self.assertEqual(
            change._payload()["field"]["field_description"], "Autre libellé"
        )
        self.rename(change, auto=True)
        self.assertEqual(change.field_name, "x_autre_libelle")
        self.assertTrue(change._payload()["name_auto"])
        # A draft made before the flag follows the label too.
        payload = change._payload()
        del payload["name_auto"]
        change._set_payload(payload)
        self.relabel_field(change, "Dernier")
        self.assertEqual(change.field_name, "x_dernier")

    def test_rename_refused_while_a_rule_names_the_field(self):
        line = self.make_model(self.project, "Studio test order", model=ORDER)
        form = pending_view(line, "form")
        change = self.add("Texte", view=form, target=LEFT, position="inside")
        required = self.op(
            self.project,
            form,
            type="required",
            target="//field[@name='x_texte']",
            value=True,
        )
        self.project._studio_save_rule(
            {
                "name": "Studio test rule",
                "model": ORDER,
                "domain": "[('x_texte', '=', 'a')]",
                "global_rule": True,
                "perm_read": True,
            }
        )
        with self.assertRaisesRegex(UserError, "Studio test rule"):
            self.rename(change, "x_note", view=form)
        self.assertEqual(change.field_name, "x_texte")
        self.assertEqual(required.xpath, "//field[@name='x_texte']")
        self.assertTrue(change._payload()["name_auto"])

    def test_many2many_table_follows_the_name(self):
        change = self.add(
            "Etiquettes", ttype="many2many", relation="res.partner.category"
        )
        before = change._payload()["field"]["relation_table"]
        self.assertIn("etiquettes", before)
        self.rename(change, "x_tags")
        definition = change._payload()["field"]
        self.assertEqual(
            definition["relation_table"], f"x_{MODULE}_res_partner_tags_rel"
        )
        self.assertEqual(
            (definition["column1"], definition["column2"]),
            ("res_partner_id", "res_partner_category_id"),
        )

    def test_one2many_follows_its_renamed_inverse(self):
        order = self.make_model(self.project, "Studio test order", model=ORDER)
        line = self.make_model(self.project, "Studio test line", model=LINE)
        line_form = pending_view(line, "form")
        parent = self.add(
            "Commande",
            view=line_form,
            target=LEFT,
            position="inside",
            ttype="many2one",
            relation=ORDER,
        )
        lines = self.add(
            "Lignes",
            view=pending_view(order, "form"),
            target=LEFT,
            position="inside",
            ttype="one2many",
            relation=LINE,
            relation_field="x_commande",
        )
        self.rename(parent, "x_order_ref", view=line_form)
        self.assertEqual(lines._payload()["field"]["relation_field"], "x_order_ref")

    def test_check_field_name(self):
        self.add("Texte")
        check = self.Editor.check_field_name
        result = check(self.project.id, PARTNER, "x_nouveau")
        self.assertEqual(result["status"], "available")
        self.assertEqual(
            [c["key"] for c in result["checks"]],
            ["format", "reserved", "prefix", "unique"],
        )
        self.assertTrue(all(c["ok"] for c in result["checks"]))
        self.assertEqual(
            (result["rule"]["prefix_required"], result["rule"]["mode"]),
            (True, "production"),
        )
        self.assertEqual(check(self.project.id, PARTNER, "x_texte")["status"], "taken")
        own = check(self.project.id, PARTNER, "x_texte", field_name="x_texte")
        self.assertEqual((own["status"], own["proposed"]), ("available", "x_texte"))
        invalid = check(self.project.id, PARTNER, "Texte")
        self.assertEqual(invalid["status"], "invalid")
        self.assertFalse(invalid["checks"][0]["ok"])
        proposed = check(self.project.id, PARTNER, "", label="Texte")
        self.assertEqual(
            (proposed["name"], proposed["proposed"], proposed["status"]),
            ("x_texte_2", "x_texte_2", "available"),
        )
        data = self.Editor.get_editor_data(
            PARTNER, self.form.id, "form", self.project.id
        )
        self.assertTrue(data["field_name_rule"]["prefix_required"])
        self.assertTrue(data["fields"]["x_texte"]["name_auto"])
        self.assertIn("rename_field", data["operations"])

    def test_forged_name_blocks_the_review(self):
        change = self.add("Texte")
        payload = change._payload()
        payload["field_name"] = "texte"
        change._set_payload(payload)
        review = self.Editor.get_review(self.project.id)
        self.assertEqual(len(review["name_blockers"]), 1)
        self.assertEqual(review["name_blockers"][0]["name"], "texte")
        self.assertIn("texte", review["blocked"])
        counts = self.Editor._project_counts(self.project)
        self.assertEqual(counts["name_blockers"], 1)
        with self.assertRaises(UserError):
            self.project.action_apply()
