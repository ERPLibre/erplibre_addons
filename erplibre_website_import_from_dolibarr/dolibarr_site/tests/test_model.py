# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import unittest

from ..model import (
    Finding,
    Media,
    MenuItem,
    Options,
    Page,
    PageError,
    PageRow,
    RenderedSite,
    Site,
)


class ModelCases:
    def test_site_json_round_trip(self):
        site = Site(
            source_key="exemplesite",
            main_lang="en",
            pages=[
                Page(
                    ref="about",
                    aliases=["a-propos"],
                    qweb_nodes={"1": {"kind": "company", "field": "name"}},
                    findings=[Finding("info", "credits", params={"a": "b"})],
                )
            ],
            media=[Media(relpath="image/exemplesite/logo.png", size=3)],
            menu=[
                MenuItem(
                    "Home",
                    "dolibarr-page:home",
                    children=[MenuItem("Sub", "https://www.example.org/")],
                )
            ],
        )
        data = json.loads(json.dumps(site.to_json()))
        again = Site.from_json(data)
        self.assertEqual(again, site)
        self.assertIsInstance(again.pages[0], Page)
        self.assertIsInstance(again.pages[0].findings[0], Finding)
        self.assertIsInstance(again.menu[0].children[0], MenuItem)

    def test_other_round_trips(self):
        for obj in (
            PageRow(ref="x", status="foreign_unlinked", include=True),
            RenderedSite(pages={"x": "<t/>"}),
            Options(include_page_refs=["a"], keep_scripts=True),
        ):
            self.assertEqual(type(obj).from_json(obj.to_json()), obj)

    def test_page_by_ref(self):
        site = Site(pages=[Page(ref="a"), Page(ref="b")])
        self.assertEqual(site.page("b").ref, "b")
        self.assertIsNone(site.page("c"))

    def test_page_error_carries_ref(self):
        err = PageError("legacy", "too deep")
        self.assertEqual((err.ref, err.detail), ("legacy", "too deep"))


class TestModel(ModelCases, unittest.TestCase):
    pass
