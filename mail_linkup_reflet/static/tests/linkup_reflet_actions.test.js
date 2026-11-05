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
  animationFrame,
  press,
  queryAllTexts,
  queryFirst,
} from "@odoo/hoot-dom";
import {
  Command,
  getService,
  makeServerError,
  onRpc,
  serverState,
} from "@web/../tests/web_test_helpers";

import { defineLinkupModels, mockLinkupReading } from "./linkup_test_helpers";

describe.current.tags("desktop");
defineLinkupModels();

/**
 * A chat between the current user and France, with one carrier message
 * holding a reflection of `values`. With `fromFrance`, France wrote it and
 * the current user received it.
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
  const category = (code) =>
    pyEnv["linkup.category"].search([["code", "=", code]])[0];
  const { fromFrance, ...fields } = values;
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
    category_id: category("emotions"),
    you_said: "the chores and a job wear you out",
    understood: "you are exhausted",
    channel_id: channelId,
    message_id: messageId,
    ...fields,
  });
  return { pyEnv, channelId, franceUserId, refletId, category };
}

/**
 * Record the calls of the reflection actions as steps. The reading that a
 * drawn card records (`action_mark_read`) is left out unless `withRead`.
 */
function stepActions({ withRead = false } = {}) {
  onRpc("linkup.reflet", "*", ({ method, args }) => {
    if (
      method.startsWith("action_") &&
      (withRead || method !== "action_mark_read")
    ) {
      expect.step(`${method} ${JSON.stringify(args.slice(1))}`);
    }
  });
}

const CARD = ".o-mail-Message .o-linkup-RefletCard";

test("the recipient of a sent reflection confirms it with a button", async () => {
  const { channelId } = await setupReflet({ fromFrance: true });
  stepActions();
  await start();
  await openDiscuss(channelId);
  await contains(
    `${CARD}[data-role='recipient'] .o-linkup-RefletActions[data-mode='validate']`
  );
  await contains(".o-linkup-RefletActions-question", {
    text: "Did this exchange really take place?",
  });
  await contains(
    ".o-linkup-RefletActions-confirm[aria-keyshortcuts='ArrowRight']"
  );
  await contains(
    ".o-linkup-RefletActions-reject[aria-keyshortcuts='ArrowLeft']"
  );
  await contains(".o-linkup-RefletActions-inaccurate");
  await contains(".o-linkup-RefletActions-ignore");
  // Lot 1 shows no points.
  expect(queryAllTexts(".o-linkup-RefletCard").join(" ")).not.toMatch(
    /\+\s?\d/
  );
  await click(".o-linkup-RefletActions-confirm");
  await expect.waitForSteps(["action_confirm []"]);
  await contains(
    `${CARD}[data-state='confirmed'] .o-linkup-RefletCard-footer`,
    { text: "That's a link!" }
  );
  await contains(".o-linkup-RefletActions[data-mode='answer']");
  await contains(".o-linkup-RefletActions-question", {
    text: "Did France understand you well?",
  });
});

test("the author of a sent reflection read by its recipient has no action on it", async () => {
  const { channelId } = await setupReflet({ read_date: "2026-01-01 10:00:00" });
  await start();
  await openDiscuss(channelId);
  await contains(`${CARD}[data-role='author'][data-state='sent']`);
  await contains(".o-linkup-RefletActions", { count: 0 });
  expect(`${CARD}`).not.toHaveAttribute("tabindex");
});

test("the author withdraws a reflection not read yet, after a confirmation", async () => {
  const { channelId } = await setupReflet();
  stepActions();
  await start();
  await openDiscuss(channelId);
  await contains(
    ".o-linkup-RefletActions[data-mode='withdraw'] .o-linkup-RefletActions-hint",
    { text: "Possible as long as France has not read it." }
  );
  expect(`${CARD}`).not.toHaveAttribute("tabindex");
  await click(".o-linkup-RefletActions-withdraw");
  await contains(".modal-body", {
    text: "Withdraw this reflection? France will no longer see its content.",
  });
  await click(".o-linkup-WithdrawDialog-confirm");
  await expect.waitForSteps(["action_withdraw []"]);
  await contains(
    `${CARD}[data-state='withdrawn'] .o-linkup-RefletCard-footer`,
    {
      text: "You withdrew this reflection.",
    }
  );
  await contains(".o-linkup-RefletActions", { count: 0 });
});

test("→ on the focused card confirms it", async () => {
  const { channelId } = await setupReflet({ fromFrance: true });
  stepActions();
  await start();
  await openDiscuss(channelId);
  await contains(
    `${CARD}[tabindex='0'][aria-keyshortcuts='ArrowRight ArrowLeft']`
  );
  queryFirst(CARD).focus();
  await press("ArrowRight");
  await expect.waitForSteps(["action_confirm []"]);
  await contains(`${CARD}[data-state='confirmed']`);
  await contains(`${CARD}[tabindex]`, { count: 0 });
});

test("← on the focused card rejects it after a confirmation", async () => {
  const { channelId } = await setupReflet({ fromFrance: true });
  stepActions();
  await start();
  await openDiscuss(channelId);
  await contains(`${CARD}[tabindex='0']`);
  queryFirst(CARD).focus();
  await press("ArrowLeft");
  await contains(".modal .modal-title", {
    text: "This exchange did not take place",
  });
  await click(".modal-footer .btn-secondary", { text: "Cancel" });
  await contains(".modal", { count: 0 });
  expect.verifySteps([]);
  await contains(`${CARD}[data-state='sent']`);
  await click(".o-linkup-RefletActions-reject");
  await click(".modal-footer .o-linkup-RejectDialog-confirm");
  await expect.waitForSteps(["action_reject []"]);
  await contains(`${CARD}[data-state='rejected'] .o-linkup-RefletCard-footer`, {
    text: "You said that this exchange did not take place.",
  });
  await contains(".o-linkup-RefletActions", { count: 0 });
});

test("ignoring folds the card for its recipient", async () => {
  const { channelId } = await setupReflet({ fromFrance: true });
  stepActions();
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-RefletActions-ignore");
  await expect.waitForSteps(["action_ignore []"]);
  await contains(
    `${CARD}.o-linkup-RefletCard-isMuted[data-state='sent'] .o-linkup-RefletCard-badge`,
    {
      text: "Set aside",
    }
  );
  await contains(".o-linkup-RefletCard-footer", {
    text: "You set this reflection aside; France is not told.",
  });
  await contains(".o-linkup-RefletCard-understood", { count: 0 });
  await contains(".o-linkup-RefletActions", { count: 0 });
});

test("“That is not what I said” sends an optional correction; Escape closes it", async () => {
  const { channelId } = await setupReflet({ fromFrance: true });
  stepActions();
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-RefletActions-inaccurate");
  await contains(
    ".o-linkup-RefletActions-form[data-form='inaccurate'] .o-linkup-RefletActions-formTitle",
    {
      text: "The exchange took place, but that is not what I said",
    }
  );
  await press("Escape");
  await contains(".o-linkup-RefletActions-form", { count: 0 });
  await click(".o-linkup-RefletActions-inaccurate");
  await insertText(".o-linkup-RefletActions-text", "I spoke about the garden");
  await click(".o-linkup-RefletActions-send", { text: "Send to France" });
  await expect.waitForSteps([
    `action_mark_inaccurate ["I spoke about the garden"]`,
  ]);
  await contains(
    `${CARD}[data-state='inaccurate'] .o-linkup-RefletCard-bodyText`,
    {
      text: "Correction: I spoke about the garden",
    }
  );
  await contains(".o-linkup-RefletActions", { count: 0 });
});

test("the exact answer posts a reply, its text being optional", async () => {
  const { channelId } = await setupReflet({
    fromFrance: true,
    state: "confirmed",
    holds_turn: true,
  });
  stepActions();
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-RefletActions-exact");
  await contains(".o-linkup-RefletActions-form[data-form='exact']");
  await click(".o-linkup-RefletActions-send");
  await expect.waitForSteps(["action_answer_exact [null]"]);
  await contains(
    `${CARD}[data-kind='answer_exact'][data-role='author'] .o-linkup-RefletCard-title`,
    {
      text: "Yes, that's exactly it!",
    }
  );
  await contains(".o-linkup-RefletActions", { count: 0 });
});

test("a precision starts empty, and its themes never fill the text", async () => {
  const { channelId, category } = await setupReflet({
    fromFrance: true,
    state: "confirmed",
    holds_turn: true,
  });
  stepActions();
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-RefletActions-precise");
  await contains(
    ".o-linkup-RefletActions-form[data-form='precision'] .o-linkup-RefletActions-text",
    { value: "" }
  );
  await contains(".o-linkup-CategoryPicker-option", { count: 12 });
  await click(".o-linkup-CategoryPicker-option[data-code='goals']");
  await contains(
    ".o-linkup-CategoryPicker-option[data-code='goals'][aria-pressed='true']"
  );
  await contains(
    ".o-linkup-CategoryPicker-option[aria-label='Goals, main theme']"
  );
  await contains(".o-linkup-RefletActions-text", { value: "" });
  await click(".o-linkup-CategoryPicker-option[data-code='emotions']");
  // Two themes at most: the others are unavailable until one is removed.
  await contains(
    ".o-linkup-CategoryPicker-option[data-code='needs'][aria-disabled='true']"
  );
  await click(".o-linkup-CategoryPicker-option[data-code='needs']");
  await contains(
    ".o-linkup-CategoryPicker-option[data-code='needs'][aria-pressed='false']"
  );
  await click(".o-linkup-RefletActions-send");
  await contains(".o-linkup-RefletActions-error[role='alert']", {
    text: "Write your text.",
  });
  expect.verifySteps([]);
  await insertText(
    ".o-linkup-RefletActions-text",
    "My goal is to find someone"
  );
  await click(".o-linkup-RefletActions-send");
  await expect.waitForSteps([
    `action_answer_precision ["My goal is to find someone",[${category(
      "goals"
    )},${category("emotions")}]]`,
  ]);
  await contains(
    `${CARD}[data-kind='precision'][data-role='author'] .o-linkup-RefletCard-footer`,
    {
      text: "Hidden theme: Goals, Emotions",
    }
  );
});

test("the recipient of a precision never receives its hidden theme before guessing", async () => {
  const { channelId, category, pyEnv } = await setupReflet({
    fromFrance: true,
  });
  const [france] = pyEnv["res.users"].search([["name", "=", "France"]]);
  const precisionId = pyEnv["linkup.reflet"].create({
    kind: "precision",
    state: "sent",
    author_id: france,
    recipient_id: serverState.userId,
    category_id: false,
    you_said: false,
    understood: false,
    body_text: "I am looking for someone to move this forward.",
    guess_state: "pending",
    hidden_category_ids: [category("goals")],
    holds_turn: true,
    channel_id: channelId,
    message_id: pyEnv["mail.message"].create({
      author_id: pyEnv["res.partner"].search([["name", "=", "France"]])[0],
      body: "<p>France clarified their thought.</p>",
      message_type: "comment",
      model: "discuss.channel",
      res_id: channelId,
    }),
  });
  stepActions();
  await start();
  await openDiscuss(channelId);
  const precision = `${CARD}[data-kind='precision']`;
  await contains(
    `${precision}[data-guess-state='pending'] svg[aria-label='Hidden theme, to guess']`
  );
  const record = getService("mail.store")["linkup.reflet"].get(precisionId);
  expect(record.revealed_category_ids.length).toBe(0);
  expect(record.primary_category_id).toBe(undefined);
  await contains(
    `${precision} .o-linkup-RefletActions[data-mode='guess'] .o-linkup-RefletActions-question`,
    {
      text: "France hid a theme in this answer. Which one?",
    }
  );
  await contains(".o-linkup-RefletActions-guess:disabled");
  await click(
    `${precision} .o-linkup-CategoryPicker-option[data-code='needs']`
  );
  await click(".o-linkup-RefletActions-guess:enabled");
  await expect.waitForSteps([`action_guess [${category("needs")}]`]);
  await contains(
    `${precision}[data-guess-state='missed'] .o-linkup-RefletCard-footer`,
    {
      text: "Theme missed: Goals",
    }
  );
  await contains(`${precision} svg[aria-label='Goals']`);
  // The single guess made, the options follow.
  await contains(`${precision} .o-linkup-RefletActions[data-mode='options']`);
});

test("a hidden theme found is revealed as found", async () => {
  const { channelId, category, pyEnv, refletId } = await setupReflet({
    fromFrance: true,
  });
  pyEnv["linkup.reflet"].write([refletId], {
    kind: "precision",
    category_id: false,
    guess_state: "pending",
    hidden_category_ids: [category("goals"), category("emotions")],
    body_text: "A clarification.",
  });
  stepActions();
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-CategoryPicker-option[data-code='emotions']");
  await click(".o-linkup-RefletActions-guess");
  await expect.waitForSteps([`action_guess [${category("emotions")}]`]);
  await contains(
    `${CARD}[data-guess-state='found'] .o-linkup-RefletCard-footer`,
    {
      text: "Theme found: Goals, Emotions",
    }
  );
});

test("the three options show only to the member whose turn it is", async () => {
  const { channelId, pyEnv, refletId } = await setupReflet({
    fromFrance: true,
    kind: "answer_exact",
    category_id: false,
    you_said: false,
    understood: false,
    holds_turn: false,
  });
  await start();
  await openDiscuss(channelId);
  await contains(`${CARD}[data-kind='answer_exact']`);
  await contains(".o-linkup-RefletActions", { count: 0 });
  pyEnv["linkup.reflet"].write([refletId], { holds_turn: true });
  const [partner] = pyEnv["res.partner"].read(serverState.partnerId);
  pyEnv["bus.bus"]._sendone(partner, "mail.record/insert", {
    "linkup.reflet": [{ id: refletId, holds_turn: true }],
  });
  await contains(".o-linkup-RefletActions[data-mode='options']");
  await contains(".o-linkup-RefletActions-question", { text: "And now?" });
  await contains(".o-linkup-RefletActions-continue", {
    text: "Continue the reflection",
  });
  await contains(".o-linkup-RefletActions-self", {
    text: "Talk about yourself",
  });
  await contains(".o-linkup-RefletActions-end", { text: "End it here" });
});

test("the author of the last reply does not get the options", async () => {
  const { channelId } = await setupReflet({
    kind: "answer_exact",
    category_id: false,
    you_said: false,
    understood: false,
    holds_turn: true,
  });
  await start();
  await openDiscuss(channelId);
  await contains(`${CARD}[data-kind='answer_exact'][data-role='author']`);
  await contains(".o-linkup-RefletActions", { count: 0 });
});

test("continuing the reflection inserts the reformulation starter", async () => {
  const { channelId, category } = await setupReflet({
    fromFrance: true,
    kind: "answer_exact",
    category_id: false,
    you_said: false,
    understood: false,
    holds_turn: true,
  });
  stepActions();
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-RefletActions-continue");
  await contains(".o-linkup-RefletActions-formTitle", {
    text: "So if I understand correctly…",
  });
  await click(".o-linkup-CategoryPicker-option[data-code='action']");
  await contains(".o-linkup-RefletActions-text", {
    value: "Your action request is that: ",
  });
  await insertText(".o-linkup-RefletActions-text", "you look for help");
  await click(".o-linkup-CategoryPicker-option[data-code='needs']");
  await contains(".o-linkup-RefletActions-text", {
    value: "You need: you look for help",
  });
  await click(".o-linkup-RefletActions-send");
  await expect.waitForSteps([
    `action_continue [${category("needs")},"You need: you look for help"]`,
  ]);
  await contains(
    `${CARD}[data-kind='continue'][data-role='author'] .o-linkup-RefletCard-title`,
    {
      text: "So if I understand correctly…",
    }
  );
  await contains(`${CARD}[data-kind='continue'] svg[aria-label='Needs']`);
});

test("talking about oneself offers the call first, then the first-person starter", async () => {
  const { channelId, category } = await setupReflet({
    fromFrance: true,
    kind: "answer_exact",
    category_id: false,
    you_said: false,
    understood: false,
    holds_turn: true,
  });
  stepActions();
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-RefletActions-self");
  await contains(".o-linkup-RefletActions-formTitle", {
    text: "I would like to tell you about something that matters to me.",
  });
  await contains(".o-linkup-RefletActions-call", { text: "Call France" });
  await contains(".o-linkup-RefletActions-video", {
    text: "Video call with France",
  });
  await click(".o-linkup-CategoryPicker-option[data-code='needs']");
  await contains(".o-linkup-RefletActions-text", { value: "I need: " });
  await insertText(".o-linkup-RefletActions-text", "more focus");
  await click(".o-linkup-RefletActions-send");
  await expect.waitForSteps([
    `action_self_disclosure [${category("needs")},"I need: more focus"]`,
  ]);
  await contains(`${CARD}[data-kind='self_disclosure'][data-role='author']`);
});

test("ending it here sends the closing sentence of each reader's language", async () => {
  const { channelId } = await setupReflet({
    fromFrance: true,
    kind: "answer_exact",
    category_id: false,
    you_said: false,
    understood: false,
    holds_turn: true,
  });
  stepActions();
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-RefletActions-end");
  await contains(".o-linkup-RefletActions-text", {
    value: "Thank you for our discussion.",
  });
  await click(".o-linkup-RefletActions-send");
  await expect.waitForSteps(["action_close [null]"]);
  await contains(`${CARD}[data-kind='close'] .o-linkup-RefletCard-title`, {
    text: "Thank you for our discussion.",
  });
  await contains(".o-linkup-RefletActions", { count: 0 });
});

test("a disclosure invites its recipient to reformulate it", async () => {
  const { channelId, category } = await setupReflet({
    fromFrance: true,
    kind: "self_disclosure",
    you_said: false,
    understood: false,
    body_text: "I need: more focus",
    holds_turn: true,
  });
  stepActions();
  await start();
  await openDiscuss(channelId);
  await contains(".o-linkup-RefletActions[data-mode='rephrase']");
  await click(".o-linkup-RefletActions-rephrase", {
    text: "Write a reflection",
  });
  await contains(
    ".o-linkup-CategoryPicker-option[data-code='emotions'][aria-pressed='true']"
  );
  await contains(".o-linkup-RefletActions-text", { value: "You feel: " });
  await insertText(".o-linkup-RefletActions-text", "short of focus");
  await click(".o-linkup-RefletActions-send");
  await expect.waitForSteps([
    `action_continue [${category("emotions")},"You feel: short of focus"]`,
  ]);
});

test("a refused action shows the message of its code", async () => {
  const { channelId } = await setupReflet({ fromFrance: true });
  onRpc("linkup.reflet", "action_confirm", () => {
    throw makeServerError({
      message: "This reflection has already been answered.",
      context: { linkup_code: "linkup.already_answered" },
    });
  });
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-RefletActions-confirm");
  await contains(
    ".o-linkup-RefletActions-error[role='alert'][data-code='linkup.already_answered']",
    {
      text: "This reflection has already been answered.",
    }
  );
});

test("the card of a received reflection records its reading once", async () => {
  const { channelId } = await setupReflet({ fromFrance: true });
  mockLinkupReading();
  stepActions({ withRead: true });
  await start();
  await openDiscuss(channelId);
  await contains(`${CARD}[data-role='recipient'][data-state='sent']`);
  await expect.waitForSteps(["action_mark_read []"]);
  await click(".o-linkup-RefletActions-confirm");
  await expect.waitForSteps(["action_confirm []"]);
});

test("a card already read, or seen by its author, records no reading", async () => {
  const { channelId, pyEnv, franceUserId } = await setupReflet({
    fromFrance: true,
    read_date: "2026-01-01 10:00:00",
  });
  pyEnv["linkup.reflet"].create({
    kind: "initial",
    state: "sent",
    author_id: serverState.userId,
    recipient_id: franceUserId,
    channel_id: channelId,
    you_said: "the garden",
    understood: "you need calm",
    message_id: pyEnv["mail.message"].create({
      author_id: serverState.partnerId,
      body: "<p>Neutral sentence of the carrier.</p>",
      message_type: "comment",
      model: "discuss.channel",
      res_id: channelId,
    }),
  });
  mockLinkupReading();
  stepActions({ withRead: true });
  await start();
  await openDiscuss(channelId);
  await contains(CARD, { count: 2 });
  await contains(`${CARD}[data-role='author']`);
  await animationFrame();
  expect.verifySteps([]);
});

test("a card drawn in a hidden tab records its reading once the tab is visible", async () => {
  const { channelId } = await setupReflet({ fromFrance: true });
  const reading = mockLinkupReading({ visible: false });
  stepActions({ withRead: true });
  await start();
  await openDiscuss(channelId);
  await contains(`${CARD}[data-role='recipient'][data-state='sent']`);
  await animationFrame();
  reading.setVisible(false);
  await animationFrame();
  expect.verifySteps([]);
  reading.setVisible(true);
  await expect.waitForSteps(["action_mark_read []"]);
  reading.setVisible(false);
  reading.setVisible(true);
  reading.setOnScreen(true);
  await animationFrame();
  expect.verifySteps([]);
});

test("a card off the screen records its reading once it is on the screen", async () => {
  const { channelId } = await setupReflet({ fromFrance: true });
  const reading = mockLinkupReading({ onScreen: false });
  stepActions({ withRead: true });
  await start();
  await openDiscuss(channelId);
  await contains(`${CARD}[data-role='recipient'][data-state='sent']`);
  reading.setVisible(true);
  await animationFrame();
  expect.verifySteps([]);
  reading.setOnScreen(true);
  await expect.waitForSteps(["action_mark_read []"]);
  reading.setOnScreen(false);
  reading.setOnScreen(true);
  await animationFrame();
  expect.verifySteps([]);
});

test("an arrow pressed on a button of the card neither confirms nor rejects", async () => {
  const { channelId } = await setupReflet({ fromFrance: true });
  stepActions();
  await start();
  await openDiscuss(channelId);
  await contains(`${CARD}[tabindex='0']`);
  queryFirst(".o-linkup-RefletActions-ignore").focus();
  await press("ArrowRight");
  await press("ArrowLeft");
  await animationFrame();
  await contains(".modal", { count: 0 });
  expect.verifySteps([]);
  await contains(`${CARD}[data-state='sent']`);
});
