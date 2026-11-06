import {
  click,
  contains,
  openDiscuss,
  start,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import {
  animationFrame,
  pointerDown,
  press,
  queryAll,
  queryAllAttributes,
  queryAllTexts,
  queryFirst,
  select,
  waitUntil,
} from "@odoo/hoot-dom";
import { getService, onRpc } from "@web/../tests/web_test_helpers";

import {
  defineLinkupNetworkModels,
  mockNetwork,
  setupNetwork,
} from "./linkup_network_test_helpers";

describe.current.tags("desktop");
defineLinkupNetworkModels();

const VIEW = ".o-linkup-NetworkView";
const NODE = `${VIEW}-node`;

async function openNetworkView() {
  await getService("action").doAction(
    "mail_linkup_network.action_linkup_network"
  );
  await contains(`${VIEW}-canvas`);
}

/** @param {string} name */
function nodeOf(users, name) {
  return `${NODE}[data-user-id='${users[name].userId}']`;
}

test("the graph centres the member and draws each contact, strongest first", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users, { steps: true });
  await start();
  await openNetworkView();
  await expect.waitForSteps(["graph x1", "ranking partners all"]);
  await contains(`${VIEW} h1`, { text: "Network view" });
  await contains(`${VIEW}-energyValue`, { text: "61,563" });
  await contains(NODE, { count: 3 });
  expect(queryAllTexts(`${NODE} ${VIEW}-name`)).toEqual([
    "France",
    "Jacques",
    "Jean",
  ]);
  // The width of each line follows the energy of the link.
  const widths = queryAllAttributes(`${VIEW}-edge`, "stroke-width").map(Number);
  expect(widths[0]).toBeGreaterThan(widths[1]);
  expect(widths[1]).toBeGreaterThan(widths[2]);
  // X1 draws the grey line the server sends, between France and Jean.
  await contains(`${VIEW}-greyEdge`, { count: 1 });
  await contains(
    `${nodeOf(users, "Jacques")}[data-highlight='true'] .o-linkup-isHighlighted`
  );
  expect(nodeOf(users, "France")).toHaveAttribute(
    "aria-label",
    "France, energy of the link 32,450 points. Open the card of the link."
  );
  // A single Tab stop: the first node.
  expect(queryAllAttributes(NODE, "tabindex")).toEqual(["0", "-1", "-1"]);
  await contains(`${VIEW}-summary`, {
    text: "You, Mitchell Admin, in the centre, and 3 people around you. X1: Two levels: my links, and the links between my contacts who agree to show them.",
  });
});

test("the graph as a list says the same in text", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users, { steps: true });
  await start();
  await openNetworkView();
  await click(`${VIEW}-list summary`);
  expect(queryAllTexts(`${VIEW}-listEntry`)).toEqual([
    "France · 32,450 points · also linked with Jean",
    "Jacques · 12,459 points · Jacques adds to your happiness.",
    "Jean · 6,909 points · also linked with France",
  ]);
  await click(`${VIEW}-listEntry:eq(1)`);
  await expect.waitForSteps([
    "graph x1",
    "ranking partners all",
    "card Jacques false",
  ]);
  await contains(`${VIEW}-card[data-available='true']`);
});

test("the densities X1, X2 and X3 read the graph again and say so", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users, { steps: true });
  await start();
  await openNetworkView();
  await expect.waitForSteps(["graph x1", "ranking partners all"]);
  expect(`${VIEW}-level[data-level='x1']`).toHaveAttribute(
    "aria-pressed",
    "true"
  );
  await click(`${VIEW}-level[data-level='x2']`);
  await expect.waitForSteps(["graph x2"]);
  await contains(`${VIEW}-canvas[data-level='x2']`);
  await contains(`${VIEW}-greyEdge`, { count: 0 });
  await contains(NODE, { count: 3 });
  expect(`${VIEW}-level[data-level='x2']`).toHaveAttribute(
    "aria-pressed",
    "true"
  );
  await click(`${VIEW}-level[data-level='x3']`);
  await expect.waitForSteps(["graph x3"]);
  await contains(NODE, { count: 2 });
  await contains(`${VIEW} [aria-live='polite']`, {
    text: "X3: My 2 strongest partners. 2 people shown.",
  });
  // The grey line legend shows in X1 only.
  await contains("[data-linkup-guide='network-grey']", { count: 0 });
});

test("the keyboard walks the nodes, opens a card and gets its focus back", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users, { steps: true });
  await start();
  await openNetworkView();
  await expect.waitForSteps(["graph x1", "ranking partners all"]);
  queryFirst(nodeOf(users, "France")).focus();
  await press("ArrowRight");
  await animationFrame();
  expect(`${nodeOf(users, "Jacques")}`).toBeFocused();
  expect(queryAllAttributes(NODE, "tabindex")).toEqual(["-1", "0", "-1"]);
  await press("End");
  await animationFrame();
  expect(`${nodeOf(users, "Jean")}`).toBeFocused();
  await press("Home");
  await animationFrame();
  expect(`${nodeOf(users, "France")}`).toBeFocused();
  await press("ArrowLeft");
  await animationFrame();
  expect(`${nodeOf(users, "Jean")}`).toBeFocused();
  await press("ArrowRight");
  await animationFrame();
  await press("ArrowRight");
  await animationFrame();
  expect(`${nodeOf(users, "Jacques")}`).toBeFocused();
  await press("Enter");
  await expect.waitForSteps(["card Jacques false"]);
  await contains(`${VIEW}-card[data-available='true']`);
  await animationFrame();
  expect(`${VIEW}-card`).toBeFocused();
  await contains(`${VIEW}-cardEnergyValue`, { text: "12,459" });
  await contains(`${VIEW}-cardHalo`, {
    text: "Jacques adds to your happiness.",
  });
  await contains(`${nodeOf(users, "Jacques")}[aria-pressed='true']`);
  await press("Escape");
  await contains(`${VIEW}-card`, { count: 0 });
  await animationFrame();
  expect(`${nodeOf(users, "Jacques")}`).toBeFocused();
});

test("the card of a link: its energy, its thread, the filter and the light", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users, { steps: true });
  onRpc("linkup.highlight", "action_send", ({ args }) => {
    expect.step(`highlight ${args[0]}`);
    return true;
  });
  await start();
  await openNetworkView();
  await click(`${VIEW}-row[data-user-id='${users.France.userId}']`);
  await expect.waitForSteps([
    "graph x1",
    "ranking partners all",
    "card France false",
  ]);
  await contains(`${VIEW}-cardTitle`, { text: "France" });
  // The same value as "My partners" (LU-F-071 RM2).
  await contains(`${VIEW}-cardEnergyValue`, { text: "32,450" });
  await contains(
    `${VIEW}-row[data-user-id='${users.France.userId}'] ${VIEW}-rowValue`,
    {
      text: "32,450",
    }
  );
  await contains(`${VIEW}-firstLink`, { text: "First link: 09/01/2026" });
  await contains(`${VIEW}-call`, { text: "Call" });
  await contains(`${VIEW}-video`, { text: "Video" });
  await contains(`${VIEW}-openChat`, { text: "Open the conversation" });
  // The thread alternates: the member on the right.
  await contains(`${VIEW}-entry`, { count: 2 });
  await contains(`${VIEW}-entry.o-isMine ${VIEW}-entryText`, {
    text: "See you at the garden",
  });
  await contains(`${VIEW}-entry:not(.o-isMine) ${VIEW}-entryText`, {
    text: "Gladly",
  });
  await click(`${VIEW}-refletsOnly`);
  await expect.waitForSteps(["card France true"]);
  await contains(`${VIEW}-refletsOnly[aria-pressed='true']`);
  await contains(`${VIEW}-noEntry`, { text: "Nothing to show here yet." });
  await click(`${VIEW}-highlight`);
  await expect.waitForSteps([`highlight ${users.France.userId}`]);
  await contains(`${VIEW}-highlight[aria-pressed='true']:disabled`, {
    text: "In the light",
  });
  await contains(`${VIEW}-cardNotice`, {
    text: "France sees your avatar on theirs until your next exchange.",
  });
});

test("a press outside the card, or the energy bubble, closes it", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users);
  await start();
  await openNetworkView();
  await click(`${VIEW}-lineHit[data-user-id='${users.France.userId}']`);
  await contains(`${VIEW}-card[data-available='true']`);
  await contains(`${VIEW}-edge.o-isSelected`, { count: 1 });
  await pointerDown(`${VIEW}-summary`);
  await contains(`${VIEW}-card`, { count: 0 });
  await click(nodeOf(users, "France"));
  await contains(`${VIEW}-card[data-available='true']`);
  // A press inside the card keeps it.
  await pointerDown(`${VIEW}-cardTitle`);
  await contains(`${VIEW}-card`);
  await click(`${VIEW}-energy`);
  await contains(`${VIEW}-card`, { count: 0 });
  await animationFrame();
  expect(`${nodeOf(users, "France")}`).toBeFocused();
});

test("a link out of reach says it is not available, whatever the reason", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users);
  await start();
  await openNetworkView();
  await click(nodeOf(users, "Jean"));
  await contains(`${VIEW}-card[data-available='false'] ${VIEW}-unavailable`, {
    text: "This link is not available.",
  });
  await contains(`${VIEW}-call`, { count: 0 });
});

test("the rankings: my partners, the most active, and the period", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users, { steps: true });
  await start();
  await openNetworkView();
  await expect.waitForSteps(["graph x1", "ranking partners all"]);
  expect(queryAllTexts(`${VIEW}-rowName`)).toEqual([
    "France",
    "Jacques",
    "Jean",
  ]);
  expect(queryAllTexts(`${VIEW}-rowValue`)).toEqual([
    "32,450",
    "12,459",
    "6,909",
  ]);
  await contains(
    `${VIEW}-row[data-user-id='${users.Jacques.userId}'] .o-linkup-isHighlighted`
  );
  await click(`${VIEW}-tab[data-kind='active']`);
  await expect.waitForSteps(["ranking partners all", "ranking active all"]);
  await contains(`${VIEW}-tab[data-kind='active'][aria-selected='true']`);
  await contains(`${VIEW}-rowName`, { count: 2 });
  expect(queryAllTexts(`${VIEW}-rowValue`)).toEqual(["87,300", "31,900"]);
  await contains(`${VIEW}-rankingHint`, {
    text: "The energy of your contacts who show it, rounded to the hundred, without penalties. Never the whole community.",
  });
  await select("30d", { target: `${VIEW}-period` });
  await expect.waitForSteps(["ranking partners all", "ranking active 30d"]);
  // The arrow keys move between the tabs.
  queryFirst(`${VIEW}-tab[data-kind='active']`).focus();
  await press("ArrowLeft");
  await animationFrame();
  expect(
    `${VIEW}-tab[data-kind='partners'][aria-selected='true']`
  ).toBeFocused();
  // "My partners" counts every line, as the card of a link does.
  await expect.waitForSteps(["ranking partners all"]);
  await contains(`${VIEW}-period`, { count: 0 });
});

test("the list button shows the most active, my partners, then the graph again", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users, { steps: true });
  await start();
  await openNetworkView();
  await expect.waitForSteps(["graph x1", "ranking partners all"]);
  const button = `${VIEW}-listButton`;
  const label = () => queryFirst(button).getAttribute("aria-label");
  expect(label()).toBe("Rankings: show The most active");
  // The button belongs to a small screen: pressed here without a pointer.
  queryFirst(button).click();
  await expect.waitForSteps(["ranking partners all", "ranking active all"]);
  await contains(`${VIEW}-tab[data-kind='active'][aria-selected='true']`);
  await waitUntil(() => label() === "Rankings: show My partners");
  expect(button).toHaveAttribute("aria-expanded", "true");
  queryFirst(button).click();
  await expect.waitForSteps(["ranking partners all"]);
  await contains(`${VIEW}-tab[data-kind='partners'][aria-selected='true']`);
  await waitUntil(() => label() === "Rankings: back to the graph");
  queryFirst(button).click();
  await waitUntil(
    () => queryFirst(button).getAttribute("aria-expanded") === "false"
  );
  expect(label()).toBe("Rankings: show The most active");
  expect.verifySteps([]);
});

test("with the points hidden, no number shows and the contacts go by name", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users);
  await start();
  getService("mail.store").settings.linkup_hide_gamification = true;
  await openNetworkView();
  await contains(`${VIEW}-energyValue`, { count: 0 });
  expect(`${VIEW}-energy`).toHaveAttribute("aria-label", "Back to the graph");
  await contains(`${VIEW}-tab`, { count: 1 });
  await contains(`${VIEW}-period`, { count: 0 });
  await contains(`${VIEW}-rowValue`, { count: 0 });
  await contains(`${VIEW}-position`, { count: 0 });
  await contains("[data-linkup-guide='network-thickness']", { count: 0 });
  const widths = new Set(queryAllAttributes(`${VIEW}-edge`, "stroke-width"));
  expect(widths.size).toBe(1);
  expect(nodeOf(users, "France")).toHaveAttribute(
    "aria-label",
    "France. Open the card of the link."
  );
  await click(nodeOf(users, "France"));
  await contains(`${VIEW}-card[data-available='true']`);
  await contains(`${VIEW}-cardEnergy`, { count: 0 });
  expect(document.body.textContent).not.toMatch(/32,450|61,563/);
});

test("the happiness field puts a contact in the light, with the keyboard", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users, { steps: true });
  onRpc("linkup.highlight", "action_send", ({ args }) => {
    expect.step(`highlight ${args[0]}`);
    return true;
  });
  await start();
  await openNetworkView();
  await click(`${VIEW}-happiness`);
  await contains(`${VIEW}-happinessList[role='listbox']`);
  await animationFrame();
  expect(`${VIEW}-happinessList`).toBeFocused();
  await contains(`${VIEW}-option`, { count: 3 });
  await press("ArrowDown");
  await contains(`${VIEW}-option.o-isActive`, { text: "Jacques" });
  await press("Escape");
  await contains(`${VIEW}-happinessList`, { count: 0 });
  await animationFrame();
  expect(`${VIEW}-happiness`).toBeFocused();
  // Escape closed the list only: the view is still there.
  await contains(`${VIEW}-canvas`);
  await click(`${VIEW}-happiness`);
  await contains(`${VIEW}-happinessList`);
  await animationFrame();
  expect(`${VIEW}-happinessList`).toBeFocused();
  await press("ArrowDown");
  await press("Enter");
  await expect.waitForSteps([
    "graph x1",
    "ranking partners all",
    `highlight ${users.Jacques.userId}`,
  ]);
  await contains(`${VIEW}-happinessNotice`, {
    text: "Jacques sees your avatar on theirs until your next exchange.",
  });
});

test("the member allows their links and their energy to be shown", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users, { steps: true });
  onRpc("res.users", "write", ({ args }) => {
    expect.step(`write ${JSON.stringify(args[1])}`);
  });
  await start();
  await openNetworkView();
  await click(`${VIEW}-privacy summary`);
  await contains(`${VIEW}-preference:not(:checked)`, { count: 2 });
  await click(`${VIEW}-preference[data-field='linkup_energy_visible']`);
  await expect.waitForSteps([
    "graph x1",
    "ranking partners all",
    'write {"linkup_energy_visible":true}',
  ]);
  await waitUntil(() => getService("mail.store").linkup_energy_visible);
  await contains(
    `${VIEW}-preference[data-field='linkup_energy_visible']:checked`
  );
});

test("in guide mode, a node explains itself instead of opening the card", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users, { steps: true });
  await start();
  await openNetworkView();
  await expect.waitForSteps(["graph x1", "ranking partners all"]);
  await click(`${VIEW}-header .o-linkup-GuideButton`);
  await contains(".o-linkup-GuideSheet");
  await click(nodeOf(users, "France"));
  await contains(".o-linkup-GuideSheet-title", { text: "A person" });
  await contains(`${VIEW}-card`, { count: 0 });
  await click(`${VIEW}-level[data-level='x3']`);
  await contains(".o-linkup-GuideSheet-title", { text: "X3 · the strongest" });
  await contains(".o-linkup-GuideSheet-definition", {
    text: "Your 2 strongest partners only.",
  });
  // Every element of the guide has a text of its own.
  for (const el of queryAll("[data-linkup-guide^='network-']")) {
    el.click();
    await animationFrame();
    expect(
      queryFirst(".o-linkup-GuideSheet-title").textContent.trim()
    ).not.toBe("Guide");
    await contains(".o-linkup-GuideSheet-behavior");
  }
  await press("Escape");
  await contains(".o-linkup-GuideSheet", { count: 0 });
  expect.verifySteps([]);
});

test("Discuss shows “Network view (n)” and Escape goes back to it", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users);
  await start();
  await openDiscuss();
  await contains(".o-linkup-SidebarSection-networkView", {
    text: "Network view (61,563)",
  });
  await click(".o-linkup-SidebarSection-networkView");
  await contains(`${VIEW}-canvas`);
  await press("Escape");
  await contains(`${VIEW}`, { count: 0 });
  await contains(".o-mail-Discuss");
});

test("the Reflet view and the Network view lead to each other", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users);
  await start();
  await openNetworkView();
  await click(`${VIEW}-refletView`);
  await contains(".o-linkup-RefletView");
  await click(".o-linkup-RefletView-networkView");
  await contains(`${VIEW}-canvas`);
  await click(nodeOf(users, "France"));
  await click(`${VIEW}-newReflet`);
  await contains(
    `.o-linkup-RefletView-contact[data-user-id='${users.France.userId}'] .o-linkup-RefletView-contactSelect[aria-pressed='true']`
  );
});

test("“+ NewLink” opens the invitation of the Reflet view", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users);
  await start();
  await openNetworkView();
  await click(`${VIEW}-newlink`);
  await contains(".o-linkup-Newlink[data-step='contact']");
});
