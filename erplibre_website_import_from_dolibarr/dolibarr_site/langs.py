# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Resolver of Dolibarr $weblangs->trans() keys from .lang files.

It follows Translate::load and Translate::trans of Dolibarr for the
domains a page loads on $weblangs. A file is read line by line (key, a
run of spaces and '=', value); a key keeps its first non-empty value; the
chain is the site locale, its xx_XX parent, then en_US. trans() output is
formatted and HTML-encoded in the same order as Dolibarr. Keys backed by
the Dolibarr database resolve to the key itself.
"""

import dataclasses
import hashlib
import html.entities
import pathlib
import re
import sys

from . import php, sqldump
from .messages import finding

BUNDLED_DOMAINS = (
    "main",
    "website",
    "languages",
    "members",
    "admin",
    "donations",
    "companies",
)
BUNDLED_LOCALES = ("en_US", "fr_FR")
BUNDLED_DIR = (
    pathlib.Path(__file__).resolve().parent.parent / "data" / "dolibarr_langs"
)
_LONG_FOR_SHORT = {
    "am": "am_ET", "ar": "ar_SA", "bn": "bn_DB", "el": "el_GR",
    "ca": "ca_ES", "cs": "cs_CZ", "en": "en_US", "fa": "fa_IR",
    "gl": "gl_ES", "he": "he_IL", "hi": "hi_IN", "ja": "ja_JP",
    "ka": "ka_GE", "km": "km_KH", "kn": "kn_IN", "ko": "ko_KR",
    "lo": "lo_LA", "nb": "nb_NO", "no": "nb_NO", "ne": "ne_NP",
    "sl": "sl_SI", "sq": "sq_AL", "sr": "sr_RS", "sv": "sv_SE",
    "uk": "uk_UA", "vi": "vi_VN", "zh": "zh_CN",
}  # fmt: skip
_PARENT_EXCEPTIONS = {"el_EL": "el_GR", "ar_AR": "ar_SA"}
_LINE = re.compile(r"^([^= ]+)[ =]+([^\n\r]+)")
_BAD_SPEC = re.compile(r"([^%])%([^%0sdmYIMpHSBb])")
_SPEC = re.compile(
    r"%(?:\d+\$)?(?P<flags>(?:[-+ 0]|'.)*)(?P<width>\d+)?"
    r"(?:\.(?P<prec>\d+))?(?P<conv>[bcdeEfFgGosuxX%])"
)
_KEEP = (
    ('"', "__quot__"), ("<b>", "__tagb__"), ("</b>", "__tagbend__"),
    ("<u>", "__tagu__"), ("</u>", "__taguend__"), ("<i>", "__tagi__"),
    ("</i>", "__tagiend__"), ("<center>", "__tagcenter__"),
    ("</center>", "__tagcenterend__"), ("<strong>", "__tagb__"),
    ("</strong>", "__tagbend__"), ("<a ", "__taga__"),
    ("</a>", "__tagaend__"), ("<br>", "__tagbr__"), ("<span", "__tagspan__"),
    ("</span>", "__tagspanend__"), ("< ", "__ltspace__"), (">", "__gt__"),
)  # fmt: skip
_RESTORE = (
    ("__quot__", '"'), ("__tagb__", "<b>"), ("__tagbend__", "</b>"),
    ("__tagu__", "<u>"), ("__taguend__", "</u>"), ("__tagi__", "<i>"),
    ("__tagiend__", "</i>"), ("__tagcenter__", "<center>"),
    ("__tagcenterend__", "</center>"), ("__taga__", "<a "),
    ("__tagaend__", "</a>"), ("__tagbr__", "<br>"), ("__tagspan__", "<span"),
    ("__tagspanend__", "</span>"), ("__ltspace__", "< "), ("__gt__", ">"),
)  # fmt: skip
_LOAD = re.compile(r"\$weblangs->load\(\s*(['\"])([A-Za-z0-9_@-]+)\1")
_LOADLANGS = re.compile(
    r"\$weblangs->loadLangs\(\s*(?:array\s*\(|\[)([^)\]]*)"
)
_QUOTED = re.compile(r"(['\"])([A-Za-z0-9_@-]+)\1")
_DOL_VERSION = re.compile(
    r"define\(\s*'DOL_(MAJOR|MINOR)_VERSION'\s*,\s*'([^']+)'\s*\)"
)


def bundled_version():
    path = BUNDLED_DIR / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def canonical_locale(code):
    """Dolibarr setDefaultLang: fr gives fr_FR, en gives en_US."""
    code = (code or "en").replace("-", "_")
    if "_" in code:
        lang, country = code.split("_", 1)
        return "%s_%s" % (lang.lower(), country.upper())
    code = code.lower()
    return _LONG_FOR_SHORT.get(code, "%s_%s" % (code, code.upper()))


def parent_locale(locale):
    lang = locale.split("_")[0].lower()
    parent = "%s_%s" % (lang, lang.upper())
    return _PARENT_EXCEPTIONS.get(parent, parent)


def _php_empty(value):
    return value in (None, "", "0")


def parse_lang_lines(text):
    """(key, value) pairs of a .lang file, as Translate::load reads them."""
    pairs = []
    for line in text.splitlines():
        match = _LINE.match(line)
        if not match or match.group(1).startswith("#"):
            continue
        value = match.group(2).replace("\\n", "\n").replace("\\\\s", "\\s")
        pairs.append((match.group(1), value))
    return pairs


def _sprintf_empty(text):
    """sprintf(text, '', '', '', ''): %s is empty, %d is 0, %% is %."""

    def repl(match):
        conv, prec = match.group("conv"), match.group("prec")
        flags = match.group("flags") or ""
        if conv == "%":
            return "%"
        if conv == "s":
            out = ""
        elif conv in "fF":
            out = "%.*f" % (int(prec) if prec else 6, 0)
        elif conv in "eE":
            out = ("%.*" + conv) % (int(prec) if prec else 6, 0)
            out = out.replace("e+00", "e+0").replace("E+00", "E+0")
        elif conv == "c":
            out = "\x00"
        else:
            out = "0"
        width = int(match.group("width") or 0)
        if len(out) < width:
            if "-" in flags:
                out = out.ljust(width)
            else:
                pad = "0" if "0" in flags and conv != "s" else " "
                out = out.rjust(width, pad)
        return out

    return _SPEC.sub(repl, text)


def _htmlentities(text):
    """PHP htmlentities(ENT_COMPAT): HTML 4 named entities, ' unchanged."""
    out = []
    for char in text:
        name = html.entities.codepoint2name.get(ord(char))
        out.append("&%s;" % name if name else char)
    return "".join(out)


def format_trans(value, key):
    """Output of Translate::trans() for a found value, in Dolibarr order."""
    text = _BAD_SPEC.sub(r"\1__percent_with_bad_specifier__\2", value)
    if not key.startswith("Format"):
        text = _sprintf_empty(text)
    text = text.replace("__percent_with_bad_specifier__", "%")
    for search, token in _KEEP:
        text = text.replace(search, token)
    text = _htmlentities(text)
    for token, restore in _RESTORE:
        text = text.replace(token, restore)
    return text.replace("%27", "").replace("&#39", "")


def weblangs_domains(code):
    """Domains loaded on $weblangs, in call order, comments excluded.

    Only the first argument of load() is a domain: the second is $alt.
    Calls on other objects ($langs, $emaillang) are ignored.
    """
    code = php.strip_comments(code)
    events = [(m.start(), [m.group(2)]) for m in _LOAD.finditer(code)]
    for match in _LOADLANGS.finditer(code):
        names = [q.group(2) for q in _QUOTED.finditer(match.group(1))]
        events.append((match.start(), names))
    found = []
    for _pos, names in sorted(events):
        for name in names:
            if name not in found:
                found.append(name)
    return found


@dataclasses.dataclass
class LangTable:
    values: dict
    inexact: set
    findings: list


class LangResolver:
    """Translation tables of one site locale over a langs folder."""

    def __init__(self, lang, langs_dir=None):
        self.locale = canonical_locale(lang)
        self.bundled = not langs_dir
        self.root = pathlib.Path(langs_dir) if langs_dir else BUNDLED_DIR
        self._files = {}

    @property
    def source_label(self):
        if self.bundled:
            return "bundled Dolibarr %s" % bundled_version()
        return "command-line folder"

    def _read(self, locale, domain):
        key = (locale, domain)
        if key not in self._files:
            path = self.root / locale / ("%s.lang" % domain)
            self._files[key] = (
                path.read_text(encoding="utf-8", errors="replace")
                if path.is_file()
                else None
            )
        return self._files[key]

    def table(self, domains):
        """Values of the domains loaded in order, as $weblangs holds them.

        A domain whose file is absent for the site locale resolves through
        the chain; its keys are inexact and one langs_fallback finding says
        which file answered.
        """
        values, inexact, findings = {}, set(), []
        chain = list(
            dict.fromkeys([self.locale, parent_locale(self.locale), "en_US"])
        )
        for domain in domains:
            present = self._read(self.locale, domain) is not None
            used = ""
            for locale in chain:
                text = self._read(locale, domain)
                if text is None:
                    continue
                used = used or locale
                for key, value in parse_lang_lines(text):
                    if _php_empty(values.get(key)):
                        values[key] = value
                        if present:
                            inexact.discard(key)
                        else:
                            inexact.add(key)
            if not present:
                findings.append(
                    finding(
                        "langs_fallback",
                        domain=domain,
                        lang=self.locale,
                        used=used or "none",
                    )
                )
        return LangTable(values, inexact, findings)

    def trans(self, key, table):
        """(text, exact) as $weblangs->trans(key) prints it."""
        value = table.values.get(key)
        if _php_empty(value):
            return key, not table.findings
        return format_trans(value, key), key not in table.inexact


def read_dolibarr_version(htdocs):
    text = (htdocs / "version.inc.php").read_text(encoding="utf-8")
    parts = dict(_DOL_VERSION.findall(text))
    return "%s.%s" % (parts.get("MAJOR", "0"), parts.get("MINOR", "0"))


def stock_domains(htdocs):
    """Domains the stock website templates load on $weblangs."""
    found = []
    pattern = "install/doctemplates/websites/*/website_pages.sql"
    for sql in sorted(htdocs.glob(pattern)):
        dump = sqldump.parse(sql.read_text(encoding="utf-8"))
        for row in dump.rows:
            for tok in php.tokenize(str(row.get("content") or "")):
                if isinstance(tok, php.Php):
                    for name in weblangs_domains(tok.code):
                        if name not in found:
                            found.append(name)
    return found


def refresh(htdocs, target=BUNDLED_DIR, check=False, out=sys.stdout):
    """Copy or compare the bundled .lang files against a Dolibarr checkout.

    README.md is never touched. Returns 0 when written or up to date, 1
    when --check finds a difference, 2 when a stock template loads a
    domain missing from BUNDLED_DOMAINS.
    """
    htdocs, target = pathlib.Path(htdocs), pathlib.Path(target)
    unknown = [d for d in stock_domains(htdocs) if d not in BUNDLED_DOMAINS]
    if unknown:
        out.write(
            "error: domains loaded on $weblangs but not bundled: %s\n"
            % ", ".join(unknown)
        )
        return 2
    expected = {}
    for locale in BUNDLED_LOCALES:
        for domain in BUNDLED_DOMAINS:
            name = "%s/%s.lang" % (locale, domain)
            expected[name] = (htdocs / "langs" / name).read_bytes()
    sums = "".join(
        "%s  %s\n" % (hashlib.sha256(data).hexdigest(), name)
        for name, data in sorted(expected.items())
    )
    expected["COPYING"] = (htdocs.parent / "COPYING").read_bytes()
    expected["VERSION"] = (read_dolibarr_version(htdocs) + "\n").encode()
    expected["SHA256SUMS"] = sums.encode()
    if check:
        differ = [
            name
            for name, data in sorted(expected.items())
            if not (target / name).is_file()
            or (target / name).read_bytes() != data
        ]
        for name in differ:
            out.write("differs: %s\n" % name)
        return 1 if differ else 0
    for name, data in expected.items():
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        (target / name).write_bytes(data)
    return 0
