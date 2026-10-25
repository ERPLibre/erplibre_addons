# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Publication idempotente dans un canal par identifiant client."""

from odoo import api, models


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    def _get_allowed_message_post_params(self):
        return super()._get_allowed_message_post_params() | {
            "erplibre_client_uuid"
        }

    def _get_message_create_valid_field_names(self):
        # message_post refuse tout champ de mail.message absent de cette liste.
        return super()._get_message_create_valid_field_names() | {
            "erplibre_client_uuid"
        }

    @api.returns("mail.message", lambda value: value.id)
    def message_post(self, **kwargs):
        """Rend le message déjà publié par le même auteur dans ce canal avec
        le même identifiant client, sans rien publier ni notifier ; sinon
        publie normalement.

        Le contrôleur appelle message_post sous sudo, qui conserve
        env.user : l'auteur comparé est donc l'utilisateur qui requiert.
        L'utilisateur public n'est jamais comparé : son partenaire est le
        même pour quiconque publie sans compte, et l'un adopterait le message
        d'un autre.
        """
        uuid = kwargs.get("erplibre_client_uuid")
        if uuid and not self.env.user._is_public():
            self.ensure_one()
            existing = (
                self.env["mail.message"]
                .sudo()
                .search(
                    [
                        ("model", "=", "discuss.channel"),
                        ("res_id", "=", self.id),
                        ("erplibre_client_uuid", "=", uuid),
                        ("author_id", "=", self.env.user.partner_id.id),
                    ],
                    limit=1,
                )
            )
            if existing:
                return existing
        return super().message_post(**kwargs)
