# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import re

from odoo.tests.common import TransactionCase, tagged
from odoo.tools.convert import convert_file

MODULE = "erplibre_streamdeck_devops_requirement"

# Requis par domaine, tels que le générateur les a comptés dans l'audit
# des specs Stream Deck : une ligne « obsolete » ne donne aucun requis.
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
        # Les tests Python de la migration ont suivi l'extension dans son
        # dépôt : leur preuve la nomme, jamais ERPLibre.
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
                "Contract 5: GET /launch/<id> 2xx when started, else "
                '{"error": line}, 403 games off, 404 unknown id'
            ),
            "SD-DEPLOY-R55": (
                "udev rule /etc/udev/rules.d/70-streamdeck.rules, the two "
                "uaccess lines for 0fd9, compared before replacing, then "
                "udevadm control --reload-rules && udevadm trigger"
            ),
            "SD-EXT-R31": (
                "Games GET http://localhost:8042/api/games, click → "
                "/launch/<id>"
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
        self.assertEqual(
            len(data.filtered(lambda d: d.model == "devops.requirement")),
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
