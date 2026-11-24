# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo.tests import tagged

from .. import arch as studio_arch
from .common import StudioCase

FORM = """
<form>
    <sheet>
        <group name="g">
            <field name="name"/>
            <field name="phone"/>
            <field name="mobile"/>
            <field name="email"/>
            <field name="website"/>
        </group>
    </sheet>
</form>
"""


@tagged("post_install", "-at_install")
class TestChangeSubject(StudioCase):
    """The ``subject`` of each change of the editor payload: what its plain
    sentence names, read in the arch right before the change, so that the
    Simple level never shows an XPath nor a technical name."""

    def setUp(self):
        super().setUp()
        self.view = self.make_view("form", FORM)
        self.project = self.make_project("studio_test_subject")
        self.labels = {
            name: info["string"]
            for name, info in self.env["res.partner"]
            .fields_get(["phone", "mobile", "email", "website", "vat"], ["string"])
            .items()
        }

    def subjects(self, view=None, view_type="form"):
        data = self.Editor.get_editor_data(
            "res.partner", (view or self.view).id, view_type, self.project.id
        )
        return {change["id"]: change for change in data["changes"]}

    def op(self, **operation):
        return super().op(self.project, self.view, **operation)

    def test_subject_of_each_kind_of_change(self):
        def named(name):
            return f"//field[@name='{name}']"

        added = self.op(
            type="add_field",
            target=named("email"),
            position="after",
            field={"ttype": "char", "field_description": "Partner level"},
        )
        existing = self.op(
            type="add_existing_field",
            target=named("name"),
            position="after",
            field_name="vat",
        )
        relabel = self.op(type="relabel", target=named("email"), value="Work email")
        required = self.op(type="required", target=named("phone"), value=True)
        readonly = self.op(type="readonly", target=named("mobile"), value=True)
        hidden = self.op(type="hide", target=named("website"), value=True)
        moved = self.op(
            type="move",
            source=named("phone"),
            target=named("mobile"),
            position="after",
        )
        tab = self.op(
            type="add_page",
            target="//group[@name='g']",
            position="after",
            label="Loyalty",
        )
        subjects = self.subjects()
        level_label = subjects[added.id]["subject"]["label"]
        self.assertEqual(level_label, "Partner level")
        expected = {
            existing.id: (self.labels["vat"], "field", False),
            # The label before the change: the sentence reads « Email
            # renamed Work email ».
            relabel.id: (self.labels["email"], "field", "Work email"),
            required.id: (self.labels["phone"], "field", True),
            readonly.id: (self.labels["mobile"], "field", True),
            hidden.id: (self.labels["website"], "field", True),
        }
        for change_id, (label, tag, value) in expected.items():
            subject = subjects[change_id]["subject"]
            with self.subTest(type=subjects[change_id]["type"]):
                self.assertEqual(
                    (subject["label"], subject["tag"], subject["value"]),
                    (label, tag, value),
                )
        move = subjects[moved.id]["subject"]
        self.assertEqual(
            (move["label"], move["anchor"], move["position"]),
            (self.labels["phone"], self.labels["mobile"], "after"),
        )
        # A first tab comes with its notebook: the tab names it.
        page = subjects[tab.id]["subject"]
        self.assertEqual(
            (page["label"], page["tag"], page["kind"]),
            ("Loyalty", "notebook", "notebook"),
        )
        # No subject carries an XPath or a technical name.
        for change in subjects.values():
            text = repr(change["subject"])
            self.assertNotIn("//", text)
            self.assertNotIn("x_", text)

    def test_subject_of_a_change_that_does_not_apply(self):
        """A change whose node left the view still has a subject, without a
        label: the editor then names the element of its block, or says « An
        element »."""
        broken = self.project._add_change(
            self.view,
            "required",
            "//field[@name='studio_test_missing']",
            "attributes",
            {"value": True},
        )
        subject = self.subjects()[broken.id]["subject"]
        self.assertTrue(self.subjects()[broken.id]["error"])
        self.assertEqual((subject["label"], subject["tag"]), (False, False))
        self.assertIs(subject["value"], True)

    def test_subject_of_a_removal_from_a_search_view(self):
        """A search view hides by removing: the change is a « remove », and
        its subject names the filter it takes out."""
        search = self.env.ref("base.view_res_partner_filter")
        target = "//filter[@name='type_company']"
        label = (
            etree.fromstring(search.get_combined_arch()).xpath(target)[0].get("string")
        )
        removed = super().op(self.project, search, type="remove", target=target)
        change = self.subjects(search, "search")[removed.id]
        self.assertEqual(change["type"], "remove")
        self.assertEqual(
            (change["subject"]["label"], change["subject"]["tag"]),
            (label, "filter"),
        )

    def test_apply_changes_observes_the_arch_before_each_change(self):
        arch = etree.fromstring(FORM)
        changes = [
            {
                "key": 1,
                "type": "relabel",
                "xpath": "//field[@name='email']",
                "position": "attributes",
                "payload": {"value": "Mail"},
            },
            {
                "key": 2,
                "type": "relabel",
                "xpath": "//field[@name='email']",
                "position": "attributes",
                "payload": {"value": "Work email"},
            },
        ]
        seen = []

        def observe(before, change):
            node = before.xpath("//field[@name='email']")[0]
            seen.append((change["key"], node.get("string")))

        result, errors = studio_arch.apply_changes(
            arch, changes, "form", observe=observe
        )
        self.assertFalse(errors)
        self.assertEqual(seen, [(1, None), (2, "Mail")])
        self.assertEqual(
            result.xpath("//field[@name='email']")[0].get("string"), "Work email"
        )
        subject = studio_arch.change_subject(
            arch, changes[0], "form", {"email": {"string": "Email"}}
        )
        self.assertEqual(
            subject,
            {
                "label": "Email",
                "tag": "field",
                "kind": False,
                "anchor": False,
                "position": False,
                "value": "Mail",
            },
        )
