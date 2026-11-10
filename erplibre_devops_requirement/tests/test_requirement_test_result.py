# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from ..models.devops_requirement_test import LOG_MAX_LENGTH, LOG_TRUNCATED_MARK

LOGGER = (
    "odoo.addons.erplibre_devops_requirement.models.devops_requirement_test"
)


@tagged("post_install", "-at_install")
class TestRequirementTestResult(TransactionCase):
    """`record_result` écrit le résultat d'un test déclaré, et rien d'autre.

    Seuls un lanceur et l'administrateur y ont droit ; un requis ou une
    ligne inconnus, ou un code vide, rendent False sans rien créer ni
    écrire ; un résultat hors de la liste est refusé. Ni le lanceur ni un
    utilisateur interne ne peuvent écrire un verdict par un autre chemin.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        category = cls.env["devops.requirement.category"].create(
            {"code": "zz_test", "name": "Test domain"}
        )
        cls.requirement = cls.env["devops.requirement"].create(
            {"code": "ZZ-01", "name": "Inventory", "category_id": category.id}
        )
        cls.line = cls.env["devops.requirement.test"].create(
            {
                "requirement_id": cls.requirement.id,
                "kind": "selenium",
                "reference": "script/zz_test/zz_inventory.py",
            }
        )
        cls.internal = new_test_user(
            cls.env, login="zz_internal", groups="base.group_user"
        )
        cls.runner = new_test_user(
            cls.env,
            login="zz_runner",
            groups=(
                "erplibre_devops_requirement.group_devops_requirement_runner"
            ),
        )

    def _record(self, user, result="passed", **kwargs):
        args = dict(
            code="ZZ-01",
            kind="selenium",
            reference="script/zz_test/zz_inventory.py",
            result=result,
        )
        args.update(kwargs)
        return (
            self.env["devops.requirement.test"]
            .with_user(user)
            .record_result(**args)
        )

    def test_internal_user_is_refused(self):
        with self.assertRaises(AccessError):
            self._record(self.internal)
        self.assertEqual(self.line.last_result, "not_run")

    def test_internal_user_reads_tests_but_cannot_write(self):
        line = self.line.with_user(self.internal)
        self.assertEqual(line.reference, "script/zz_test/zz_inventory.py")
        with self.assertRaises(AccessError):
            line.write({"last_result": "passed"})

    def test_runner_records_a_result(self):
        self.assertTrue(self._record(self.runner, duration=1.5, log="ok"))
        self.assertEqual(self.line.last_result, "passed")
        self.assertEqual(self.line.last_duration, 1.5)
        self.assertEqual(self.line.last_log, "ok")
        self.assertTrue(self.line.last_run)
        self.assertEqual(self.requirement.test_state, "passed")

    def test_runner_cannot_write_directly(self):
        # Le droit d'écriture du lanceur passe par la méthode seulement :
        # une écriture directe sur un autre champ reste refusée.
        with self.assertRaises(AccessError):
            self.line.with_user(self.runner).write({"reference": "zz_other"})

    def test_admin_records_a_result(self):
        self.assertTrue(
            self._record(self.env.ref("base.user_admin"), "failed")
        )
        self.assertEqual(self.requirement.test_state, "failed")

    def test_unknown_line_creates_nothing(self):
        before = self.env["devops.requirement.test"].search_count([])
        with self.assertLogs(LOGGER, "WARNING"):
            self.assertFalse(self._record(self.runner, reference="zz_missing"))
        self.assertEqual(
            self.env["devops.requirement.test"].search_count([]), before
        )

    def test_unknown_requirement_creates_nothing(self):
        before = self.env["devops.requirement"].search_count([])
        with self.assertLogs(LOGGER, "WARNING"):
            self.assertFalse(self._record(self.runner, code="ZZ-404"))
        self.assertEqual(
            self.env["devops.requirement"].search_count([]), before
        )

    def test_invalid_result_is_refused(self):
        with self.assertRaises(ValidationError):
            self._record(self.runner, result="green")
        self.assertEqual(self.line.last_result, "not_run")

    def test_log_is_truncated_keeping_the_end(self):
        log = "x" * LOG_MAX_LENGTH + "AssertionError: zz_end"
        self._record(self.runner, "failed", log=log)
        stored = self.line.last_log
        self.assertEqual(len(stored), LOG_MAX_LENGTH)
        self.assertTrue(stored.startswith(LOG_TRUNCATED_MARK))
        # C'est la fin du journal qui porte l'assertion en échec : une
        # troncature qui garderait le début la perdrait.
        self.assertTrue(stored.endswith("AssertionError: zz_end"))

    def test_record_without_log_clears_the_previous_one(self):
        self._record(self.runner, "failed", log="zz_old trace")
        self._record(self.runner, "passed")
        self.assertFalse(self.line.last_log)

    def test_empty_code_designates_no_requirement(self):
        # Deux requis sans code déclarent la même ligne : un code vide ne
        # doit en désigner aucun, ni le premier dans l'ordre de tri.
        category = self.requirement.category_id
        uncoded = self.env["devops.requirement"].create(
            [
                {"name": f"Uncoded {index}", "category_id": category.id}
                for index in (1, 2)
            ]
        )
        lines = self.env["devops.requirement.test"].create(
            [
                {
                    "requirement_id": requirement.id,
                    "kind": "selenium",
                    "reference": "script/zz_test/zz_inventory.py",
                }
                for requirement in uncoded
            ]
        )
        for empty in (False, None, ""):
            with self.assertLogs(LOGGER, "WARNING"):
                self.assertFalse(self._record(self.runner, code=empty))
        self.assertEqual(set(lines.mapped("last_result")), {"not_run"})
        self.assertEqual(self.line.last_result, "not_run")

    def test_runner_reads_requirements_but_cannot_write_them(self):
        # Le groupe n'implique pas l'utilisateur interne : il lit le code
        # qu'il rapproche, sans pouvoir le changer ni toucher à l'état.
        requirement = self.requirement.with_user(self.runner)
        self.assertEqual(requirement.code, "ZZ-01")
        self.assertFalse(self.runner.has_group("base.group_user"))
        with self.assertRaises(AccessError):
            requirement.write({"code": "ZZ-02"})

    def test_test_state_cannot_be_written_directly(self):
        # Un verdict écrit à la main ferait sortir le requis du filtre
        # « Failing tests » jusqu'au prochain lancement.
        self._record(self.runner, "failed")
        for user in (self.internal, self.env.ref("base.user_admin")):
            requirement = self.requirement.with_user(user)
            with self.assertRaises(AccessError):
                requirement.write({"test_state": "passed"})
            with self.assertRaises(AccessError):
                requirement.create(
                    {
                        "name": "Inventory",
                        "category_id": self.requirement.category_id.id,
                        "test_state": "passed",
                    }
                )
        self.assertEqual(self.requirement.test_state, "failed")
        # Les autres champs restent ouverts à l'utilisateur interne.
        self.requirement.with_user(self.internal).write(
            {"devsecops_stage": "test"}
        )
        self.assertEqual(self.requirement.devsecops_stage, "test")
