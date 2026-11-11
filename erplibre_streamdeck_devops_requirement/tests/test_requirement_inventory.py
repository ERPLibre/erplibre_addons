# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import ast
import importlib
import inspect
import re
import subprocess
import unittest
from pathlib import Path

import polib

from odoo.tests.common import TransactionCase, tagged
from odoo.tools.misc import file_path
from odoo.tools.translate import TranslationModuleReader

from .test_streamdeck_requirement_data import (
    AUDIT_ALIAS,
    FIRST_PERSON,
    FRENCH_LEXICON,
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
    "test_streamdeck_holding",
    "test_streamdeck_service",
    "test_streamdeck_routes",
    "test_streamdeck_i18n",
)

# Un test node:test se déclare par test('nom', …), le nom pouvant être
# coupé en littéraux joints par « + ». Un nom gabarit `… ${x} …` est le
# corps d'une boucle `for (const [x, …] of [[…], …])` : il nomme un test
# par valeur littérale de la boucle, et aucun quand la boucle ne se lit
# pas, de sorte qu'une preuve ne cite jamais un nom que la boucle ne
# produit pas.
JS_STRING = r"(?:'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`)"
NODE_TEST_CALL = re.compile(
    r"(?<![\w.])test\(\s*(%s(?:\s*\+\s*%s)*)" % (JS_STRING, JS_STRING)
)
JS_STRING_PART = re.compile(JS_STRING)
TEMPLATE_HOLE = re.compile(r"\$\{([^}]*)\}")
JS_FOR_OF = re.compile(
    r"(?<![\w.])for\s*\(\s*(?:const|let|var)\s+(\[[\w\s,]*\]|\w+)\s+of\s+"
)
# Entre la fin de l'en-tête de la boucle et l'appel test( de son corps.
JS_LOOP_BODY = re.compile(r"\s*\)\s*\{?\s*")
JS_SPACE = re.compile(r"\s*")
JS_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?![\w.])")
# Une valeur de boucle qui n'est ni chaîne, ni nombre, ni tableau : un
# objet, un identifiant, une expression. Un trou qui la lit ne nomme rien.
OPAQUE = object()

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

# Les requis dont la garantie repose sur un autre, qui reste à faire tant
# que celui-ci l'est : un deck sans numéro de série ne garde sa clé, et un
# employé ne lit que les decks que son poste a eus, que si aucun numéro de
# série ne peut prendre la forme d'une clé nosn: (SD-INV-R44).
DEPENDS_ON = {
    "SD-INV-R23": ["SD-INV-R44"],
    "SD-INV-R40": ["SD-INV-R44"],
}

# Un test cité par deux requis : un seul verdict les atteint tous deux.
SHARED_REFERENCE = (
    "odoo.addons.erplibre_streamdeck.tests.test_streamdeck_access"
    ".TestStreamdeckAccess"
    ".test_a_deck_lent_keeps_its_whole_history_for_the_lender"
)

FRENCH = {
    "cat_sd_inv": "Inventaire",
    "SD-INV-R02": (
        "L'extension appelle Odoo en HTTPS, et en HTTP simple seulement "
        "vers la machine elle-même : 127.0.0.0/8, ::1 ou localhost"
    ),
}


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


def js_string(literal):
    """(guillemet, corps sans échappements) d'un littéral chaîne JS."""
    return literal[0], re.sub(r"\\(.)", r"\1", literal[1:-1])


def js_value(source, start):
    """(valeur, fin) de la valeur JS qui commence à `source[start:]` :
    chaîne, nombre ou tableau de ces valeurs ; toute autre valeur, gabarit
    à trous compris, est OPAQUE et court jusqu'à la virgule ou au crochet
    fermant de son niveau. Lève IndexError sur une source tronquée."""
    i = JS_SPACE.match(source, start).end()
    if source[i] == "[":
        items = []
        i = JS_SPACE.match(source, i + 1).end()
        while source[i] != "]":
            value, i = js_value(source, i)
            items.append(value)
            i = JS_SPACE.match(source, i).end()
            if source[i] == ",":
                i = JS_SPACE.match(source, i + 1).end()
        return items, i + 1
    string = JS_STRING_PART.match(source, i)
    if string:
        quote, body = js_string(string.group(0))
        if quote == "`" and TEMPLATE_HOLE.search(body):
            return OPAQUE, string.end()
        return body, string.end()
    number = JS_NUMBER.match(source, i)
    if number:
        value = float(number.group(0))
        return (int(value) if value.is_integer() else value), number.end()
    depth = 0
    while True:
        string = JS_STRING_PART.match(source, i)
        if string:
            i = string.end()
            continue
        char = source[i]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            if not depth:
                return OPAQUE, i
            depth -= 1
        elif char == "," and not depth:
            return OPAQUE, i
        i += 1


def node_loop_bindings(source):
    """{position d'un appel test( : [{variable: valeur}, …]} pour chaque
    test qui est le corps d'une boucle for…of sur un tableau littéral,
    une liaison par élément du tableau."""
    loops = {}
    for loop in JS_FOR_OF.finditer(source):
        try:
            values, end = js_value(source, loop.end())
        except IndexError:
            continue
        body = JS_LOOP_BODY.match(source, end)
        if not body or not isinstance(values, list):
            continue
        target = loop.group(1)
        if target.startswith("["):
            variables = re.findall(r"\w+", target)
            if not all(isinstance(value, list) for value in values):
                continue
            loops[body.end()] = [
                dict(zip(variables, value)) for value in values
            ]
        else:
            loops[body.end()] = [{target: value} for value in values]
    return loops


def node_test_name(literals, binding):
    """Le nom que forment les littéraux joints d'un appel test() sous
    `binding`, ou None quand un trou ne lit pas une chaîne ou un nombre
    de la liaison."""
    name = ""
    for literal in literals:
        quote, body = js_string(literal)
        if quote != "`":
            name += body
            continue
        parts = TEMPLATE_HOLE.split(body)
        for index, part in enumerate(parts):
            if index % 2 == 0:
                name += part
                continue
            value = binding.get(part.strip(), OPAQUE)
            if isinstance(value, bool) or not isinstance(
                value, (str, int, float)
            ):
                return None
            name += str(value)
    return name


def node_test_names(source):
    """Les noms exacts des test() d'un fichier node:test : un nom
    littéral tel quel, un gabarit une fois par élément de sa boucle."""
    loops = node_loop_bindings(source)
    names = set()
    for call in NODE_TEST_CALL.finditer(source):
        literals = JS_STRING_PART.findall(call.group(1))
        for binding in loops.get(call.start(), [{}]):
            name = node_test_name(literals, binding)
            if name is not None:
                names.add(name)
    return names


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
                self.assertIn(name, names[path])

    def test_a_loop_names_one_node_test_per_literal_value(self):
        source = (
            "for (const [status, error] of [[401, 'token_invalid'],\n"
            '    [403, "user_inactive"],])\n'
            "    test(`a ${status} ${error} is revoked`, async () => {\n"
            "    });\n"
            "for (const what of ['URL', `database`]) {\n"
            "    test(`the ${ what } changes`, () => {});\n"
            "}\n"
            "test('a name cut ' + \"in two\", () => {});\n"
        )
        self.assertEqual(
            node_test_names(source),
            {
                "a 401 token_invalid is revoked",
                "a 403 user_inactive is revoked",
                "the URL changes",
                "the database changes",
                "a name cut in two",
            },
        )

    def test_a_template_its_loop_does_not_fill_names_no_test(self):
        # Sans boucle lisible, aucun nom : la preuve qui cite le gabarit
        # tombe, au lieu de passer sur n'importe quelle valeur.
        source = (
            "test(`a ${status} alone`, () => {});\n"
            "for (const [what, change] of [[OTHER, 'x'], [{url: 'u'}, 'y']])"
            "\n    test(`a ${what} change`, () => {});\n"
            "for (const [what, change] of [['URL', OTHER.url]])\n"
            "    test(`a ${what.length} change`, () => {});\n"
            "for (const value of values)\n"
            "    test(`a ${value} value`, () => {});\n"
        )
        self.assertEqual(node_test_names(source), set())

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

    def test_a_requirement_is_not_done_before_what_it_rests_on(self):
        for code, depends_on in DEPENDS_ON.items():
            self.assertEqual(
                sorted(self._requirement(code).depends_on_ids.mapped("code")),
                depends_on,
                code,
            )
        for requirement in self.requirements:
            undone = requirement.depends_on_ids.filtered(lambda r: not r.done)
            with self.subTest(code=requirement.code):
                if undone:
                    self.assertFalse(requirement.done)
                for code in undone.mapped("code"):
                    self.assertIn(code, requirement.missing or "")

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

    def test_the_inventory_reads_in_fr_CA(self):
        # Les termes que l'export d'Odoo tire des données de l'inventaire
        # sont au catalogue, et chacun a son français.
        exported = {
            term[4]
            for term in TranslationModuleReader(self.env.cr, modules=[MODULE])
            if re.search(r"\.(req_sd_inv_r\d+|cat_sd_inv)$", term[3] or "")
        }
        self.assertGreater(len(exported), COUNT)
        template = polib.pofile(file_path("%s/i18n/%s.pot" % (MODULE, MODULE)))
        self.assertFalse(sorted(exported - {e.msgid for e in template}))
        french = {
            entry.msgid: entry.msgstr
            for entry in polib.pofile(file_path("%s/i18n/fr_CA.po" % MODULE))
            if entry.msgid in exported
        }
        self.assertEqual(set(french), exported)
        self.assertFalse([msgid for msgid, s in french.items() if not s])
        # Un nom ou une description est une phrase : aucun ne s'écrit pareil
        # dans les deux langues, et un msgstr recopié du msgid laisserait
        # le requis en anglais pour un utilisateur fr_CA.
        self.assertFalse([msgid for msgid, s in french.items() if s == msgid])
        for msgstr in french.values():
            self.assertNotRegex(msgstr, FRENCH_LEXICON)
        self.env["res.lang"]._activate_lang("fr_CA")
        self.env["ir.module.module"]._load_module_terms(
            [MODULE], ["fr_CA"], overwrite=True
        )
        self.assertEqual(
            self.category.with_context(lang="fr_CA").name,
            FRENCH["cat_sd_inv"],
        )
        self.assertEqual(
            self._requirement("SD-INV-R02").with_context(lang="fr_CA").name,
            FRENCH["SD-INV-R02"],
        )
