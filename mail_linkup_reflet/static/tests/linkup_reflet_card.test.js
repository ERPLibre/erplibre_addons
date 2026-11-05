import {
  click,
  contains,
  openDiscuss,
  start,
  startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { Command, serverState } from "@web/../tests/web_test_helpers";

import { defineLinkupModels } from "./linkup_test_helpers";

describe.current.tags("desktop");
defineLinkupModels();

/**
 * A chat between the current user and France, with one carrier message
 * holding a reflection of `values`.
 */
async function setupReflet(values = {}) {
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
  const fromFrance = values.fromFrance;
  delete values.fromFrance;
  const messageId = pyEnv["mail.message"].create({
    author_id: fromFrance ? franceId : serverState.partnerId,
    body: "<p>Neutral sentence of the carrier.</p>",
    message_type: "comment",
    model: "discuss.channel",
    res_id: channelId,
  });
  const refletId = pyEnv["linkup.reflet"].create({
    kind: "initial",
    state: "sent",
    author_id: fromFrance ? franceUserId : serverState.userId,
    recipient_id: fromFrance ? serverState.userId : franceUserId,
    category_id: emotions,
    you_said: "the chores and a job wear you out",
    understood: "you are exhausted",
    channel_id: channelId,
    message_id: messageId,
    ...values,
  });
  return { pyEnv, channelId, franceId, franceUserId, refletId };
}

test("a carrier message shows the card of its reflection instead of its body", async () => {
  const { channelId } = await setupReflet();
  await start();
  await openDiscuss(channelId);
  await contains(
    ".o-mail-Message .o-linkup-RefletCard[data-state='sent'][data-role='author']"
  );
  await contains(".o-linkup-RefletCard-title", {
    text: "You told me about your emotions",
  });
  await contains(".o-linkup-RefletCard-badge", { text: "Waiting" });
  await contains(".o-linkup-RefletCard-youSaid", {
    text: "You told me: the chores and a job wear you out",
  });
  await contains(".o-linkup-RefletCard-understood", {
    text: "I understood that: you are exhausted",
  });
  await contains(".o-linkup-RefletCard-footer", {
    text: "Waiting for the confirmation of France",
  });
  await contains(".o-linkup-RefletCard svg[role='img'][aria-label='Emotions']");
  await contains(".o-mail-Message-body", { count: 0 });
  await contains(".o-mail-Message", {
    text: "Neutral sentence of the carrier.",
    count: 0,
  });
});

test("the recipient reads who sent the reflection", async () => {
  const { channelId } = await setupReflet({ fromFrance: true });
  await start();
  await openDiscuss(channelId);
  await contains(".o-linkup-RefletCard[data-role='recipient']");
  await contains(".o-linkup-RefletCard-footer", {
    text: "France sent you a reflection.",
  });
});

test("the badge and the footer follow the state", async () => {
  const { channelId } = await setupReflet({ state: "rejected" });
  await start();
  await openDiscuss(channelId);
  await contains(
    ".o-linkup-RefletCard.o-linkup-RefletCard-isMuted[data-state='rejected']"
  );
  await contains(".o-linkup-RefletCard-badge", { text: "Rejected" });
  await contains(".o-linkup-RefletCard-footer", {
    text: "France said that this exchange did not take place.",
  });
});

test("a withdrawn reflection shows no text", async () => {
  const { channelId } = await setupReflet({ state: "withdrawn" });
  await start();
  await openDiscuss(channelId);
  await contains(".o-linkup-RefletCard-title", {
    text: "Reflection withdrawn",
  });
  await contains(".o-linkup-RefletCard-badge", { text: "Withdrawn" });
  await contains(".o-linkup-RefletCard-youSaid", { count: 0 });
  await contains(".o-linkup-RefletCard-understood", { count: 0 });
});

test("a reply of the chain is named by its kind", async () => {
  const { channelId } = await setupReflet({
    kind: "precision",
    category_id: false,
    guess_state: "pending",
    you_said: false,
    understood: false,
    body_text: "I am looking for someone to move this forward.",
    fromFrance: true,
  });
  await start();
  await openDiscuss(channelId);
  await contains(".o-linkup-RefletCard-title", {
    text: "I would like to clarify…",
  });
  await contains(".o-linkup-RefletCard-badge", { text: "Precision" });
  await contains(
    ".o-linkup-RefletCard svg[role='img'][aria-label='Hidden theme, to guess']"
  );
  await contains(".o-linkup-RefletCard-footer", {
    text: "A theme is hidden in this answer.",
  });
});

test("the card follows the updates of the bus", async () => {
  const { pyEnv, channelId, refletId } = await setupReflet();
  await start();
  await openDiscuss(channelId);
  await contains(".o-linkup-RefletCard-badge", { text: "Waiting" });
  const [partner] = pyEnv["res.partner"].read(serverState.partnerId);
  pyEnv["bus.bus"]._sendone(partner, "mail.record/insert", {
    "linkup.reflet": [{ id: refletId, state: "confirmed" }],
  });
  await contains(
    ".o-linkup-RefletCard[data-state='confirmed'] .o-linkup-RefletCard-badge",
    {
      text: "Confirmed",
    }
  );
  await contains(".o-linkup-RefletCard-footer", { text: "That's a link!" });
});

test("a carrier message can be neither edited nor deleted", async () => {
  const { channelId } = await setupReflet();
  await start();
  await openDiscuss(channelId);
  await contains(".o-linkup-RefletCard");
  await click(".o-mail-Message [title='Expand']");
  await contains(".o-mail-Message-moreMenu");
  await contains(".o-mail-Message-moreMenu [title='Edit']", { count: 0 });
  await contains(".o-mail-Message-moreMenu [title='Delete']", { count: 0 });
  expect(".o-linkup-RefletCard").toHaveCount(1);
});
