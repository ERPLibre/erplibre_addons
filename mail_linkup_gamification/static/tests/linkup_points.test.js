import {
  click,
  contains,
  openDiscuss,
  start,
  startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { press, queryAllTexts, queryFirst, waitUntil } from "@odoo/hoot-dom";
import { advanceTime } from "@odoo/hoot-mock";
import {
  Command,
  getService,
  onRpc,
  patchWithCleanup,
  serverState,
} from "@web/../tests/web_test_helpers";

import {
  LINKUP_BURST_DURATION,
  LINKUP_POINTS_GROUP_DELAY,
} from "@mail_linkup_gamification/core/common/points_service";
import { linkupPointsGuideSentence } from "@mail_linkup_gamification/core/common/points_patches";

import {
  defineLinkupPointsModels,
  ledgerLine,
  myPointsResult,
} from "./linkup_points_test_helpers";
import { LINKUP_TEST_RULES } from "./mock_server/mock_models/res_users";

describe.current.tags("desktop");
defineLinkupPointsModels();

/** A chat between the current user and France. */
async function setupChat() {
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
  return { pyEnv, franceId, franceUserId, channelId };
}

/**
 * A reflection France sent the current user, waiting for an answer, with
 * its carrier message in their chat.
 */
function receivedReflet(pyEnv, { channelId, franceId, franceUserId }) {
  const [emotions] = pyEnv["linkup.category"].search([
    ["code", "=", "emotions"],
  ]);
  const messageId = pyEnv["mail.message"].create({
    author_id: franceId,
    body: "<p>Neutral sentence of the carrier.</p>",
    message_type: "comment",
    model: "discuss.channel",
    res_id: channelId,
  });
  return pyEnv["linkup.reflet"].create({
    kind: "initial",
    state: "sent",
    author_id: franceUserId,
    recipient_id: serverState.userId,
    category_id: emotions,
    you_said: "the chores wear you out",
    understood: "you are exhausted",
    channel_id: channelId,
    message_id: messageId,
  });
}

/** Send a ledger line of the current user on the bus. */
function sendAwarded(pyEnv, payload) {
  const [partner] = pyEnv["res.partner"].read(serverState.partnerId);
  pyEnv["bus.bus"]._sendone(partner, "linkup.points/awarded", {
    rule_code: "reflect_confirmed",
    capped: false,
    cap_reason: false,
    counterpart_id: false,
    reflet_id: false,
    channel_id: false,
    ...payload,
  });
}

/** Record the sounds played as steps. */
function stepSounds() {
  patchWithCleanup(getService("mail.sound_effects"), {
    play(name) {
      expect.step(`play ${name}`);
    },
  });
}

async function setReward(enabled) {
  getService("mail.store").settings.linkup_reward_sounds_enabled = enabled;
}

async function openRefletView() {
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.reflet_view",
  });
  await contains(".o-linkup-RefletView-body");
}

test("a gain rises above the energy, is announced and moves the energy", async () => {
  const { pyEnv } = await setupChat();
  pyEnv["res.users"].write([serverState.userId], {
    linkup_karma: 100,
    linkup_rank: "Spark",
  });
  await start();
  await openRefletView();
  await contains(".o-linkup-Energy-bubble .o-linkup-Energy-value", {
    text: "100",
  });
  sendAwarded(pyEnv, { id: 11, points: 1000, karma: 1100 });
  await contains(".o-linkup-PointsBurst.o-isAnchored[data-kind='gain']", {
    text: "+1,000That's a link!",
  });
  await contains(".o-linkup-PointsOverlay-live", {
    text: "You earn 1,000 points",
  });
  expect(".o-linkup-PointsBurst").toHaveAttribute("aria-hidden", "true");
  await contains(".o-linkup-Energy-bubble .o-linkup-Energy-value", {
    text: "1,100",
  });
  expect(".o-linkup-Energy-bubble").toHaveAttribute(
    "aria-label",
    "My energy: 1,100 points. Rank: Spark. Open my points."
  );
  await advanceTime(LINKUP_BURST_DURATION);
  await contains(".o-linkup-PointsBurst", { count: 0 });
});

test("without the energy on the screen, the burst shows in the top corner", async () => {
  const { pyEnv, channelId } = await setupChat();
  await start();
  await openDiscuss(channelId);
  sendAwarded(pyEnv, {
    id: 12,
    points: 250,
    karma: 250,
    rule_code: "answer_exact",
  });
  await contains(".o-linkup-PointsBurst[data-kind='gain']:not(.o-isAnchored)", {
    text: "+250Reformulation confirmed",
  });
});

test("a loss shows “−N” and plays no sound", async () => {
  const { pyEnv } = await setupChat();
  await start();
  stepSounds();
  await setReward(true);
  sendAwarded(pyEnv, {
    id: 13,
    points: -150,
    karma: -150,
    rule_code: "reflect_rejected",
  });
  await contains(".o-linkup-PointsBurst[data-kind='loss']", {
    text: "−150The exchange did not take place",
  });
  await contains(".o-linkup-PointsOverlay-live", {
    text: "You lose 150 points",
  });
  expect.verifySteps([]);
});

test("a gain plays “linkup-yeah” once, only with the reward sounds", async () => {
  const { pyEnv } = await setupChat();
  await start();
  stepSounds();
  sendAwarded(pyEnv, { id: 14, points: 100, karma: 100 });
  await contains(".o-linkup-PointsBurst", { count: 1 });
  expect.verifySteps([]);
  await advanceTime(LINKUP_POINTS_GROUP_DELAY);
  await setReward(true);
  sendAwarded(pyEnv, { id: 15, points: 1000, karma: 1100 });
  sendAwarded(pyEnv, {
    id: 16,
    points: 100,
    karma: 1200,
    rule_code: "reflect_sent",
  });
  await contains(".o-linkup-PointsBurst", { count: 3 });
  expect.verifySteps(["play linkup-yeah"]);
  await contains(".o-linkup-PointsOverlay-live", {
    text: "You earn 1,000 points You earn 100 points",
  });
});

test("the core sound setting silences the points too", async () => {
  const { pyEnv } = await setupChat();
  await start();
  stepSounds();
  const settings = getService("mail.store").settings;
  settings.linkup_reward_sounds_enabled = true;
  settings.linkup_sound_enabled = false;
  sendAwarded(pyEnv, { id: 17, points: 1000, karma: 1000 });
  await contains(".o-linkup-PointsBurst", { count: 1 });
  expect.verifySteps([]);
});

test("discreet notifications silence the points, the “+N” still shows", async () => {
  const { pyEnv } = await setupChat();
  await start();
  stepSounds();
  const settings = getService("mail.store").settings;
  settings.linkup_reward_sounds_enabled = true;
  settings.linkup_notify_discreet = true;
  sendAwarded(pyEnv, { id: 23, points: 1000, karma: 1000 });
  await contains(".o-linkup-PointsBurst[data-kind='gain']", {
    text: "+1,000That's a link!",
  });
  await contains(".o-linkup-PointsOverlay-live", {
    text: "You earn 1,000 points",
  });
  expect.verifySteps([]);
  // Without them, the next gain sounds again.
  await advanceTime(LINKUP_POINTS_GROUP_DELAY);
  settings.linkup_notify_discreet = false;
  sendAwarded(pyEnv, { id: 24, points: 100, karma: 1100 });
  await contains(".o-linkup-PointsBurst", { count: 2 });
  expect.verifySteps(["play linkup-yeah"]);
});

test("a capped line shows the information of the cap, without a burst", async () => {
  const { pyEnv } = await setupChat();
  await start();
  sendAwarded(pyEnv, {
    id: 18,
    points: 0,
    karma: 0,
    capped: true,
    cap_reason: "daily_cap",
    linkup_code: "linkup.cap_reached",
  });
  await contains(".o_notification.o-linkup-CapNotice", {
    text: "Sent. No more points today for this action.",
  });
  await contains(".o-linkup-PointsBurst", { count: 0 });
});

test("a line seen once shows once, from the bus or from a reading", async () => {
  const { pyEnv } = await setupChat();
  onRpc("linkup.points.ledger", "linkup_my_points", ({ kwargs }) => {
    expect.step(`after ${kwargs.after_id}`);
    return myPointsResult([ledgerLine(19)], { balance: 1000 });
  });
  await start();
  sendAwarded(pyEnv, { id: 19, points: 1000, karma: 1000 });
  await contains(".o-linkup-PointsBurst", { count: 1 });
  await getService("linkup.points").catchUp();
  expect.verifySteps(["after 19"]);
  await contains(".o-linkup-PointsBurst", { count: 1 });
  sendAwarded(pyEnv, { id: 19, points: 1000, karma: 1000 });
  await advanceTime(100);
  await contains(".o-linkup-PointsBurst", { count: 1 });
});

test("a confirmation reads its points at once, without the bus", async () => {
  const { pyEnv, channelId, franceId, franceUserId } = await setupChat();
  receivedReflet(pyEnv, { channelId, franceId, franceUserId });
  onRpc("linkup.points.ledger", "linkup_my_points", ({ kwargs }) => {
    expect.step(`after ${kwargs.after_id}`);
    return myPointsResult([ledgerLine(21)], { balance: 1000 });
  });
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-RefletActions-confirm");
  await contains(".o-linkup-PointsBurst[data-kind='gain']", {
    text: "+1,000That's a link!",
  });
  await expect.waitForSteps(["after 0"]);
  expect(getService("mail.store").linkup_karma).toBe(1000);
  expect(getService("mail.store").linkup_points_last_id).toBe(21);
});

test("a new rank and a new badge are shown and announced", async () => {
  const { pyEnv } = await setupChat();
  await start();
  const [partner] = pyEnv["res.partner"].read(serverState.partnerId);
  pyEnv["bus.bus"]._sendone(partner, "linkup.points/rank", {
    rank_id: 2,
    name: "Flame",
    karma: 2600,
  });
  await contains(".o-linkup-PointsBurst[data-kind='rank']", {
    text: "New rank: Flame",
  });
  expect(getService("mail.store").linkup_rank).toBe("Flame");
  pyEnv["bus.bus"]._sendone(partner, "linkup.points/badge", {
    badge_id: 3,
    name: "First link",
  });
  await contains(".o-linkup-PointsBurst[data-kind='badge']", {
    text: "New badge: First link",
  });
  await contains(".o-linkup-PointsOverlay-live", {
    text: "New rank: Flame New badge: First link",
  });
});

test("hiding the points removes the energy, the bursts and their sound", async () => {
  const { pyEnv } = await setupChat();
  await start();
  stepSounds();
  const settings = getService("mail.store").settings;
  settings.linkup_reward_sounds_enabled = true;
  settings.linkup_hide_gamification = true;
  await openRefletView();
  await contains(".o-linkup-ProfileMenu");
  await contains(".o-linkup-Energy", { count: 0 });
  sendAwarded(pyEnv, { id: 22, points: 1000, karma: 1000 });
  // The new karma tells that the line arrived: what it must not show is
  // checked after it, not before.
  await waitUntil(() => getService("mail.store").linkup_karma === 1000);
  await advanceTime(100);
  await contains(".o-linkup-PointsBurst", { count: 0 });
  expect(".o-linkup-PointsOverlay-live").toHaveText("");
  expect.verifySteps([]);
});

test("the menu of the avatar ends with “My points”, even with the points hidden", async () => {
  await setupChat();
  await start();
  getService("mail.store").settings.linkup_hide_gamification = true;
  await openRefletView();
  await click(".o-linkup-ProfileMenu-toggle");
  await contains(".o-linkup-ProfileMenu-menu[role='menu']");
  expect(queryAllTexts(".o-linkup-ProfileMenu-label")).toEqual([
    "Help",
    "Email",
    "Phone",
    "Photo",
    "Sounds and notifications",
    "Privacy",
    "My data",
    "Blocked members",
    "My points",
  ]);
  const points = ".o-linkup-ProfileMenu-entry[data-entry='points']";
  expect(points).toHaveAttribute("role", "menuitem");
  expect(points).toHaveAttribute("tabindex", "-1");
  expect(points).not.toHaveAttribute("aria-disabled");
  await press("End");
  expect(points).toBeFocused();
  await press("ArrowDown");
  expect(".o-linkup-ProfileMenu-entry[data-entry='help']").toBeFocused();
  await press("ArrowUp");
  expect(points).toBeFocused();
  patchWithCleanup(getService("action"), {
    doAction(action) {
      expect.step(action);
    },
  });
  await click(points);
  await contains(".o-linkup-ProfileMenu-menu", { count: 0 });
  expect.verifySteps(["mail_linkup_gamification.action_linkup_my_points"]);
});

test("the help page offers to hide the points", async () => {
  await startServer();
  onRpc("res.users.settings", "set_res_users_settings", ({ kwargs }) => {
    expect.step(JSON.stringify(kwargs.new_settings));
  });
  await start();
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.help",
  });
  await contains(".o-linkup-Help-settings .form-check", {
    text: "Hide the points and their animations",
  });
  await click("#o-linkup-Help-linkup_hide_gamification");
  await expect.waitForSteps(['{"linkup_hide_gamification":true}']);
});

test("the LinkUp panel shows the energy of the member and of the link", async () => {
  const { pyEnv, channelId } = await setupChat();
  pyEnv["res.users"].write([serverState.userId], {
    linkup_karma: 4100,
    linkup_rank: "Flame",
  });
  await start();
  await openDiscuss(channelId);
  await click(".o-mail-Discuss-header button[name='linkup-panel']");
  await contains(".o-linkup-Energy-card .o-linkup-Energy-value", {
    text: "4,100",
  });
  await contains(".o-linkup-Energy-card .o-linkup-Energy-rank", {
    text: "Rank: Flame",
  });
  await contains(".o-linkup-Panel-linkEnergy", {
    text: "Energy of the link: 1,350 points",
  });
});

test("the guide tells the points of a confirmation, a rejection and a guess", async () => {
  // The numbers follow the localization of the web client.
  await startServer();
  await start();
  expect(linkupPointsGuideSentence("reflet-confirm", LINKUP_TEST_RULES)).toBe(
    "Each of you earns +1,000 points, and the author +100 more for the reflection."
  );
  expect(linkupPointsGuideSentence("reflet-reject", LINKUP_TEST_RULES)).toBe(
    "The author loses 150 points."
  );
  expect(linkupPointsGuideSentence("guess-submit", LINKUP_TEST_RULES)).toBe(
    "A right guess earns +100 points to each of you."
  );
  expect(linkupPointsGuideSentence("highlight", LINKUP_TEST_RULES)).toBe("");
  expect(
    linkupPointsGuideSentence("reflet-confirm", { reflect_confirmed: 800 })
  ).toBe("Each of you earns +800 points.");
});

test("the guide sheet of a received card ends with its points", async () => {
  const { pyEnv, channelId, franceId, franceUserId } = await setupChat();
  receivedReflet(pyEnv, { channelId, franceId, franceUserId });
  await start();
  await openDiscuss(channelId);
  await contains(".o-linkup-RefletActions-confirm");
  getService("linkup.guide").open();
  await click(".o-linkup-RefletActions-confirm");
  await contains(".o-linkup-GuideSheet-behavior");
  expect(queryFirst(".o-linkup-GuideSheet-behavior").textContent).toInclude(
    "Each of you earns +1,000 points, and the author +100 more for the reflection."
  );
  getService("linkup.guide").close();
  await contains(".o-linkup-GuideSheet", { count: 0 });
  expect(queryFirst(".o-linkup-RefletActions-confirm")).not.toBe(null);
  expect(queryAllTexts(".o-linkup-PointsBurst")).toEqual([]);
});
