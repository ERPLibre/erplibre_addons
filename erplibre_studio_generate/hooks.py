# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from .models.ir_model_fields import drop_manual_name_constraint


def post_init_hook(env):
    drop_manual_name_constraint(env.cr)
