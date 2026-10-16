# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestGuidePage(TransactionCase):
    """`get_page` rend une page entière, sans un seul False.

    Un Char, un Text, un Html ou un Many2one vide se relit False côté
    Python. Rendu tel quel au navigateur, il s'affiche « false ».
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.guide = cls.env["devops.guide"].create(
            {
                "name": "Page test",
                "title": "A title",
                "eyebrow": "An eyebrow",
            }
        )
        cls.lead = cls.env["devops.guide.section"].create(
            {
                "guide_id": cls.guide.id,
                "kind": "lead",
                "sequence": 1,
                "title": "The need",
                "intro": "<p>Dispersed <strong>data</strong>.</p>",
            }
        )
        cls.cards = cls.env["devops.guide.section"].create(
            {
                "guide_id": cls.guide.id,
                "kind": "cards",
                "sequence": 2,
                "num": "1",
                "title": "Foundation",
            }
        )
        cls.env["devops.guide.card"].create(
            {
                "section_id": cls.cards.id,
                "title": "A card",
                "icon": "fa-database",
                "action_label": "Open",
                "action_xmlid": "base.action_res_users",
            }
        )
        cls.env["devops.guide.stat"].create(
            {"guide_id": cls.guide.id, "num": "42", "label": "Things"}
        )

    def test_page_carries_no_false(self):
        page = self.guide.get_page()
        flat = []

        def walk(value):
            if isinstance(value, dict):
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
            else:
                flat.append(value)

        walk(page)
        # `in` compare par égalité, et 0 == False : comparer par identité,
        # sinon un futur champ valant 0 ferait échouer le test à tort.
        self.assertFalse(
            [value for value in flat if value is False],
            "get_page must not leak a False",
        )

    def test_sections_are_ordered_and_typed(self):
        # Créées dans l'ordre INVERSE de leur `sequence` : un tri par id
        # rendrait ["cards", "lead"] et le test échouerait.
        guide = self.env["devops.guide"].create(
            {"name": "Order test", "title": "Order"}
        )
        section = self.env["devops.guide.section"]
        section.create({"guide_id": guide.id, "kind": "cards", "sequence": 20})
        section.create({"guide_id": guide.id, "kind": "lead", "sequence": 10})
        guide.invalidate_recordset(["section_ids"])
        kinds = [item["kind"] for item in guide.get_page()["sections"]]
        self.assertEqual(kinds, ["lead", "cards"])

    def test_lead_keeps_its_markup(self):
        page = self.guide.get_page()
        self.assertIn("<strong>", page["sections"][0]["intro"])

    def test_cards_travel_with_their_section(self):
        page = self.guide.get_page()
        self.assertEqual(len(page["sections"][1]["cards"]), 1)
        self.assertEqual(page["sections"][1]["cards"][0]["title"], "A card")

    def test_stat_value_is_resolved_not_raw(self):
        # `num` vaut 99 mais le décompte borné à ce guide en rend 2 : rendre
        # `num` brut donnerait "99".
        stat = self.env["devops.guide.stat"].create(
            {
                "guide_id": self.guide.id,
                "sequence": 99,
                "num": "99",
                "label": "Counted",
                "count_model": "devops.guide.section",
                "count_domain": f"[('guide_id', '=', {self.guide.id})]",
            }
        )
        self.assertEqual(stat.value, "2")
        page = self.guide.get_page()
        self.assertEqual(page["stats"][-1]["value"], "2")

    def test_literal_stat_keeps_its_number(self):
        self.assertEqual(self.guide.get_page()["stats"][0]["value"], "42")

    def test_card_label_is_resolved_not_raw(self):
        # Rendre `action_label` brut laisserait « {count} » à l'écran.
        guide = self.env["devops.guide"].create(
            {"name": "Label test", "title": "Label"}
        )
        section = self.env["devops.guide.section"].create(
            {"guide_id": guide.id, "kind": "cards"}
        )
        self.env["devops.guide.card"].create(
            {
                "section_id": section.id,
                "title": "Counted",
                "action_label": "Open {count} sections",
                "count_model": "devops.guide.section",
                "count_domain": f"[('guide_id', '=', {guide.id})]",
            }
        )
        card = guide.get_page()["sections"][0]["cards"][0]
        self.assertEqual(card["action_label"], "Open 1 sections")

    def test_resolve_by_xmlid(self):
        self.env["ir.model.data"].create(
            {
                "module": "erplibre_devops_guide",
                "name": "guide_page_test",
                "model": "devops.guide",
                "res_id": self.guide.id,
            }
        )
        found = (
            self.env["devops.guide"]
            .with_context(guide_xmlid="erplibre_devops_guide.guide_page_test")
            ._resolve_from_context()
        )
        self.assertEqual(found, self.guide)

    def test_resolve_by_id(self):
        found = (
            self.env["devops.guide"]
            .with_context(guide_id=self.guide.id)
            ._resolve_from_context()
        )
        self.assertEqual(found, self.guide)

    def test_resolve_without_context_is_empty(self):
        found = self.env["devops.guide"]._resolve_from_context()
        self.assertFalse(found)

    def test_resolve_refuses_a_foreign_model_xmlid(self):
        # Une vue du module existe, mais n'est pas un `devops.guide`.
        found = (
            self.env["devops.guide"]
            .with_context(
                guide_xmlid="erplibre_devops_guide.view_devops_guide_form"
            )
            ._resolve_from_context()
        )
        self.assertFalse(found)
        self.assertEqual(found._name, "devops.guide")

    def test_resolve_unknown_xmlid_is_empty(self):
        found = (
            self.env["devops.guide"]
            .with_context(guide_xmlid="erplibre_devops_guide.no_such_guide")
            ._resolve_from_context()
        )
        self.assertFalse(found)

    def test_resolve_unknown_id_is_empty(self):
        found = (
            self.env["devops.guide"]
            .with_context(guide_id=999999999)
            ._resolve_from_context()
        )
        self.assertFalse(found)
