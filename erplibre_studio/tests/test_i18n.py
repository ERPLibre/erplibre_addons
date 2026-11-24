# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import re

import polib

from odoo.tests import BaseCase, tagged
from odoo.tools.misc import file_path

# A French participle or adjective that agrees with the element named by
# its label (« %(label)s » then the word, or the word opening the sentence):
# the editor does not know the gender of a label, so each of them is wrong
# for half the labels. A word that agrees with a noun of the sentence
# (« un réglage modifié ») stays out.
AGREEING = re.compile(
    r"(^|%\(label\)s[ ,:]*(devient |n'est plus )?)"
    r"(masqué|affiché|déplacé|retiré|renommé|modifié|inséré|ajouté|rétabli"
    r"|requis|optionnel)\b",
    re.IGNORECASE,
)


@tagged("post_install", "-at_install")
class TestTranslations(BaseCase):
    """The French catalogue of the module against its template: every
    term of the .pot has a French text, and the web client receives the
    terms the .pot marks as used by JavaScript."""

    def _catalogues(self):
        pot = polib.pofile(file_path("erplibre_studio/i18n/erplibre_studio.pot"))
        french = polib.pofile(file_path("erplibre_studio/i18n/fr_CA.po"))
        return pot, {entry.msgid: entry for entry in french}

    def test_every_term_has_french(self):
        pot, french = self._catalogues()
        missing = [
            entry.msgid
            for entry in pot
            if entry.msgid not in french or not french[entry.msgid].msgstr
        ]
        self.assertFalse(missing, "Terms without a French text")
        fuzzy = [entry.msgid for entry in french.values() if entry.fuzzy]
        self.assertFalse(fuzzy, "Fuzzy French entries")

    def test_javascript_flag_follows_the_template(self):
        # Odoo serves the web client only the entries of the .po whose
        # comments carry « odoo-javascript »: a flag lost in fr_CA.po
        # leaves the term in English on screen.
        pot, french = self._catalogues()
        lost = [
            entry.msgid
            for entry in pot
            if "odoo-javascript" in entry.comment
            and entry.msgid in french
            and "odoo-javascript" not in french[entry.msgid].comment
        ]
        self.assertFalse(lost, "Terms used by JavaScript without the flag")

    def test_sentences_on_a_label_do_not_agree(self):
        # A sentence whose subject is the label of an element (« %(label)s
        # moved ») reads « Adresse déplacé » for a feminine label: its
        # French says it without a participle that agrees.
        _pot, french = self._catalogues()
        agreeing = [
            (entry.msgid, entry.msgstr)
            for entry in french.values()
            if entry.msgid.startswith(("%(label)s", "Inserted %(where)s"))
            and AGREEING.search(entry.msgstr)
        ]
        self.assertFalse(agreeing, "Sentences whose participle agrees")
