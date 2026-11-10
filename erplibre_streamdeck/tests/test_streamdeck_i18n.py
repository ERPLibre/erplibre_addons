# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import polib

from odoo.tests.common import TransactionCase, tagged
from odoo.tools.misc import file_path
from odoo.tools.translate import TranslationModuleReader

MODULE = "erplibre_streamdeck"


@tagged("post_install", "-at_install")
class TestStreamdeckI18n(TransactionCase):
    """Le catalogue `.pot` suit le module, et `fr_CA.po` traduit chacun de
    ses termes."""

    @staticmethod
    def _catalog(name):
        return polib.pofile(file_path("%s/i18n/%s" % (MODULE, name)))

    def test_the_template_holds_every_term_of_the_module(self):
        # Les termes que l'export d'Odoo tirerait du module installé :
        # données, vues, champs et chaînes `_()` du code.
        exported = {
            term[4]
            for term in TranslationModuleReader(self.env.cr, modules=[MODULE])
        }
        template = {entry.msgid for entry in self._catalog(MODULE + ".pot")}
        self.assertFalse(
            sorted(exported - template), "terms missing from the .pot"
        )
        self.assertFalse(
            sorted(template - exported), "terms the module no longer has"
        )

    def test_every_term_is_translated_in_fr_CA(self):
        template = {entry.msgid for entry in self._catalog(MODULE + ".pot")}
        french = self._catalog("fr_CA.po")
        self.assertEqual({entry.msgid for entry in french}, template)
        self.assertFalse(
            [entry.msgid for entry in french if not entry.msgstr],
            "every term has its French",
        )
        self.assertFalse(
            [entry.msgid for entry in french if "fuzzy" in entry.flags],
            "no translation is left fuzzy",
        )

        self.env["res.lang"]._activate_lang("fr_CA")
        self.env["ir.module.module"]._load_module_terms(
            [MODULE], ["fr_CA"], overwrite=True
        )
        for xmlid, english, translated in (
            (
                "erplibre_streamdeck.menu_streamdeck_my_workstations",
                "My workstations",
                "Mes postes",
            ),
            (
                "erplibre_streamdeck.menu_streamdeck_fleet",
                "Fleet",
                "Parc",
            ),
        ):
            with self.subTest(xmlid=xmlid):
                menu = self.env.ref(xmlid)
                self.assertEqual(menu.with_context(lang="en_US").name, english)
                self.assertEqual(
                    menu.with_context(lang="fr_CA").name, translated
                )
        Workstation = self.env["streamdeck.workstation"].with_context(
            lang="fr_CA"
        )
        self.assertEqual(
            Workstation.fields_get(["user_id"])["user_id"]["string"],
            "Employé",
        )
