# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Publication idempotente sur tout fil par identifiant client et
notifications vers les appareils de l'application."""

import copy
import json

from odoo import api, models
from odoo.addons.mail.models.mail_thread import MAX_DIRECT_PUSH

from ..tools import app_push
from .discuss_channel import LOCK_NAMESPACE_MESSAGE, erplibre_lock_uuid
from .mail_push_device import WATCHED_MODES


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

    def _erplibre_app_payloads(self, message, msg_vals, devices, online=None):
        """Rend {id d'appareil: charge JSON (str)} de `message` pour les
        appareils de l'application `devices` : la charge d'Odoo (celle du
        canal sur un discuss.channel) avec `options.data.erplibre`.

        Un appareil en charge v 1 (`erplibre_payload_v`, marqué par une
        application 1.5) reçoit {"v", "message_id", "channel_type"},
        `channel_type` valant le type du canal ou None hors d'un canal ;
        un appareil en charge v 2 reçoit en plus `mentioned`, vrai quand
        son partenaire est dans `message.partner_ids` (un @everyone y met
        tous les membres) et que le message n'est pas un `user_notification`
        (message_notify, l'assignation d'une activité par exemple, qui
        nomme son destinataire sans le mentionner), et `browser_online`,
        vrai quand l'appareil attend ou se tait (WATCHED_MODES) et que son
        partenaire est dans `online` (voir _erplibre_online_partners,
        appelée quand `online` vaut None).

        `_truncate_payload` tourne une fois par version pour que le JSON
        chiffré tienne dans un enregistrement de 4096 octets : la v 1 comme
        avant le module 1.6, la v 2 avec les deux drapeaux à faux, puis
        les drapeaux de chaque appareil y sont posés ; `true` est plus
        court que `false`, donc aucune charge ne dépasse la limite.
        """
        payload = self._notify_by_web_push_prepare_payload(
            message, msg_vals=msg_vals
        )
        channel_type = (
            self[:1].channel_type if self._name == "discuss.channel" else None
        ) or None
        v2_devices = devices.filtered(
            lambda device: device.erplibre_payload_v
            == app_push.MESSAGE_PAYLOAD_VERSION
        )
        v1_devices = devices - v2_devices
        payloads = {}
        if v1_devices:
            v1 = copy.deepcopy(payload)
            v1["options"]["data"]["erplibre"] = {
                "v": app_push.PAYLOAD_VERSION,
                "message_id": message.id,
                "channel_type": channel_type,
            }
            content = json.dumps(self._truncate_payload(v1))
            payloads.update(dict.fromkeys(v1_devices.ids, content))
        if v2_devices:
            if online is None:
                online = self._erplibre_online_partners(v2_devices)
            flags = payload["options"]["data"]["erplibre"] = {
                "v": app_push.MESSAGE_PAYLOAD_VERSION,
                "message_id": message.id,
                "channel_type": channel_type,
                "mentioned": False,
                "browser_online": False,
            }
            payload = self._truncate_payload(payload)
            # sudo: mail.message - l'appartenance d'un partenaire aux
            # mentionnés ne dépend pas des règles d'accès aux partenaires.
            message_sudo = message.sudo()
            mentioned = (
                message_sudo.partner_ids
                if message_sudo.message_type != "user_notification"
                else self.env["res.partner"]
            )
            for device in v2_devices:
                flags["mentioned"] = device.partner_id in mentioned
                flags["browser_online"] = (
                    device.erplibre_browser_mode in WATCHED_MODES
                    and device.partner_id in online
                )
                payloads[device.id] = json.dumps(payload)
        return payloads

    def _notify_thread_by_web_push(
        self, message, recipients_data, msg_vals=False, **kwargs
    ):
        """Envoie aux appareils de l'application des destinataires leurs
        charges (_erplibre_app_payloads), puis rend la main au code d'Odoo
        sous `erplibre_skip_app_devices`, qui lui cache ces appareils : tout
        autre appareil reçoit exactement ce qu'Odoo lui enverrait.

        Les destinataires sont ceux d'Odoo
        (`_extract_partner_ids_for_notifications`) ; sur un canal, le filtre
        de discuss.channel (« web_push » seulement) est déjà passé. La
        présence des navigateurs est lue une seule fois
        (_erplibre_online_partners) : elle sert à sauter les appareils
        `quiet` (_erplibre_drop_quiet) et au drapeau `browser_online`.
        Moins de MAX_DIRECT_PUSH appareils partent après la validation
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
            online = self._erplibre_online_partners(devices)
            devices = self._erplibre_drop_quiet(devices, online)
            if devices:
                self._erplibre_push_to_app(devices, message, values, online)
        return super(
            MailThread, self.with_context(erplibre_skip_app_devices=True)
        )._notify_thread_by_web_push(
            message, recipients_data, msg_vals=msg_vals, **kwargs
        )

    def _erplibre_online_partners(self, devices):
        """Rend les partenaires des appareils de `devices` qui attendent ou
        se taisent (WATCHED_MODES) dont un navigateur de l'utilisateur est
        actif (`res.users._erplibre_browser_online_users`), en une seule
        recherche de présence ; aucune quand aucun appareil n'est dans ces
        modes."""
        watched = devices.filtered(
            lambda device: device.erplibre_browser_mode in WATCHED_MODES
        )
        if not watched:
            return self.env["res.partner"]
        return (
            watched.partner_id.sudo()
            .user_ids._erplibre_browser_online_users()
            .partner_id
        )

    def _erplibre_drop_quiet(self, devices, online=None):
        """Rend `devices` sans les appareils `quiet` dont le partenaire est
        dans `online` (voir _erplibre_online_partners, appelée quand
        `online` vaut None) ; les autres modes ne sont jamais sautés."""
        quiet = devices.filtered(
            lambda device: device.erplibre_browser_mode == "quiet"
        )
        if not quiet:
            return devices
        if online is None:
            online = self._erplibre_online_partners(quiet)
        return devices - quiet.filtered(
            lambda device: device.partner_id in online
        )

    def _erplibre_push_to_app(self, devices, message, msg_vals, online=None):
        """Envoie à chaque appareil de `devices` (sudo) sa charge de
        `message` (_erplibre_app_payloads, avec `online`) : après la
        validation sous MAX_DIRECT_PUSH appareils, par des lignes mail.push
        et le cron de mail au-delà."""
        payloads = self._erplibre_app_payloads(
            message, msg_vals, devices, online
        )
        if len(devices) < MAX_DIRECT_PUSH:
            app_push.schedule(
                self.env,
                [(device, payloads[device.id]) for device in devices],
            )
            return
        self.env["mail.push"].sudo().create(
            [
                {
                    "mail_push_device_id": device.id,
                    "payload": payloads[device.id],
                }
                for device in devices
            ]
        )
        self.env.ref("mail.ir_cron_web_push_notification")._trigger()
