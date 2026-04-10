#!/usr/bin/env python3
# © 2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    claude_anthropic_api_key = fields.Char(
        string="Clé API Anthropic",
        config_parameter="projet_dev_code.anthropic_api_key",
        help=(
            "Clé API Anthropic utilisée pour authentifier l'agent Claude Code."
            " Si vide, le SDK utilise la session active de la CLI Claude"
            " (variable ANTHROPIC_API_KEY ou ~/.claude/)."
        ),
    )
    claude_cli_path = fields.Char(
        string="Chemin du binaire Claude",
        config_parameter="projet_dev_code.cli_path",
        placeholder="claude",
        help=(
            "Chemin absolu vers l'exécutable claude (ex: /usr/local/bin/claude)."
            " Laisser vide pour utiliser la détection automatique via PATH."
        ),
    )
