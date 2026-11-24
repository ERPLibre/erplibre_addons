# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase, tagged

from .test_requirement_inventory import (
    MODULE,
    PROOF_REFERENCE,
    REPOSITORIES,
    assert_proofs_committed,
    assert_python_proof,
    committed_names,
    long_test_checks,
)

# Chaque sorte de preuve que livre ce module, et ce qui la vérifie : un
# test Odoo s'importe, les autres se lisent au HEAD du clone de leur dépôt.
CHECKED_KINDS = ("python", "repo_unittest", "node_test", "long_test")


@tagged("post_install", "-at_install")
class TestRequirementProofs(TransactionCase):
    """Toutes les preuves que livre ce module, chaque domaine compris.

    Une preuve dont le test a été renommé, déplacé ou retiré ne reçoit plus
    jamais de verdict, et son requis reste fait sur la foi d'un test qui
    n'existe pas. Chaque ligne nomme donc un test qui existe : un test
    Odoo par son chemin pointé, un test de dépôt dans le fichier que porte
    le HEAD du clone de ce dépôt, qui saute quand le checkout ne l'a pas.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        data = cls.env["ir.model.data"].search(
            [
                ("module", "=", MODULE),
                ("model", "=", "devops.requirement.test"),
            ]
        )
        cls.lines = cls.env["devops.requirement.test"].browse(
            data.mapped("res_id")
        )

    def _proofs(self, *kinds):
        lines = self.lines.filtered(lambda line: line.kind in kinds)
        return [(line.kind, line.reference) for line in lines]

    def test_every_kind_of_proof_has_its_check(self):
        self.assertEqual(
            sorted(set(self.lines.mapped("kind"))), sorted(CHECKED_KINDS)
        )
        for kind, reference in self._proofs(*CHECKED_KINDS[1:]):
            with self.subTest(reference=reference):
                match = PROOF_REFERENCE.match(reference)
                self.assertTrue(match)
                self.assertIn(match.group(1), REPOSITORIES)

    def test_odoo_proofs_name_tests_their_module_runs(self):
        proofs = self._proofs("python")
        self.assertTrue(proofs)
        for _kind, reference in proofs:
            with self.subTest(reference=reference):
                assert_python_proof(self, reference)

    def test_repository_proofs_name_their_committed_tests(self):
        proofs = self._proofs(*CHECKED_KINDS[1:])
        self.assertTrue(proofs)
        assert_proofs_committed(self, proofs)

    def test_a_long_test_names_the_command_and_checks_of_its_stages(self):
        # Le nom d'une étape n'est pas un verdict : seuls sa commande et
        # ses contrôles le sont. Un nom calculé ne se lit pas.
        source = (
            "def _etape(nom, commande, option, controles):\n"
            "    return {}\n"
            "CHECK = 'computed'\n"
            "ETAPES = (\n"
            "    _etape('base', None, None, ('session', 'extension-dbus')),\n"
            "    _etape('deck', 'install-deck', '--deck',"
            " controles=['udev', CHECK]),\n"
            ")\n"
            "OTHER = (_etape('x', 'not-a-stage', None, ('nor-this',)),)\n"
        )
        self.assertEqual(
            long_test_checks(source),
            {"session", "extension-dbus", "install-deck", "udev"},
        )
        self.assertEqual(long_test_checks("ETAPES = ()\n"), set())

    def test_a_proof_names_what_its_kind_reads(self):
        source = (
            "import unittest\n"
            "class Case(unittest.TestCase):\n"
            "    def test_one(self):\n"
            "        pass\n"
        )
        self.assertEqual(
            committed_names("repo_unittest", source), {"Case::test_one"}
        )
        self.assertEqual(
            committed_names("node_test", "test('a name', () => {});\n"),
            {"a name"},
        )
        # Une sorte qui ne se lit pas dans un fichier n'a aucun nom à
        # citer : sa preuve tombe au lieu de passer sans être lue.
        with self.assertRaises(KeyError):
            committed_names("manual", source)
        for reference, valid in (
            ("streamdeck_game:tests/test_x.py::Case::test_y", True),
            ("erplibre:long_test/install.py::extension-dbus", True),
            ("erplibre:test/test_x.py", False),
            ("erplibre::Case::test_y", False),
        ):
            with self.subTest(reference=reference):
                self.assertEqual(bool(PROOF_REFERENCE.match(reference)), valid)
