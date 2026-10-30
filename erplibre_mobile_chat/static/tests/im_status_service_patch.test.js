/* © 2026 TechnoLibre — License AGPL-3.0 or later */

import { onWebsocketEvent } from "@bus/../tests/mock_websocket";
import { UPDATE_BUS_PRESENCE_DELAY } from "@bus/im_status_service";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { click } from "@odoo/hoot-dom";
import { advanceTime, Deferred } from "@odoo/hoot-mock";
import { asyncStep, getService, makeMockEnv, waitForSteps } from "@web/../tests/web_test_helpers";

defineMailModels();
describe.current.tags("desktop");

// Un envoi passe par le port du worker (asynchrone) puis par son anti-rebond
// de 300 ms : il arrive en temps réel bien avant cette limite.
const ARRIVAL = { timeout: 2000 };

async function startBus() {
    await makeMockEnv();
    await getService("bus_service").start();
}

test("update_presence repart à chaque UPDATE_BUS_PRESENCE_DELAY", async () => {
    onWebsocketEvent("update_presence", () => asyncStep("update_presence"));
    await startBus();
    await waitForSteps(["update_presence"], ARRIVAL);
    for (let minute = 1; minute <= 2; minute++) {
        await advanceTime(UPDATE_BUS_PRESENCE_DELAY);
        await waitForSteps(["update_presence"], ARRIVAL);
    }
});

test("l'envoi périodique porte la vraie durée d'inactivité", async () => {
    // Durée d'inactivité de chaque envoi, et l'envoi qu'on attend.
    const periods = [];
    let next = new Deferred();
    onWebsocketEvent("update_presence", ({ inactivity_period }) => {
        periods.push(inactivity_period);
        next.resolve();
    });
    await startBus();
    await next;
    await advanceTime(UPDATE_BUS_PRESENCE_DELAY / 2);
    // Le clic peut lui-même déclencher un envoi (voir imStatusService) :
    // il est attendu avant d'avancer jusqu'à la 60e seconde.
    await click(document.body);
    await new Promise((resolve) => setTimeout(resolve, 1000));
    const before = periods.length;
    next = new Deferred();
    await advanceTime(UPDATE_BUS_PRESENCE_DELAY / 2);
    await Promise.race([next, new Promise((resolve) => setTimeout(resolve, 2000))]);
    expect(periods.length).toBe(before + 1);
    // Dernier clic à 30 s : l'envoi de la 60e seconde dit environ 30 s.
    expect(periods.at(-1)).toBeWithin(
        UPDATE_BUS_PRESENCE_DELAY / 2 - 1000,
        UPDATE_BUS_PRESENCE_DELAY / 2 + 1000
    );
});
