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

from .test_requirement_inventory import ANTI_GOAL, PYTHON_REFERENCE
from .test_streamdeck_requirement_data import (
    AUDIT_ALIAS,
    FIRST_PERSON,
    FRENCH_LEXICON,
    NON_GOAL,
    ORIGIN,
    TEXT_FIELDS,
)

MODULE = "erplibre_streamdeck_devops_requirement"
CATEGORY = "sd_mon"
# Un requis par décision de l'utilisateur, choix, élément du côté Odoo,
# non-objectif et anti-objectif de la conception de la surveillance.
COUNT = 38

# Les fichiers de test de la surveillance dans erplibre_streamdeck, par
# motif : chacun de leurs tests prouve au moins un requis, et un fichier
# ajouté sous ce motif l'est sans retouche de cette liste.
MONITORING_TEST_FILES = (
    "test_streamdeck_monitor*.py",
    "test_streamdeck_settings.py",
)

# Les requis qui protègent un accès, un réglage ou l'intégrité de
# l'historique et des activités.
SECURITY = (
    "SD-MON-R10",
    "SD-MON-R12",
    "SD-MON-R17",
    "SD-MON-R22",
    "SD-MON-R23",
    "SD-MON-R36",
    "SD-MON-R38",
)

# Les décisions de conception qu'aucun test d'Odoo ne peut tenir : faites,
# sans preuve, leur raison dans Réalisation.
DECISIONS = ("SD-MON-R07",)

# Les requis encore à faire : chacun décrit son écart dans Ce qui manque,
# et le passer à fait passe par cette liste.
TO_DO = (
    "SD-MON-R23",
    "SD-MON-R38",
)

# Un requis dont la garantie repose sur un autre en dépend, et reste à
# faire tant que celui-là ne l'est pas. Une activité d'un type de la
# surveillance posée par un autre que la surveillance occupe la place de
# celle qu'elle ouvrirait pour le même utilisateur ; ceux qui promettent
# qu'une activité s'ouvre pour un destinataire reposent donc sur SD-MON-R17.
DEPENDS_ON = {
    "SD-MON-R05": ["SD-MON-R17"],
    "SD-MON-R18": ["SD-MON-R17"],
    "SD-MON-R19": ["SD-MON-R17"],
}

# Un problème a une activité ouverte par utilisateur, et le destinataire
# « les deux » en ouvre deux (SD-MON-R18) : un requis qui refuse deux
# activités ouvertes pour un problème borne ce refus à un utilisateur, dans
# chaque langue où il se lit.
ONE_OPEN_ACTIVITY = {
    "en_US": (
        re.compile(r"\btwo open activities\b"),
        re.compile(r"\b(?:one|same) user\b"),
    ),
    "fr_CA": (
        re.compile(r"\bdeux activités ouvertes\b"),
        re.compile(r"\b(?:un|le) même utilisateur\b"),
    ),
}

FRENCH = {
    "cat_sd_mon": "Surveillance",
    "SD-MON-R12": (
        "Odoo seul écrit les événements Poste muet et Poste revenu : un "
        "poste qui en envoie un reçoit 400 bad_request"
    ),
}


@tagged("post_install", "-at_install")
class TestRequirementMonitoring(TransactionCase):
    """Les requis de la surveillance du Stream Deck, domaine `sd_mon`.

    Chaque requis porte un code `SD-MON-R<nn>` ; chaque ligne de preuve
    nomme par son chemin pointé un test Odoo qui existe et que lance
    `--test-tags /<module>`, la référence que pousse
    `odoo_test_report.py`.
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

    def test_the_monitoring_domain_numbers_its_requirements(self):
        self.assertEqual(len(self.category), 1)
        self.assertEqual(self.category.name, "Monitoring")
        self.assertEqual(
            sorted(self.requirements.mapped("code")),
            ["SD-MON-R%02d" % number for number in range(1, COUNT + 1)],
        )

    def test_every_proof_is_an_odoo_test_reference(self):
        self.assertTrue(self.lines)
        for line in self.lines:
            with self.subTest(reference=line.reference):
                self.assertEqual(line.kind, "python")
                self.assertRegex(line.reference, PYTHON_REFERENCE)

    def test_python_proofs_name_tests_their_module_runs(self):
        # `--test-tags /<module>` lance les tests « standard » : un test
        # renommé, ou exclu de ce tag, ne recevrait jamais de verdict.
        for line in self.lines:
            match = PYTHON_REFERENCE.match(line.reference)
            with self.subTest(reference=line.reference):
                self.assertTrue(match)
                module, test_file, class_name, method = match.groups()
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

    def test_every_monitoring_test_of_the_module_proves_a_requirement(self):
        cited = set(self.lines.mapped("reference"))
        folder = Path(file_path("erplibre_streamdeck/tests"))
        files = sorted(
            {
                path.stem
                for p in MONITORING_TEST_FILES
                for path in folder.glob(p)
            }
        )
        self.assertIn("test_streamdeck_monitor", files)
        self.assertIn("test_streamdeck_settings", files)
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

    def test_a_done_requirement_has_a_proof_and_nothing_missing(self):
        for requirement in self.requirements:
            with self.subTest(code=requirement.code):
                if requirement.moscow == "wont":
                    # Un non-objectif est tenu par ce que le lot ne fait
                    # pas : sa raison est dans la description.
                    self.assertRegex(requirement.name, NON_GOAL)
                    self.assertTrue(requirement.done)
                    self.assertTrue(requirement.description)
                    self.assertFalse(requirement.test_ids)
                    self.assertFalse(requirement.missing)
                elif requirement.code in DECISIONS:
                    self.assertEqual(requirement.moscow, "should")
                    self.assertEqual(
                        requirement.requirement_type, "non_functional"
                    )
                    self.assertTrue(requirement.done)
                    self.assertFalse(requirement.test_ids)
                    self.assertTrue(requirement.achievement)
                    self.assertFalse(requirement.missing)
                    self.assertTrue(
                        requirement.notes.startswith(
                            "Origin: documented only."
                        )
                    )
                elif requirement.done:
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

    def test_one_open_activity_per_problem_is_counted_per_user(self):
        self.env["res.lang"]._activate_lang("fr_CA")
        self.env["ir.module.module"]._load_module_terms(
            [MODULE], ["fr_CA"], overwrite=True
        )
        for lang, (refusal, per_user) in ONE_OPEN_ACTIVITY.items():
            refusing = self.requirements.with_context(lang=lang).filtered(
                lambda r: refusal.search(r.name)
            )
            self.assertIn("SD-MON-R06", refusing.mapped("code"), lang)
            for requirement in refusing:
                with self.subTest(lang=lang, code=requirement.code):
                    self.assertRegex(requirement.name, per_user)

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
        self.assertEqual(len([n for n in names if ANTI_GOAL.match(n)]), 6)

    def test_notes_open_on_an_origin_and_texts_read_alone(self):
        for requirement in self.requirements:
            with self.subTest(code=requirement.code):
                self.assertRegex(requirement.notes or "", ORIGIN)
                for field in TEXT_FIELDS:
                    value = requirement[field] or ""
                    self.assertNotRegex(value, AUDIT_ALIAS)
                    self.assertNotRegex(value, FIRST_PERSON)

    def test_the_monitoring_data_is_noupdate(self):
        data = self.env["ir.model.data"].search(
            [
                ("module", "=", MODULE),
                "|",
                "|",
                ("name", "=like", "req_sd_mon_%"),
                ("name", "=like", "test_sd_mon_%"),
                ("name", "=", "cat_sd_mon"),
            ]
        )
        self.assertEqual(
            len(data), 1 + len(self.requirements) + len(self.lines)
        )
        self.assertTrue(all(data.mapped("noupdate")))

    def test_the_monitoring_reads_in_fr_CA(self):
        # Les termes que l'export d'Odoo tire des données de la
        # surveillance sont au catalogue, et chacun a son français.
        exported = {
            term[4]
            for term in TranslationModuleReader(self.env.cr, modules=[MODULE])
            if re.search(r"\.(req_sd_mon_r\d+|cat_sd_mon)$", term[3] or "")
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
            FRENCH["cat_sd_mon"],
        )
        self.assertEqual(
            self._requirement("SD-MON-R12").with_context(lang="fr_CA").name,
            FRENCH["SD-MON-R12"],
        )
