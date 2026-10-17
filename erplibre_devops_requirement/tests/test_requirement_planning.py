# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError


@tagged("post_install", "-at_install")
class TestRequirementPlanning(TransactionCase):
    """Un requis se retrouve sans ambiguïté et se planifie sans boucle.

    Le code est unique, les dépendances ne forment jamais de cycle, et
    l'état des tests résume les lignes de test par leur pire résultat.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env["devops.requirement.category"].create(
            {"code": "zz_test", "name": "Test domain"}
        )
        cls.req_a, cls.req_b, cls.req_c = cls.env["devops.requirement"].create(
            [
                {
                    "code": f"ZZ-0{index}",
                    "name": f"Requirement {index}",
                    "category_id": cls.category.id,
                }
                for index in (1, 2, 3)
            ]
        )

    def _requirement(self, **values):
        return self.env["devops.requirement"].create(
            dict(
                {"name": "Inventory", "category_id": self.category.id},
                **values,
            )
        )

    def _test_line(self, requirement, result, kind="python", **values):
        index = len(requirement.test_ids)
        return self.env["devops.requirement.test"].create(
            dict(
                {
                    "requirement_id": requirement.id,
                    "kind": kind,
                    "reference": f"zz_test.{result}.{index}",
                    "last_result": result,
                },
                **values,
            )
        )

    def test_defaults(self):
        requirement = self._requirement()
        self.assertEqual(requirement.devsecops_stage, "plan")
        self.assertEqual(requirement.requirement_type, "functional")
        self.assertEqual(requirement.test_state, "none")
        self.assertEqual(requirement.test_count, 0)

    def test_code_is_unique(self):
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self._requirement(code="ZZ-01")

    def test_several_requirements_without_code(self):
        # PostgreSQL tient deux NULL pour distincts : sans cette tolérance,
        # le second requis sans code lèverait une IntegrityError.
        first = self._requirement()
        second = self._requirement()
        self.assertFalse(first.code or second.code)

    def test_dependency_cycle_is_refused(self):
        self.req_b.depends_on_ids = self.req_a
        self.req_c.depends_on_ids = self.req_b
        # A → C ferme la boucle A → C → B → A par deux sauts : un contrôle
        # limité aux dépendances directes la laisserait passer.
        with self.assertRaises(ValidationError):
            self.req_a.depends_on_ids = self.req_c

    def test_self_dependency_is_refused(self):
        with self.assertRaises(ValidationError):
            self.req_a.depends_on_ids = self.req_a

    def test_dependent_ids_mirror_depends_on_ids(self):
        self.req_b.depends_on_ids = self.req_a
        self.assertEqual(self.req_a.dependent_ids, self.req_b)

    def test_state_failed_wins(self):
        requirement = self._requirement()
        for result in ("passed", "not_run", "skipped", "failed"):
            self._test_line(requirement, result)
        self.assertEqual(requirement.test_state, "failed")

    def test_state_error_counts_as_failed(self):
        requirement = self._requirement()
        self._test_line(requirement, "passed")
        self._test_line(requirement, "error")
        self.assertEqual(requirement.test_state, "failed")

    def test_state_not_run_blocks_passed(self):
        requirement = self._requirement()
        self._test_line(requirement, "passed")
        self._test_line(requirement, "not_run")
        self.assertEqual(requirement.test_state, "not_run")

    def test_state_passed_ignores_skipped(self):
        requirement = self._requirement()
        self._test_line(requirement, "passed")
        self._test_line(requirement, "skipped")
        self.assertEqual(requirement.test_state, "passed")
        self.assertEqual(requirement.test_count, 2)

    def test_state_all_skipped_proves_nothing(self):
        requirement = self._requirement()
        self._test_line(requirement, "skipped")
        self.assertEqual(requirement.test_state, "not_run")

    def test_state_follows_last_result(self):
        # Le champ est stocké : sans `depends` sur last_result, il
        # garderait « passed » après l'échec et le filtre « Failing tests »
        # manquerait ce requis.
        requirement = self._requirement()
        line = self._test_line(requirement, "passed")
        self.assertEqual(requirement.test_state, "passed")
        line.last_result = "failed"
        self.assertEqual(
            self.env["devops.requirement"].search(
                [("test_state", "=", "failed"), ("id", "=", requirement.id)]
            ),
            requirement,
        )

    def test_tour_name_is_first_tour_by_sequence(self):
        requirement = self._requirement()
        self.assertEqual(requirement.tour_name, "")
        self._test_line(requirement, "not_run", kind="python", sequence=1)
        self._test_line(
            requirement,
            "not_run",
            kind="tour",
            sequence=20,
            reference="zz_late",
        )
        self._test_line(
            requirement,
            "not_run",
            kind="tour",
            sequence=5,
            reference="zz_first",
        )
        # Créée après « zz_late » mais de séquence plus basse : un tri par
        # id rendrait « zz_late ».
        self.assertEqual(requirement.tour_name, "zz_first")

    def test_residual_risk_labels_are_distinct(self):
        # Un libellé anglais partagé avec `priority` ou `size` ne ferait
        # qu'une entrée de traduction pour deux accords différents.
        requirement_model = self.env["devops.requirement"]
        taken = {
            label
            for field_name in ("priority", "size")
            for _key, label in requirement_model._fields[field_name].selection
        }
        risk = self.env["devops.requirement.threat"]._fields["residual_risk"]
        labels = {label for _key, label in risk.selection}
        self.assertEqual(len(labels), 3)
        self.assertFalse(labels & taken, "residual_risk reuses a label")

    def test_stage_labels_are_not_field_labels(self):
        # Une étape libellée comme un champ du module partagerait son
        # entrée de traduction : l'étape « code » ne pourrait pas se dire
        # comme une activité tant que le champ `code` s'appelle « Code ».
        field_labels = {
            field.string
            for model_name in (
                "devops.requirement",
                "devops.requirement.category",
                "devops.requirement.phase",
                "devops.requirement.test",
                "devops.requirement.threat",
            )
            for field in self.env[model_name]._fields.values()
        }
        stage = self.env["devops.requirement"]._fields["devsecops_stage"]
        stage_labels = {label for _key, label in stage.selection}
        self.assertEqual(len(stage_labels), 8)
        self.assertFalse(
            stage_labels & field_labels, "devsecops_stage reuses a field label"
        )
