# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Expéditeur des notifications vers les appareils de l'application.

Le chiffrement et l'en-tête VAPID sont ceux de `mail.tools.web_push`
(`push_to_end_point`). Deux différences : 200 vaut succès comme 201 (ntfy
répond 200 à une publication), et aucune ligne de journal ne nomme le point
de terminaison, qui porte le sujet secret : un appareil y est désigné par
son id.
"""

import json
import logging
from urllib.parse import urlsplit

import requests
from odoo import SUPERUSER_ID, api
from odoo.addons.mail.tools import jwt
from odoo.addons.mail.tools.web_push import _encrypt_payload

_logger = logging.getLogger(__name__)

# Version de la clé `erplibre` des charges envoyées à l'application.
PAYLOAD_VERSION = 1

# Clé de `cr.postcommit.data` qui regroupe les notifications « lu » d'une
# transaction.
READ_DATA_KEY = "erplibre.read"

SENT = "sent"
GONE = "gone"
FAILED = "failed"

# Durée de validité du jeton VAPID, comme push_to_end_point.
VAPID_TTL = 12 * 60 * 60


def send(
    session,
    base_url,
    device,
    payload,
    vapid_private_key,
    vapid_public_key,
    timeout=2,
):
    """Envoie `payload` (JSON, str) chiffré à `device` ({id, endpoint,
    keys}) par `session` et rend SENT (200 ou 201), GONE (404, 410 ou un
    hôte en `.invalid`, l'appareil est à supprimer) ou FAILED (toute autre
    réponse, ou une erreur de transport).

    Chaque envoi attend au plus `timeout` secondes : envoyés après la
    validation, ils retiennent la réponse de la requête qui les a
    inscrits.

    Le jeton VAPID a les revendications de push_to_end_point : `aud`,
    schéma et hôte du point de terminaison, et `sub`, `base_url`. Un échec
    est journalisé avec l'id de l'appareil et le statut, ou le nom de la
    classe de l'exception : le message d'une exception de requests cite
    l'URL.
    """
    endpoint = device["endpoint"]
    url = urlsplit(endpoint)
    if url.netloc.endswith(".invalid"):
        return GONE
    token = jwt.sign(
        {"aud": f"{url.scheme}://{url.netloc}", "sub": base_url},
        vapid_private_key,
        ttl=VAPID_TTL,
        algorithm=jwt.Algorithm.ES256,
    )
    headers = {
        "Authorization": f"vapid t={token}, k={vapid_public_key}",
        "Content-Encoding": "aes128gcm",
        "TTL": "60",
    }
    body = _encrypt_payload(payload.encode(), device)
    try:
        response = session.post(
            endpoint, headers=headers, data=body, timeout=timeout
        )
    except requests.RequestException as error:
        _logger.warning(
            "App push to device %s failed: %s",
            device["id"],
            type(error).__name__,
        )
        return FAILED
    status = response.status_code
    if status in (200, 201):
        _logger.debug("App push sent to device %s", device["id"])
        return SENT
    if status in (404, 410):
        _logger.info("App push device %s gone: %s", device["id"], status)
        return GONE
    _logger.warning("App push to device %s failed: %s", device["id"], status)
    return FAILED


def _vapid_and_base_url(env):
    """Rend (clé privée, clé publique, URL de base), lues sous sudo ; les
    clés valent None quand l'une des deux manque."""
    params = env["ir.config_parameter"].sudo()
    private = params.get_param("mail.web_push_vapid_private_key")
    public = params.get_param("mail.web_push_vapid_public_key")
    if not private or not public:
        return None, None, None
    return private, public, params.get_param("web.base.url")


def _deliver(registry, base_url, private, public, items):
    """Envoie chaque (appareil, charge) de `items` sur une seule session
    HTTP, puis supprime les appareils GONE dans un curseur neuf de
    `registry`. Ne lit aucun enregistrement et ne lève jamais : appelée
    après la validation de la transaction, une exception remonterait dans
    la réponse d'une requête déjà validée. Un appareil GONE n'est plus
    contacté pour les éléments suivants."""
    session = requests.Session()
    gone = set()
    for device, payload in items:
        if device["id"] in gone:
            continue
        try:
            status = send(session, base_url, device, payload, private, public)
        except Exception as error:
            # Clés illisibles, par exemple : la notification seule échoue.
            _logger.warning(
                "App push to device %s failed: %s",
                device["id"],
                type(error).__name__,
            )
            continue
        if status == GONE:
            gone.add(device["id"])
    if not gone:
        return
    try:
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            env["mail.push.device"].browse(sorted(gone)).exists().unlink()
    except Exception:
        _logger.exception("App push: unlinking devices %s failed", gone)


def vapid_keys_present(env):
    """Rend vrai quand les deux clés VAPID d'Odoo sont renseignées."""
    return _vapid_and_base_url(env)[0] is not None


def device_data(device):
    """Rend {id, endpoint, keys} de `device` (enregistrement ou dict),
    seule forme que reçoit une fonction différée."""
    return {
        "id": device["id"],
        "endpoint": device["endpoint"],
        "keys": device["keys"],
    }


def schedule(env, items):
    """Envoie `items`, liste de (appareil {id, endpoint, keys}, charge
    JSON), après la validation de la transaction de `env`
    (`cr.postcommit`) : rien ne part si elle est annulée, et l'appareil ne
    reçoit pas une notification d'un message encore illisible par RPC.
    Sans clés VAPID, n'envoie rien.

    Les clés, l'URL de base et les appareils sont lus maintenant : la
    fonction différée ne reçoit que des données simples (dict et str) et le
    registre, jamais un enregistrement dont le curseur serait fermé. Les
    appareils disparus sont supprimés dans un curseur neuf (voir _deliver).
    """
    private, public, base_url = _vapid_and_base_url(env)
    if not private:
        _logger.warning("Missing web push vapid keys !")
        return
    if not items:
        return
    items = [(device_data(device), str(payload)) for device, payload in items]
    registry = env.registry
    env.cr.postcommit.add(
        lambda: _deliver(registry, base_url, private, public, items)
    )


def read_payload(channel_id, message_id):
    """Rend la charge JSON (str) de la notification « lu » : le canal
    `channel_id` est lu jusqu'au message `message_id` inclus."""
    return json.dumps(
        {
            "erplibre": {
                "v": PAYLOAD_VERSION,
                "type": "read",
                "channel_id": channel_id,
                "last_message_id": message_id,
            }
        }
    )


def schedule_read(env, devices, channel_id, message_id):
    """Inscrit la notification « lu » de (`channel_id`, `message_id`) pour
    `devices` dans `cr.postcommit.data[READ_DATA_KEY]`, qui garde par
    (appareil, canal) le plus grand id de message de la transaction.

    La première inscription d'une transaction ajoute l'unique fonction
    différée, qui envoie une charge par (appareil, canal) après la
    validation ; les clés VAPID et l'URL de base sont celles lues à ce
    moment. Sans clés VAPID, rien n'est inscrit.
    """
    # cr.rollback() efface l'inscription ; le retour à un point de
    # sauvegarde ne l'efface pas, comme pour tout postcommit d'Odoo.
    postcommit = env.cr.postcommit
    pending = postcommit.data.get(READ_DATA_KEY)
    if pending is None:
        private, public, base_url = _vapid_and_base_url(env)
        if not private:
            return
        pending = postcommit.data[READ_DATA_KEY] = {}
        registry = env.registry

        def deliver():
            items = [
                (device, read_payload(channel, message))
                for (_device_id, channel), (device, message) in sorted(
                    pending.items()
                )
            ]
            _deliver(registry, base_url, private, public, items)

        postcommit.add(deliver)
    for device in devices:
        key = (device["id"], channel_id)
        known = pending.get(key)
        if known is None or known[1] < message_id:
            pending[key] = (device_data(device), message_id)
