# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import unittest

from ..model import (
    primary_lang,
    slugify_ref,
    valid_key,
    valid_lang,
    valid_ref,
    valid_relpath,
)


class ValidateCases:
    def test_key(self):
        self.assertTrue(valid_key("exemplesite"))
        self.assertTrue(valid_key("Exemple.site_2-b"))
        for bad in ("a{{1+1}}", "", ".hidden", "a..b", "a/b", "x" * 65, "a\n"):
            self.assertFalse(valid_key(bad), bad)

    def test_ref(self):
        self.assertTrue(valid_ref("Equipe"))
        self.assertTrue(valid_ref("news-1_b"))
        for bad in ("a'+1+'", "", "a b", "a.php", "x" * 129, "a\n"):
            self.assertFalse(valid_ref(bad), bad)

    def test_lang(self):
        for good in ("", "en", "fr_CA", "fr-ca", "ast"):
            self.assertTrue(valid_lang(good), good)
        for bad in ("english", "f", "fr_CAN", "fr;", "1a", "fr\n"):
            self.assertFalse(valid_lang(bad), bad)

    def test_relpath(self):
        key = "exemplesite"
        self.assertTrue(valid_relpath("image/exemplesite/logo.png", key))
        self.assertTrue(
            valid_relpath("image/exemplesite/sub dir/Été (1)+b,c.jpg", key)
        )
        self.assertTrue(valid_relpath("js/exemplesite/app.js", key))
        for bad in (
            "image/exemplesite/a').png",
            "image/exemplesite/../x.png",
            "image/exemplesite/./x.png",
            "image/other/x.png",
            "css/exemplesite/x.css",
            'image/exemplesite/a"b.png',
            "image/exemplesite/a;b.png",
            "image/exemplesite/a%20b.png",
            "image/exemplesite/a\x01b.png",
            "image/exemplesite/" + "x" * 250,
        ):
            self.assertFalse(valid_relpath(bad, key), bad)

    def test_slugify_and_primary_lang(self):
        self.assertEqual(slugify_ref("hé llo.php"), "h-llo-php")
        self.assertEqual(slugify_ref("!!!"), "page")
        self.assertEqual(primary_lang("fr_CA"), "fr")
        self.assertEqual(primary_lang("EN-us"), "en")
        self.assertEqual(primary_lang(""), "")


class TestValidate(ValidateCases, unittest.TestCase):
    pass
