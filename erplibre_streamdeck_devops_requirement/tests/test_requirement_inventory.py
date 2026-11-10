# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import ast
import importlib
import inspect
import re
import subprocess
import unittest
from pathlib import Path


from odoo.tests.common import TransactionCase, tagged
from odoo.tools.misc import file_path

from .test_streamdeck_requirement_data import (
    AUDIT_ALIAS,
    FIRST_PERSON,
    NON_GOAL,
    ORIGIN,
    TEXT_FIELDS,
)

MODULE = "erplibre_streamdeck_devops_requirement"
CATEGORY = "sd_inv"
# Un requis par décision, non-objectif et anti-objectif de la conception
# de l'inventaire.
COUNT = 44

# Les trois formes de preuve de l'inventaire : la référence que pousse
# chaque lanceur. Un test Odoo se nomme par son chemin pointé, celui
# qu'odoo_test_report.py lit du journal d'Odoo.
PYTHON_REFERENCE = re.compile(
    r"^odoo\.addons\.(erplibre_streamdeck|%s)\.tests\.(test_\w+)"
    r"\.(\w+)\.(test_\w+)$" % MODULE
)
NODE_REFERENCE = re.compile(
    r"^erplibre-home-gnome-extension:(test/unit/[\w.-]+\.test\.js)::(.+)$"
)
REPO_REFERENCE = re.compile(
    r"^erplibre:(test/test_\w+\.py)::(\w+)::(test_\w+)$"
)
KINDS = {
    "python": PYTHON_REFERENCE,
    "node_test": NODE_REFERENCE,
    "repo_unittest": REPO_REFERENCE,
}

# Les fichiers de test de l'inventaire dans erplibre_streamdeck : chacun de
# leurs tests prouve au moins un requis, sans quoi son verdict n'atteint
# aucune ligne du registre.
INVENTORY_TEST_FILES = (
    "test_streamdeck_access",
    "test_streamdeck_service",
    "test_streamdeck_routes",
    "test_streamdeck_i18n",
)

# Un test node:test se déclare par test('nom', …), le nom pouvant être
# coupé en littéraux joints par « + » ; un nom gabarit `… ${x} …` est
# produit par une boucle et se compare comme un motif.
JS_STRING = r"(?:'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`)"
NODE_TEST_CALL = re.compile(
    r"(?<![\w.])test\(\s*(%s(?:\s*\+\s*%s)*)" % (JS_STRING, JS_STRING)
)
JS_STRING_PART = re.compile(JS_STRING)
TEMPLATE_HOLE = re.compile(r"\$\{[^}]*\}")

ANTI_GOAL = re.compile(r"^Anti-goal\b")

# Les requis qui protègent un secret ou un accès, dont ceux que la revue du
# lot surveille : jeton, empreinte, routes, refus, cloisonnement des
# employés, clés de deck.
SECURITY = (
    "SD-INV-R02",
    "SD-INV-R03",
    "SD-INV-R08",
    "SD-INV-R09",
    "SD-INV-R16",
    "SD-INV-R17",
    "SD-INV-R18",
    "SD-INV-R26",
    "SD-INV-R27",
    "SD-INV-R28",
    "SD-INV-R29",
    "SD-INV-R34",
    "SD-INV-R39",
    "SD-INV-R40",
    "SD-INV-R42",
    "SD-INV-R44",
)

# Un test cité par deux requis : un seul verdict les atteint tous deux.
SHARED_REFERENCE = (
    "odoo.addons.erplibre_streamdeck.tests.test_streamdeck_access"
    ".TestStreamdeckAccess"
    ".test_a_deck_lent_keeps_its_whole_history_for_the_lender"
)


def erplibre_root():
    """Le checkout ERPLibre qui porte ce module, ou None : le module vit
    sous odoo<version>/addons/<dépôt>/ d'un checkout, que désigne le
    fichier de version du contrat de l'extension."""
    for parent in Path(file_path(MODULE)).resolve().parents:
        if (
            parent / "script/gnome-extension/erplibre_home_contract"
        ).is_file():
            return parent
    return None


def committed(repository, path):
    """Le texte de `path` au HEAD du dépôt git `repository`, ou None quand
    le fichier n'y est pas commité."""
    result = subprocess.run(
        ["git", "-C", str(repository), "show", "HEAD:%s" % path],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def node_test_names(source):
    """Les noms des test() d'un fichier node:test, en motifs : un nom
    littéral se compare tel quel, un gabarit avec ses trous en `.+`."""
    patterns = []
    for name in NODE_TEST_CALL.findall(source):
        pattern = ""
        for literal in JS_STRING_PART.findall(name):
            quote, body = literal[0], literal[1:-1]
            body = re.sub(r"\\(.)", r"\1", body)
            if quote == "`":
                parts = TEMPLATE_HOLE.split(body)
                pattern += ".+".join(re.escape(part) for part in parts)
            else:
                pattern += re.escape(body)
        patterns.append(re.compile("^%s$" % pattern, re.DOTALL))
    return patterns


def python_test_methods(source):
    """{classe: {méthodes test_*}} d'un fichier de tests Python."""
    methods = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.ClassDef):
            methods[node.name] = {
                item.name
                for item in node.body
                if isinstance(item, ast.FunctionDef)
                and item.name.startswith("test_")
            }
    return methods


@tagged("post_install", "-at_install")
class TestRequirementInventory(TransactionCase):
    """Les requis de l'inventaire Odoo du Stream Deck, domaine `sd_inv`.

    Chaque requis porte un code `SD-INV-R<nn>` ; chaque ligne de preuve
    nomme un test qui existe, sous la référence que pousse son lanceur :
    test Odoo par son chemin pointé, test node de l'extension et test
    unitaire d'ERPLibre par `<dépôt>:<chemin>::<test>`.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env["devops.requirement.category"].search(
            [("code", "=", CATEGORY)]
        )
        cls.requirements = cls.env["devops.requirement"].search(
            [("category_id", "in", cls.category.ids)]
        )
        cls.lines = cls.requirements.test_ids

    def _requirement(self, code):
        requirement = self.requirements.filtered(lambda r: r.code == code)
        self.assertEqual(len(requirement), 1, code)
        return requirement

    def _references(self, kind):
        lines = self.lines.filtered(lambda line: line.kind == kind)
        return [KINDS[kind].match(line.reference) for line in lines]

    def test_the_inventory_domain_numbers_its_requirements(self):
        self.assertEqual(len(self.category), 1)
        self.assertEqual(self.category.name, "Inventory")
        self.assertEqual(
            sorted(self.requirements.mapped("code")),
            ["SD-INV-R%02d" % number for number in range(1, COUNT + 1)],
        )

    def test_every_proof_has_the_reference_of_its_runner(self):
        self.assertTrue(self.lines)
        for line in self.lines:
            self.assertIn(line.kind, KINDS, line.reference)
            self.assertRegex(line.reference, KINDS[line.kind])
        for kind in KINDS:
            self.assertTrue(self._references(kind), kind)

    def test_python_proofs_name_tests_their_module_runs(self):
        # `--test-tags /<module>` lance les tests « standard » : un test
        # renommé, ou exclu de ce tag, ne recevrait jamais de verdict.
        for match in self._references("python"):
            module, test_file, class_name, method = match.groups()
            with self.subTest(reference=match.group(0)):
                tests = importlib.import_module(
                    "odoo.addons.%s.tests.%s" % (module, test_file)
                )
                test_class = getattr(tests, class_name, None)
                self.assertTrue(
                    inspect.isclass(test_class)
                    and issubclass(test_class, unittest.TestCase)
                )
                self.assertTrue(callable(getattr(test_class, method, None)))
                self.assertIn("standard", test_class.test_tags)

    def test_every_inventory_test_of_the_module_proves_a_requirement(self):
        cited = {match.group(0) for match in self._references("python")}
        for test_file in INVENTORY_TEST_FILES:
            dotted = "odoo.addons.erplibre_streamdeck.tests.%s" % test_file
            tests = importlib.import_module(dotted)
            loader = unittest.TestLoader()
            for _name, test_class in inspect.getmembers(
                tests, inspect.isclass
            ):
                if test_class.__module__ != dotted or not issubclass(
                    test_class, unittest.TestCase
                ):
                    continue
                for method in loader.getTestCaseNames(test_class):
                    reference = "%s.%s.%s" % (
                        dotted,
                        test_class.__name__,
                        method,
                    )
                    self.assertIn(reference, cited)

    def test_extension_proofs_name_its_committed_tests(self):
        root = erplibre_root()
        extension = root and root / "script/gnome-extension/erplibre_home"
        if not extension or not (extension / ".git").exists():
            self.skipTest("no clone of the extension in this checkout")
        names = {}
        for match in self._references("node_test"):
            path, name = match.groups()
            with self.subTest(reference=match.group(0)):
                if path not in names:
                    source = committed(extension, path)
                    self.assertIsNotNone(source, "%s not committed" % path)
                    names[path] = node_test_names(source)
                self.assertTrue(
                    any(pattern.match(name) for pattern in names[path])
                )

    def test_erplibre_proofs_name_its_committed_tests(self):
        root = erplibre_root()
        if not root or not (root / ".git").exists():
            self.skipTest("this module is not inside an ERPLibre checkout")
        methods = {}
        for match in self._references("repo_unittest"):
            path, class_name, method = match.groups()
            with self.subTest(reference=match.group(0)):
                if path not in methods:
                    source = committed(root, path)
                    self.assertIsNotNone(source, "%s not committed" % path)
                    methods[path] = python_test_methods(source)
                self.assertIn(method, methods[path].get(class_name, ()))

    def test_a_done_requirement_has_a_proof_and_nothing_missing(self):
        for requirement in self.requirements:
            with self.subTest(code=requirement.code):
                if requirement.moscow == "wont":
                    # Un non-objectif est tenu par ce que le lot ne fait
                    # pas : sa raison est dans la description.
                    self.assertRegex(requirement.name, NON_GOAL)
                    self.assertTrue(requirement.done)
                    self.assertTrue(requirement.description)
                    self.assertFalse(requirement.missing)
                elif requirement.done:
                    self.assertTrue(requirement.test_ids)
                    self.assertTrue(requirement.achievement)
                    self.assertFalse(requirement.missing)
                else:
                    self.assertTrue(requirement.missing)
                    self.assertNotEqual(requirement.devsecops_stage, "plan")

    def test_security_requirements_are_must_and_flagged(self):
        security = self.requirements.filtered(
            lambda r: r.requirement_type == "security"
        )
        self.assertEqual(sorted(security.mapped("code")), sorted(SECURITY))
        for requirement in self.requirements:
            with self.subTest(code=requirement.code):
                self.assertEqual(
                    requirement.security_relevant,
                    requirement.requirement_type == "security",
                )
                if requirement.security_relevant:
                    self.assertEqual(requirement.moscow, "must")
                if ANTI_GOAL.match(requirement.name):
                    self.assertEqual(requirement.moscow, "must")

    def test_the_lot_states_its_non_goals_and_anti_goals(self):
        names = self.requirements.mapped("name")
        self.assertEqual(len([n for n in names if NON_GOAL.match(n)]), 4)
        self.assertEqual(len([n for n in names if ANTI_GOAL.match(n)]), 4)

    def test_notes_open_on_an_origin_and_texts_read_alone(self):
        for requirement in self.requirements:
            with self.subTest(code=requirement.code):
                self.assertRegex(requirement.notes or "", ORIGIN)
                for field in TEXT_FIELDS:
                    value = requirement[field] or ""
                    self.assertNotRegex(value, AUDIT_ALIAS)
                    self.assertNotRegex(value, FIRST_PERSON)

    def test_a_python_verdict_reaches_every_requirement_citing_it(self):
        lines = self.lines.filtered(
            lambda line: line.kind == "python"
            and line.reference == SHARED_REFERENCE
        )
        self.assertGreaterEqual(len(lines.requirement_id), 2)
        updated = self.env[
            "devops.requirement.test"
        ].record_result_by_reference(
            "python", SHARED_REFERENCE, "passed", duration=0.2
        )
        self.assertEqual(updated, len(lines))
        self.assertEqual(set(lines.mapped("last_result")), {"passed"})

    def test_the_inventory_data_is_noupdate(self):
        data = self.env["ir.model.data"].search(
            [
                ("module", "=", MODULE),
                "|",
                "|",
                ("name", "=like", "req_sd_inv_%"),
                ("name", "=like", "test_sd_inv_%"),
                ("name", "=", "cat_sd_inv"),
            ]
        )
        self.assertEqual(
            len(data), 1 + len(self.requirements) + len(self.lines)
        )
        self.assertTrue(all(data.mapped("noupdate")))
