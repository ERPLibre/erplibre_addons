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
        other = self.env.ref("%s.test_sd_bundle_r05_1" % MODULE)
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
