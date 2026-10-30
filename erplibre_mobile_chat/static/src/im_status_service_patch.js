/* © 2026 TechnoLibre — License AGPL-3.0 or later */

import { imStatusService, UPDATE_BUS_PRESENCE_DELAY } from "@bus/im_status_service";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";

/**
 * Le service d'Odoo 18 n'envoie update_presence qu'à la connexion et aux
 * passages à « absent » ; le battement de 60 s du worker est une trame
 * vide que le serveur ignore. Ce correctif le renvoie en plus toutes les
 * UPDATE_BUS_PRESENCE_DELAY ms, avec la durée d'inactivité réelle
 * (updateBusPresence lit presence.getInactivityPeriod()).
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
        browser.setInterval(() => api.updateBusPresence(), UPDATE_BUS_PRESENCE_DELAY);
        return api;
    },
});
