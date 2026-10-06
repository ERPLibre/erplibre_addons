# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..tools.sms_api_erplibre import SmsApiErplibre

#: Valeur du champ qui signifie « ce module ne route rien ».
AUCUN = "aucun"
#: Valeur qui route les SMS vers la passerelle mobile.
PASSERELLE = "passerelle"


class ResCompany(models.Model):
    _inherit = "res.company"

    erplibre_gateway_id = fields.Many2one(
        "erplibre.sms.gateway",
        "Passerelle mobile",
        ondelete="set null",
        help="Materiel qui envoie les SMS de cette societe : un telephone, un "
             "modem, ou tout autre appareil declare ici. Laisser vide reprend "
             "l'ancien comportement, la premiere passerelle active par "
             "sequence -- suffisant tant qu'il n'y en a qu'une, arbitraire des "
             "qu'il y en a deux.",
    )

    #: Champ PROPRE, et non un `selection_add` sur `res.company.sms_provider`
    #: du module `sms_twilio`. Deux modules qui declarent la meme Selection
    #: avec `selection=` s'ecrasent : le dernier charge impose sa liste, la
    #: valeur de l'autre reste en base sans etre dans le choix, et toute
    #: lecture de la societe leve « Wrong value for res.company.sms_provider ».
    #: Un nom distinct ne collisionne jamais, et n'impose pas d'installer un
    #: connecteur tiers pour envoyer par sa propre carte SIM.
    erplibre_sms_provider = fields.Selection(
        selection="_selection_erplibre_sms_provider",
        string="Fournisseur SMS ERPLibre",
        default=AUCUN,
        required=True,
        help="Qui envoie les SMS de cette societe. « Aucun » laisse le choix "
             "au coeur d'Odoo et a ses connecteurs.",
    )

    @api.model
    def _selection_erplibre_sms_provider(self):
        """Liste des fournisseurs, telle qu'elle s'affiche.

        Point d'extension : un module qui ajoute un fournisseur surcharge
        cette methode et y ajoute sa paire, plutot que de faire un
        `selection_add` -- les deux marchent, mais la methode garde la liste
        et la table des classes d'API cote a cote.
        """
        return [
            (AUCUN, "Aucun -- laisser Odoo decider"),
            (PASSERELLE, "Passerelle mobile ERPLibre"),
        ]

    @api.model
    def _erplibre_sms_api_classes(self):
        """Classe d'API a utiliser, par valeur d'`erplibre_sms_provider`.

        Une valeur absente de cette table n'est pas routee par ce module et
        repart au `super()`. C'est ici qu'un fournisseur supplementaire se
        branche : une entree, et rien a toucher dans `_get_sms_api_class`.
        """
        return {PASSERELLE: SmsApiErplibre}

    def _erplibre_uses_gateway(self):
        """Vrai quand les SMS de cette societe partent par la passerelle.

        Distingue du fait d'avoir UN fournisseur ERPLibre : la passerelle
        mobile a du materiel, une file et une alarme, ce que les autres
        fournisseurs n'auront pas.
        """
        self.ensure_one()
        return self.erplibre_sms_provider == PASSERELLE

    @api.constrains("erplibre_gateway_id")
    def _check_erplibre_gateway_company(self):
        """Refuse a la configuration ce que l'envoi refuserait en silence.

        `_for_company` ecarte une passerelle d'une autre societe : sans cette
        contrainte, le choix serait accepte a l'ecran et les SMS echoueraient
        plus tard, loin de la cause.
        """
        for company in self:
            gateway = company.erplibre_gateway_id
            if gateway and gateway.company_id != company:
                raise ValidationError(_(
                    "La passerelle « %(gateway)s » appartient a une autre "
                    "societe. Une passerelle envoie depuis SA carte SIM : "
                    "elle ne se prete pas.", gateway=gateway.display_name,
                ))

    @api.constrains("erplibre_sms_provider")
    def _check_erplibre_sms_provider_exclusif(self):
        """Refuse deux fournisseurs actifs en meme temps sur une societe.

        Chaque connecteur surcharge `_get_sms_api_class` et rend sa classe
        quand SON champ le designe ; celui qui gagne est celui dont la
        surcharge est la plus externe, donc l'ordre de chargement des modules.
        Laisser passer la combinaison donnerait un routage qui depend de cet
        ordre, et le meme reglage n'enverrait pas au meme endroit d'une base a
        l'autre.
        """
        # Le champ n'existe que si un connecteur du coeur est installe : le
        # test reste juste quand il est absent.
        if "sms_provider" not in self._fields:
            return
        for company in self:
            if company.erplibre_sms_provider == AUCUN:
                continue
            if company.sms_provider in (False, "iap"):
                continue
            raise ValidationError(_(
                "Deux fournisseurs de SMS sont choisis pour « %(company)s » : "
                "%(autre)s cote Odoo et %(notre)s ici. Ramenez le fournisseur "
                "d'Odoo a l'envoi par Odoo, ou mettez celui-ci a « Aucun ».",
                company=company.display_name,
                autre=company.sms_provider,
                notre=dict(self._selection_erplibre_sms_provider())[
                    company.erplibre_sms_provider],
            ))

    def _get_sms_api_class(self):
        self.ensure_one()
        classe = self._erplibre_sms_api_classes().get(self.erplibre_sms_provider)
        return classe or super()._get_sms_api_class()
