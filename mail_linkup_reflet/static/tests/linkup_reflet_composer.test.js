import {
  click,
  contains,
  insertText,
  openDiscuss,
  start,
  startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { queryAllAttributes } from "@odoo/hoot-dom";
import {
  Command,
  makeServerError,
  onRpc,
  serverState,
} from "@web/../tests/web_test_helpers";

import { defineLinkupModels } from "./linkup_test_helpers";

describe.current.tags("desktop");
defineLinkupModels();

/** A chat between the current user and France, a LinkUp member. */
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
  return { pyEnv, channelId, franceId, franceUserId };
}

test("the Help bar shows the reduced bar in its order, then every category", async () => {
  const { channelId } = await setupChat();
  await start();
  await openDiscuss(channelId);
  await contains(
    ".o-linkup-HelpBar[aria-label='HELP — What did France tell you about?']"
  );
  await contains(".o-linkup-HelpBar-category", { count: 7 });
  expect(queryAllAttributes(".o-linkup-HelpBar-category", "data-code")).toEqual(
    [
      "observation",
      "emotions",
      "needs",
      "team",
      "go_speak",
      "goals",
      "vulnerability",
    ]
  );
  await contains(
    ".o-linkup-HelpBar-category[aria-label='Write a reflection: Team'][title='Team']"
  );
  // The tooltip gives the short definition of the category.
  await contains(
    ".o-linkup-HelpBar-category[data-code='emotions'][title='Emotions — What a person feels.']"
  );
  await click(".o-linkup-HelpBar-toggle[aria-expanded='false']");
  await contains(".o-linkup-HelpBar-category", { count: 12 });
  await contains(".o-linkup-HelpBar-toggle[aria-expanded='true']");
  expect(
    queryAllAttributes(".o-linkup-HelpBar-category", "data-code").slice(0, 5)
  ).toEqual(["observation", "emotions", "needs", "action", "inhibition"]);
});

test("another category changes the title of the form and keeps the texts", async () => {
  const { channelId } = await setupChat();
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-HelpBar-category[data-code='vulnerability']");
  await contains(".o-linkup-RefletForm-title", {
    text: "You told me about your vulnerability",
  });
  await insertText(".o-linkup-RefletForm-youSaid", "the chores wear you out");
  await insertText(".o-linkup-RefletForm-understood", "you are exhausted");
  await click(".o-linkup-HelpBar-category[data-code='emotions']");
  await contains(".o-linkup-RefletForm-title", {
    text: "You told me about your emotions",
  });
  await contains(
    ".o-linkup-HelpBar-category[data-code='emotions'][aria-pressed='true']"
  );
  await contains(".o-linkup-RefletForm-youSaid", {
    value: "the chores wear you out",
  });
  await contains(".o-linkup-RefletForm-understood", {
    value: "you are exhausted",
  });
});

test("sending checks the form, then saves and sends the draft to the other member", async () => {
  const { channelId, franceUserId } = await setupChat();
  onRpc("linkup.reflet", "action_send", ({ args }) => {
    expect.step(`action_send ${args[1]}`);
  });
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-HelpBar-category[data-code='emotions']");
  await click(".o-linkup-RefletForm-send");
  await contains(".o-linkup-RefletForm-error[role='alert']", {
    text: "Fill in “You told me”.",
  });
  await insertText(".o-linkup-RefletForm-youSaid", "the chores wear you out");
  await insertText(".o-linkup-RefletForm-understood", "you are exhausted");
  await click(".o-linkup-RefletForm-previewButton");
  await contains(
    ".o-linkup-RefletForm-preview .o-linkup-RefletCard[data-state='draft']",
    {
      text: "You told me about your emotions",
    }
  );
  await click(".o-linkup-RefletForm-send");
  await contains(".o-linkup-RefletForm-error", {
    text: "Confirm that this exchange took place in person.",
  });
  expect.verifySteps([]);
  await click(".o-linkup-RefletForm-realWorld input[type='checkbox']");
  await click(".o-linkup-RefletForm-send");
  await expect.waitForSteps([`action_send ${franceUserId}`]);
  await contains(".o-linkup-RefletComposer-notice[role='status']", {
    text: "Reflection sent to France.",
  });
  await contains(".o-linkup-RefletForm", { count: 0 });
  await contains(
    ".o-mail-Message .o-linkup-RefletCard[data-state='sent'][data-role='author']"
  );
  await contains(".o-mail-Message .o-linkup-RefletCard-badge", {
    text: "Waiting",
  });
  await contains(".o-mail-Message .o-linkup-RefletCard-understood", {
    text: "I understood that: you are exhausted",
  });
});

test("a refused sending shows the message of its code", async () => {
  const { channelId } = await setupChat();
  onRpc("linkup.reflet", "action_send", () => {
    throw makeServerError({
      message: "This reflection cannot be sent.",
      context: { linkup_code: "linkup.unavailable" },
    });
  });
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-HelpBar-category[data-code='needs']");
  await insertText(".o-linkup-RefletForm-youSaid", "you need rest");
  await insertText(".o-linkup-RefletForm-understood", "you are tired");
  await click(".o-linkup-RefletForm-realWorld input[type='checkbox']");
  await click(".o-linkup-RefletForm-send");
  await contains(".o-linkup-RefletForm-error[data-code='linkup.unavailable']", {
    text: "Sending is not possible.",
  });
  await contains(".o-linkup-RefletForm");
});

test("a validation refusal of the server names the field", async () => {
  const { channelId } = await setupChat();
  onRpc("linkup.reflet", "action_send", () => {
    throw makeServerError({
      context: { linkup_code: "linkup.validation", linkup_field: "understood" },
    });
  });
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-HelpBar-category[data-code='needs']");
  await insertText(".o-linkup-RefletForm-youSaid", "you need rest");
  await insertText(".o-linkup-RefletForm-understood", "you are tired");
  await click(".o-linkup-RefletForm-realWorld input[type='checkbox']");
  await click(".o-linkup-RefletForm-send");
  await contains(".o-linkup-RefletForm-error", {
    text: "Fill in “I understood that”.",
  });
});

test("the draft is restored, and Cancel deletes it", async () => {
  const { pyEnv, channelId } = await setupChat();
  const [goals] = pyEnv["linkup.category"].search([["code", "=", "goals"]]);
  const draftId = pyEnv["linkup.reflet"].create({
    kind: "initial",
    state: "draft",
    author_id: serverState.userId,
    category_id: goals,
    you_said: "a draft kept by the server",
  });
  onRpc("linkup.reflet", "action_discard_draft", ({ args }) => {
    expect.step(`discard ${args[0]}`);
  });
  await start();
  await openDiscuss(channelId);
  await contains(".o-linkup-RefletForm-title", {
    text: "You told me about your goal",
  });
  await contains(".o-linkup-RefletForm-youSaid", {
    value: "a draft kept by the server",
  });
  await click(".o-linkup-RefletForm-cancel");
  await expect.waitForSteps([`discard ${draftId}`]);
  await contains(".o-linkup-RefletForm", { count: 0 });
  expect(pyEnv["linkup.reflet"].search([["id", "=", draftId]])).toEqual([]);
});

test("the Reflection button shows and hides the Help bar", async () => {
  const { channelId } = await setupChat();
  await start();
  await openDiscuss(channelId);
  await contains(".o-linkup-HelpBar");
  await click(".o-linkup-Composer-refletButton[aria-pressed='true']");
  await contains(".o-linkup-HelpBar", { count: 0 });
  await contains(".o-linkup-Composer-refletButton[aria-pressed='false']");
  await click(".o-linkup-Composer-refletButton");
  await contains(".o-linkup-HelpBar");
});

test("a group conversation keeps the plain composer", async () => {
  const pyEnv = await startServer();
  const channelId = pyEnv["discuss.channel"].create({
    name: "Workshop",
    channel_type: "channel",
  });
  await start();
  await openDiscuss(channelId);
  await contains(".o-mail-Composer-input");
  await contains(".o-linkup-Composer-refletButton", { count: 0 });
  await contains(".o-linkup-HelpBar", { count: 0 });
  await contains(".o-mail-Discuss-header button[name='linkup-panel']", {
    count: 0,
  });
});

test("a user outside LinkUp keeps the plain composer", async () => {
  const { pyEnv, channelId } = await setupChat();
  pyEnv["res.users"].write([serverState.userId], { linkup_is_member: false });
  await start();
  await openDiscuss(channelId);
  await contains(".o-mail-Composer-input");
  await contains(".o-linkup-Composer-refletButton", { count: 0 });
  await contains(".o-linkup-HelpBar", { count: 0 });
  await contains(".o-mail-Discuss-header button[name='linkup-panel']", {
    count: 0,
  });
});

test("the draft is read again when the window takes the focus back", async () => {
  const { pyEnv, channelId } = await setupChat();
  const [goals] = pyEnv["linkup.category"].search([["code", "=", "goals"]]);
  const draftId = pyEnv["linkup.reflet"].create({
    kind: "initial",
    state: "draft",
    author_id: serverState.userId,
    category_id: goals,
    you_said: "a draft kept by the server",
  });
  await start();
  await openDiscuss(channelId);
  await contains(".o-linkup-RefletForm-youSaid", {
    value: "a draft kept by the server",
  });
  // Another tab saves the draft, then sends it.
  pyEnv["linkup.reflet"].write([draftId], { you_said: "saved in another tab" });
  window.dispatchEvent(new FocusEvent("focus"));
  await contains(".o-linkup-RefletForm-youSaid", {
    value: "saved in another tab",
  });
  pyEnv["linkup.reflet"].write([draftId], { state: "sent" });
  window.dispatchEvent(new FocusEvent("focus"));
  await contains(".o-linkup-RefletForm", { count: 0 });
});

test("a text refused as too long gives the limit, not a missing field", async () => {
  const { channelId } = await setupChat();
  onRpc("linkup.reflet", "action_send", () => {
    throw makeServerError({
      context: {
        linkup_code: "linkup.validation",
        linkup_field: "understood",
        linkup_limit: 1000,
      },
    });
  });
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-HelpBar-category[data-code='needs']");
  await insertText(".o-linkup-RefletForm-youSaid", "you need rest");
  await insertText(".o-linkup-RefletForm-understood", "you are tired");
  await click(".o-linkup-RefletForm-realWorld input[type='checkbox']");
  await click(".o-linkup-RefletForm-send");
  await contains(".o-linkup-RefletForm-error[data-code='linkup.validation']", {
    text: "This text holds at most 1000 characters.",
  });
});
