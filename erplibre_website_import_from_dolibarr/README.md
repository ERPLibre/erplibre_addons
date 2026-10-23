# Website import from Dolibarr

Imports a Dolibarr website export (the zip made by Dolibarr's Website
module: `website_pages.sql`, `containers/`, `medias/`) into an Odoo
website: pages, blog posts, media, site CSS, header menu and 301
redirects from every Dolibarr URL. A second import updates the same
records and never duplicates them.

The export zip is the only source: the module never connects to a
Dolibarr instance or to a published website.

## Usage

- **Wizard**: Website > Configuration > Import from Dolibarr. Choose the
  zip, check the source key, press Analyse. The run stops on its Review
  tab: tick the pages in another language to import, look at the PHP
  preview and at the scripts (Keep scripts is off by default), then press
  Import. Dolibarr import reports lists every run.
- **Command line**:
  `./odoo_bin.sh dolibarr_website_import -d DB --website-id 1 --zip FILE`
  with `--source-key KEY`, `--lang CODE`, `--langs-dir DIR`,
  `--blog-name NAME` (default Blog), `--no-menu`, `--no-homepage`,
  `--no-style-blog-posts`, `--keep-scripts`, `--max-media N` (default
  2000), `--include-page REF`, `--skip-page REF` (both repeatable),
  `--include-unlinked-langs`, `--overwrite-local-edits`,
  `--analyse-only` and `--report-json FILE`. Exit code 0 when done, 2
  when done with error lines in the report, 1 on failure.
  The command is `odoo-bin dolibarr_website_import`: the addons path must
  reach this module, so point `ODOO_RC` at a configuration file that lists
  it, or pass `--addons-path` first, before the command name.
- **Engine only** (no Odoo, no database):
  `PYTHONPATH=<module> python -m dolibarr_site inspect --zip FILE`.

## What happens to PHP

Known Dolibarr idioms become QWeb (company fields, address, map, logo,
page title, `$weblangs` texts, blog lists, search and contact forms).
Unknown PHP is removed; an unknown control structure is removed with all
the HTML it wraps, and the review shows the byte count before anything
is written.

## Re-import

Edits made in Odoo are kept by default and reported; the per-run option
"Overwrite local edits" replaces them. Records whose source is gone are
only reported. Existing menu entries are kept; imported entries are
added after them.

## Security

Only system administrators can import. Source markup goes through an
allow-list cleaner; forms posting to the Odoo form controller are
removed; SVG media are always cleaned. Site JavaScript is imported only
when "Keep scripts" is checked at review; without it no script file is
created, and inline handlers, `<script>` elements and `javascript:` URLs
are removed.

## Limits

- Styles that use CSS escapes, such as icon fonts
  (`content:"\f101"`), are dropped and reported: the cleaner refuses what
  it cannot read with certainty.
- CSS exfiltration through an allowed https `url()` or `@import` is an
  accepted risk: an imported stylesheet can make the visitor's browser
  request an external address.
- Any system administrator sees every company's runs. There is no
  multi-company split of the reports.
- The media limit (`--max-media`, 2000 by default) counts the media
  listed in the zip, not the media imported. A single file larger than
  20 MiB is skipped and reported; the rest of the zip imports.
- The zip limits are system parameters named
  `erplibre_website_import_from_dolibarr.zip_<limit>` (`max_entries`,
  `max_total`, `max_sql`, `max_container`, `max_media`, `max_ratio`,
  `max_central_directory`). Only administrators can set them, and they
  have no upper bound.
- Two concurrent imports of different keys on the same website can
  collide. The loser fails cleanly and can be run again.

## Licences

This module is licensed under AGPL-3.0-or-later. data/dolibarr_langs/
bundles unmodified language files from Dolibarr under GPL-3.0-or-later.
The notice is in data/dolibarr_langs/README.md, and the licence text is
in COPYING next to it.

## Development

    M=odoo18.0/addons/ERPLibre_erplibre_addons/erplibre_website_import_from_dolibarr
    .venv.odoo18.0_python3.12.10/bin/python -m unittest discover -s $M/dolibarr_site/tests -t $M
    make test_website_import_dolibarr_engine
    make test_addons_website_import_dolibarr

The stock website templates of a Dolibarr checkout are analysed when
`DOLIBARR_HTDOCS` names its `htdocs` folder; the test is skipped otherwise.

Refresh the bundled language files when the Dolibarr version changes:
`PYTHONPATH=$M python -m dolibarr_site langs-refresh --htdocs <dolibarr>/htdocs`.
