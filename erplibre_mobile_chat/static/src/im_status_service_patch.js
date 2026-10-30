/* © 2026 TechnoLibre — License AGPL-3.0 or later */

import { imStatusService, UPDATE_BUS_PRESENCE_DELAY } from "@bus/im_status_service";
import { WORKER_STATE } from "@bus/workers/websocket_worker";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";

/**
 * Le service d'Odoo 18 n'envoie update_presence qu'à la première connexion
 * et aux passages à « absent » ; le battement de 60 s du worker est une
 * trame vide que le serveur ignore. Ce correctif le renvoie en plus toutes
 * les UPDATE_BUS_PRESENCE_DELAY ms, avec la durée d'inactivité réelle
 * (updateBusPresence lit presence.getInactivityPeriod()).
 *
 * Le battement ne part que si le bus est connecté. Le worker met en file
 * tout envoi fait pendant une coupure et vide la file d'un coup à la
 * reconnexion : une file d'un envoi par minute dépasse la limite de débit
 * du websocket côté serveur (rate limit de bus/websocket.py) après
 * quelques minutes hors ligne. La connexion se lit sur deux signaux du
 * bus_service : « worker_state_updated », qui précède chaque « connect » et
 * « reconnect », et « disconnect », seul signal d'un arrêt par l'événement
 * « offline » du navigateur, après lequel le worker garde l'état CONNECTED.
 *
 * Le correctif ajoute une présence, une seule, à chaque connexion rétablie :
 * « reconnect » après une coupure du websocket, et « connect » à partir du
 * second, après un arrêt propre (hors ligne puis en ligne). Le premier
 * « connect » est laissé à l'écouteur { once: true } d'Odoo, qui l'envoie
 * déjà. Les envois du service d'Odoo faits pendant la coupure restent en
 * file et partent avant elle : le passage à « absent » (AWAY_DELAY) et le
 * retour d'activité qui le suit, au plus deux par onglet et par AWAY_DELAY
 * de coupure (im_status_updated arrive par le bus, donc jamais pendant elle).
 *
 * Côté serveur, ir.websocket._update_bus_presence du module en tire la
 * présence d'un navigateur : en ligne tant que le dernier envoi date de
 * moins de DISCONNECTION_TIMER (65 s) et la dernière activité de moins de
 * BROWSER_ACTIVE_S (voir res.users._erplibre_browser_domain). Plusieurs
 * onglets partagent le worker, dont l'anti-rebond de 300 ms fond leurs
 * envois simultanés.
 */
patch(imStatusService, {
    start(env, services) {
        const api = super.start(env, services);
        const { bus_service } = services;
        let connected = bus_service.workerState === WORKER_STATE.CONNECTED;
        let connects = 0;
        bus_service.addEventListener("worker_state_updated", ({ detail }) => {
            connected = detail === WORKER_STATE.CONNECTED;
        });
        bus_service.addEventListener("disconnect", () => {
            connected = false;
        });
        bus_service.addEventListener("connect", () => {
            if (connects++) {
                api.updateBusPresence();
            }
        });
        bus_service.addEventListener("reconnect", () => api.updateBusPresence());
        browser.setInterval(() => {
            if (connected) {
                api.updateBusPresence();
            }
        }, UPDATE_BUS_PRESENCE_DELAY);
        return api;
    },
});
