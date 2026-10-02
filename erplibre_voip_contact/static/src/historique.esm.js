/* © 2026 TechnoLibre — License AGPL-3.0 or later */

import {Component, onWillUpdateProps, useState} from "@odoo/owl";
import {deserializeDateTime, formatDateTime} from "@web/core/l10n/dates";
import {durationStr} from "@voip_oca/utils/utils.esm";
import {useDebounced} from "@web/core/utils/timing";
import {useService} from "@web/core/utils/hooks";

/**
 * Ce qu'on s'est deja dit avec ce correspondant : les appels, les SMS.
 *
 * <p>Un composant plutot qu'un bloc colle au panneau d'appel, parce que les
 * trois moments ou l'historique sert n'en comportent pas tous un : pendant
 * l'appel, apres avoir raccroche, et pendant qu'on compose un numero.
 *
 * <p>Le chargement n'empeche JAMAIS l'affichage. Un echec laisse les listes
 * vides et le panneau utilisable ; l'inverse ferait perdre l'ecran d'un appel
 * en cours — le nom, le bouton pour raccrocher — pour une liste d'archives.
 */
export class HistoriqueCorrespondant extends Component {
    static template = "erplibre_voip_contact.Historique";
    static props = {
        phoneNumber: {type: [String, Boolean], optional: true},
        partnerId: {type: [Number, Boolean], optional: true},
        excludeCallId: {type: [Number, Boolean], optional: true},
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            appels: [],
            sms: [],
            // Les appels ouverts, les SMS replies : c'est un panneau de
            // softphone, et tout deplier repousserait le bouton de
            // raccrochage hors de l'ecran.
            ouvert: {appels: true, sms: false},
        });
        // Le numero compose change a chaque touche. Interroger le serveur a
        // chacune enverrait une dizaine de requetes pour un seul numero, et
        // les reponses reviendraient dans le desordre.
        this.chargerPlusTard = useDebounced(() => this.charger(this.props), 400);
        this.charger(this.props);
        onWillUpdateProps((suivantes) => {
            this.props = suivantes;
            this.chargerPlusTard();
        });
    }

    async charger(props) {
        if (!props.phoneNumber && !props.partnerId) {
            this.state.appels = [];
            this.state.sms = [];
            return;
        }
        try {
            const historique = await this.orm.call(
                "res.partner",
                "historique_correspondant",
                [],
                {
                    phone_number: props.phoneNumber || false,
                    partner_id: props.partnerId || false,
                    exclude_call_id: props.excludeCallId || false,
                }
            );
            this.state.appels = historique.appels;
            this.state.sms = historique.sms;
        } catch (erreur) {
            // Journalise et continue : voir le correspondant importe plus que
            // voir ce qu'on lui a dit la semaine derniere.
            console.warn("historique du correspondant indisponible", erreur);
        }
    }

    basculer(section) {
        this.state.ouvert[section] = !this.state.ouvert[section];
    }

    chevron(section) {
        return this.state.ouvert[section]
            ? "fa fa-fw fa-chevron-down"
            : "fa fa-fw fa-chevron-right";
    }

    /** La date a montrer : celle du decroche, ou celle de la tentative. */
    dateAppel(appel) {
        return this.dateCourte(appel.startDate || appel.createDate);
    }

    dateCourte(brut) {
        return brut ? formatDateTime(deserializeDateTime(brut)) : "";
    }

    iconeSens(sens) {
        return sens === "incoming" || sens === "in"
            ? "fa fa-fw fa-arrow-down text-success"
            : "fa fa-fw fa-arrow-up text-primary";
    }

    /**
     * La duree, vide tant que l'appel n'a pas ete pris.
     *
     * <p>Un appel sans decroche n'a pas une duree de zero seconde : il n'en a
     * pas du tout, et afficher « 0 » ferait croire a une communication coupee
     * net plutot qu'a un appel manque.
     */
    dureeAppel(appel) {
        if (!appel.startDate || !appel.endDate) {
            return "";
        }
        const debut = deserializeDateTime(appel.startDate);
        const fin = deserializeDateTime(appel.endDate);
        return durationStr(Math.round((fin - debut) / 1000));
    }
}
