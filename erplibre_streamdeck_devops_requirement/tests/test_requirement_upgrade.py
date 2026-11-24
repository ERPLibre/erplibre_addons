# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import importlib.util

import polib
from lxml import etree

from odoo.tests.common import TransactionCase, tagged
from odoo.tools.misc import file_path

MODULE = "erplibre_streamdeck_devops_requirement"
MIGRATION = "%s/migrations/18.0.1.2.0/post-migrate.py" % MODULE
MIGRATION_1_3 = "%s/migrations/18.0.1.3.0/post-migrate.py" % MODULE
MIGRATION_1_4 = "%s/migrations/18.0.1.4.0/post-migrate.py" % MODULE
MIGRATION_1_5 = "%s/migrations/18.0.1.5.0/post-migrate.py" % MODULE
INVENTORY = "%s/data/requirement_inventory.xml" % MODULE
CONTROL = "%s/data/requirement_control.xml" % MODULE
MONITORING = "%s/data/requirement_monitoring.xml" % MODULE
AUDIT_PROOFS = "%s/data/devops_requirement_test.xml" % MODULE
REQUIREMENTS = "%s/data/devops_requirement.xml" % MODULE
# Une référence de preuve à un test qui n'existe pas, comme celle qu'une
# base du lot 1 garde d'un test renommé depuis.
GONE = (
    "odoo.addons.erplibre_streamdeck.tests.test_streamdeck_access."
    "TestStreamdeckAccess.test_a_test_renamed_since"
)
# Le nom qu'un test de contrat de l'extension portait jusqu'à son
# contrat 1.3, et qu'une base de la version 18.0.1.2.0 cite encore.
CONTRACT_1_2 = (
    "erplibre-home-gnome-extension:test/unit/contract.test.js::"
    "the contract is at 1.2 since the extension reports to Odoo"
)
# Le nom qu'il portait jusqu'au contrat 1.4, qu'une base de la version
# 18.0.1.3.0 cite encore.
CONTRACT_1_3 = (
    "erplibre-home-gnome-extension:test/unit/contract.test.js::"
    "the contract is at 1.3 since Odoo pilots the deck settings"
)
# Le nom qu'il portait jusqu'au contrat 1.5, qu'une base de la version
# 18.0.1.4.0 cite encore.
CONTRACT_1_4 = (
    "erplibre-home-gnome-extension:test/unit/contract.test.js::"
    "the contract is at 1.4 since Odoo lays out the home keys"
)


@tagged("post_install", "-at_install")
class TestRequirementUpgrade(TransactionCase):
    """Une base dont les requis viennent d'une version antérieure du
    module, mise à niveau.

    Les fichiers de données sont noupdate : une mise à niveau ne récrit
    aucun requis, et la migration récrit ceux dont le texte a changé
    depuis. Le test met la base dans l'état d'avant, lance le script de
    migration comme Odoo le lance, puis charge les traductions sans
    écraser, comme la mise à niveau qui le suit.
    """

    def _migrate(self, version, migration=MIGRATION):
        spec = importlib.util.spec_from_file_location(
            "streamdeck_requirement_post_migrate", file_path(migration)
        )
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        script.migrate(self.env.cr, version)

    @staticmethod
    def _in_file(xmlid, field, data=INVENTORY):
        [node] = etree.parse(file_path(data)).xpath(
            "//record[@id=$xmlid]/field[@name=$field]",
            xmlid=xmlid,
            field=field,
        )
        return node.text

    def test_an_upgrade_rewrites_the_requirements_rewritten_since(self):
        self.env["res.lang"]._activate_lang("fr_CA")
        requirement = self.env.ref("%s.req_sd_inv_r09" % MODULE)
        proof = self.env.ref("%s.test_sd_inv_r09_2" % MODULE)
        edited = self.env.ref("%s.req_sd_inv_r10" % MODULE)
        requirement.with_context(lang="en_US").write(
            {"name": "An outdated name", "achievement": "An outdated way"}
        )
        requirement.with_context(lang="fr_CA").write(
            {"name": "Un nom dépassé"}
        )
        proof.write({"reference": GONE})
        edited.with_context(lang="en_US").write({"name": "Edited by hand"})
        self._migrate("18.0.1.1.0")
        self.env["ir.module.module"]._load_module_terms([MODULE], ["fr_CA"])
        self.env.invalidate_all()
        name = self._in_file("req_sd_inv_r09", "name")
        self.assertEqual(requirement.with_context(lang="en_US").name, name)
        self.assertEqual(
            requirement.achievement,
            self._in_file("req_sd_inv_r09", "achievement"),
        )
        self.assertEqual(
            proof.reference, self._in_file("test_sd_inv_r09_2", "reference")
        )
        french = {
            entry.msgid: entry.msgstr
            for entry in polib.pofile(file_path("%s/i18n/fr_CA.po" % MODULE))
        }
        self.assertEqual(
            requirement.with_context(lang="fr_CA").name, french[name]
        )
        # Un requis que la migration ne nomme pas garde sa retouche, et
        # ceux qu'elle récrit restent noupdate.
        self.assertEqual(
            edited.with_context(lang="en_US").name, "Edited by hand"
        )
        data = self.env["ir.model.data"].search(
            [
                ("module", "=", MODULE),
                ("name", "in", ["req_sd_inv_r09", "test_sd_inv_r09_2"]),
            ]
        )
        self.assertEqual(len(data), 2)
        self.assertTrue(all(data.mapped("noupdate")))

    def test_an_install_runs_no_rewrite(self):
        # Sans version installée, rien n'est récrit : l'installation vient
        # de charger les fichiers.
        proof = self.env.ref("%s.test_sd_inv_r09_2" % MODULE)
        proof.write({"reference": GONE})
        self._migrate(None)
        self.assertEqual(proof.reference, GONE)

    def test_an_upgrade_to_1_3_follows_the_renamed_contract_test(self):
        requirement = self.env.ref("%s.req_sd_inv_r24" % MODULE)
        proof = self.env.ref("%s.test_sd_inv_r24_1" % MODULE)
        requirement.write({"achievement": "An outdated way"})
        proof.write({"reference": CONTRACT_1_2})
        self._migrate("18.0.1.2.0", MIGRATION_1_3)
        self.env.invalidate_all()
        reference = self._in_file("test_sd_inv_r24_1", "reference")
        self.assertNotEqual(reference, CONTRACT_1_2)
        self.assertEqual(proof.reference, reference)
        self.assertEqual(
            requirement.achievement,
            self._in_file("req_sd_inv_r24", "achievement"),
        )

    def test_an_upgrade_to_1_4_follows_the_renamed_contract_test(self):
        # Le contrat 1.4 renomme le test qui prouve SD-INV-R24 et
        # SD-CTL-R27 ; la disposition des touches fait mentir ce que
        # SD-CTL-R27 et SD-CTL-R43 disent de la version et des fichiers, et
        # SD-CTL-R47 gagne la règle des actions plugin du catalogue.
        proofs = {
            "test_sd_inv_r24_1": (INVENTORY, CONTRACT_1_3),
            "test_sd_ctl_r27_1": (CONTROL, CONTRACT_1_3),
        }
        for xmlid, (_data, former) in proofs.items():
            self.env.ref("%s.%s" % (MODULE, xmlid)).write(
                {"reference": former}
            )
        requirements = ("req_sd_ctl_r27", "req_sd_ctl_r43", "req_sd_ctl_r47")
        for xmlid in requirements:
            self.env.ref("%s.%s" % (MODULE, xmlid)).write(
                {"achievement": "An outdated way"}
            )
        renamed = self.env.ref("%s.req_sd_ctl_r27" % MODULE)
        renamed.write({"name": "An outdated name"})
        self._migrate("18.0.1.3.0", MIGRATION_1_4)
        self.env.invalidate_all()
        for xmlid, (data, former) in proofs.items():
            with self.subTest(xmlid=xmlid):
                reference = self._in_file(xmlid, "reference", data)
                self.assertNotEqual(reference, former)
                self.assertEqual(
                    self.env.ref("%s.%s" % (MODULE, xmlid)).reference,
                    reference,
                )
        for xmlid in requirements:
            with self.subTest(xmlid=xmlid):
                self.assertEqual(
                    self.env.ref("%s.%s" % (MODULE, xmlid)).achievement,
                    self._in_file(xmlid, "achievement", CONTROL),
                )
        self.assertEqual(
            renamed.name, self._in_file("req_sd_ctl_r27", "name", CONTROL)
        )

    def test_an_upgrade_to_1_4_marks_the_identifying_data_sweep_done(self):
        # SD-MON-R38 et SD-INV-R42 sont faits depuis la version 18.0.1.4.0 :
        # une base qui les garde à faire, avec leur écart, les reçoit faits
        # de la migration.
        cases = (("req_sd_mon_r38", MONITORING), ("req_sd_inv_r42", INVENTORY))
        requirements = {}
        for xmlid, _data in cases:
            requirements[xmlid] = self.env.ref("%s.%s" % (MODULE, xmlid))
            requirements[xmlid].write(
                {
                    "done": False,
                    "achievement": "An outdated way",
                    "missing": "An outdated gap",
                    "notes": "Origin: unit test missing.",
                }
            )
        self._migrate("18.0.1.3.0", MIGRATION_1_4)
        self.env.invalidate_all()
        for xmlid, data in cases:
            requirement = requirements[xmlid]
            with self.subTest(requirement=xmlid):
                self.assertTrue(requirement.done)
                self.assertFalse(requirement.missing)
                for field in ("achievement", "notes"):
                    self.assertEqual(
                        requirement[field], self._in_file(xmlid, field, data)
                    )
                self.assertTrue(requirement.test_ids)

    def test_an_upgrade_to_1_5_follows_the_renamed_contract_test(self):
        # Le contrat 1.5 renomme le test qui prouve SD-INV-R24, SD-CTL-R27
        # et SD-CTL-R66 : une base de la version 18.0.1.4.0, dont la
        # migration est déjà passée, cite encore le nom du contrat 1.4.
        proofs = {
            "test_sd_inv_r24_1": INVENTORY,
            "test_sd_ctl_r27_1": CONTROL,
            "test_sd_ctl_r66_1": CONTROL,
        }
        for xmlid in proofs:
            self.env.ref("%s.%s" % (MODULE, xmlid)).write(
                {"reference": CONTRACT_1_4}
            )
        self._migrate("18.0.1.4.0", MIGRATION_1_5)
        self.env.invalidate_all()
        for xmlid, data in proofs.items():
            with self.subTest(xmlid=xmlid):
                reference = self._in_file(xmlid, "reference", data)
                self.assertNotEqual(reference, CONTRACT_1_4)
                self.assertEqual(
                    self.env.ref("%s.%s" % (MODULE, xmlid)).reference,
                    reference,
                )

    def test_an_upgrade_to_1_5_follows_the_deck_citations_of_the_texts(self):
        # Le texte d'un requis cite les tests du deck sous test/
        # d'ERPLibre sur une base de la version 18.0.1.4.0 : la migration
        # récrit ces citations sur place, retouche gardée, et laisse celles
        # des tests qu'ERPLibre garde.
        cases = (
            ("req_sd_deploy_r15", "achievement", ""),
            ("req_sd_plugin_r04", "achievement", " Edited by hand."),
            ("req_sd_plugin_r94", "missing", ""),
        )
        for xmlid, field, edit in cases:
            text = self._in_file(xmlid, field, REQUIREMENTS)
            self.assertIn("erplibre_streamdeck:tests/", text)
            former = text.replace(
                "erplibre_streamdeck:tests/test_entry_points.py",
                "erplibre:test/test_streamdeck_entry_points.py",
            ).replace("erplibre_streamdeck:tests/", "erplibre:test/")
            self.env.ref("%s.%s" % (MODULE, xmlid)).write(
                {field: former + edit}
            )
        kept = self.env.ref("%s.req_sd_deploy_r17" % MODULE)
        self.assertIn(
            "erplibre:test/test_streamdeck_entry_points.py::TestMakefile",
            kept.achievement,
        )
        before = kept.achievement
        self._migrate("18.0.1.4.0", MIGRATION_1_5)
        self.env.invalidate_all()
        for xmlid, field, edit in cases:
            with self.subTest(xmlid=xmlid):
                self.assertEqual(
                    self.env.ref("%s.%s" % (MODULE, xmlid))[field],
                    self._in_file(xmlid, field, REQUIREMENTS) + edit,
                )
        self.assertEqual(kept.achievement, before)

    def test_an_upgrade_to_1_5_names_the_deck_link_of_an_event(self):
        # SD-INV-R09 dit depuis la version 18.0.1.5.0 comment un événement
        # lie son deck : une base de la version 18.0.1.4.0 reçoit le texte
        # du fichier, son nom traduit rechargé du catalogue, et un autre
        # requis garde sa retouche.
        self.env["res.lang"]._activate_lang("fr_CA")
        requirement = self.env.ref("%s.req_sd_inv_r09" % MODULE)
        achievement = self._in_file("req_sd_inv_r09", "achievement")
        self.assertIn("device_readable", achievement)
        requirement.write(
            {"achievement": achievement.split("; the event form")[0] + "."}
        )
        edited = self.env.ref("%s.req_sd_inv_r10" % MODULE)
        edited.write({"achievement": "Edited by hand"})
        self._migrate("18.0.1.4.0", MIGRATION_1_5)
        self.env["ir.module.module"]._load_module_terms([MODULE], ["fr_CA"])
        self.env.invalidate_all()
        self.assertEqual(requirement.achievement, achievement)
        name = self._in_file("req_sd_inv_r09", "name")
        french = {
            entry.msgid: entry.msgstr
            for entry in polib.pofile(file_path("%s/i18n/fr_CA.po" % MODULE))
        }
        self.assertEqual(
            requirement.with_context(lang="fr_CA").name, french[name]
        )
        self.assertEqual(edited.achievement, "Edited by hand")
        self.assertIn(
            "test_an_event_links_its_deck_only_to_who_reads_it",
            " ".join(requirement.test_ids.mapped("reference")),
        )

    def test_an_upgrade_to_1_5_follows_the_deck_tests_to_their_repo(self):
        # Les tests du programme du deck ont quitté test/ d'ERPLibre pour
        # tests/ de leur dépôt : une base qui cite encore l'ancien chemin
        # reçoit le nouveau, et une preuve d'un autre dépôt garde le sien.
        proofs = {
            "test_sd_ctl_r43_7": CONTROL,
            "test_sd_service_r31_4": AUDIT_PROOFS,
        }
        for xmlid, data in proofs.items():
            reference = self._in_file(xmlid, "reference", data)
            self.assertTrue(reference.startswith("erplibre_streamdeck:"))
            self.env.ref("%s.%s" % (MODULE, xmlid)).write(
                {
                    "reference": reference.replace(
                        "erplibre_streamdeck:tests/", "erplibre:test/", 1
                    )
                }
            )
        other = self.env.ref("%s.test_sd_deploy_r45_2" % MODULE)
        other.write({"reference": GONE})
        self._migrate("18.0.1.4.0", MIGRATION_1_5)
        self.env.invalidate_all()
        for xmlid, data in proofs.items():
            with self.subTest(xmlid=xmlid):
                self.assertEqual(
                    self.env.ref("%s.%s" % (MODULE, xmlid)).reference,
                    self._in_file(xmlid, "reference", data),
                )
        self.assertEqual(other.reference, GONE)

    def test_an_upgrade_to_1_5_follows_the_stale_proofs(self):
        # Une base de la version 18.0.1.4.0 cite des tests qu'ERPLibre a
        # renommés ou retirés depuis : la preuve renommée suit son test, la
        # preuve retirée part, et son requis redevient à faire, son texte
        # repris du fichier.
        renamed = self.env.ref("%s.test_sd_deploy_r45_1" % MODULE)
        renamed.write(
            {
                "reference": "erplibre:test/test_install_erplibre_home.py"
                "::LesRefus::test_a_package_manager_failure_exits_one"
            }
        )
        requirement = self.env.ref("%s.req_sd_grepo_r41" % MODULE)
        requirement.write(
            {"done": True, "achievement": "An outdated way", "missing": False}
        )
        self.assertFalse(self._carried("test_sd_grepo_r41_1"))
        gone = self.env["devops.requirement.test"].create(
            {
                "requirement_id": requirement.id,
                "kind": "repo_unittest",
                "reference": "erplibre:test/test_install_erplibre_home.py"
                "::TestJeux::test_a_test_removed_since",
            }
        )
        self.env["ir.model.data"].create(
            {
                "module": MODULE,
                "name": "test_sd_grepo_r41_1",
                "model": gone._name,
                "res_id": gone.id,
                "noupdate": True,
            }
        )
        self._migrate("18.0.1.4.0", MIGRATION_1_5)
        self.env.invalidate_all()
        self.assertEqual(
            renamed.reference,
            self._in_file("test_sd_deploy_r45_1", "reference", AUDIT_PROOFS),
        )
        self.assertFalse(gone.exists())
        self.assertFalse(
            self.env.ref(
                "%s.test_sd_grepo_r41_1" % MODULE, raise_if_not_found=False
            )
        )
        self.assertFalse(requirement.done)
        self.assertFalse(requirement.achievement)
        self.assertEqual(
            requirement.missing,
            self._in_file("req_sd_grepo_r41", "missing", REQUIREMENTS),
        )

    def test_an_upgrade_to_1_5_renames_what_the_code_no_longer_names(self):
        # Un requis qui nomme une constante ou un fichier que le code n'a
        # plus prend le nom du fichier, dans les deux langues ; un requis
        # fait dont la seule preuve ne le prouvait pas redevient à faire.
        self.env["res.lang"]._activate_lang("fr_CA")
        renamed = self.env.ref("%s.req_sd_rename_r28" % MODULE)
        renamed.with_context(lang="en_US").write(
            {"name": "CONTROLLER_REL in lib/deck-service.js stays"}
        )
        renamed.with_context(lang="fr_CA").write(
            {"name": "CONTROLLER_REL de lib/deck-service.js reste"}
        )
        reset = self.env.ref("%s.req_sd_grepo_r43" % MODULE)
        reset.write(
            {
                "done": True,
                "missing": False,
                "notes": "Origin: unit test missing; a unit test pins it.",
            }
        )
        self.assertFalse(self._carried("test_sd_grepo_r43_1"))
        unproven = self.env["devops.requirement.test"].create(
            {
                "requirement_id": reset.id,
                "kind": "repo_unittest",
                "reference": "erplibre:test/test_install_erplibre_home.py"
                "::TestPoseParRepo::test_a_synced_checkout_follows_main",
            }
        )
        self.env["ir.model.data"].create(
            {
                "module": MODULE,
                "name": "test_sd_grepo_r43_1",
                "model": unproven._name,
                "res_id": unproven.id,
                "noupdate": True,
            }
        )
        self._migrate("18.0.1.4.0", MIGRATION_1_5)
        self.env["ir.module.module"]._load_module_terms([MODULE], ["fr_CA"])
        self.env.invalidate_all()
        name = self._in_file("req_sd_rename_r28", "name", REQUIREMENTS)
        self.assertEqual(renamed.with_context(lang="en_US").name, name)
        french = {
            entry.msgid: entry.msgstr
            for entry in polib.pofile(file_path("%s/i18n/fr_CA.po" % MODULE))
        }
        self.assertEqual(renamed.with_context(lang="fr_CA").name, french[name])
        self.assertFalse(unproven.exists())
        self.assertFalse(reset.done)
        for field in ("missing", "notes"):
            self.assertEqual(
                reset[field],
                self._in_file("req_sd_grepo_r43", field, REQUIREMENTS),
            )

    def test_an_upgrade_to_1_5_follows_the_renamed_hand_over(self):
        # La passation d'ERPLibre et son test portent le nom du service
        # qu'ils arrêtent : une base de la version 18.0.1.4.0 qui cite
        # l'ancien nom reçoit le nouveau, dans la référence d'une preuve,
        # le texte d'un requis, retouche gardée, et son nom, dans les deux
        # langues.
        self.env["res.lang"]._activate_lang("fr_CA")

        def former(text):
            return text.replace(
                "erplibre_home_streamdeck_handover", "erplibre_home_handover"
            )

        proof = self.env.ref("%s.test_sd_service_r31_1" % MODULE)
        reference = self._in_file(
            "test_sd_service_r31_1", "reference", AUDIT_PROOFS
        )
        self.assertIn("test_erplibre_home_streamdeck_handover.py", reference)
        proof.write({"reference": former(reference)})
        cases = (
            ("req_sd_gsplit_r43", "achievement", " Edited by hand."),
            ("req_sd_service_r88", "missing", ""),
        )
        for xmlid, field, edit in cases:
            text = self._in_file(xmlid, field, REQUIREMENTS)
            self.assertIn("erplibre_home_streamdeck_handover", text)
            self.env.ref("%s.%s" % (MODULE, xmlid)).write(
                {field: former(text) + edit}
            )
        french = {
            entry.msgid: entry.msgstr
            for entry in polib.pofile(file_path("%s/i18n/fr_CA.po" % MODULE))
        }
        named = self.env.ref("%s.req_sd_grepo_r17" % MODULE)
        name = self._in_file("req_sd_grepo_r17", "name", REQUIREMENTS)
        self.assertIn("erplibre_home_streamdeck_handover", french[name])
        named.with_context(lang="en_US").write({"name": former(name)})
        named.with_context(lang="fr_CA").write({"name": former(french[name])})
        self._migrate("18.0.1.4.0", MIGRATION_1_5)
        self.env["ir.module.module"]._load_module_terms([MODULE], ["fr_CA"])
        self.env.invalidate_all()
        self.assertEqual(proof.reference, reference)
        for xmlid, field, edit in cases:
            with self.subTest(xmlid=xmlid):
                self.assertEqual(
                    self.env.ref("%s.%s" % (MODULE, xmlid))[field],
                    self._in_file(xmlid, field, REQUIREMENTS) + edit,
                )
        self.assertEqual(named.with_context(lang="en_US").name, name)
        self.assertEqual(named.with_context(lang="fr_CA").name, french[name])

    def test_an_upgrade_to_1_5_follows_the_pattern_rule_of_the_games(self):
        # ERPLibre lance chaque jeu par une seule règle à motif, à travers
        # la passation : une base de la version 18.0.1.4.0 cite les tests
        # make d'une cible par jeu. La preuve suit le test renommé, le texte
        # d'un requis aussi, retouche gardée, et le risque ouvert que la
        # règle ferme devient fait, ses preuves posées, dans les deux
        # langues.
        self.env["res.lang"]._activate_lang("fr_CA")
        former = (
            "erplibre:test/test_streamdeck_entry_points.py::"
            "TestMakefileUsesTheVenv::"
            "test_every_game_target_requires_the_games_guard"
        )
        proof = self.env.ref("%s.test_sd_grepo_r56_2" % MODULE)
        proof.write({"reference": former})
        cited = self.env.ref("%s.req_sd_grepo_r93" % MODULE)
        text = self._in_file("req_sd_grepo_r93", "achievement", REQUIREMENTS)
        current = former.replace(
            "test_every_game_target_requires_the_games_guard",
            "test_one_pattern_rule_runs_every_game_behind_the_guard",
        )
        self.assertIn(current, text)
        cited.write(
            {"achievement": text.replace(current, former) + " Edited by hand."}
        )
        risk = self.env.ref("%s.req_sd_service_r82" % MODULE)
        risk.with_context(lang="en_US").write(
            {
                "name": "Open risk: make streamdeck_<game> skips the"
                " hand-over and takes no lock",
                "done": False,
                "achievement": "Stated in the install guide.",
                "missing": "Open risk: a game target runs the game directly.",
                "notes": "Origin: documented only.",
            }
        )
        risk.with_context(lang="fr_CA").write(
            {
                "name": "Risque ouvert : make streamdeck_<game> contourne la"
                " passation et ne prend aucun verrou"
            }
        )
        self.env.ref("%s.test_sd_service_r82_1" % MODULE).unlink()
        self._migrate("18.0.1.4.0", MIGRATION_1_5)
        self.env["ir.module.module"]._load_module_terms([MODULE], ["fr_CA"])
        self.env.invalidate_all()
        self.assertEqual(
            proof.reference,
            self._in_file("test_sd_grepo_r56_2", "reference", AUDIT_PROOFS),
        )
        self.assertEqual(cited.achievement, text + " Edited by hand.")
        name = self._in_file("req_sd_service_r82", "name", REQUIREMENTS)
        french = {
            entry.msgid: entry.msgstr
            for entry in polib.pofile(file_path("%s/i18n/fr_CA.po" % MODULE))
        }
        self.assertEqual(risk.with_context(lang="en_US").name, name)
        self.assertEqual(risk.with_context(lang="fr_CA").name, french[name])
        self.assertTrue(risk.done)
        self.assertFalse(risk.missing)
        for field in ("achievement", "notes"):
            self.assertEqual(
                risk[field],
                self._in_file("req_sd_service_r82", field, REQUIREMENTS),
            )
        restored = self.env.ref("%s.test_sd_service_r82_1" % MODULE)
        self.assertEqual(restored.requirement_id, risk)
        self.assertEqual(
            restored.reference,
            self._in_file("test_sd_service_r82_1", "reference", AUDIT_PROOFS),
        )

    def test_an_upgrade_to_1_5_proves_the_bundle_checker_again(self):
        # Les tests du vérificateur de bundle sont dans test/ d'ERPLibre :
        # une base de la version 18.0.1.4.0 qui tient ces requis pour à
        # faire, sans preuve, les reçoit faits, leurs preuves posées.
        proofs = {
            "req_sd_bundle_r05": [
                "test_sd_bundle_r05_%d" % n for n in (1, 2, 3, 4)
            ],
            "req_sd_bundle_r05b": [
                "test_sd_bundle_r05b_%d" % n for n in (1, 2)
            ],
        }
        for xmlid, lines in proofs.items():
            self.env.ref("%s.%s" % (MODULE, xmlid)).write(
                {
                    "done": False,
                    "missing": "No test pins the bundle checker.",
                    "notes": "Origin: unit test missing.",
                }
            )
            for line in lines:
                self.assertTrue(self._carried(line), line)
                proof = self.env.ref(
                    "%s.%s" % (MODULE, line), raise_if_not_found=False
                )
                if proof:
                    proof.unlink()
        self._migrate("18.0.1.4.0", MIGRATION_1_5)
        self.env.invalidate_all()
        for xmlid, lines in proofs.items():
            with self.subTest(xmlid=xmlid):
                requirement = self.env.ref("%s.%s" % (MODULE, xmlid))
                self.assertTrue(requirement.done)
                self.assertFalse(requirement.missing)
                self.assertEqual(
                    requirement.notes,
                    self._in_file(xmlid, "notes", REQUIREMENTS),
                )
                for line in lines:
                    proof = self.env.ref("%s.%s" % (MODULE, line))
                    self.assertEqual(proof.requirement_id, requirement)
                    self.assertEqual(
                        proof.reference,
                        self._in_file(line, "reference", AUDIT_PROOFS),
                    )

    @staticmethod
    def _carried(xmlid, data=AUDIT_PROOFS):
        """True when `data` still carries the record `xmlid`."""
        return bool(
            etree.parse(file_path(data)).xpath("//record[@id=$x]", x=xmlid)
        )
