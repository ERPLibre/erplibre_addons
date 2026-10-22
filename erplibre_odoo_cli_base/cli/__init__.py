# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.cli import db as odoo_db

# The commands extend OCB's db command, recognised by its _check_target. An
# ERPLibre fork that still carries the old flag-based db (and the
# --uninstall, --install-theme server options) has none: the module then
# registers nothing, so the fork's own db and i18n stay in place and
# ERPLibre's odoo_bin.sh translates the new syntax for them.
if hasattr(odoo_db.Db, "_check_target"):
    from . import db, i18n, module, theme  # noqa: F401
