import {
  click,
  contains,
  insertText,
  openDiscuss,
  start,
  startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import {
  Command,
  getService,
  patchWithCleanup,
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
  return { pyEnv, franceId, franceUserId, channelId };
}

/** Record the sounds played as steps. */
function stepSounds() {
  patchWithCleanup(getService("mail.sound_effects"), {
    play(name) {
      expect.step(`play ${name}`);
    },
  });
}

async function sendFromRefletView() {
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.reflet_view",
  });
  await click(".o-linkup-HelpBar-category[data-code='emotions']");
  await click(".o-linkup-RefletView-contactSelect");
  await insertText(".o-linkup-RefletForm-youSaid", "the chores wear you out");
  await insertText(".o-linkup-RefletForm-understood", "you are exhausted");
  await click(".o-linkup-RefletForm-realWorld input[type='checkbox']");
  await click(".o-linkup-RefletForm-send");
  await contains(".o-linkup-RefletView-notice", {
    text: "Reflection sent to France.",
  });
}

test("the LinkUp sounds are added to the sound service", async () => {
  await startServer();
  await start();
  const sounds = getService("mail.sound_effects").soundEffects;
  for (const name of [
    "linkup-sent",
    "linkup-received",
    "linkup-success",
    "linkup-yeah",
    "linkup-ting",
  ]) {
    expect(sounds[name].path).toMatch(
      /^\/mail_linkup_reflet\/static\/src\/audio\//
    );
  }
});

test("a sent reflection plays its sound", async () => {
  await setupFrance();
  await start();
  stepSounds();
  await sendFromRefletView();
  expect.verifySteps(["play linkup-sent"]);
});

test("the sounds turned off, a sent reflection plays nothing", async () => {
  const { pyEnv } = await setupFrance();
  pyEnv["res.users.settings"].create({
    user_id: serverState.userId,
    linkup_sound_enabled: false,
  });
  await start();
  stepSounds();
  await sendFromRefletView();
  expect.verifySteps([]);
});

test("“You add to my happiness” asks first, then shines until withdrawn", async () => {
  const { pyEnv, channelId, franceUserId } = await setupFrance();
  await start();
  await openDiscuss(channelId);
  await click(".o-mail-Discuss-header button[name='linkup-panel']");
  await click(".o-linkup-Panel-highlightButton[aria-pressed='false']");
  await contains(".o-linkup-Panel-highlightConfirm", {
    text: "Put France in the light?",
  });
  await contains(".o-linkup-Panel-highlightConfirm", {
    text: "France will see your avatar on theirs until your next exchange, with the notification “Mitchell Admin adds to your happiness”.",
  });
  await click(".o-linkup-Panel-highlightCancel");
  expect(pyEnv["linkup.highlight"].search([])).toEqual([]);
  await click(".o-linkup-Panel-highlightButton");
  await click(".o-linkup-Panel-highlightConfirmButton");
  await contains(".o-linkup-Panel-highlightButton[aria-pressed='true']");
  const [highlight] = pyEnv["linkup.highlight"].search_read([]);
  expect(highlight.sender_id[0]).toBe(serverState.userId);
  expect(highlight.recipient_id[0]).toBe(franceUserId);
  expect(highlight.channel_id[0]).toBe(channelId);
  await click(".o-linkup-Panel-highlightWithdraw");
  await contains(".o-linkup-Panel-highlightButton[aria-pressed='false']");
  await contains(".o-linkup-Panel-highlightWithdraw", { count: 0 });
});

test("a received highlight shines in the panel and in the Reflet view", async () => {
  const { pyEnv, channelId, franceUserId } = await setupFrance();
  const highlightId = pyEnv["linkup.highlight"].create({
    sender_id: franceUserId,
    recipient_id: serverState.userId,
    channel_id: channelId,
  });
  await start();
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.reflet_view",
  });
  await contains(".o-linkup-RefletView-selfAvatar.o-linkup-isHighlighted");
  await contains(
    ".o-linkup-RefletView-highlights .o-linkup-Highlights-avatar",
    {
      count: 1,
    }
  );
  await contains(".o-linkup-RefletView-highlights", {
    text: "Who adds to your happiness: France",
  });
  await contains(".o-linkup-RefletView-avatar.o-linkup-isHighlighted");
  await openDiscuss(channelId);
  await click(".o-mail-Discuss-header button[name='linkup-panel']");
  await contains(".o-linkup-Panel-highlightReceived", {
    text: "France adds to your happiness",
  });
  await click(".o-linkup-Panel-highlightDismiss");
  await contains(".o-linkup-Panel-highlightReceived", { count: 0 });
  expect(pyEnv["linkup.highlight"].browse(highlightId)[0].active).toBe(false);
});

test("discreet notifications name nobody", async () => {
  const { pyEnv, franceUserId } = await setupFrance();
  const jacquesId = pyEnv["res.partner"].create({ name: "Jacques" });
  const jacquesUserId = pyEnv["res.users"].create({
    name: "Jacques",
    partner_id: jacquesId,
  });
  await start();
  patchWithCleanup(getService("mail.out_of_focus"), {
    sendNotification({ message, title, icon }) {
      expect.step(`${title} | ${message} | ${icon ? "avatar" : "no avatar"}`);
    },
  });
  const Highlight = pyEnv["linkup.highlight"];
  const fromFrance = Highlight.create({
    sender_id: franceUserId,
    recipient_id: serverState.userId,
  });
  Highlight._linkupNotify(fromFrance, "linkup.highlight/received");
  await expect.waitForSteps([
    "LinkUp | France adds to your happiness. | avatar",
  ]);
  getService("mail.store").settings.linkup_notify_discreet = true;
  const fromJacques = Highlight.create({
    sender_id: jacquesUserId,
    recipient_id: serverState.userId,
  });
  Highlight._linkupNotify(fromJacques, "linkup.highlight/received");
  await expect.waitForSteps(["LinkUp | New LinkUp event | no avatar"]);
});
