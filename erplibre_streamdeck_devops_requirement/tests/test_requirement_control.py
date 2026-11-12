# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import importlib
import inspect
import re
import unittest
from pathlib import Path

import polib

from odoo.tests.common import TransactionCase, tagged
from odoo.tools.misc import file_path
from odoo.tools.translate import TranslationModuleReader

from .test_requirement_inventory import (
    ANTI_GOAL,
    KINDS,
    committed,
    erplibre_root,
    node_test_names,
    python_test_methods,
)
from .test_streamdeck_requirement_data import (
    AUDIT_ALIAS,
    FIRST_PERSON,
    FRENCH_LEXICON,
    NON_GOAL,
    ORIGIN,
    TEXT_FIELDS,
)

MODULE = "erplibre_streamdeck_devops_requirement"
CATEGORY = "sd_ctl"
# Un requis par décision de l'utilisateur, par choix de conception et par
# anti-objectif de la conception du pilotage : SD-CTL-R01 à R49 pour le
# sous-lot des réglages, puis ceux de la disposition des touches.
COUNT = 71

# Les fichiers de test du pilotage dans erplibre_streamdeck, par motif :
# chacun de leurs tests prouve au moins un requis, et un fichier ajouté
# sous ce motif l'est sans retouche de cette liste. Les tests de la
# politique du premier pilotage vivent dans test_streamdeck_config_settings,
# ceux de la disposition des touches dans test_streamdeck_key_layout.
CONTROL_TEST_FILES = (
    "test_streamdeck_config*.py",
    "test_streamdeck_key_layout.py",
)

# Les requis qui protègent un accès, un verrou, une entrée du fil ou un
# fichier du poste.
SECURITY = (
    "SD-CTL-R04",
    "SD-CTL-R10",
    "SD-CTL-R11",
    "SD-CTL-R13",
    "SD-CTL-R14",
    "SD-CTL-R19",
    "SD-CTL-R22",
    "SD-CTL-R23",
    "SD-CTL-R31",
    "SD-CTL-R38",
    "SD-CTL-R39",
    "SD-CTL-R43",
    "SD-CTL-R47",
    "SD-CTL-R49",
    "SD-CTL-R54",
    "SD-CTL-R59",
    "SD-CTL-R62",
    "SD-CTL-R67",
    "SD-CTL-R69",
)

# Les requis encore à faire : chacun décrit son écart dans Ce qui manque,
# et le passer à fait passe par cette liste.
TO_DO = ("SD-CTL-R49",)

ODOO = "odoo.addons.erplibre_streamdeck.tests."
EXTENSION = "erplibre-home-gnome-extension:test/unit/"
ERPLIBRE = "erplibre:test/test_erplibre_home_pilot.py::"
KEYMAP = "erplibre:test/test_erplibre_streamdeck_keymap.py::"
HOME = "erplibre:test/test_erplibre_streamdeck_home.py::LayoutAllocationTest::"
APP = "erplibre:test/test_erplibre_streamdeck_app.py::KeymapBuildTest::"
KEY_LAYOUT = ODOO + "test_streamdeck_key_layout.TestStreamdeckKeyLayout."

# Les tests qui tiennent les points de revue du pilotage : chacun prouve un
# requis, de sorte que son verdict atteint le registre.
REVIEW_FOCUS = (
    EXTENSION + "deck-config.test.js::a_bad_value_refuses_the_whole_revision",
    EXTENSION + "deck-config.test.js::rewrite_keeps_every_other_line",
    ERPLIBRE
    + "LeContratDuPilote"
    + "::test_write_settings_and_the_extension_rewrite_agree_on_the_fixtures",
    EXTENSION
    + "inventory-service.test.js::only_the_pilot_destination_is_applied",
    ODOO
    + "test_streamdeck_config_wire.TestStreamdeckConfigWire"
    + ".test_a_free_local_change_is_adopted_once",
    ODOO
    + "test_streamdeck_config_access.TestStreamdeckConfigAccess"
    + ".test_an_employee_cannot_replace_a_manager_assigned_profile",
    ODOO
    + "test_streamdeck_config_access.TestStreamdeckConfigAccess"
    + ".test_an_employee_cannot_clear_the_profile",
    ODOO
    + "test_streamdeck_config_wire.TestStreamdeckConfigWire"
    + ".test_a_forced_policy_ignores_the_client_choice",
    ODOO
    + "test_streamdeck_config_wire.TestStreamdeckConfigWire"
    + ".test_locked_keys_are_offered_under_every_policy",
    EXTENSION
    + "inventory-service.test.js"
    + "::keep_local_writes_nothing_and_reports_the_choice",
    # Disposition des touches : un keymap.json hostile, un plugin sans
    # touche, fixtures et tableau de bord, un catalogue trop ancien, un
    # employé devant une disposition verrouillée ou d'un autre poste.
    KEYMAP + "LoadTest::test_a_bad_file_is_empty_with_one_line",
    KEYMAP
    + "LayoutForTest::test_hostile_entries_are_skipped_one_problem_each",
    APP + "test_a_hostile_keymap_still_starts_the_deck",
    HOME + "test_an_unnamed_plugin_gets_no_home_key",
    KEY_LAYOUT + "test_the_preview_warns_of_plugins_without_a_key",
    HOME + "test_fixtures_skip_named_keys",
    HOME + "test_the_dashboard_takes_tiles_keys_first_then_free_keys",
    EXTENSION
    + "deck-config.test.js::a_layout_action_outside_the_catalog_refuses",
    EXTENSION
    + "inventory-service.test.js::a_layout_action_outside_the_catalog_refuses",
    KEY_LAYOUT
    + "test_an_employee_edits_a_free_layout_of_their_workstation_only",
    KEY_LAYOUT + "test_an_employee_cannot_edit_a_locked_layout",
)

FRENCH = {
    "cat_sd_ctl": "Pilotage",
    "SD-CTL-R11": (
        "Le gestionnaire marque des profils au choix ; l'employé en choisit "
        "un pour chacun de ses postes, le gestionnaire assigne n'importe quel "
        "profil, et un profil qui n'est pas au choix ne s'assigne que par lui"
    ),
    "SD-CTL-R51": (
        "La disposition des touches ne couvre que l'écran d'accueil : les "
        "touches d'accueil des plugins, le tableau de bord et les touches "
        "noires"
    ),
}


@tagged("post_install", "-at_install")
class TestRequirementControl(TransactionCase):
    """Les requis du pilotage du Stream Deck par Odoo, domaine `sd_ctl`.

    Chaque requis porte un code `SD-CTL-R<nn>` ; chaque ligne de preuve
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

    def test_the_control_domain_numbers_its_requirements(self):
        self.assertEqual(len(self.category), 1)
        self.assertEqual(self.category.name, "Control")
        self.assertEqual(
            sorted(self.requirements.mapped("code")),
            ["SD-CTL-R%02d" % number for number in range(1, COUNT + 1)],
        )

    def test_every_proof_has_the_reference_of_its_runner(self):
        self.assertTrue(self.lines)
        for line in self.lines:
            with self.subTest(reference=line.reference):
                self.assertIn(line.kind, KINDS)
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

    def test_every_control_test_of_the_module_proves_a_requirement(self):
        cited = {match.group(0) for match in self._references("python")}
        folder = Path(file_path("erplibre_streamdeck/tests"))
        files = sorted(
            {
                path.stem
                for pattern in CONTROL_TEST_FILES
                for path in folder.glob(pattern)
            }
        )
        for expected in (
            "test_streamdeck_config",
            "test_streamdeck_config_access",
            "test_streamdeck_config_settings",
            "test_streamdeck_config_wire",
            "test_streamdeck_key_layout",
        ):
            self.assertIn(expected, files)
        loader = unittest.TestLoader()
        for test_file in files:
            dotted = "odoo.addons.erplibre_streamdeck.tests.%s" % test_file
            tests = importlib.import_module(dotted)
            classes = [
                test_class
                for _name, test_class in inspect.getmembers(
                    tests, inspect.isclass
                )
                if test_class.__module__ == dotted
                and issubclass(test_class, unittest.TestCase)
            ]
            self.assertTrue(classes, test_file)
            for test_class in classes:
                for method in loader.getTestCaseNames(test_class):
                    reference = "%s.%s.%s" % (
                        dotted,
                        test_class.__name__,
                        method,
                    )
                    with self.subTest(reference=reference):
                        self.assertIn(reference, cited)

    def test_the_review_focus_tests_prove_a_requirement(self):
        cited = set(self.lines.mapped("reference"))
        for reference in REVIEW_FOCUS:
            with self.subTest(reference=reference):
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
                if requirement.done:
                    self.assertTrue(requirement.test_ids)
                    self.assertTrue(requirement.achievement)
                    self.assertFalse(requirement.missing)
                else:
                    self.assertTrue(requirement.missing)
                    self.assertNotEqual(requirement.devsecops_stage, "plan")

    def test_what_stays_to_do_is_named(self):
        self.assertEqual(
            sorted(self.requirements.filtered(lambda r: not r.done).ids),
            sorted(self._requirement(code).id for code in TO_DO),
        )

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

    def test_the_lot_states_its_anti_goals(self):
        # La conception du pilotage tire ses requis de ses décisions, de
        # ses choix et de ses anti-objectifs ; ses non-objectifs restent
        # dans la conception.
        names = self.requirements.mapped("name")
        self.assertFalse([n for n in names if NON_GOAL.match(n)])
        self.assertEqual(len([n for n in names if ANTI_GOAL.match(n)]), 7)

    def test_notes_open_on_an_origin_and_texts_read_alone(self):
        for requirement in self.requirements:
            with self.subTest(code=requirement.code):
                self.assertRegex(requirement.notes or "", ORIGIN)
                for field in TEXT_FIELDS:
                    value = requirement[field] or ""
                    self.assertNotRegex(value, AUDIT_ALIAS)
                    self.assertNotRegex(value, FIRST_PERSON)

    def test_the_control_data_is_noupdate(self):
        data = self.env["ir.model.data"].search(
            [
                ("module", "=", MODULE),
                "|",
                "|",
                ("name", "=like", "req_sd_ctl_%"),
                ("name", "=like", "test_sd_ctl_%"),
                ("name", "=", "cat_sd_ctl"),
            ]
        )
        self.assertEqual(
            len(data), 1 + len(self.requirements) + len(self.lines)
        )
        self.assertTrue(all(data.mapped("noupdate")))

    def test_the_control_reads_in_fr_CA(self):
        # Les termes que l'export d'Odoo tire des données du pilotage sont
        # au catalogue, et chacun a son français.
        exported = {
            term[4]
            for term in TranslationModuleReader(self.env.cr, modules=[MODULE])
            if re.search(r"\.(req_sd_ctl_r\d+|cat_sd_ctl)$", term[3] or "")
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
        self.assertFalse([msgid for msgid, s in french.items() if s == msgid])
        for msgstr in french.values():
            self.assertNotRegex(msgstr, FRENCH_LEXICON)
        self.env["res.lang"]._activate_lang("fr_CA")
        self.env["ir.module.module"]._load_module_terms(
            [MODULE], ["fr_CA"], overwrite=True
        )
        self.assertEqual(
            self.category.with_context(lang="fr_CA").name,
            FRENCH["cat_sd_ctl"],
        )
        for code in ("SD-CTL-R11", "SD-CTL-R51"):
            self.assertEqual(
                self._requirement(code).with_context(lang="fr_CA").name,
                FRENCH[code],
            )
