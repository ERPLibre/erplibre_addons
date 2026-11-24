/* © 2026 TechnoLibre — License AGPL-3.0 or later */

import { getWebSocketWorker, onWebsocketEvent } from "@bus/../tests/mock_websocket";
import { UPDATE_BUS_PRESENCE_DELAY } from "@bus/im_status_service";
import { BACK_ONLINE_RECONNECT_DELAY } from "@bus/services/bus_service";
import { WEBSOCKET_CLOSE_CODES } from "@bus/workers/websocket_worker";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { click, manuallyDispatchProgrammaticEvent } from "@odoo/hoot-dom";
import { advanceTime, Deferred } from "@odoo/hoot-mock";
import {
    getService,
    makeMockEnv,
    MockServer,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";

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
    onWebsocketEvent("update_presence", () => expect.step("update_presence"));
    await startBus();
    await expect.waitForSteps(["update_presence"], ARRIVAL);
    for (let minute = 1; minute <= 2; minute++) {
        await advanceTime(UPDATE_BUS_PRESENCE_DELAY);
        await expect.waitForSteps(["update_presence"], ARRIVAL);
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

// Durée d'une coupure dans les tests : trois battements manqués.
const OUTAGE_TICKS = 3;

/** Laisse passer ARRIVAL en temps réel : un envoi parti y serait arrivé. */
function arrivalWindow() {
    return new Promise((resolve) => setTimeout(resolve, ARRIVAL.timeout));
}

/**
 * Attend que le premier envoi de la connexion ait quitté le worker : il
 * part après le premier abonnement (firstSubscribeDeferred). Couper avant
 * laisserait cet envoi en attente d'un websocket que l'arrêt a retiré.
 */
async function firstSendFlushed() {
    await getWebSocketWorker().firstSubscribeDeferred;
}

/** Rend une promesse tenue au prochain « disconnect » reçu par l'onglet. */
function nextDisconnect() {
    return new Promise((resolve) =>
        getService("bus_service").addEventListener("disconnect", resolve, { once: true })
    );
}

async function advanceWhileCut() {
    for (let tick = 1; tick <= OUTAGE_TICKS; tick++) {
        await advanceTime(UPDATE_BUS_PRESENCE_DELAY);
    }
    await arrivalWindow();
}

test("pas d'update_presence pendant une coupure, un seul à la reconnexion", async () => {
    onWebsocketEvent("update_presence", () => expect.step("update_presence"));
    await startBus();
    await expect.waitForSteps(["update_presence"], ARRIVAL);
    await firstSendFlushed();
    const worker = getWebSocketWorker();
    // Le serveur reste injoignable : le worker ne retente pas la connexion.
    const allowRetry = patchWithCleanup(worker, { _retryConnectionWithDelay() {} });
    const disconnected = nextDisconnect();
    MockServer.env["bus.bus"]._simulateDisconnection(WEBSOCKET_CLOSE_CODES.ABNORMAL_CLOSURE);
    await disconnected;
    await advanceWhileCut();
    expect.verifySteps([]);
    allowRetry();
    worker._start();
    await expect.waitForSteps(["update_presence"], ARRIVAL);
    // Pas d'envoi plus tardif pour la même reconnexion. Deux envois à moins
    // de 300 ms l'un de l'autre ne font qu'une étape ici : voir stepTabSends.
    await arrivalWindow();
    expect.verifySteps([]);
    await advanceTime(UPDATE_BUS_PRESENCE_DELAY);
    await expect.waitForSteps(["update_presence"], ARRIVAL);
});

test("pas d'update_presence hors ligne, un seul au retour en ligne", async () => {
    onWebsocketEvent("update_presence", () => expect.step("update_presence"));
    await startBus();
    await expect.waitForSteps(["update_presence"], ARRIVAL);
    await firstSendFlushed();
    // « offline » arrête le worker sans changer son état (il reste
    // CONNECTED) : seul l'événement « disconnect » signale la coupure.
    const disconnected = nextDisconnect();
    patchWithCleanup(navigator, { onLine: false });
    await manuallyDispatchProgrammaticEvent(window, "offline");
    await disconnected;
    await advanceWhileCut();
    expect.verifySteps([]);
    patchWithCleanup(navigator, { onLine: true });
    await manuallyDispatchProgrammaticEvent(window, "online");
    await advanceTime(BACK_ONLINE_RECONNECT_DELAY);
    await expect.waitForSteps(["update_presence"], ARRIVAL);
    // Pas d'envoi plus tardif pour la même connexion (voir stepTabSends).
    await arrivalWindow();
    expect.verifySteps([]);
    await advanceTime(UPDATE_BUS_PRESENCE_DELAY);
    await expect.waitForSteps(["update_presence"], ARRIVAL);
});

/**
 * Fait une étape « onglet » de chaque update_presence que l'onglet confie au
 * worker. onWebsocketEvent ne voit que la sortie de l'anti-rebond de 300 ms
 * du worker, qui fond deux envois proches en une seule trame : seul ce
 * compte, pris avant, distingue un envoi d'un envoi doublé.
 */
function stepTabSends() {
    const bus = getService("bus_service");
    const send = bus.send;
    patchWithCleanup(bus, {
        send(eventName, data) {
            if (eventName === "update_presence") {
                expect.step("onglet");
            }
            return send(eventName, data);
        },
    });
}

test("un seul update_presence par connexion, compté avant l'anti-rebond", async () => {
    onWebsocketEvent("update_presence", () => expect.step("serveur"));
    await makeMockEnv();
    stepTabSends();
    await getService("bus_service").start();
    // Premier « connect » : l'écouteur { once: true } d'Odoo envoie, seul.
    await expect.waitForSteps(["onglet", "serveur"], ARRIVAL);
    await arrivalWindow();
    expect.verifySteps([]);
    await firstSendFlushed();
    // Second « connect », après un arrêt propre : le correctif envoie, seul.
    const disconnected = nextDisconnect();
    patchWithCleanup(navigator, { onLine: false });
    await manuallyDispatchProgrammaticEvent(window, "offline");
    await disconnected;
    patchWithCleanup(navigator, { onLine: true });
    await manuallyDispatchProgrammaticEvent(window, "online");
    await advanceTime(BACK_ONLINE_RECONNECT_DELAY);
    await expect.waitForSteps(["onglet", "serveur"], ARRIVAL);
    await arrivalWindow();
    expect.verifySteps([]);
});
