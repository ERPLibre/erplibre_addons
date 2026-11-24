# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Notification « lu » vers les appareils de l'application quand un membre
avance son dernier message vu."""

from odoo import models

from ..tools import app_push


class DiscussChannelMember(models.Model):
    _inherit = "discuss.channel.member"

    def _set_last_seen_message(self, message, notify=True):
        """Comme Odoo ; quand `seen_message_id` avance, inscrit la
        notification « lu » (canal, nouveau message vu) pour les appareils
        de l'application du partenaire du membre (app_push.schedule_read).

        Couvre le marquage comme lu et la publication du membre lui-même
        (discuss.channel._message_post_after_hook). Plusieurs avancées dans
        une transaction ne font qu'une notification par (appareil, canal),
        après la validation. Un appareil silencieux la reçoit aussi : elle
        retire des notifications, elle n'en ajoute pas.
        """
        seen = self.seen_message_id.id
        result = super()._set_last_seen_message(message, notify=notify)
        if self.seen_message_id.id > seen and self.partner_id:
            devices = self.env["mail.push.device"]._erplibre_app_devices(
                self.partner_id.ids
            )
            if devices:
                app_push.schedule_read(
                    self.env,
                    devices,
                    self.channel_id.id,
                    self.seen_message_id.id,
                )
        return result
