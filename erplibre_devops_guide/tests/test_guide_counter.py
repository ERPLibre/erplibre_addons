# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase, tagged

LOGGER = "odoo.addons.erplibre_devops_guide"


@tagged("post_install", "-at_install")
class TestGuideCounter(TransactionCase):
    """Le compteur rend un nombre dans tous les cas, y compris en panne.

    Une page de présentation ne doit jamais empêcher l'ouverture d'un
    écran : un modèle inconnu, un domaine illisible ou un refus de droit
    rendent 0 et laissent une trace au journal.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env["devops.requirement.category"].create(
            {"code": "zz_test", "name": "Test domain"}
        )
        for index in range(3):
            cls.env["devops.requirement"].create(
                {
                    "name": f"Requirement {index}",
                    "category_id": cls.category.id,
                    "done": index == 0,
                }
            )
        cls.guide = cls.env["devops.guide"].create(
            {"name": "Test guide", "title": "Test"}
        )

    def _stat(self, **values):
        return self.env["devops.guide.stat"].create(
            dict({"guide_id": self.guide.id}, **values)
        )

    def test_literal_value_when_no_model(self):
        stat = self._stat(num="B2B", label="Market")
        self.assertEqual(stat.value, "B2B")

    def test_empty_literal_reads_as_empty_string(self):
        """Un Char vide se relit False : la valeur rendue reste une chaîne."""
        stat = self._stat(label="Nothing")
        self.assertEqual(stat.value, "")

    def test_count_without_total(self):
        stat = self._stat(
            label="Requirements",
            count_model="devops.requirement",
            count_domain=f"[('category_id', '=', {self.category.id})]",
        )
        self.assertEqual(stat.value, "3")

    def test_count_with_total_renders_a_ratio(self):
        stat = self._stat(
            label="Done",
            count_model="devops.requirement",
            count_domain=(
                f"[('category_id', '=', {self.category.id}),"
                " ('done', '=', True)]"
            ),
            total_domain=f"[('category_id', '=', {self.category.id})]",
        )
        self.assertEqual(stat.value, "1 / 3")

    def _assert_counts_zero_with_warning(self, message, **values):
        """Le zéro vient du chemin de secours, pas d'un hasard.

        Le message cherché est celui que seule la branche visée émet.
        """
        stat = self._stat(**values)
        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.assertEqual(stat.value, "0")
        self.assertIn(message, "\n".join(logs.output))

    def test_unknown_model_counts_zero(self):
        self._assert_counts_zero_with_warning(
            "Guide counter: unknown model",
            label="Ghost",
            count_model="devops.no.such.model",
        )

    def test_unreadable_domain_counts_zero(self):
        self._assert_counts_zero_with_warning(
            "Guide counter: unreadable domain",
            label="Broken",
            count_model="devops.requirement",
            count_domain="[('category_id', '=',",
        )

    def test_domain_that_is_not_a_list_counts_zero(self):
        self._assert_counts_zero_with_warning(
            "Guide counter: domain is not a list",
            label="Wrong shape",
            count_model="devops.requirement",
            count_domain="{'a': 1}",
        )

    def test_unknown_field_in_domain_counts_zero(self):
        self._assert_counts_zero_with_warning(
            "Guide counter: cannot count",
            label="Wrong field",
            count_model="devops.requirement",
            count_domain="[('no_such_field', '=', 1)]",
        )

    def test_card_label_substitutes_the_count(self):
        section = self.env["devops.guide.section"].create(
            {"guide_id": self.guide.id, "kind": "cards", "title": "S"}
        )
        card = self.env["devops.guide.card"].create(
            {
                "section_id": section.id,
                "title": "Domain",
                "action_label": "{count} requirements",
                "count_model": "devops.requirement",
                "count_domain": f"[('category_id', '=', {self.category.id})]",
            }
        )
        self.assertEqual(card.resolved_label, "3 requirements")

    def test_card_label_untouched_without_a_model(self):
        section = self.env["devops.guide.section"].create(
            {"guide_id": self.guide.id, "kind": "cards", "title": "S"}
        )
        card = self.env["devops.guide.card"].create(
            {
                "section_id": section.id,
                "title": "Plain",
                "action_label": "Open the pipeline",
            }
        )
        self.assertEqual(card.resolved_label, "Open the pipeline")

    def test_wrong_type_value_leaves_the_transaction_usable(self):
        """Une erreur SQL ne doit pas avorter la transaction de l'appelant."""
        stat = self._stat(
            label="Wrong type",
            count_model="devops.requirement",
            count_domain="[('id', '=', 'abc')]",
        )
        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.assertEqual(stat.value, "0")
        self.assertIn("Guide counter: cannot count", "\n".join(logs.output))
        # Une requête ordinaire APRÈS l'échec : elle casse sans savepoint.
        self.assertEqual(
            self.env["devops.requirement"].search_count(
                [("category_id", "=", self.category.id)]
            ),
            3,
        )

    def test_failing_total_domain_renders_zero_total(self):
        stat = self._stat(
            label="Broken total",
            count_model="devops.requirement",
            count_domain="[('no_such_field', '=', 1)]",
            total_domain="[('no_such_field', '=', 1)]",
        )
        with self.assertLogs(LOGGER, "WARNING"):
            self.assertEqual(stat.value, "0 / 0")

    def _card(self, **values):
        section = self.env["devops.guide.section"].create(
            {"guide_id": self.guide.id, "kind": "cards", "title": "S"}
        )
        return self.env["devops.guide.card"].create(
            dict({"section_id": section.id, "title": "C"}, **values)
        )

    def test_card_label_empty(self):
        card = self._card(count_model="devops.requirement")
        self.assertEqual(card.resolved_label, "")

    def test_card_label_without_marker_keeps_text(self):
        card = self._card(
            action_label="Open", count_model="devops.requirement"
        )
        self.assertEqual(card.resolved_label, "Open")

    def test_card_label_marker_without_model_is_untouched(self):
        card = self._card(action_label="{count} requirements")
        self.assertEqual(card.resolved_label, "{count} requirements")

    def test_deleting_a_guide_cascades(self):
        card = self._card(action_label="x")
        stat = self._stat(label="S")
        section = card.section_id
        self.guide.unlink()
        self.assertFalse(section.exists())
        self.assertFalse(card.exists())
        self.assertFalse(stat.exists())

    def test_sections_are_ordered_by_sequence(self):
        guide = self.env["devops.guide"].create(
            {"name": "Ordered", "title": "Ordered"}
        )
        for seq, title in ((30, "c"), (10, "a"), (20, "b")):
            self.env["devops.guide.section"].create(
                {"guide_id": guide.id, "sequence": seq, "title": title}
            )
        guide.invalidate_recordset(["section_ids"])
        self.assertEqual(guide.section_ids.mapped("title"), ["a", "b", "c"])
