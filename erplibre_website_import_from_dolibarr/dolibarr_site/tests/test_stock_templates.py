# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Optional pass on the stock website templates of a Dolibarr checkout.

Skipped unless DOLIBARR_HTDOCS names a Dolibarr htdocs folder. Nothing
from the templates is copied into the module: they are zipped in memory.
"""

import io
import os
import pathlib
import unittest
import zipfile

from ..model import Options
from ..php import Php, tokenize
from ..pipeline import all_findings, analyse, build_from_zip
from ..sqldump import parse

HTDOCS = os.environ.get("DOLIBARR_HTDOCS", "")


def zip_folder(folder):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(folder).as_posix())
    return buf.getvalue()


def block_count(sql_path):
    dump = parse(sql_path.read_text(encoding="utf-8"))
    return sum(
        isinstance(tok, Php)
        for row in dump.rows
        for column in ("content", "htmlheader")
        for tok in tokenize(str(row.get(column) or ""))
    )


@unittest.skipUnless(HTDOCS, "set DOLIBARR_HTDOCS to a Dolibarr htdocs folder")
class StockTemplatesCases:
    def test_stock_templates(self):
        root = pathlib.Path(HTDOCS) / "install" / "doctemplates" / "websites"
        folders = [
            p for p in sorted(root.glob("website_template-*")) if p.is_dir()
        ]
        self.assertEqual(len(folders), 6)
        total = stock = 0
        for folder in folders:
            blocks = block_count(folder / "website_pages.sql")
            total += blocks
            if not folder.name.endswith("_exp"):
                stock += blocks
            opts = Options(
                filename="website_%s.zip" % folder.name[len("website_") :]
            )
            site = build_from_zip(zip_folder(folder), opts)
            rows = analyse(site, opts)
            self.assertTrue(rows, folder.name)
            unknown = sum(p.php_unknown_blocks for p in site.pages)
            t1 = sum(
                1
                for p in site.pages
                for n in p.qweb_nodes.values()
                if n.get("kind") == "text" and n.get("key")
            )
            print(
                "%s: %d blocks, %d unknown, %d $weblangs texts, %d findings"
                % (folder.name, blocks, unknown, t1, len(all_findings(site)))
            )
        # The unknown-block count is printed above and read by hand, not
        # asserted, until a Dolibarr 24.0.1 checkout pins the expected value.
        self.assertEqual(total, 470)
        self.assertEqual(stock, 128)


class TestStockTemplates(StockTemplatesCases, unittest.TestCase):
    pass
