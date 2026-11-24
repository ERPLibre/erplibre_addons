import {
  click,
  contains,
  openDiscuss,
  start,
  startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { Command, onRpc, serverState } from "@web/../tests/web_test_helpers";

import { defineLinkupNetworkModels } from "./linkup_network_test_helpers";

describe.current.tags("desktop");
defineLinkupNetworkModels();

const CARD = ".o-mail-Message .o-linkup-RefletCard";

/**
 * A chat between the current user and France, with a reflection France
 * sent to the current user, of the category `code`.
 */
async function setupRequest(code, values = {}) {
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
  const [categoryId] = pyEnv["linkup.category"].search([["code", "=", code]]);
  const messageId = pyEnv["mail.message"].create({
    author_id: franceId,
    body: "<p>Neutral sentence of the carrier.</p>",
    message_type: "comment",
    model: "discuss.channel",
    res_id: channelId,
  });
  pyEnv["linkup.reflet"].create({
    kind: "initial",
    state: "confirmed",
    author_id: franceUserId,
    recipient_id: serverState.userId,
    category_id: categoryId,
    you_said: "we could cook together on Sunday",
    understood: "you would like us to cook together",
    channel_id: channelId,
    message_id: messageId,
    holds_turn: true,
    ...values,
  });
  return { pyEnv, channelId };
}

function stepReplies() {
  onRpc("linkup.reflet", "action_answer_action_request", ({ args }) => {
    expect.step(`reply ${args[1]}`);
  });
}

test("a request for action offers three replies, none required", async () => {
  const { channelId } = await setupRequest("action");
  stepReplies();
  await start();
  await openDiscuss(channelId);
  await contains(`${CARD} .o-linkup-ActionRequest`);
  await contains(".o-linkup-ActionRequest-question", {
    text: "A request for action: answer as you wish, or not at all.",
  });
  await contains(".o-linkup-ActionRequest-agree", { text: "Agreed" });
  await contains(".o-linkup-ActionRequest-propose", {
    text: "Let's propose something else",
  });
  await contains(".o-linkup-ActionRequest-notNow", { text: "Not for now" });
  // The usual answers stay: no reply is required.
  await contains(".o-linkup-RefletActions[data-mode='answer']");
  await click(".o-linkup-ActionRequest-notNow");
  await expect.waitForSteps(["reply not_now"]);
  await contains(".o-linkup-ActionRequest", { count: 0 });
  await contains(".o-linkup-ActionRequest-reply[data-reply='not_now']", {
    text: "Answer to the request: Not for now.",
  });
  await contains(".o-mail-Message-body", { text: "Not for now." });
  // No "+N" rises: the reply pays and costs nothing.
  await contains(".o-linkup-PointsBurst", { count: 0 });
});

test("“Let's propose something else” opens the precision", async () => {
  const { channelId } = await setupRequest("action");
  stepReplies();
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-ActionRequest-propose");
  await contains(".o-linkup-RefletActions-form[data-form='precision']");
  await contains(".o-linkup-ActionRequest", { count: 0 });
  expect.verifySteps([]);
});

test("“Agreed” is posted once, then both parties read it", async () => {
  const { channelId } = await setupRequest("action", { holds_turn: false });
  stepReplies();
  await start();
  await openDiscuss(channelId);
  await contains(".o-linkup-ActionRequest-agree");
  // Without the turn, "Let's propose something else" has no form to open.
  await contains(".o-linkup-ActionRequest-propose", { count: 0 });
  await click(".o-linkup-ActionRequest-agree");
  await expect.waitForSteps(["reply agree"]);
  await contains(".o-linkup-ActionRequest-reply[data-reply='agree']", {
    text: "Answer to the request: Agreed.",
  });
  await contains(".o-linkup-ActionRequest-agree", { count: 0 });
});

test("another category, or a reflection not confirmed, asks for nothing", async () => {
  const { channelId } = await setupRequest("emotions");
  await start();
  await openDiscuss(channelId);
  await contains(`${CARD} .o-linkup-RefletActions[data-mode='answer']`);
  await contains(".o-linkup-ActionRequest", { count: 0 });
});

test("a request for action waiting for its confirmation offers no reply yet", async () => {
  const { channelId } = await setupRequest("action", { state: "sent" });
  await start();
  await openDiscuss(channelId);
  await contains(`${CARD} .o-linkup-RefletActions[data-mode='validate']`);
  await contains(".o-linkup-ActionRequest", { count: 0 });
});
