# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import SUPERUSER_ID, api
from odoo.addons.erplibre_studio.upgrade import migrate_projects


def migrate(cr, version):
    migrate_projects(api.Environment(cr, SUPERUSER_ID, {}))
