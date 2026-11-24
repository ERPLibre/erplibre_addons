import {
  click,
  contains,
  insertText,
  openDiscuss,
  start,
  startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-dom";
import { Command, onRpc, serverState } from "@web/../tests/web_test_helpers";

import { defineLinkupModels } from "./linkup_test_helpers";

describe.current.tags("desktop");
defineLinkupModels();

/**
 * A chat between the current user and France under the start rule `mode`,
 * not yet opened by a confirmed reflection. With `chatWindow`, the chat is
 * open in a chat window.
 */
async function setupChat(mode, { chatWindow = false } = {}) {
  const pyEnv = await startServer();
  const franceId = pyEnv["res.partner"].create({ name: "France" });
  const franceUserId = pyEnv["res.users"].create({
    name: "France",
    partner_id: franceId,
  });
  const channelId = pyEnv["discuss.channel"].create({
    channel_member_ids: [
      Command.create({
        partner_id: serverState.partnerId,
        fold_state: chatWindow ? "open" : "closed",
      }),
      Command.create({ partner_id: franceId }),
    ],
    channel_type: "chat",
    linkup_start_rule: mode,
    linkup_start_rule_satisfied: false,
  });
  return { pyEnv, channelId, franceId, franceUserId };
}

const BANNER = ".o-linkup-StartRule";

test("strict: the banner replaces the text field in Discuss", async () => {
  const { channelId } = await setupChat("strict");
  onRpc("/mail/message/post", () => expect.step("post"));
  await start();
  await openDiscuss(channelId);
  await contains(`${BANNER}[data-mode='strict'][role='status']`);
  await contains(`${BANNER} .o-linkup-StartRule-title`, {
    text: "This conversation starts with a reflection",
  });
  await contains(`${BANNER} .o-linkup-StartRule-text`, {
    text: "Reflect an exchange you had in person. Free text opens once a reflection is confirmed.",
  });
  await contains(".o-mail-Composer-input", { visible: false });
  await contains(".o-linkup-HelpBar");
  expect.verifySteps([]);
});

test("strict: the banner replaces the text field in a chat window", async () => {
  await setupChat("strict", { chatWindow: true });
  await start();
  await contains(".o-mail-ChatWindow");
  await contains(`.o-mail-ChatWindow ${BANNER}[data-mode='strict']`);
  await contains(".o-mail-ChatWindow .o-mail-Composer-input", {
    visible: false,
  });
  await contains(".o-mail-ChatWindow .o-linkup-StartRule-reflet", {
    text: "Make a reflection",
  });
});

test("strict: Make a reflection opens the Help bar and gives it the focus", async () => {
  const { channelId } = await setupChat("strict");
  await start();
  await openDiscuss(channelId);
  await contains(".o-linkup-HelpBar");
  await click(".o-linkup-StartRule-reflet");
  await contains(".o-linkup-HelpBar");
  await animationFrame();
  expect(document.activeElement).toHaveClass("o-linkup-HelpBar-category");
});

test("strict: a confirmed reflection gives the text field back", async () => {
  const { channelId, pyEnv, franceId, franceUserId } = await setupChat(
    "strict"
  );
  const [emotions] = pyEnv["linkup.category"].search([
    ["code", "=", "emotions"],
  ]);
  pyEnv["linkup.reflet"].create({
    kind: "initial",
    state: "sent",
    author_id: franceUserId,
    recipient_id: serverState.userId,
    category_id: emotions,
    you_said: "the garden",
    understood: "you need calm",
    channel_id: channelId,
    read_date: "2026-01-01 10:00:00",
    message_id: pyEnv["mail.message"].create({
      author_id: franceId,
      body: "<p>Neutral sentence of the carrier.</p>",
      message_type: "comment",
      model: "discuss.channel",
      res_id: channelId,
    }),
  });
  await start();
  await openDiscuss(channelId);
  await contains(BANNER);
  await click(".o-linkup-RefletActions-confirm");
  await contains(BANNER, { count: 0 });
  await contains(".o-mail-Composer-input", { visible: true });
  await insertText(".o-mail-Composer-input", "Bonjour France");
  await contains(".o-mail-Composer-send:enabled");
});

test("incentive: the banner sits above a composer that stays usable", async () => {
  const { channelId } = await setupChat("incitative");
  await start();
  await openDiscuss(channelId);
  await contains(`${BANNER}[data-mode='incitative']`);
  await contains(`${BANNER} .o-linkup-StartRule-title`, {
    text: "Start with a reflection of a real exchange",
  });
  await contains(".o-linkup-StartRule-reflet", { text: "Make a reflection" });
  await insertText(".o-mail-Composer-input", "Bonjour");
  await click(".o-mail-Composer-send:enabled");
  await contains(".o-mail-Message", { text: "Bonjour" });
  await contains(BANNER);
});

test("a satisfied rule, or none, shows no banner", async () => {
  const { channelId, pyEnv } = await setupChat("strict");
  pyEnv["discuss.channel"].write([channelId], {
    linkup_start_rule_satisfied: true,
  });
  await start();
  await openDiscuss(channelId);
  await contains(".o-mail-Composer-input", { visible: true });
  await contains(BANNER, { count: 0 });
});

test("a group under strict mode shows the banner without the reflection", async () => {
  const pyEnv = await startServer();
  const franceId = pyEnv["res.partner"].create({ name: "France" });
  const channelId = pyEnv["discuss.channel"].create({
    name: "Atelier",
    channel_member_ids: [
      Command.create({ partner_id: serverState.partnerId }),
      Command.create({ partner_id: franceId }),
    ],
    channel_type: "group",
    linkup_start_rule: "strict",
    linkup_start_rule_satisfied: false,
  });
  await start();
  await openDiscuss(channelId);
  await contains(`${BANNER}[data-mode='strict']`);
  await contains(".o-linkup-StartRule-reflet", { count: 0 });
  await contains(".o-mail-Composer-input", { visible: false });
});
