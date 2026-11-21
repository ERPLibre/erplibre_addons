# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
from unittest.mock import patch

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
TEXTE = "//field[@name='texte']"
# A rule that allows a name without x_, as a development database has.
DEVELOPMENT_RULE = {
    "prefix_required": False,
    "mode": "development",
    "label": "Development · x_ optional",
    "text": "Without x_ allowed: development database",
    "detail": "",
}


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


@tagged("post_install", "-at_install")
class TestUnprefixedRule(StudioCase):
    """The technical name of a new field on a database whose rule allows a
    name without x_: the other checks still refuse what would collide, the
    texts people read do not name a field, and a database that requires
    x_ again blocks such a draft before Apply writes it."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project(MODULE)
        self.Change = self.env["erplibre.studio.change"]

    def development(self):
        return patch.object(
            type(self.Project),
            "_studio_field_name_rule",
            lambda self_: dict(DEVELOPMENT_RULE),
        )

    def add(self, label, **f):
        return self.op(
            self.project,
            self.form,
            type="add_field",
            target=VAT,
            position="after",
            field={"ttype": "char", "field_description": label, **f},
        )

    def rename(self, change, new_name):
        return self.op(
            self.project,
            self.form,
            type="rename_field",
            field_name=change.field_name,
            new_name=new_name,
        )

    def names(self, change_type, xpath, payload, names=("texte",)):
        change = self.Change.new(
            {
                "change_type": change_type,
                "xpath": xpath,
                "payload": json.dumps(payload),
            }
        )
        return self.project._studio_change_names(change, set(names))

    def test_unprefixed_name_in_the_draft(self):
        with self.development():
            change = self.add("Texte", name="texte")
            self.assertEqual(change.field_name, "texte")
            required = self.op(
                self.project, self.form, type="required", target=TEXTE, value=True
            )
            self.op(
                self.project,
                self.form,
                type="update_field",
                field_name="texte",
                field={"field_description": "Texte court"},
            )
            self.assertEqual(change.field_name, "texte")
            self.rename(change, "texte_court")
            self.assertEqual(change.field_name, "texte_court")
            self.assertEqual(required.xpath, "//field[@name='texte_court']")
            self.assertEqual(self.project._studio_field_name_problems(), [])
            arch = self.draft(self.project, self.form)
            self.assertEqual(len(arch.xpath("//field[@name='texte_court']")), 1)

    def test_refusals_without_the_prefix(self):
        cases = {
            "login": "unique",
            "name": "unique",
            "write": "reserved",
            "class": "reserved",
            "_x": "reserved",
            "in_group_3": "reserved",
            "Texte": "format",
        }
        with self.development():
            for name, code in cases.items():
                with self.subTest(name=name):
                    problem = self.project._studio_field_name_problem(PARTNER, name)
                    self.assertEqual(problem["code"], code)
            # A field of res.users, which inherits res.partner by delegation.
            login = self.project._studio_field_name_problem(PARTNER, "login")
            self.assertEqual(
                (login["owner"]["kind"], login["owner"]["model"]),
                ("child", "res.users"),
            )
            self.assertIn("which inherits", login["message"])
            self.assertEqual(
                self.project._studio_field_name_problem(PARTNER, "name")["owner"][
                    "kind"
                ],
                "model",
            )
            self.assertIsNone(self.project._studio_field_name_problem(PARTNER, "texte"))
            with self.assertRaises(UserError):
                self.add("Identifiant", name="login")

    def test_methods_of_the_inheriting_models_are_reserved(self):
        # res.users inherits res.partner by delegation and copies its
        # fields: a field « authenticate » of res.partner would replace the
        # login method of res.users.
        self.assertFalse(hasattr(type(self.env[PARTNER]), "authenticate"))
        names = ("authenticate", "check")
        for name in names:
            with self.subTest(name=name):
                problem = self.project._studio_field_name_problem(PARTNER, name)
                self.assertEqual(problem["code"], "reserved")
        with self.development():
            for name in names:
                with self.subTest(name=name, development=True):
                    problem = self.project._studio_field_name_problem(PARTNER, name)
                    self.assertEqual(problem["code"], "reserved")
            with self.assertRaises(UserError):
                self.add("Authenticate", name="authenticate")

    def test_reserved_names_of_a_model_not_created_yet(self):
        # The registry sets « pool » on every class; the chatter brings the
        # methods of the mail mixins.
        chatter = self.mail_available()
        self.make_model(self.project, "Studio test order", model=ORDER, chatter=chatter)
        self.make_model(self.project, "Studio test line", model=LINE)
        cases = [(ORDER, "pool", "reserved"), (LINE, "message_post", None)]
        if chatter:
            cases += [
                (ORDER, "message_post", "reserved"),
                (ORDER, "activity_schedule", "reserved"),
            ]
        with self.development():
            for model, name, code in cases:
                with self.subTest(model=model, name=name):
                    status = self.project._studio_field_name_status(model, name)
                    self.assertEqual(status["code"], code)

    def test_new_fields_of_a_parent_and_its_child_collide(self):
        # A new field of res.users and one of the same name on res.partner
        # would land on the same class of res.users.
        users_form = self.env.ref("base.view_users_form")
        self.op(
            self.project,
            users_form,
            type="add_field",
            target="//field[@name='tz']",
            position="after",
            field={"ttype": "char", "field_description": "Shared", "name": "x_shared"},
        )
        status = self.project._studio_field_name_status(PARTNER, "x_shared")
        self.assertEqual(status["code"], "unique")
        self.assertEqual(
            (status["owner"]["kind"], status["owner"]["model"]),
            ("child", "res.users"),
        )
        with self.assertRaises(UserError):
            self.add("Shared", name="x_shared")
        # From another project, the other way round.
        other = self.make_project(f"{MODULE}_other")
        self.op(
            other,
            self.form,
            type="add_field",
            target=VAT,
            position="after",
            field={"ttype": "char", "field_description": "Both", "name": "x_both"},
        )
        status = self.project._studio_field_name_status("res.users", "x_both")
        self.assertEqual(
            (status["owner"]["kind"], status["owner"]["model"]),
            ("parent", PARTNER),
        )
        self.assertEqual(status["owner"]["project"], other.name)
        self.assertIn("which", status["message"])
        self.assertEqual(self.project._studio_field_name_problems(), [])

    def test_inherited_field_of_the_model_is_no_collision(self):
        # res.users shows the fields of res.partner: they are not its own.
        self.assertIsNone(self.Project._studio_inheriting_owner(PARTNER, "email"))
        self.assertEqual(
            self.Project._studio_inheriting_owner(PARTNER, "login"), "res.users"
        )
        self.assertIsNone(self.Project._studio_inheriting_owner("res.users", "login"))

    def test_human_texts_name_no_field(self):
        self.assertEqual(self.names("relabel", VAT, {"value": "texte"}), set())
        self.assertEqual(self.names("help", VAT, {"value": "texte"}), set())
        selection = {
            "field_name": "x_choix",
            "field": {
                "ttype": "selection",
                "field_description": "texte",
                "help": "texte",
                "selection": [["texte", "texte"]],
            },
        }
        self.assertEqual(self.names("add_field", VAT, selection), set())
        inverse = {
            "field_name": "x_parent",
            "field": {
                "ttype": "many2one",
                "relation": PARTNER,
                "inverse_o2m": {"name": "x_enfants", "field_description": "texte"},
            },
        }
        self.assertEqual(self.names("add_field", VAT, inverse), set())
        ribbon = {"node": {"tag": "widget", "attrs": {"title": "texte"}}}
        self.assertEqual(self.names("add_node", VAT, ribbon), set())
        # A path, a domain or an expression still names it.
        self.assertEqual(self.names("required", TEXTE, {"value": True}), {"texte"})
        node = {
            "node": {
                "tag": "filter",
                "attrs": {"string": "texte", "domain": "[('texte', '=', 1)]"},
            }
        }
        self.assertEqual(self.names("add_node", VAT, node), {"texte"})
        expression = {"attribute": "invisible", "value": "texte == False"}
        self.assertEqual(self.names("set_attribute", VAT, expression), {"texte"})
        self.assertEqual(
            self.names("add_field", VAT, {"field_name": "texte"}), {"texte"}
        )

    def test_production_blocks_an_unprefixed_draft(self):
        with self.development():
            change = self.add("Texte", name="texte")
            self.assertFalse(self.Editor.get_review(self.project.id)["name_blockers"])
        # The rule is read on each call: the same draft no longer applies.
        review = self.Editor.get_review(self.project.id)
        self.assertEqual([b["name"] for b in review["name_blockers"]], ["texte"])
        with self.assertRaisesRegex(UserError, "texte"):
            self.project.action_apply()
        with self.assertRaisesRegex(UserError, "needs the x_ prefix"):
            self.project._apply_fields([])
        self.assertFalse(
            self.env["ir.model.fields"].sudo()._get(PARTNER, "texte"),
        )
        # Still pending: renamed, it applies.
        self.rename(change, "x_texte")
        self.assertFalse(self.Editor.get_review(self.project.id)["name_blockers"])
        self.project.action_apply()
        self.assertTrue(self.env["ir.model.fields"].sudo()._get(PARTNER, "x_texte"))
