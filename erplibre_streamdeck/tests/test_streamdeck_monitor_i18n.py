# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import polib
from lxml import etree

from odoo.tests.common import TransactionCase, tagged
from odoo.tools.misc import file_path

MODULE = "erplibre_streamdeck"

# The monitoring terms and their fr_CA text, as fr_CA.po holds them.
MONITORING_TERMS = {
    "Workstation silent": "Poste muet",
    "Workstation heard again": "Poste revenu",
    "Resolved at %s: %s": "Résolu à %s : %s",
    "Service started": "Service démarré",
    "Service failed": "Service en échec",
    "Service stopped": "Service arrêté",
    "Service absent": "Service absent",
    "Deck service failed": "Service du deck en échec",
    "Deck unplugged for long": "Deck débranché longtemps",
    "Deck changed workstation": "Deck changé de poste",
    "Stream Deck detection activities": "Activités de détection Stream Deck",
    "Activities for": "Activités pour",
    "Activity manager": "Gestionnaire des activités",
    "Employee and manager": "Employé et gestionnaire",
    "Silent after (minutes)": "Muet après (minutes)",
    "Unplugged for long after (hours)": "Débranché longtemps après (heures)",
    "Service failed for (minutes)": "Service en échec depuis (minutes)",
    "Monitoring": "Surveillance",
    "Problems that open an activity": "Problèmes qui ouvrent une activité",
    "Silent since": "Muet depuis",
    "Silent": "Muets",
    "Event": "Événement",
}


@tagged("post_install", "-at_install")
class TestStreamdeckMonitorI18n(TransactionCase):
    """Les termes de la surveillance en fr_CA : sortes d'événement,
    libellés, types d'activité, Paramètres, filtres et colonnes, dans
    `fr_CA.po` puis tels qu'Odoo les sert une fois les termes chargés.

    La complétude du catalogue (chaque terme du module traduit) est
    l'affaire de `test_streamdeck_i18n` ; ici, chaque terme a SON texte.
    """

    def test_every_monitoring_term_has_its_fr_CA_text(self):
        french = {
            entry.msgid: entry.msgstr
            for entry in polib.pofile(file_path("%s/i18n/fr_CA.po" % MODULE))
        }
        for english, translated in MONITORING_TERMS.items():
            with self.subTest(term=english):
                self.assertEqual(french.get(english), translated)

        self.env["res.lang"]._activate_lang("fr_CA")
        self.env["ir.module.module"]._load_module_terms(
            [MODULE], ["fr_CA"], overwrite=True
        )
        fr = self.env(context={"lang": "fr_CA"})
        for kind, name in (
            ("service_failed", "Service du deck en échec"),
            ("silent", "Poste muet"),
            ("unplugged", "Deck débranché longtemps"),
            ("moved", "Deck changé de poste"),
        ):
            with self.subTest(activity_type=kind):
                xmlid = "%s.activity_type_streamdeck_%s" % (MODULE, kind)
                self.assertEqual(fr.ref(xmlid).name, name)
        settings = fr["res.config.settings"].fields_get(
            [
                "streamdeck_activities_enabled",
                "streamdeck_activity_recipient",
                "streamdeck_silent_after_min",
            ]
        )
        self.assertEqual(
            {name: field["string"] for name, field in settings.items()},
            {
                "streamdeck_activities_enabled": (
                    "Activités de détection Stream Deck"
                ),
                "streamdeck_activity_recipient": "Activités pour",
                "streamdeck_silent_after_min": "Muet après (minutes)",
            },
        )
        for model, name, string in (
            ("streamdeck.workstation", "silent", "Muets"),
            ("streamdeck.event", "silent", "Poste muet"),
            ("streamdeck.event", "heard_again", "Poste revenu"),
            ("streamdeck.event", "service_started", "Service démarré"),
            ("streamdeck.event", "service_failed", "Service en échec"),
        ):
            with self.subTest(model=model, filter=name):
                arch = fr[model].get_views([(False, "search")])["views"][
                    "search"
                ]["arch"]
                (node,) = etree.fromstring(arch).xpath(
                    "//filter[@name='%s']" % name
                )
                self.assertEqual(node.get("string"), string)
