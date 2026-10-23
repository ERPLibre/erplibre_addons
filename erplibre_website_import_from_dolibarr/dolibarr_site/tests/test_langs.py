# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import hashlib
import io
import pathlib
import tempfile
import unittest

from ..langs import (
    BUNDLED_DIR,
    BUNDLED_DOMAINS,
    BUNDLED_LOCALES,
    LangResolver,
    bundled_version,
    canonical_locale,
    format_trans,
    parent_locale,
    refresh,
    weblangs_domains,
)

SQL_TEMPLATE = (
    "INSERT INTO llx_website_page(rowid, pageurl, type_container, content)"
    " VALUES(1__+MAX_llx_website_page__, 'p', 'page', '%s');\n"
)
STOCK_CODE = (
    '<?php $weblangs->loadLangs(array(\\"main\\",\\"website\\"));'
    ' $weblangs->load(\\"admin\\", \\"zzz\\");'
    " $langs->load(\\'recruitment\\');"
    " $emaillang->loadLangs(array(\\'agenda\\'));"
    ' //$weblangs->load(\\"withdrawals\\");\n ?>'
)


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        content if isinstance(content, bytes) else content.encode()
    )  # noqa: E501


class LangsCases:
    def test_bundle_is_complete_and_checksummed(self):
        self.assertTrue(bundled_version().strip())
        self.assertTrue((BUNDLED_DIR / "README.md").is_file())
        self.assertTrue((BUNDLED_DIR / "COPYING").is_file())
        sums = {}
        for line in (BUNDLED_DIR / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ", 1)
            sums[name] = digest
        for locale in BUNDLED_LOCALES:
            for domain in BUNDLED_DOMAINS:
                name = "%s/%s.lang" % (locale, domain)
                data = (BUNDLED_DIR / name).read_bytes()
                self.assertTrue(data.startswith(b"# Dolibarr language file"))
                self.assertEqual(hashlib.sha256(data).hexdigest(), sums[name])

    def _fake_htdocs(self, root, extra_code=""):
        htdocs = root / "dolibarr" / "htdocs"
        write(
            htdocs / "version.inc.php",
            "<?php\ndefine('DOL_MAJOR_VERSION', '99');\n"
            "define('DOL_MINOR_VERSION', '1.2');\n",
        )
        write(root / "dolibarr" / "COPYING", "GPL text\n")
        for locale in BUNDLED_LOCALES:
            for domain in BUNDLED_DOMAINS:
                write(
                    htdocs / "langs" / locale / ("%s.lang" % domain),
                    "# Dolibarr language file - Source file is en_US - %s\n"
                    "Home=Home %s\n" % (domain, locale),
                )
        write(
            htdocs
            / "install/doctemplates/websites/website_template-x"
            / "website_pages.sql",
            SQL_TEMPLATE % (STOCK_CODE + extra_code),
        )
        return htdocs

    def test_refresh_then_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            htdocs = self._fake_htdocs(root)
            target = root / "bundle"
            out = io.StringIO()
            self.assertEqual(refresh(htdocs, target, out=out), 0)
            self.assertEqual((target / "VERSION").read_text(), "99.1.2\n")
            self.assertEqual((target / "COPYING").read_text(), "GPL text\n")
            self.assertEqual(refresh(htdocs, target, check=True, out=out), 0)
            write(target / "fr_FR/main.lang", "# Dolibarr language file\n")
            self.assertEqual(refresh(htdocs, target, check=True, out=out), 1)
            self.assertIn("fr_FR/main.lang", out.getvalue())

    def test_refresh_refuses_unbundled_domain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            htdocs = self._fake_htdocs(
                root, "<?php $weblangs->load(\\'agenda\\'); ?>"
            )
            out = io.StringIO()
            self.assertEqual(refresh(htdocs, root / "b", out=out), 2)
            self.assertIn("agenda", out.getvalue())

    def test_weblangs_domains(self):
        code = (
            "$weblangs->loadLangs(array('main', \"website\"));"
            " $weblangs->load('admin', 'alt'); $langs->load('x');"
            " // $weblangs->load('hidden')\n $weblangs->loadLangs(['members'])"
        )
        self.assertEqual(
            weblangs_domains(code), ["main", "website", "admin", "members"]
        )

    def test_locales(self):
        self.assertEqual(canonical_locale("en"), "en_US")
        self.assertEqual(canonical_locale("fr"), "fr_FR")
        self.assertEqual(canonical_locale("fr-ca"), "fr_CA")
        self.assertEqual(canonical_locale("zh"), "zh_CN")
        self.assertEqual(parent_locale("fr_CA"), "fr_FR")
        self.assertEqual(parent_locale("el_CY"), "el_GR")

    def _dir(self, root):
        write(root / "en_US/main.lang", "Home=Home\nEmpty=\nZero=0\n# c=x\n")
        write(root / "en_US/website.lang", "Empty=Filled\nZero=Zed\n")
        write(root / "fr_FR/main.lang", "Home=Accueil\n")
        write(root / "fr_FR/website.lang", "Other=Autre\n")
        return str(root)

    def test_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            langs_dir = self._dir(pathlib.Path(tmp))
            en = LangResolver("en", langs_dir)
            nothing = en.table([])
            self.assertEqual(en.trans("Home", nothing), ("Home", True))
            both = en.table(["main", "website"])
            self.assertEqual(en.trans("Empty", both)[0], "Filled")
            self.assertEqual(en.trans("Zero", both)[0], "Zed")
            self.assertEqual(en.trans("Home", both), ("Home", True))
            fr = LangResolver("fr", langs_dir)
            self.assertEqual(
                fr.trans("Home", fr.table(["main"])), ("Accueil", True)
            )  # noqa: E501
            ca = LangResolver("fr_CA", langs_dir)
            table = ca.table(["main"])
            self.assertEqual(ca.trans("Home", table), ("Accueil", False))
            self.assertEqual(
                [f.code for f in table.findings], ["langs_fallback"]
            )  # noqa: E501
            self.assertEqual(table.findings[0].params["used"], "fr_FR")

    def test_bundled_resolution(self):
        fr = LangResolver("fr")
        self.assertEqual(fr.trans("Home", fr.table(["main"]))[0], "Accueil")
        self.assertTrue(fr.source_label.startswith("bundled Dolibarr "))

    def test_trans_output(self):
        self.assertEqual(
            format_trans("Field '%s' is required", "ErrorFieldRequired"),
            "Field '' is required",
        )
        self.assertEqual(format_trans("%d items", "N"), "0 items")
        self.assertEqual(
            format_trans("%m/%d/%Y", "FormatDateShort"), "%m/%d/%Y"
        )  # noqa: E501
        self.assertEqual(format_trans("100% sure", "K"), "100% sure")
        self.assertEqual(format_trans('a > b "c"', "K"), 'a > b "c"')
        out = format_trans("<script>x</script><br><strong>b</strong>", "K")
        self.assertNotIn("<script", out)
        self.assertIn("&lt;script", out)
        self.assertIn("<br><b>b</b>", out)
        self.assertEqual(format_trans("élève", "K"), "&eacute;l&egrave;ve")
        self.assertEqual(format_trans("a%27b", "K"), "ab")

    def test_literal_newline_in_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            write(root / "en_US/main.lang", "Two=a\\nb\nSp=x\\\\sy\n")
            en = LangResolver("en", str(root))
            table = en.table(["main"])
            self.assertEqual(en.trans("Two", table)[0], "a\nb")
            self.assertEqual(en.trans("Sp", table)[0], "x\\sy")


class TestLangs(LangsCases, unittest.TestCase):
    pass
