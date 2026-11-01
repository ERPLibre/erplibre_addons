# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Réglage de la durée de vie des identifiants TURN temporaires."""

from odoo import fields, models

from .mail_ice_server import DEFAULT_TTL_HOURS, PARAM_TTL


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Stocké dans le paramètre système que lit `mail.ice.server` ; le
    # paramètre absent affiche la valeur par défaut.
    erplibre_turn_ttl_hours = fields.Integer(
        "Durée des identifiants TURN (heures)",
        config_parameter=PARAM_TTL,
        default=DEFAULT_TTL_HOURS,
        help="Durée de validité des identifiants TURN remis à chaque entrée"
        " dans un appel. Un participant qui rejoint un appel ouvert depuis"
        " plus longtemps n'obtient plus de relais. Une valeur inférieure à 1"
        " compte pour 1.",
    )
