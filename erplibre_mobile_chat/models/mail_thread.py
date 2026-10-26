# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Publication idempotente sur tout fil par identifiant client."""

from odoo import api, models

from .discuss_channel import LOCK_NAMESPACE_MESSAGE, erplibre_lock_uuid


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    def _get_allowed_message_post_params(self):
        # /mail/message/post ne transmet à message_post que ces clés.
        return super()._get_allowed_message_post_params() | {
            "erplibre_client_uuid"
        }

    def _get_message_create_valid_field_names(self):
        # message_post refuse tout champ de mail.message absent de cette liste.
        return super()._get_message_create_valid_field_names() | {
            "erplibre_client_uuid"
        }

    def _erplibre_posted_message(self, uuid):
        """Rend le message déjà publié sur ce fil (un seul enregistrement)
        par l'utilisateur courant avec l'identifiant client `uuid`, ou un
        recordset vide.

        Prend d'abord le verrou de l'identifiant (voir erplibre_lock_uuid) ;
        un second appel dans la même transaction le reprend sans attendre.
        La recherche est sous sudo : un message de l'auteur que sa
        recherche ne voit plus doit être trouvé, sinon la création échoue
        sur l'index unique. L'auteur comparé est le partenaire de env.user,
        que sudo conserve. Hors sudo, un message trouvé exige le même droit
        qu'une publication (`_get_mail_message_access(..., "create")`, soit
        `_mail_post_access` du modèle), que la création du message
        vérifierait sinon ; sous sudo, la route l'a déjà vérifié. Le
        résultat reprend l'environnement courant.
        """
        self.ensure_one()
        erplibre_lock_uuid(self.env, LOCK_NAMESPACE_MESSAGE, uuid)
        # sudo: mail.message - le message de l'auteur est cherché quels que
        # soient ses droits actuels (voir la docstring).
        existing = (
            self.env["mail.message"]
            .sudo()
            .search(
                [
                    ("model", "=", self._name),
                    ("res_id", "=", self.id),
                    ("erplibre_client_uuid", "=", uuid),
                    ("author_id", "=", self.env.user.partner_id.id),
                ],
                limit=1,
            )
        )
        if existing and not self.env.su:
            self.check_access(
                self._get_mail_message_access(self.ids, "create")
            )
        return existing.with_env(self.env)

    @api.returns("mail.message", lambda value: value.id)
    def message_post(self, **kwargs):
        """Rend le message déjà publié par le même auteur sur ce fil avec le
        même identifiant client (voir _erplibre_posted_message), sans rien
        publier ni notifier ; sinon publie normalement. Vaut pour tout
        modèle `mail.thread`.

        L'utilisateur public n'est jamais comparé : son partenaire est le
        même pour quiconque publie sans compte, et l'un adopterait le
        message d'un autre. Son identifiant n'est pas non plus enregistré :
        l'index unique de mail.message refuserait un second message du même
        partenaire partagé.

        Limite d'ordre : cette méthode vient après les surcharges de
        message_post des modèles qui héritent de mail.thread, et après les
        extensions de mail.thread chargées après ce module (`rating`, par
        exemple). Ce qu'une telle surcharge fait avant super() se rejoue
        sur un renvoi ; seuls la création du message et ses notifications
        ne se rejouent pas. Pour discuss.channel, la surcharge de ce module
        cherche le message avant le message_post de mail ; celles des
        modules chargés après ce module passent encore avant elle.
        """
        uuid = kwargs.get("erplibre_client_uuid")
        if not uuid or not self:
            return super().message_post(**kwargs)
        if self.env.user._is_public():
            kwargs.pop("erplibre_client_uuid")
            return super().message_post(**kwargs)
        return self._erplibre_posted_message(uuid) or super().message_post(
            **kwargs
        )
