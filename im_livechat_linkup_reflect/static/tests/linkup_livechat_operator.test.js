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
  contains as webContains,
  onRpc,
  serverState,
} from "@web/../tests/web_test_helpers";

import { defineLinkupLivechatModels } from "./linkup_livechat_test_helpers";

describe.current.tags("desktop");
defineLinkupLivechatModels();

/**
 * A welcome conversation of the live chat between the current user, a
 * member who operates it, and a visitor; `values` are its fields.
 */
async function setupConversation(values = {}) {
  const pyEnv = await startServer();
  const guestId = pyEnv["mail.guest"].create({ name: "Visitor 12" });
  const channelId = pyEnv["discuss.channel"].create({
    name: "Visitor 12",
    channel_type: "livechat",
    livechat_active: true,
    livechat_operator_id: serverState.partnerId,
    channel_member_ids: [
      Command.create({ partner_id: serverState.partnerId }),
      Command.create({ guest_id: guestId }),
    ],
    linkup_livechat_kind: "welcome",
    linkup_can_reflect: true,
    ...values,
  });
  return { pyEnv, guestId, channelId };
}

/** A reflection of the visitor to the current user, with its carrier. */
function addVisitorReflet(pyEnv, channelId, guestId, values = {}) {
  const [emotions] = pyEnv["linkup.category"].search([
    ["code", "=", "emotions"],
  ]);
  const messageId = pyEnv["mail.message"].create({
    author_guest_id: guestId,
    body: "<p>Visitor 12 sent you a reflection.</p>",
    message_type: "comment",
    model: "discuss.channel",
    res_id: channelId,
  });
  const refletId = pyEnv["linkup.reflet"].create({
    kind: "initial",
    state: "sent",
    author_guest_id: guestId,
    recipient_id: serverState.userId,
    category_id: emotions,
    you_said: "the chores and a job wear you out",
    understood: "you are exhausted",
    channel_id: channelId,
    message_id: messageId,
    livechat: true,
    ...values,
  });
  return refletId;
}

test("the card of a visitor shows to the operator as the card of a member", async () => {
  const { pyEnv, guestId, channelId } = await setupConversation();
  addVisitorReflet(pyEnv, channelId, guestId);
  await start();
  await openDiscuss(channelId);
  await contains(
    ".o-linkup-RefletCard[data-role='recipient'][data-state='sent']"
  );
  await contains(".o-linkup-RefletCard-title", {
    text: "You told me about your emotions",
  });
  await contains(".o-linkup-RefletCard-footer", {
    text: "Visitor 12 sent you a reflection.",
  });
  await contains(".o-linkup-RefletActions-confirm");
  await contains(".o-linkup-RefletActions-reject");
  await contains(".o-linkup-RefletActions-inaccurate", { count: 0 });
  await contains(".o-linkup-RefletActions-ignore", { count: 0 });
});

test("the operator confirms through the route of the live chat", async () => {
  const { pyEnv, guestId, channelId } = await setupConversation();
  const refletId = addVisitorReflet(pyEnv, channelId, guestId);
  onRpc("linkup.reflet", "action_confirm", () => expect.step("action_confirm"));
  onRpc("/linkup/v1/livechat/reflet/confirm", async (request) => {
    const { params } = await request.json();
    expect.step(`confirm ${params.channel_id} ${params.reflet_id}`);
    pyEnv["linkup.reflet"].write([refletId], { state: "confirmed" });
    return true;
  });
  onRpc("/linkup/v1/livechat/reflet/info", () => ({
    available: true,
    can_send: true,
    reflet_ids: [refletId],
  }));
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-RefletActions-confirm");
  await expect.waitForSteps([`confirm ${channelId} ${refletId}`]);
});

test("a rejection of the live chat asks first, then goes through its route", async () => {
  const { pyEnv, guestId, channelId } = await setupConversation();
  const refletId = addVisitorReflet(pyEnv, channelId, guestId);
  onRpc("/linkup/v1/livechat/reflet/reject", async (request) => {
    const { params } = await request.json();
    expect.step(`reject ${params.reflet_id}`);
    return true;
  });
  onRpc("/linkup/v1/livechat/reflet/info", () => ({ available: true }));
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-RefletActions-reject");
  await contains(".modal-body", {
    text: "Declare that the exchange of this reflection never took place? Visitor 12 will see it.",
  });
  await click(".o-linkup-RejectDialog-confirm");
  await expect.waitForSteps([`reject ${refletId}`]);
});

test("the operator reports the visitor, who cannot be blocked", async () => {
  const { pyEnv, guestId, channelId } = await setupConversation();
  addVisitorReflet(pyEnv, channelId, guestId);
  onRpc("linkup.report", "action_report_livechat_visitor", ({ args }) => {
    expect.step(`report ${args.join(" ")}`);
    return 1;
  });
  await start();
  await openDiscuss(channelId);
  await contains(".o-linkup-Safety-report");
  await contains(".o-linkup-Safety-block", { count: 0 });
  await click(".o-linkup-Safety-report");
  await webContains(".o-linkup-Safety-reason").select("harassment");
  await click(".o-linkup-Safety-send");
  await expect.waitForSteps([`report ${channelId} harassment `]);
  await contains(".o-linkup-Safety-ack");
});

test("strict: the operator writes the reflection, sent through the live chat", async () => {
  const { channelId } = await setupConversation({
    linkup_start_rule: "strict",
    linkup_start_rule_satisfied: false,
  });
  onRpc("/linkup/v1/livechat/reflet/info", () => ({
    available: true,
    can_send: true,
    recipient_name: "Visitor 12",
    draft: false,
    reflet_ids: [],
    linkup_start_rule: "strict",
    linkup_start_rule_satisfied: false,
  }));
  let draft = null;
  onRpc("/linkup/v1/livechat/reflet/draft", async (request) => {
    draft = (await request.json()).params;
    return 7;
  });
  onRpc("/linkup/v1/livechat/reflet/send", async (request) => {
    const { params } = await request.json();
    expect.step(`send ${params.channel_id}`);
    return 7;
  });
  await start();
  await openDiscuss(channelId);
  await contains(".o-linkup-StartRule[data-mode='strict']");
  await contains(".o-mail-Composer.d-none");
  await click(".o-linkup-StartRule-reflet");
  await click(".o-linkup-HelpBar-category[data-code='emotions']");
  await insertText(".o-linkup-RefletForm-youSaid", "the chores wear you out");
  await insertText(".o-linkup-RefletForm-understood", "you are exhausted");
  await click(
    ".o-linkup-RefletForm-realWorld input[name='real_world_declared']"
  );
  await click(".o-linkup-RefletForm-send");
  await expect.waitForSteps([`send ${channelId}`]);
  expect(draft.channel_id).toBe(channelId);
  expect(draft.vals.you_said).toBe("the chores wear you out");
  expect(draft.vals.real_world_declared).toBe(true);
  await contains(".o-linkup-RefletComposer-notice", {
    text: "Reflection sent to Visitor 12.",
  });
});

test("a conversation of distress has neither start rule nor reflection", async () => {
  const { channelId } = await setupConversation({
    linkup_livechat_kind: "distress",
    linkup_can_reflect: false,
    linkup_start_rule: "off",
  });
  await start();
  await openDiscuss(channelId);
  await contains(".o-mail-Composer-input");
  await contains(".o-linkup-StartRule", { count: 0 });
  await contains(".o-linkup-Composer-refletButton", { count: 0 });
});
