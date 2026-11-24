# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import polib
from lxml import etree

from odoo.tests.common import TransactionCase, tagged
from odoo.tools.misc import file_path

MODULE = "erplibre_streamdeck"

# The terms of the managed configuration and their fr_CA text, as
# fr_CA.po holds them: menus, filters, tab, first-pilot setting and
# history labels.
CONFIG_TERMS = {
    "Configuration": "Configuration",
    "Profiles": "Profils",
    "Deck models": "Modèles de deck",
    "Selectable": "Au choix",
    "First pilot": "Premier pilotage",
    "First pilot policy": "Politique du premier pilotage",
    "Ask the employee": "Demander à l'employé",
    "Keep local values": "Garder les valeurs locales",
    "Take Odoo's values": "Prendre les valeurs d'Odoo",
    "Configuration pending": "Configuration en attente",
    "Configuration refused": "Configuration refusée",
    "Configuration applied": "Configuration appliquée",
    "Local setting adopted": "Réglage local adopté",
    "Setting changed locally": "Réglage changé localement",
    "Effective configuration": "Configuration effective",
    "Overrides of this workstation": "Surcharges de ce poste",
}


@tagged("post_install", "-at_install")
class TestStreamdeckConfigI18n(TransactionCase):
    """Les termes de la configuration pilotée en fr_CA : menus du
    gestionnaire, onglet du poste, réglage du premier pilotage, filtres et
    libellés de l'historique, dans `fr_CA.po` puis tels qu'Odoo les sert
    une fois les termes chargés.

    La complétude du catalogue est l'affaire de `test_streamdeck_i18n` ;
    ici, chaque terme a SON texte.
    """

    def test_every_configuration_term_has_its_fr_CA_text(self):
        french = {
            entry.msgid: entry.msgstr
            for entry in polib.pofile(file_path("%s/i18n/fr_CA.po" % MODULE))
        }
        for english, translated in CONFIG_TERMS.items():
            with self.subTest(term=english):
                self.assertEqual(french.get(english), translated)

        self.env["res.lang"]._activate_lang("fr_CA")
        self.env["ir.module.module"]._load_module_terms(
            [MODULE], ["fr_CA"], overwrite=True
        )
        fr = self.env(context={"lang": "fr_CA"})
        for xmlid, name in (
            ("menu_streamdeck_configuration", "Configuration"),
            ("menu_streamdeck_config_profiles", "Profils"),
            ("menu_streamdeck_config_models", "Modèles de deck"),
            ("menu_streamdeck_config_policy", "Premier pilotage"),
        ):
            with self.subTest(menu=xmlid):
                self.assertEqual(fr.ref("%s.%s" % (MODULE, xmlid)).name, name)
        policy = fr["res.config.settings"].fields_get(
            ["streamdeck_first_pilot_policy"]
        )["streamdeck_first_pilot_policy"]
        self.assertEqual(policy["string"], "Premier pilotage")
        self.assertEqual(
            dict(policy["selection"]),
            {
                "ask": "Demander à l'employé",
                "keep_local": "Garder les valeurs locales",
                "take_odoo": "Prendre les valeurs d'Odoo",
            },
        )
        for model, name, string in (
            (
                "streamdeck.workstation",
                "config_pending",
                "Configuration en attente",
            ),
            (
                "streamdeck.workstation",
                "config_refused",
                "Configuration refusée",
            ),
            ("streamdeck.event", "config_applied", "Configuration appliquée"),
            ("streamdeck.event", "config_drift", "Réglage changé localement"),
        ):
            with self.subTest(model=model, filter=name):
                arch = fr[model].get_views([(False, "search")])["views"][
                    "search"
                ]["arch"]
                (node,) = etree.fromstring(arch).xpath(
                    "//filter[@name='%s']" % name
                )
                self.assertEqual(node.get("string"), string)
        arch = fr["streamdeck.workstation"].get_views([(False, "form")])[
            "views"
        ]["form"]["arch"]
        (page,) = etree.fromstring(arch).xpath("//page[@name='configuration']")
        self.assertEqual(page.get("string"), "Configuration")
        self.assertIn(
            "Surcharges de ce poste", etree.tostring(page, encoding=str)
        )
