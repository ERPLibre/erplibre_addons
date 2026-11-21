# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.addons.erplibre_studio_generate.models.ir_model_fields import (
    drop_manual_name_constraint,
)


def migrate(cr, version):
    drop_manual_name_constraint(cr)
