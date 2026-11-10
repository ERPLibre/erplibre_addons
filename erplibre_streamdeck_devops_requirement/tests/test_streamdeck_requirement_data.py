# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import re

import polib

from odoo.tests.common import TransactionCase, tagged
from odoo.tools.convert import convert_file
from odoo.tools.misc import file_path

MODULE = "erplibre_streamdeck_devops_requirement"

# Requis par domaine : une ligne d'audit « obsolete » ne donne aucun requis.
COUNTS = {
    "sd_bundle": 66,
    "sd_defects": 107,
    "sd_deploy": 132,
    "sd_ext": 128,
    "sd_grepo": 89,
    "sd_gsplit": 68,
    "sd_mobplug": 83,
    "sd_plugin": 131,
    "sd_rename": 65,
    "sd_service": 89,
}

REPOSITORY_REFERENCE = re.compile(
    r"^(erplibre|erplibre-home-gnome-extension|streamdeck_game"
    r"|erplibre_home_mobile):[^:]+::.+$"
)

# Une référence que plusieurs requis citent : un seul verdict de test doit
# les atteindre tous.
SHARED_REFERENCE = (
    "erplibre:test/test_deck_lock.py::LaCommandeSousVerrou"
    "::test_a_busy_deck_runs_nothing_and_exits_two"
)

# Les alias de l'audit (M: dépôt mobile, J/ jeux, EXT/ extension) et le
# nom daté d'un clone local ne se résolvent pas hors de l'audit. L'alias M
# est suivi d'un chemin, ce qui laisse passer un format d'heure « H:M:S ».
AUDIT_ALIAS = re.compile(r"\bM[:/](?=[\w-]+[./])|\bJ/|\bEXT/|plain-clone-\d")
# Le « I » anglais isolé est la première personne de l'auditeur ; « I/O »
# et un « I » collé à un identifiant n'en sont pas.
FIRST_PERSON = re.compile(r"(?<![\w/])I(?![\w/'’-])")
TEXT_FIELDS = ("name", "description", "achievement", "missing", "notes")

# Les Notes s'ouvrent sur l'origine du requis, l'un des libellés que
# définit le README du module, jamais sur le code brut de l'audit.
ORIGIN = re.compile(
    r"^Origin: (covered by a test|unit test missing|long test needed"
    r"|documented only|proof in another repository|violated)[.;]"
)
NON_GOAL = re.compile(r"^(Non-goals?|Out of scope)\b")

# Le français des requis suit celui de l'interface d'ERPLibre : « plugin »,
# « hors périmètre », « se termine avec le code N ».
FRENCH_LEXICON = re.compile(
    r"plugiciel|hors portée|\bsort(?:ent)? en \d", re.IGNORECASE
)
# Un « ; » prend une espace avant lui ; une commande citée après
# « bash -lc » garde le « ; » du shell.
GLUED_SEMICOLON = re.compile(r"(?<=\S);(?=\s)")
QUOTED_SHELL = re.compile(r"bash -lc '[^']*'")

# Un requis et un domaine lus en fr_CA : le nom du requis porte chevrons,
# accolades et guillemets, qui traversent aussi le fichier .po.
FRENCH = {
    "SD-GREPO-R14": (
        "CONTRACT.md, galerie : GET /launch/<id> répond 2xx quand le jeu "
        'démarre, sinon {"error": ligne} avec 403 quand les jeux sont '
        "désactivés et 404 pour un id inconnu"
    ),
    "sd_deploy": "Déploiement d'ERPLibre Home",
}


@tagged("post_install", "-at_install")
class TestStreamdeckRequirementData(TransactionCase):
    """Les requis Stream Deck livrés en données, et leurs preuves.

    Chaque requis porte un code `SD-<domaine>-<ligne d'audit>`, son domaine
    est l'une des dix catégories `sd_*`, et chaque ligne de preuve désigne
    un test de dépôt par `<dépôt>:<chemin>::<test>`, la clé qu'un lanceur
    envoie à `record_result_by_reference`.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.categories = cls.env["devops.requirement.category"].search(
            [("code", "in", list(COUNTS))]
        )
        cls.requirements = cls.env["devops.requirement"].search(
            [("category_id", "in", cls.categories.ids)]
        )

    def _requirement(self, code):
        requirement = self.requirements.filtered(lambda r: r.code == code)
        self.assertEqual(len(requirement), 1, code)
        return requirement

    def test_codes_are_unique_and_prefixed(self):
        self.assertTrue(self.requirements)
        codes = self.requirements.mapped("code")
        self.assertEqual(len(codes), len(set(codes)))
        for requirement in self.requirements:
            self.assertRegex(requirement.code, r"^SD-[A-Z]+-R\w+$")
            category = requirement.category_id.code
            self.assertTrue(
                requirement.code.startswith("SD-%s-" % category[3:].upper()),
                requirement.code,
            )

    def test_counts_match_the_audit(self):
        self.assertEqual(len(self.categories), len(COUNTS))
        for category in self.categories:
            self.assertEqual(
                len(category.requirement_ids),
                COUNTS[category.code],
                category.code,
            )
        self.assertEqual(len(self.requirements), sum(COUNTS.values()))

    def test_every_proof_has_a_repository_reference(self):
        lines = self.requirements.test_ids
        self.assertTrue(lines)
        for line in lines:
            self.assertIn(
                line.kind, ("repo_unittest", "node_test", "long_test")
            )
            self.assertRegex(line.reference, REPOSITORY_REFERENCE)
            if line.kind == "long_test":
                self.assertIn(":long_test/", line.reference)
            if line.kind == "node_test":
                self.assertTrue(
                    line.reference.startswith(
                        "erplibre-home-gnome-extension:test/unit/"
                    ),
                    line.reference,
                )

    def test_no_reference_points_into_the_moved_extension(self):
        # Les tests de l'extension vivent dans son propre dépôt : une
        # référence qui garde l'ancien chemin dans ERPLibre ne recevrait
        # jamais de verdict.
        lines = self.requirements.test_ids
        self.assertFalse(
            lines.filtered(
                lambda line: "script/gnome-extension" in line.reference
            )
        )
        self.assertTrue(
            lines.filtered(lambda line: line.kind == "node_test"),
            "the extension's node tests are proofs too",
        )
        # Les tests Python de la migration vivent dans le dépôt de
        # l'extension : leur preuve le nomme, jamais ERPLibre.
        self.assertFalse(
            lines.filtered(
                lambda line: "test_erplibre_home_migrate_legacy"
                in line.reference
            )
        )
        self.assertTrue(
            lines.filtered(
                lambda line: line.reference.startswith(
                    "erplibre-home-gnome-extension:test/python/"
                )
            )
        )

    def test_text_with_markup_characters_survives(self):
        # Chevrons, guillemets, accolades, esperluettes et flèche passent
        # par l'échappement XML et reviennent tels que l'audit les écrit.
        texts = {
            "SD-GREPO-R14": (
                "CONTRACT.md, Gallery: GET /launch/<id> answers 2xx when the "
                'game starts, otherwise {"error": line} with 403 when the '
                "games are off and 404 for an unknown id"
            ),
            "SD-DEPLOY-R55": (
                "udev rule /etc/udev/rules.d/70-streamdeck.rules, the two "
                "uaccess lines for 0fd9, compared before replacing, then "
                "udevadm control --reload-rules && udevadm trigger"
            ),
            "SD-EXT-R40": (
                "Terminal fallback gnome-terminal → xterm → kgx; with none "
                "of them, a notification"
            ),
        }
        for code, text in texts.items():
            self.assertEqual(self._requirement(code).name, text)

    def test_a_long_text_keeps_its_whole_text_in_the_description(self):
        # Le nom est borné ; le texte entier passe alors à la description.
        requirement = self._requirement("SD-SERVICE-R07")
        self.assertLessEqual(len(requirement.name), 250)
        self.assertTrue(requirement.name.endswith("…"))
        self.assertGreater(len(requirement.description), 250)
        self.assertTrue(
            requirement.description.startswith(requirement.name[:-1])
        )

    def test_requirement_data_is_noupdate(self):
        data = self.env["ir.model.data"].search(
            [
                ("module", "=", MODULE),
                (
                    "model",
                    "in",
                    [
                        "devops.requirement",
                        "devops.requirement.category",
                        "devops.requirement.test",
                    ],
                ),
            ]
        )
        self.assertTrue(data)
        self.assertTrue(all(data.mapped("noupdate")))
        # Chacun des requis de ces dix domaines vient des données ; le
        # domaine Inventaire a son propre test.
        self.assertEqual(
            len(
                data.filtered(
                    lambda d: d.model == "devops.requirement"
                    and d.res_id in self.requirements.ids
                )
            ),
            len(self.requirements),
        )
        # Une mise à jour du module relit le fichier : un requis déjà
        # présent et retouché à la main garde sa retouche.
        requirement = self._requirement("SD-DEFECTS-R02")
        requirement.write({"name": "Edited by hand", "done": False})
        convert_file(
            self.env,
            MODULE,
            "data/devops_requirement.xml",
            {},
            mode="update",
        )
        requirement.invalidate_recordset()
        self.assertEqual(requirement.name, "Edited by hand")
        self.assertFalse(requirement.done)

    def test_a_shared_test_proves_several_requirements(self):
        Test = self.env["devops.requirement.test"]
        lines = Test.search(
            [
                ("kind", "=", "repo_unittest"),
                ("reference", "=", SHARED_REFERENCE),
            ]
        )
        self.assertGreaterEqual(len(lines.requirement_id), 2)
        updated = Test.record_result_by_reference(
            "repo_unittest", SHARED_REFERENCE, "passed", duration=0.5
        )
        self.assertEqual(updated, len(lines))
        self.assertEqual(set(lines.mapped("last_result")), {"passed"})

    def test_open_risks_and_security_invariants_are_classified(self):
        # Une question ouverte, un risque sans parade ou une suite à mener
        # reste à faire : un filtre « pas fait » les montre.
        for code in (
            "SD-MOBPLUG-R80",
            "SD-MOBPLUG-R90",
            "SD-RENAME-R44",
            "SD-SERVICE-R81",
            "SD-SERVICE-R82",
            "SD-DEPLOY-R126",
        ):
            requirement = self._requirement(code)
            self.assertFalse(requirement.done, code)
            self.assertTrue(requirement.missing, code)
        # Un secret, un mot de passe ou le mode d'un fichier : invariant de
        # sécurité.
        for code in (
            "SD-EXT-R28",
            "SD-EXT-R122",
            "SD-EXT-R55",
            "SD-EXT-R58",
            "SD-GREPO-R45",
        ):
            requirement = self._requirement(code)
            self.assertEqual(requirement.moscow, "must", code)
            self.assertEqual(requirement.requirement_type, "security", code)
            self.assertTrue(requirement.security_relevant, code)

    def test_a_done_requirement_lists_no_missing_work(self):
        # Un requis fait n'a plus rien à faire : « Ce qui manque » vide.
        done = self.requirements.filtered("done")
        self.assertFalse(done.filtered("missing").mapped("code"))

    def test_security_type_and_flag_agree(self):
        # Le type Sécurité et « Touche la sécurité » désignent les mêmes
        # requis : un filtre sur l'un trouve tous ceux de l'autre.
        self.assertFalse(
            self.requirements.filtered(
                lambda r: (r.requirement_type == "security")
                != r.security_relevant
            ).mapped("code")
        )

    def test_non_goals_are_wont_and_done(self):
        non_goals = self.requirements.filtered(
            lambda r: NON_GOAL.match(r.name)
        )
        self.assertIn("SD-DEFECTS-R89", non_goals.mapped("code"))
        for requirement in non_goals:
            self.assertEqual(requirement.moscow, "wont", requirement.code)
            self.assertTrue(requirement.done, requirement.code)
            self.assertFalse(requirement.missing, requirement.code)

    def test_notes_open_on_an_origin(self):
        for requirement in self.requirements:
            self.assertRegex(requirement.notes or "", ORIGIN, requirement.code)

    def test_french_follows_one_vocabulary(self):
        for entry in self._french_entries():
            self.assertNotRegex(entry.msgstr, FRENCH_LEXICON, entry.msgid)
            self.assertNotRegex(
                QUOTED_SHELL.sub("", entry.msgstr),
                GLUED_SEMICOLON,
                entry.msgid,
            )

    def test_no_text_carries_audit_shorthand(self):
        # Chaque texte se lit seul dans Odoo : ni alias de l'audit, ni
        # clone local daté, ni première personne.
        records = [(c, ("name",)) for c in self.categories]
        records += [(r, TEXT_FIELDS) for r in self.requirements]
        for record, fields in records:
            for field in fields:
                value = record[field] or ""
                self.assertNotRegex(value, AUDIT_ALIAS, record.display_name)
                self.assertNotRegex(value, FIRST_PERSON, record.display_name)
        for entry in self._french_entries():
            self.assertNotRegex(entry.msgstr, AUDIT_ALIAS, entry.msgid)

    def _french_entries(self):
        po = polib.pofile(file_path("%s/i18n/fr_CA.po" % MODULE))
        return [
            entry
            for entry in po
            if any(
                path.startswith("model:devops.requirement")
                for path, _line in entry.occurrences
            )
        ]

    def test_requirements_read_in_fr_CA(self):
        entries = self._french_entries()
        self.assertTrue(entries)
        self.assertFalse(
            [entry.msgid for entry in entries if not entry.msgstr],
            "every data term has its French",
        )
        self.env["res.lang"]._activate_lang("fr_CA")
        self.env["ir.module.module"]._load_module_terms(
            [MODULE], ["fr_CA"], overwrite=True
        )
        requirement = self._requirement("SD-GREPO-R14")
        category = self.categories.filtered(lambda c: c.code == "sd_deploy")
        for record, french in (
            (requirement, FRENCH["SD-GREPO-R14"]),
            (category, FRENCH["sd_deploy"]),
        ):
            name = record.with_context(lang="fr_CA").name
            self.assertEqual(name, french)
            self.assertNotEqual(name, record.with_context(lang="en_US").name)
