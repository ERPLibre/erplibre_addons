# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Branche le bouton « Appeler » d'OCA sur la passerelle mobile.

`base_phone` pose un `click2dial` explicitement destine a etre surcharge par
un connecteur — sa docstring cite Asterisk et OVH. Ici le connecteur est un
telephone Android : on ne compose pas via un IPBX, on met l'appel en file et
l'appareil s'en charge.

La difference avec un IPBX compte pour l'utilisateur : un IPBX fait sonner le
poste de la personne QUI CLIQUE, puis appelle le correspondant. Ici c'est le
telephone-passerelle qui compose, et quelqu'un doit etre a cote de LUI. Le
message de retour le dit, plutot que de laisser attendre un combine qui ne
sonnera jamais.
"""
import logging
import uuid

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PhoneCommon(models.AbstractModel):
    _inherit = "phone.common"

    @api.model
    def get_record_from_phone_number(self, presented_number):
        """Retrouve le correspondant en ne comparant QUE les chiffres.

        La version d'origine ne retire que les espaces :

            replace(champ, ' ', '') ilike '%45550142'

        Un numero stocke « +1 514-555-0142 » devient donc « +1514-555-0142 »,
        qui se termine par « 555-0142 » et non par « 45550142 ». Tirets,
        points et parentheses defont le rapprochement, et ce sont les formats
        que produisent aussi bien la saisie humaine que le formatage
        automatique d'Odoo : la fiche existe, l'appelant est tout de meme
        annonce comme inconnu.

        On retire donc tout ce qui n'est pas un chiffre des DEUX cotes. En cas
        d'echec, on repasse la main a l'implementation d'origine plutot que de
        la remplacer : elle connait des modeles que celle-ci ignore.
        """
        # Le rapprochement se fait en SQL, ici comme dans l'implementation
        # d'origine, et le SQL ne voit pas le cache de l'ORM : un numero
        # ecrit dans la meme transaction que la recherche resterait
        # introuvable, et la fiche serait annoncee comme inconnue.
        self.env.flush_all()
        chiffres = "".join(c for c in str(presented_number or "") if c.isdigit())
        if chiffres:
            longueur = self.env.company.number_of_digits_to_match_from_end or 8
            fin = chiffres[-longueur:] if len(chiffres) >= longueur else chiffres
            for description in self._get_phone_models():
                objet = description["object"]
                conditions, arguments = [], []
                for champ in description["fields"]:
                    conditions.append(
                        "regexp_replace(%s, '[^0-9]', '', 'g') LIKE %%s" % champ
                    )
                    arguments.append("%" + fin)
                self._cr.execute(
                    "SELECT id FROM %s WHERE %s LIMIT 2"
                    % (objet._table, " OR ".join(conditions)),
                    tuple(arguments),
                )
                lignes = self._cr.fetchall()
                if not lignes:
                    continue
                if len(lignes) > 1:
                    # Deux fiches partagent la fin du numero : on prend la
                    # premiere, mais on le dit — c'est presque toujours un
                    # doublon a fusionner.
                    _logger.warning(
                        "erplibre_mobile_gateway: %s fiches %s finissent"
                        " par %s, la premiere est retenue",
                        len(lignes), objet._name, fin,
                    )
                enregistrement = objet.browse(lignes[0][0])
                return (objet._name, enregistrement.id, enregistrement.display_name)

        return super().get_record_from_phone_number(presented_number)

    @api.model
    def click2dial(self, erp_number):
        """Met l'appel en file pour la passerelle mobile.

        Renvoie le dictionnaire attendu par `base_phone`, enrichi d'un
        `dialing_message` que le bouton affiche : sans lui, l'utilisateur
        decrocherait son propre telephone en attendant une sonnerie.
        """
        result = super().click2dial(erp_number)
        company = self.env.company
        if company.sms_provider != "erplibre":
            # Un autre connecteur est actif : on ne s'impose pas.
            return result

        gateway = self.env["erplibre.sms.gateway"]._for_company(company)
        if not gateway:
            raise UserError(
                _(
                    "Aucune passerelle mobile active : l'appel ne peut pas"
                    " etre place. Verifiez Passerelle mobile > Configuration."
                )
            )
        if gateway.alarm_active:
            # Mettre un appel en file vers une passerelle en panne le ferait
            # partir des son retour, peut-etre des heures plus tard, vers
            # quelqu'un qui ne s'y attend plus.
            raise UserError(
                _("La passerelle est en panne : %s") % (gateway.alarm_reason or "")
            )

        numero = self.convert_to_dial_number(erp_number)
        appel = self.env["erplibre.mobile.call"].create(
            {
                "call_uuid": uuid.uuid4().hex,
                "number": numero,
                "direction": "out",
                # `click` et non `queued` : c'est un humain qui a clique. La
                # distinction n'est pas cosmetique — elle separe la telephonie
                # CRM de l'appel automatise, et le filtre d'audit s'en sert.
                "source": "click",
                "company_id": company.id,
                "gateway_id": gateway.id,
                "requested_by_uid": self.env.uid,
                "state": "queued",
            }
        )
        _logger.info(
            "erplibre_mobile_gateway: appel %s mis en file vers %s",
            appel.call_uuid,
            numero,
        )
        result.update(
            {
                "dialed_number": numero,
                "dialing_message": _(
                    "Appel mis en file. C'est le telephone-passerelle qui"
                    " compose : decrochez CELUI-LA, pas le votre."
                ),
            }
        )
        return result
