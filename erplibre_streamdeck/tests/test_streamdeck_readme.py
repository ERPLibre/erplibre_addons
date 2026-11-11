# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import BaseCase, tagged
from odoo.tools.misc import file_path

MODULE = "erplibre_streamdeck"


def _section(name, heading):
    """Text of the `heading` section of the module's `name` README, from
    the line after the heading to the next heading of any level, with its
    whitespace folded to single spaces so that a sentence wrapped by mmg
    reads as one line."""
    with open(file_path("%s/%s" % (MODULE, name)), encoding="utf-8") as f:
        lines = f.read().splitlines()
    start = lines.index(heading) + 1
    end = next(
        (i for i in range(start, len(lines)) if lines[i].startswith("#")),
        len(lines),
    )
    return " ".join(" ".join(lines[start:end]).split())


@tagged("post_install", "-at_install")
class TestStreamdeckReadme(BaseCase):
    """Ce que le README dit qu'Odoo peut faire sur un poste, en anglais et
    en français : l'extension redémarre le service du deck seulement
    quand il tourne, et ne démarre jamais un service arrêté. Le README est
    lu par l'administrateur pour borner le pouvoir d'Odoo ; une
    application qui démarrerait un deck arrêté l'élargirait."""

    def test_the_readme_says_a_stopped_deck_is_never_started(self):
        for name, heading, sentences in (
            (
                "README.md",
                "### Offer and application",
                (
                    "a setting that needs it changed and the service is"
                    " running",
                    "a stopped deck service is never started",
                ),
            ),
            (
                "README.fr.md",
                "### Proposition et application",
                (
                    "un réglage qui l'exige a changé et que le service"
                    " tourne",
                    "un service du deck arrêté n'est jamais démarré",
                ),
            ),
        ):
            text = _section(name, heading)
            for sentence in sentences:
                with self.subTest(readme=name, sentence=sentence):
                    self.assertIn(sentence, text)
