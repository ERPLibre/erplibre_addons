import {
  click,
  contains,
  openDiscuss,
  start,
  startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { press, waitUntil } from "@odoo/hoot-dom";
import {
  Command,
  getService,
  onRpc,
  serverState,
} from "@web/../tests/web_test_helpers";

import { defineLinkupModels } from "./linkup_test_helpers";

describe.current.tags("desktop");
defineLinkupModels();

/** France, in a direct conversation with the current user. */
async function setupFrance() {
  const pyEnv = await startServer();
  const franceId = pyEnv["res.partner"].create({ name: "France" });
  const franceUserId = pyEnv["res.users"].create({
    name: "France",
    partner_id: franceId,
  });
  const channelId = pyEnv["discuss.channel"].create({
    channel_member_ids: [
      Command.create({ partner_id: serverState.partnerId }),
      Command.create({ partner_id: franceId }),
    ],
    channel_type: "chat",
  });
  const category = (code) =>
    pyEnv["linkup.category"].search([["code", "=", code]])[0];
  return { pyEnv, franceId, franceUserId, channelId, category };
}

async function openRefletView() {
  await start();
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.reflet_view",
  });
  await contains(".o-linkup-RefletView-body");
}

const SHEET = ".o-linkup-GuideSheet";

test("the guide explains a category of the Help bar instead of opening a card", async () => {
  await setupFrance();
  await openRefletView();
  await click(".o-linkup-HelpBar .o-linkup-GuideButton[aria-pressed='false']");
  await contains(
    ".o-linkup-HelpBar .o-linkup-GuideButton[aria-pressed='true']"
  );
  await contains(`${SHEET} .o-linkup-GuideSheet-counter`, {
    text: "Guide · 1 of 11",
  });
  await contains(`${SHEET} .o-linkup-GuideSheet-title`, {
    text: "Observation",
  });
  await click(".o-linkup-HelpBar-category[data-code='emotions']");
  await contains(`${SHEET} .o-linkup-GuideSheet-title`, { text: "Emotions" });
  await contains(`${SHEET} .o-linkup-GuideSheet-counter`, {
    text: "Guide · 2 of 11",
  });
  await contains(`${SHEET} .o-linkup-GuideSheet-definition`, {
    text: "What a person feels.",
  });
  await contains(`${SHEET} .o-linkup-GuideSheet-do`, {
    text: "What to say: “I feel anger when I see that the rule is not respected.”",
  });
  await contains(`${SHEET} .o-linkup-GuideSheet-starter`, {
    text: "Starter: I feel:",
  });
  await contains(`${SHEET} .o-linkup-GuideSheet-behavior`, {
    text: "Behaviour: Outside the guide, this button opens the card “You told me about your emotions”: You told me / I understood that.",
  });
  // Reading changes nothing on the screen.
  await contains(".o-linkup-RefletView-placeholder");
  await contains(".o-linkup-RefletForm", { count: 0 });
  await click(`${SHEET} .o-linkup-GuideSheet-next`);
  await contains(`${SHEET} .o-linkup-GuideSheet-title`, { text: "Needs" });
  await click(`${SHEET} .o-linkup-GuideSheet-previous`);
  await contains(`${SHEET} .o-linkup-GuideSheet-title`, { text: "Emotions" });
  await press("Escape");
  await contains(SHEET, { count: 0 });
  await contains(
    ".o-linkup-HelpBar .o-linkup-GuideButton[aria-pressed='false']"
  );
  await contains(".o-linkup-RefletForm", { count: 0 });
  // "Show" leaves the guide and opens the card of the category.
  await click(".o-linkup-HelpBar .o-linkup-GuideButton");
  await click(".o-linkup-HelpBar-category[data-code='emotions']");
  await click(`${SHEET} .o-linkup-GuideSheet-show`);
  await contains(SHEET, { count: 0 });
  await contains(".o-linkup-RefletForm-title", {
    text: "You told me about your emotions",
  });
});

test("a second press on “?” leaves the guide; the contacts explain themselves", async () => {
  await setupFrance();
  await openRefletView();
  await click(".o-linkup-GuideButton");
  await click(".o-linkup-RefletView-contactSelect");
  await contains(`${SHEET} .o-linkup-GuideSheet-title`, { text: "A contact" });
  await contains(".o-linkup-RefletView-contact.o-isSelected", { count: 0 });
  await click(".o-linkup-GuideButton[aria-pressed='true']");
  await contains(SHEET, { count: 0 });
  await click(".o-linkup-RefletView-contactSelect");
  await contains(".o-linkup-RefletView-contact.o-isSelected");
});

test("in guide mode, a theme of the guess is explained and no guess is made", async () => {
  const { pyEnv, franceId, franceUserId, channelId, category } =
    await setupFrance();
  pyEnv["linkup.reflet"].create({
    kind: "precision",
    state: "sent",
    author_id: franceUserId,
    recipient_id: serverState.userId,
    body_text: "I am looking for someone to move this forward.",
    guess_state: "pending",
    hidden_category_ids: [category("goals")],
    holds_turn: true,
    channel_id: channelId,
    message_id: pyEnv["mail.message"].create({
      author_id: franceId,
      body: "<p>France clarified their thought.</p>",
      message_type: "comment",
      model: "discuss.channel",
      res_id: channelId,
    }),
  });
  onRpc("linkup.reflet", "action_guess", () => {
    expect.step("action_guess");
  });
  await start();
  await openDiscuss(channelId);
  const actions = ".o-linkup-RefletActions[data-mode='guess']";
  await click(`${actions} .o-linkup-GuideButton`);
  await click(`${actions} .o-linkup-CategoryPicker-option[data-code='goals']`);
  await contains(`${SHEET} .o-linkup-GuideSheet-title`, { text: "Goals" });
  await contains(`${SHEET} .o-linkup-GuideSheet-behavior`, {
    text: "Behaviour: Outside the guide, this button chooses this theme as your guess; “Propose this theme” sends it, once.",
  });
  await contains(
    `${actions} .o-linkup-CategoryPicker-option[data-code='goals'][aria-pressed='false']`
  );
  await click(`${actions} .o-linkup-CategoryPicker-option[data-code='needs']`);
  await contains(`${SHEET} .o-linkup-GuideSheet-title`, { text: "Needs" });
  // "Show" leaves the guide and chooses the theme, without proposing it.
  await click(`${SHEET} .o-linkup-GuideSheet-show`);
  await contains(SHEET, { count: 0 });
  await contains(
    `${actions} .o-linkup-CategoryPicker-option[data-code='needs'][aria-pressed='true']`
  );
  await contains(".o-linkup-RefletActions-guess:enabled");
  expect.verifySteps([]);
});

test("the help page lists the twelve categories, the NVC group first", async () => {
  await startServer();
  await start();
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.help",
  });
  await contains(".o-linkup-Help h1", { text: "LinkUp help" });
  await contains(".o-linkup-Help-category", { count: 12 });
  await contains(".o-linkup-Help-cnv .o-linkup-Help-category", { count: 5 });
  await contains(
    ".o-linkup-Help-category[data-code='emotions'] .o-linkup-Help-definition",
    { text: "What a person feels." }
  );
});

test("the help page writes the sounds of the member", async () => {
  const pyEnv = await startServer();
  onRpc("res.users.settings", "set_res_users_settings", ({ kwargs }) => {
    expect.step(JSON.stringify(kwargs.new_settings));
  });
  await start();
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.help",
  });
  await contains("input[name='linkup_sound_enabled']:checked");
  await contains("input[name='linkup_reward_sounds_enabled']:not(:checked)");
  await click("input[name='linkup_sound_enabled']");
  await expect.waitForSteps(['{"linkup_sound_enabled":false}']);
  await contains("input[name='linkup_sound_enabled']:not(:checked)");
  const [settings] = pyEnv["res.users.settings"].search_read([
    ["user_id", "=", serverState.userId],
  ]);
  expect(settings.linkup_sound_enabled).toBe(false);
});

test("the first-use tour shows five steps once, then is remembered", async () => {
  const { pyEnv, channelId } = await setupFrance();
  pyEnv["res.users"].write([serverState.userId], { linkup_tour_done: false });
  onRpc("res.users", "linkup_tour_consume", () => {
    expect.step("linkup_tour_consume");
  });
  await start();
  await openDiscuss(channelId);
  await contains(".o-linkup-Tour .o-linkup-Tour-step", { text: "Step 1 of 5" });
  await contains(".o-linkup-Tour .o-linkup-Tour-title", {
    text: "Your LinkUp views",
  });
  await contains(".o-linkup-SidebarSection.o-linkup-Tour-anchor");
  await click(".o-linkup-Tour-next");
  await contains(".o-linkup-Tour-step", { text: "Step 2 of 5" });
  await contains(
    ".o-linkup-RefletComposer .o-linkup-HelpBar.o-linkup-Tour-anchor"
  );
  await click(".o-linkup-Tour-next");
  await contains(".o-linkup-Tour-step", { text: "Step 3 of 5" });
  await click(".o-linkup-Tour-next");
  await contains(".o-linkup-Tour-step", { text: "Step 4 of 5" });
  await contains(".o-linkup-Tour-title", { text: "Your LinkUp panel" });
  await contains(".o-linkup-Panel-content.o-linkup-Tour-anchor");
  await click(".o-linkup-Tour-next");
  await contains(".o-linkup-Tour-step", { text: "Step 5 of 5" });
  await contains(".o-linkup-GuideButton.o-linkup-Tour-anchor");
  await click(".o-linkup-Tour-next", { text: "Finish" });
  await contains(".o-linkup-Tour", { count: 0 });
  await expect.waitForSteps(["linkup_tour_consume"]);
  expect(getService("mail.store").linkup_tour_pending).toBe(false);
});

test("a tour ended in another client does not start in this one", async () => {
  const { pyEnv, channelId } = await setupFrance();
  pyEnv["res.users"].write([serverState.userId], { linkup_tour_done: false });
  await start();
  expect(getService("mail.store").linkup_tour_pending).toBe(true);
  const [partner] = pyEnv["res.partner"].read(serverState.partnerId);
  pyEnv["bus.bus"]._sendone(partner, "mail.record/insert", {
    Store: { linkup_tour_pending: false },
  });
  await waitUntil(() => getService("mail.store").linkup_tour_pending === false);
  await openDiscuss(channelId);
  await contains(".o-linkup-SidebarSection");
  await contains(".o-linkup-Tour", { count: 0 });
});

test("“Skip the tour” ends it at once; a member who saw it gets none", async () => {
  const { pyEnv, channelId } = await setupFrance();
  pyEnv["res.users"].write([serverState.userId], { linkup_tour_done: false });
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-Tour-skip");
  await contains(".o-linkup-Tour", { count: 0 });
  const [user] = pyEnv["res.users"].search_read([
    ["id", "=", serverState.userId],
  ]);
  expect(user.linkup_tour_done).toBe(true);
  await openDiscuss(channelId);
  await contains(".o-mail-Discuss");
  await contains(".o-linkup-Tour", { count: 0 });
});
