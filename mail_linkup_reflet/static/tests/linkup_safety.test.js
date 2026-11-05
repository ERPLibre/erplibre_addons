import {
  click,
  contains,
  insertText,
  openDiscuss,
  start,
  startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { queryAllTexts } from "@odoo/hoot-dom";
import {
  Command,
  contains as webContains,
  getService,
  onRpc,
  serverState,
} from "@web/../tests/web_test_helpers";

import { defineLinkupModels, mockLinkupReading } from "./linkup_test_helpers";

describe.current.tags("desktop");
defineLinkupModels();

/**
 * A chat between the current user and France, with one carrier message of
 * a reflection that France sent to the current user, unless `fromMe`.
 */
async function setupReceived({ fromMe = false } = {}) {
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
  const [emotions] = pyEnv["linkup.category"].search([
    ["code", "=", "emotions"],
  ]);
  const messageId = pyEnv["mail.message"].create({
    author_id: fromMe ? serverState.partnerId : franceId,
    body: "<p>Neutral sentence of the carrier.</p>",
    message_type: "comment",
    model: "discuss.channel",
    res_id: channelId,
  });
  const refletId = pyEnv["linkup.reflet"].create({
    kind: "initial",
    state: "rejected",
    author_id: fromMe ? serverState.userId : franceUserId,
    recipient_id: fromMe ? franceUserId : serverState.userId,
    category_id: emotions,
    you_said: "the chores and a job wear you out",
    understood: "you are exhausted",
    channel_id: channelId,
    message_id: messageId,
  });
  return { pyEnv, channelId, franceId, franceUserId, refletId };
}

const CARD = ".o-mail-Message .o-linkup-RefletCard";

test("the recipient of a card reports it with a reason and a comment", async () => {
  const { pyEnv, channelId, refletId } = await setupReceived();
  mockLinkupReading();
  onRpc("linkup.report", "action_create_report", ({ kwargs }) => {
    expect.step(
      `report ${kwargs.reflet_id} ${kwargs.reason} ${kwargs.description}`
    );
  });
  await start();
  await openDiscuss(channelId);
  await contains(`${CARD}[data-role='recipient'] .o-linkup-Safety-block`, {
    text: "Block France",
  });
  await click(`${CARD} .o-linkup-Safety-report`);
  await contains(".o-linkup-Safety-reportForm", {
    text: "France will not know who reported this reflection.",
  });
  // The reasons of a member, without the one of the server.
  expect(queryAllTexts(".o-linkup-Safety-reason option")).toEqual([
    "Choose a reason…",
    "Harassment",
    "Hate speech",
    "Sexual content",
    "Threat",
    "Minor in danger",
    "Person in distress or at risk for themselves",
    "Spam",
    "Impersonation",
    "Other",
  ]);
  await click(".o-linkup-Safety-send");
  await contains(".o-linkup-Safety-error[role='alert']", {
    text: "Choose a reason.",
  });
  expect.verifySteps([]);
  await webContains(".o-linkup-Safety-reason").select("harassment");
  await insertText(".o-linkup-Safety-description", "again and again");
  await click(".o-linkup-Safety-send");
  await expect.waitForSteps([`report ${refletId} harassment again and again`]);
  await contains(".o-linkup-Safety-ack[role='status']", {
    text: "Thank you, your report is passed on to the moderation.",
  });
  await contains(".o-linkup-Safety-report", { count: 0 });
  expect(
    pyEnv["linkup.report"].search_read([["reflet_id", "=", refletId]]).length
  ).toBe(1);
});

test("Escape closes the form of a report", async () => {
  const { channelId } = await setupReceived();
  mockLinkupReading();
  await start();
  await openDiscuss(channelId);
  await click(`${CARD} .o-linkup-Safety-report`);
  await contains(".o-linkup-Safety-reportForm");
  await webContains(".o-linkup-Safety-description").press("Escape");
  await contains(".o-linkup-Safety-reportForm", { count: 0 });
  await contains(".o-linkup-Safety-report");
});

test("the author of a card neither reports nor blocks from it", async () => {
  const { channelId } = await setupReceived({ fromMe: true });
  await start();
  await openDiscuss(channelId);
  await contains(`${CARD}[data-role='author']`);
  await contains(`${CARD} .o-linkup-Safety`, { count: 0 });
});

test("blocking from the card asks first, then tells what follows", async () => {
  const { pyEnv, channelId, franceUserId } = await setupReceived();
  mockLinkupReading();
  await start();
  await openDiscuss(channelId);
  await click(`${CARD} .o-linkup-Safety-block`);
  await contains(".modal-title", { text: "Block France?" });
  expect(".modal-body").toHaveText(
    /France is not told: what they send seems to leave, but nothing reaches you\./
  );
  await click(".modal .o-linkup-BlockDialog-confirm");
  await contains(".o_notification", {
    text: "France is blocked. The conversation is hidden.",
  });
  const blocks = pyEnv["linkup.block"].search_read([]);
  expect(blocks.map((block) => block.blocked_id[0])).toEqual([franceUserId]);
});

test("the LinkUp panel blocks, then unblocks, the other member", async () => {
  const { channelId, franceId } = await setupReceived();
  mockLinkupReading();
  onRpc("linkup.block", "*", ({ method, kwargs }) => {
    expect.step(`${method} ${kwargs.partner_id}`);
  });
  await start();
  await openDiscuss(channelId);
  await click(".o-mail-Discuss-header button[name='linkup-panel']");
  await click(".o-linkup-Panel-safety .o-linkup-Safety-block");
  await click(".modal .o-linkup-BlockDialog-confirm");
  await contains(".o-linkup-Panel-safety .o-linkup-Safety-unblock", {
    text: "Unblock France",
  });
  await click(".o-linkup-Panel-safety .o-linkup-Safety-unblock");
  await contains(".o-linkup-Panel-safety .o-linkup-Safety-block", {
    text: "Block France",
  });
  await expect.waitForSteps([
    `action_block ${franceId}`,
    `action_unblock ${franceId}`,
  ]);
});

test("the help page lists the blocked members and unblocks them", async () => {
  const pyEnv = await startServer();
  const franceId = pyEnv["res.partner"].create({ name: "France" });
  const franceUserId = pyEnv["res.users"].create({
    name: "France",
    partner_id: franceId,
  });
  pyEnv["linkup.block"].create({
    blocker_id: serverState.userId,
    blocked_id: franceUserId,
  });
  await start();
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.help",
  });
  await contains(".o-linkup-Help-blockedMember", { text: "France" });
  await click(".o-linkup-Help-unblock", { text: "Unblock France" });
  await contains(".o-linkup-Help-blockedMember", { count: 0 });
  await contains(".o-linkup-Help-blocked", { text: "You block nobody." });
});
