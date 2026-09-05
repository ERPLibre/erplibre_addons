/* © 2026 TechnoLibre — License AGPL-3.0 or later */

import {VoipOCASoftphone} from "@voip_oca/components/softphone/softphone.esm";
import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

/**
 * Le bouton « appeler » du pied du softphone.
 *
 * <p>Trois branches y menaient, et la derniere lisait une propriete qui
 * n'existe pas — le service ne porte ni `number` ni rien d'approchant. Le
 * rappel partait donc sans numero ET sans contact, et la creation de l'appel
 * echouait sur un champ obligatoire vide, message que rien ne rattachait au
 * bouton qu'on venait de presser.
 *
 * <p>On resout donc le numero en UN SEUL endroit, puis on refuse
 * lisiblement quand il n'y en a pas.
 */
patch(VoipOCASoftphone.prototype, {
    setup() {
        super.setup();
        this.notification = useService("notification");
    },

    /**
     * Le numero a composer : celui de l'appel affiche, sinon celui de la
     * fiche.
     *
     * <p>L'appel prime sur la fiche parce qu'il porte le numero REELLEMENT
     * compose ou recu ; une fiche peut en porter deux, et rappeler sur
     * l'autre ne joint pas la personne qui vient d'appeler.
     */
    numeroARappeler() {
        const appel = this.voip.call || {};
        const contact = this.voip.partner || {};
        return (
            appel.phoneNumber || contact.mobileNumber || contact.landlineNumber || ""
        );
    },

    onCall() {
        if (this.voip.numpadTab && this.voip.numpad.value) {
            return this.agent.call({number: this.voip.numpad.value});
        }
        const numero = this.numeroARappeler();
        if (numero) {
            return this.agent.call({
                number: numero,
                partner: this.voip.partner || undefined,
            });
        }
        // Un appel ouvert ou une fiche ouverte sans aucun numero : on sait
        // QUI, on ne sait pas OU. Le dire vaut mieux que de laisser partir
        // une creation qui echouera sur un champ obligatoire.
        if (this.voip.call || this.voip.partner) {
            return this.notification.add(
                _t("Aucun numéro à composer : cette fiche n'en porte pas."),
                {type: "warning"}
            );
        }
        const element = registry.category("voip_elements").get(this.voip.selectedTab);
        return element.call(this.voip);
    },
});
