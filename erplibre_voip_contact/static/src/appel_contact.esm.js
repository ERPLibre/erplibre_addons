/* © 2026 TechnoLibre — License AGPL-3.0 or later */

import {Call} from "@voip_oca/components/call/call.esm";
import {HistoriqueCorrespondant} from "./historique.esm";
import {Numpad} from "@voip_oca/components/numpad/numpad.esm";
import {Partner} from "@voip_oca/components/partner/partner.esm";
import {ouvrirCompositeurSms} from "./sms.esm";
import {patch} from "@web/core/utils/patch";
import {useService} from "@web/core/utils/hooks";

// L'historique s'affiche aux TROIS moments ou il sert, et non au seul ou un
// appel existe : pendant l'appel, apres avoir raccroche — le panneau de fiche
// prend alors la place —, et pendant qu'on compose un numero, avant meme de
// savoir si quelqu'un repondra.
Call.components = {...Call.components, HistoriqueCorrespondant};
Partner.components = {...Partner.components, HistoriqueCorrespondant};
Numpad.components = {...Numpad.components, HistoriqueCorrespondant};

patch(Call.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
    },

    /**
     * Cree la fiche, puis rattache l'appel EN COURS a ce qui vient d'etre
     * cree. Sans ce second temps, la fiche existe et l'appel affiche encore
     * « No contact info » : le rapprochement n'a lieu qu'a la creation de
     * l'appel, qui est deja passee.
     */
    onCreerContact() {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "res.partner",
                views: [[false, "form"]],
                target: "new",
                context: {default_phone: this.voip.call.phoneNumber},
            },
            {
                onClose: async () => {
                    if (!this.voip.call.id) {
                        return;
                    }
                    const appel = await this.orm.call(
                        "voip.call",
                        "rattacher_le_contact",
                        [[this.voip.call.id]]
                    );
                    if (appel.partner) {
                        this.voip.partner = appel.partner;
                    }
                },
            }
        );
    },

    onEnvoyerSms() {
        const contact = this.voip.partner || {};
        ouvrirCompositeurSms(this.action, contact.id, this.voip.call.phoneNumber);
    },
});

patch(Partner.prototype, {
    onEnvoyerSms() {
        ouvrirCompositeurSms(this.action, this.props.partner.id, this.phoneNumber);
    },
});
