# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Publication idempotente sur tout fil par identifiant client et
notifications vers les appareils de l'application."""

import json

from odoo import api, models
from odoo.addons.mail.models.mail_thread import MAX_DIRECT_PUSH

from ..tools import app_push
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

    def _erplibre_app_payload(self, message, msg_vals):
        """Rend la charge d'Odoo pour `message` (celle du canal sur un
        discuss.channel) avec `options.data.erplibre` = {"v", "message_id",
        "channel_type"}, `channel_type` valant le type du canal ou None
        hors d'un canal, tronquée ensuite par `_truncate_payload` pour que
        le JSON chiffré tienne dans un enregistrement de 4096 octets."""
        payload = self._notify_by_web_push_prepare_payload(
            message, msg_vals=msg_vals
        )
        channel_type = (
            self[:1].channel_type if self._name == "discuss.channel" else None
        )
        payload["options"]["data"]["erplibre"] = {
            "v": app_push.PAYLOAD_VERSION,
            "message_id": message.id,
            "channel_type": channel_type or None,
        }
        return self._truncate_payload(payload)

    def _notify_thread_by_web_push(
        self, message, recipients_data, msg_vals=False, **kwargs
    ):
        """Envoie aux appareils de l'application des destinataires la
        charge de _erplibre_app_payload, puis rend la main au code d'Odoo
        sous `erplibre_skip_app_devices`, qui lui cache ces appareils : tout
        autre appareil reçoit exactement ce qu'Odoo lui enverrait.

        Les destinataires sont ceux d'Odoo
        (`_extract_partner_ids_for_notifications`) ; sur un canal, le filtre
        de discuss.channel (« web_push » seulement) est déjà passé. Un
        appareil qui se tait pendant qu'un navigateur est en ligne
        (`erplibre_quiet_while_online`) est sauté quand
        `res.users._erplibre_browser_online` le dit. Moins de
        MAX_DIRECT_PUSH appareils partent après la validation
        (app_push.schedule) ; au-delà, des lignes mail.push et le cron de
        mail, que ce module traite (voir mail.push).
        """
        values = dict(msg_vals or {})
        partner_ids = self._extract_partner_ids_for_notifications(
            message, values, recipients_data
        )
        if partner_ids:
            devices = self.env["mail.push.device"]._erplibre_app_devices(
                partner_ids
            )
            devices = self._erplibre_drop_quiet(devices)
            if devices:
                self._erplibre_push_to_app(devices, message, values)
        return super(
            MailThread, self.with_context(erplibre_skip_app_devices=True)
        )._notify_thread_by_web_push(
            message, recipients_data, msg_vals=msg_vals, **kwargs
        )

    def _erplibre_drop_quiet(self, devices):
        """Rend `devices` sans les appareils silencieux dont un navigateur
        de l'utilisateur du partenaire est en ligne, en une seule
        recherche de présence pour tous les partenaires."""
        quiet = devices.filtered("erplibre_quiet_while_online")
        if not quiet:
            return devices
        online = (
            quiet.partner_id.sudo()
            .user_ids._erplibre_browser_online_users()
            .partner_id
        )
        return devices.filtered(
            lambda device: not device.erplibre_quiet_while_online
            or device.partner_id not in online
        )

    def _erplibre_push_to_app(self, devices, message, msg_vals):
        """Envoie la charge de l'application de `message` à `devices`
        (sudo) : après la validation sous MAX_DIRECT_PUSH appareils, par
        des lignes mail.push et le cron de mail au-delà."""
        payload = json.dumps(self._erplibre_app_payload(message, msg_vals))
        if len(devices) < MAX_DIRECT_PUSH:
            app_push.schedule(
                self.env,
                [(device, payload) for device in devices],
            )
            return
        self.env["mail.push"].sudo().create(
            [
                {"mail_push_device_id": device.id, "payload": payload}
                for device in devices
            ]
        )
        self.env.ref("mail.ir_cron_web_push_notification")._trigger()
