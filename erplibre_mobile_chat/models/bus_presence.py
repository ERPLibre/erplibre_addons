# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Présence des navigateurs d'un utilisateur, à côté de celle d'Odoo, qui
compte aussi le bus de l'application."""

from datetime import timedelta

from odoo import api, fields, models, tools
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY


class BusPresence(models.Model):
    _inherit = "bus.presence"

    erplibre_browser_poll = fields.Datetime(
        string="Last Browser Poll",
        help="Last presence update of a browser of this user; the bus of the"
        " ERPLibre mobile app does not count.",
    )
    erplibre_browser_presence = fields.Datetime(
        string="Last Browser Presence",
        help="Last activity in a browser of this user; the bus of the"
        " ERPLibre mobile app does not count.",
    )

    @api.model
    def erplibre_update_browser_presence(self, inactivity_period, user_id):
        """Écrit, comme update_presence d'Odoo, le dernier sondage (now) et
        la dernière activité (now − `inactivity_period` millisecondes) d'un
        navigateur de `user_id` dans sa présence existante, puis valide.

        Une erreur de concurrence (deux onglets en même temps) annule la
        transaction et est ignorée, comme chez Odoo : la présence n'est pas
        essentielle. Sans ligne de présence, rien n'est écrit : celle
        d'Odoo, écrite juste avant, a alors cédé à la même concurrence.
        """
        try:
            with tools.mute_logger("odoo.sql_db"):
                presence = self.search([("user_id", "=", user_id)])
                if presence:
                    now = fields.Datetime.now()
                    presence.write(
                        {
                            "erplibre_browser_poll": now,
                            "erplibre_browser_presence": now
                            - timedelta(milliseconds=inactivity_period),
                        }
                    )
                self.env.cr.commit()
        except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
            return self.env.cr.rollback()
