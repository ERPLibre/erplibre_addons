# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import re
import shutil
import tempfile
from pathlib import Path

from odoo.tests.common import BaseCase, tagged

# Les deux modules balayés, frères dans ce dépôt : ce module dépend de
# erplibre_streamdeck, et l'un ne s'installe jamais sans l'autre.
MODULES = ("erplibre_streamdeck", "erplibre_streamdeck_devops_requirement")
ADDONS = Path(__file__).resolve().parents[2]

# Les fichiers texte d'un module : code, données, catalogues, pages et
# documentation. Une image n'a rien à lire.
SUFFIXES = (
    ".py",
    ".xml",
    ".csv",
    ".po",
    ".pot",
    ".js",
    ".css",
    ".json",
    ".md",
    ".html",
)

# Les trois classes que refusent le hook commit-msg d'ERPLibre et
# check_comment_hygiene.py, par les mêmes motifs. La liste privée des noms
# de clients et de machines vit hors de ce dépôt : aucun nom n'est balayé ici.
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]*[\w-]\b")
# Un chemin de compte s'ouvre à la racine : un segment « home » au milieu
# d'un chemin, comme dans le nom d'un paquet Java, n'en est pas un.
# Un segment entre chevrons ou une variable est un gabarit, pas un compte.
HOME = re.compile(r"(?<![\w.~-])/(?:home|Users)/(?![<$\"'{])([\w.-]+)/")

# La liste permise, courte, et chaque entrée pour une raison :
# - une adresse : la boucle locale (127/8), une adresse de réseau (dernier
#   octet nul), un bloc de documentation de la RFC 5737, ou une version de
#   module Odoo (`18.0.1.4`), qui a la forme d'une adresse ; une adresse
#   privée désigne une machine d'un réseau réel et reste refusée ;
# - un courriel : le domaine du propriétaire du dépôt, que porte l'UUID de
#   l'extension, et les domaines réservés à l'exemple par la RFC 2606 ;
# - un chemin de compte : les comptes génériques des gabarits.
IPV4_DOCUMENTATION = ("192.0.2.", "198.51.100.", "203.0.113.")
EMAIL_ALLOWED = re.compile(
    r"@(?:technolibre|erplibre)\.|@(?:[\w-]+\.)*example\.(?:com|net|org)$",
    re.IGNORECASE,
)
HOME_ALLOWED = frozenset({"runner", "user", "utilisateur", "USER"})


def _is_host_address(value):
    """True when the four numbers of `value` name a machine: every octet
    within 0-255, and none of the allowed forms above."""
    numbers = [int(octet) for octet in value.split(".")]
    if any(number > 255 for number in numbers):
        return False
    if 12 <= numbers[0] <= 18 and numbers[1] == 0:
        return False
    if numbers[0] in (0, 127, 255) or numbers[3] == 0:
        return False
    return not value.startswith(IPV4_DOCUMENTATION)


def findings(text):
    """The identifying data of one line of text, as (kind, excerpt)
    pairs in the order they appear."""
    found = [
        (match.start(), "address", match.group(0))
        for match in IPV4.finditer(text)
        if _is_host_address(match.group(0))
    ]
    found += [
        (match.start(), "email", match.group(0))
        for match in EMAIL.finditer(text)
        if not EMAIL_ALLOWED.search(match.group(0))
    ]
    found += [
        (match.start(), "account path", match.group(0))
        for match in HOME.finditer(text)
        if match.group(1) not in HOME_ALLOWED
    ]
    return [(kind, excerpt) for _start, kind, excerpt in sorted(found)]


def sweep(roots):
    """The identifying data of every text file under `roots`, as
    (path, line, kind, excerpt) tuples sorted by path and line; `path`
    starts with the name of its root."""
    swept = []
    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in SUFFIXES:
                continue
            relative = path.relative_to(root.parent).as_posix()
            text = path.read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), start=1):
                for kind, excerpt in findings(line):
                    swept.append((relative, number, kind, excerpt))
    return swept


@tagged("post_install", "-at_install")
class TestStreamdeckIdentifyingData(BaseCase):
    """Aucune donnée identifiante dans les fichiers des deux modules du
    Stream Deck : ni adresse d'une machine, ni courriel, ni chemin de
    compte, dans le code, les données, les catalogues ou la documentation.

    Le test lit les fichiers et rien d'autre : il ne touche pas la base.
    """

    def test_no_file_of_the_modules_carries_identifying_data(self):
        roots = [ADDONS / module for module in MODULES]
        for root in roots:
            self.assertTrue((root / "__manifest__.py").is_file(), root)
        self.assertEqual(sweep(roots), [])

    def test_the_sweep_finds_a_planted_identifying_line(self):
        # Les valeurs plantées sont inventées et assemblées à l'exécution :
        # écrites en clair, ce fichier serait lui-même une trouvaille.
        address = ".".join(("10", "11", "12", "13"))
        email = "@".join(("someone", "invented-client.test"))
        account = "/home/%s/" % "jdoe"
        planted = {
            "models/planted.py": "HOST = %r\n" % address,
            "data/planted.xml": "<odoo><!-- %s --></odoo>\n" % email,
            "i18n/planted.po": 'msgid "%sdeck.log"\n' % account,
        }
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / MODULES[0]
            shutil.copytree(ADDONS / MODULES[0], root)
            self.assertEqual(sweep([root]), [])
            for name, line in planted.items():
                (root / name).write_text(line, encoding="utf-8")
            self.assertEqual(
                sweep([root]),
                [
                    ("%s/data/planted.xml" % MODULES[0], 1, "email", email),
                    (
                        "%s/i18n/planted.po" % MODULES[0],
                        1,
                        "account path",
                        account,
                    ),
                    (
                        "%s/models/planted.py" % MODULES[0],
                        1,
                        "address",
                        address,
                    ),
                ],
            )

    def test_only_the_listed_examples_are_allowed(self):
        for text in (
            "the gallery listens on 127.0.0.1",
            "this machine: 127.0.0.0/8",
            "a flood from 192.0.2.7",
            "module version 18.0.1.4.0",
            "the extension erplibre-home@technolibre.ca",
            "write to someone@example.org",
            "a template path /home/<user>/deck.log",
            "the package ca/erplibre/home/streamdeck/DeckRegistry.java",
        ):
            with self.subTest(text=text):
                self.assertEqual(findings(text), [])
        private = ".".join(("192", "168", "1", "20"))
        self.assertEqual(
            findings("a workstation at %s" % private), [("address", private)]
        )
