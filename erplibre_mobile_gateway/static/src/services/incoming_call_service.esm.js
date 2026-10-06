/* © 2026 TechnoLibre — License AGPL-3.0 or later */

import {registry} from "@web/core/registry";
import {_t} from "@web/core/l10n/translation";

/**
 * Affiche la fiche de l'appelant quand le telephone-passerelle sonne.
 *
 * Le serveur ne peut pas ouvrir une vue a la place de l'utilisateur : il
 * pousse un evenement, et c'est ici qu'on decide quoi en faire. On propose
 * plutot qu'on impose — ouvrir de force une fiche ferait perdre la saisie en
 * cours de quelqu'un qui n'attend aucun appel.
 *
 * La notification est COLLANTE. Un appel dure moins qu'une minute de
 * distraction : une bulle qui s'efface au bout de quelques secondes serait
 * ratee la moitie du temps, et c'est exactement quand on est occupe qu'on a
 * besoin de savoir qui appelle.
 */
/**
 * Age au-dela duquel une annonce n'est plus affichee, en secondes.
 *
 * A la connexion, le bus rejoue les annonces manquees. Sans ce garde-fou, un
 * poste qui ouvre Odoo le matin recevrait une bulle COLLANTE par appel de la
 * veille, a fermer une par une — et la vraie annonce se perdrait dans le tas.
 * La pastille du systray, elle, garde la trace des appels manques : c'est son
 * role, pas celui d'une bulle.
 */
const AGE_MAX_S = 120;

export const incomingCallService = {
    dependencies: ["bus_service", "notification", "action"],

    start(env, {bus_service, notification, action}) {
        bus_service.subscribe("erplibre_incoming_call", (payload) => {
            if (payload.at && Date.now() / 1000 - payload.at > AGE_MAX_S) {
                return;
            }
            const numero = payload.number || _t("numéro inconnu");

            if (!payload.model || !payload.res_id) {
                // Inconnu au fichier : on le dit quand meme. Un appel d'un
                // numero inconnu est justement celui qu'on veut enregistrer.
                notification.add(
                    _t("Appel entrant de %s — aucune fiche connue", numero),
                    {type: "warning", sticky: true, title: _t("Passerelle mobile")}
                );
                return;
            }

            notification.add(
                _t("Appel entrant : %s (%s)", payload.name || numero, numero),
                {
                    type: "info",
                    sticky: true,
                    title: _t("Passerelle mobile"),
                    buttons: [
                        {
                            name: _t("Ouvrir la fiche"),
                            onClick: () => {
                                action.doAction({
                                    type: "ir.actions.act_window",
                                    res_model: payload.model,
                                    res_id: payload.res_id,
                                    views: [[false, "form"]],
                                    target: "current",
                                });
                            },
                        },
                    ],
                }
            );
        });
    },
};

registry.category("services").add("erplibre_incoming_call", incomingCallService);
