# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
import logging

_logger = logging.getLogger(__name__)

# Le cron d'envoi du module coeur `sms` tourne toutes les HEURES
# (odoo/addons/sms/data/ir_cron_data.xml : interval_number=1, interval_type=hours).
# Pour un canal d'alerte, cela signifie qu'un « la seance de 19 h est annulee »
# saisi a 17 h 40 peut ne partir qu'a 18 h 30.
#
# Ce cron est declare dans un bloc `noupdate="1"`. Le surcharger par un fichier
# XML fonctionne a l'installation mais est SILENCIEUSEMENT IGNORE a chaque mise
# a jour du module (odoo/models.py, garde `if not (update and d_noupdate)`).
# Le reglage doit donc etre fait par du code, a chaque installation ET mise a
# jour, ce qui est le role de ce hook.
SMS_QUEUE_CRON_XMLID = "sms.ir_cron_sms_scheduler_action"
SMS_QUEUE_INTERVAL_MINUTES = 2


def post_init_hook(env):
    """Ramene le cron d'envoi SMS a un intervalle compatible avec une alerte."""
    cron = env.ref(SMS_QUEUE_CRON_XMLID, raise_if_not_found=False)
    if not cron:
        _logger.warning(
            "erplibre_mobile_gateway: cron %s introuvable, l'intervalle d'envoi reste celui du coeur",
            SMS_QUEUE_CRON_XMLID,
        )
        return
    if cron.interval_type == "minutes" and cron.interval_number <= SMS_QUEUE_INTERVAL_MINUTES:
        return
    previous = f"{cron.interval_number} {cron.interval_type}"
    cron.write({
        "interval_number": SMS_QUEUE_INTERVAL_MINUTES,
        "interval_type": "minutes",
    })
    _logger.info(
        "erplibre_mobile_gateway: cron d'envoi SMS ramene de %s a %s minutes",
        previous, SMS_QUEUE_INTERVAL_MINUTES,
    )
