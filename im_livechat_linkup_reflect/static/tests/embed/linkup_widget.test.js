import {
  defineLivechatModels,
  loadDefaultEmbedConfig,
} from "@im_livechat/../tests/livechat_test_helpers";
import { Chatbot } from "@im_livechat/embed/common/chatbot/chatbot_model";
import { LivechatButton } from "@im_livechat/embed/common/livechat_button";
import {
  click,
  contains,
  insertText,
  start,
  startServer,
  triggerHotkey,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { advanceTime } from "@odoo/hoot-mock";
import {
  getService,
  makeServerError,
  mountWithCleanup,
  onRpc,
  patchWithCleanup,
} from "@web/../tests/web_test_helpers";

import { browser } from "@web/core/browser/browser";
import { session } from "@web/session";

describe.current.tags("desktop");
defineLivechatModels();

const CATEGORIES = [
  {
    id: 1,
    code: "observation",
    name: "Observation",
    reflet_title: "You told me about what you observed",
    sequence: 10,
    in_reflet_bar: true,
    reflet_bar_sequence: 1,
  },
  {
    id: 2,
    code: "emotions",
    name: "Emotions",
    reflet_title: "You told me about your emotions",
    sequence: 20,
    in_reflet_bar: true,
    reflet_bar_sequence: 2,
  },
];

/**
 * The widget of the welcome channel, opened, its conversation saved by a
 * first message of the visitor. Return the conversation, the store and
 * the id of the visitor.
 */
async function openWelcomeConversation() {
  const pyEnv = await startServer();
  await loadDefaultEmbedConfig();
  onRpc("/linkup/v1/livechat/categories", () => CATEGORIES);
  onRpc("/linkup/v1/livechat/help", () => ({
    resources: ["9-8-8: crisis line.", "9-1-1: emergency services."],
    moderation_hours: "",
    urgent_hours: 4,
  }));
  await start({ authenticateAs: false });
  getService("im_livechat.livechat").linkupKind = "welcome";
  await mountWithCleanup(LivechatButton);
  await click(".o-livechat-LivechatButton");
  await insertText(".o-mail-Composer-input", "Hello");
  triggerHotkey("Enter");
  await contains(".o-mail-Message", { text: "Hello" });
  const store = getService("mail.store");
  const thread = getService("im_livechat.livechat").thread;
  return { pyEnv, store, thread, guestId: store.self.id };
}

test("the steps of the guide that wait for the visitor", async () => {
  await startServer();
  await loadDefaultEmbedConfig();
  await start({ authenticateAs: false });
  const store = getService("mail.store");
  const types = [
    "linkup_category",
    "linkup_you_said",
    "linkup_understood",
    "linkup_reflet_review",
    "linkup_forward_moderator",
  ];
  const expected = types.map((type, index) =>
    store.ChatbotStep.insert({
      scriptStep: { id: 100 + index, type },
      message: { id: 200 + index },
    })
  );
  expect(expected.map((step) => step.expectAnswer)).toEqual([
    true,
    true,
    true,
    false,
    false,
  ]);
});

test("the answers of the chatbot are buttons, a category with its icon", async () => {
  const { store, thread } = await openWelcomeConversation();
  store.insert({
    "chatbot.script.answer": [
      { id: 31, name: "Observation", linkup_category_code: "observation" },
      { id: 32, name: "Emotions", linkup_category_code: "emotions" },
    ],
    "chatbot.script.step": [
      { id: 30, type: "linkup_category", answers: [31, 32] },
    ],
  });
  const message = store.Message.insert({
    id: 300,
    body: "Which category names the exchange?",
    thread,
    author: thread.operator,
  });
  store.ChatbotStep.insert({ scriptStep: { id: 30 }, message: { id: 300 } });
  thread.messages.add(message);
  await contains(".o-linkup-ChatbotAnswers-isGrid[aria-label='Categories']");
  await contains("li > button.o-linkup-ChatbotAnswer", { count: 2 });
  await contains("button.o-linkup-ChatbotAnswer[data-code='emotions'] svg");
  await contains("button.o-linkup-ChatbotAnswer", { text: "Emotions" });
});

test("a refused answer keeps the step and says why", async () => {
  const { store, thread } = await openWelcomeConversation();
  onRpc("/chatbot/step/trigger", () => {
    throw makeServerError({
      message: "Fill in “I understood that”.",
      context: {
        linkup_code: "linkup.validation",
        linkup_field: "understood",
      },
    });
  });
  store.insert({
    "chatbot.script.step": [{ id: 40, type: "linkup_understood" }],
  });
  const question = store.Message.insert({
    id: 400,
    body: "I understood that: write what you understood of it.",
    thread,
    author: thread.operator,
  });
  thread.messages.add(question);
  // The answer of the visitor is processed: the chatbot asks the server
  // for the next step once its typing is over, and the server refuses.
  const step = store.ChatbotStep.insert({
    scriptStep: { id: 40 },
    message: { id: 400 },
    completed: true,
  });
  store.Chatbot.insert({
    script: { id: 41 },
    thread,
    steps: [step],
    currentStep: step,
  });
  await advanceTime(Chatbot.MESSAGE_DELAY + 10);
  await contains(".o-linkup-ChatbotError[role='alert']", {
    text: "Fill in “I understood that”.",
  });
  expect(step.completed).toBe(false);
  await contains(".o-mail-Composer-input[placeholder='I understood that…']");
});

test("Need help now shows the resources and brings a moderator", async () => {
  const { thread } = await openWelcomeConversation();
  onRpc("/linkup/v1/livechat/help_now", async (request) => {
    const { params } = await request.json();
    expect.step(`help_now ${params.channel_id === thread.id}`);
    return {
      operator_found: true,
      step_id: false,
      message_id: false,
      resources: ["9-8-8: crisis line.", "9-1-1: emergency services."],
      moderation_hours: "",
      urgent_hours: 4,
      store: {},
    };
  });
  await contains(".o-linkup-LivechatHelp", {
    text: "LinkUp is not an emergency service.",
  });
  await click(".o-linkup-LivechatHelp-button");
  await expect.waitForSteps(["help_now true"]);
  await contains(".o-linkup-HelpNow-resources li", {
    text: "9-8-8: crisis line.",
  });
  await contains(".o-linkup-LivechatHelp-status[role='status']", {
    text: "A person of the moderation joins you in this conversation.",
  });
});

test("without a moderator, the request waits and the resources stay", async () => {
  await openWelcomeConversation();
  onRpc("/linkup/v1/livechat/help_now", () => ({
    operator_found: false,
    step_id: false,
    message_id: false,
    resources: ["9-8-8: crisis line."],
    moderation_hours: "",
    urgent_hours: 4,
    store: {},
  }));
  await click(".o-linkup-LivechatHelp-button");
  await contains(".o-linkup-LivechatHelp-status", {
    text: "No person of the moderation is available right now. Your request waits in the queue, processed within 4 hours.",
  });
  await contains(".o-linkup-HelpNow-resources li", {
    text: "9-8-8: crisis line.",
  });
});

test("beyond the limit, the request is already with the team", async () => {
  await openWelcomeConversation();
  onRpc("/linkup/v1/livechat/help_now", () => ({
    operator_found: false,
    limited: true,
    step_id: false,
    message_id: false,
    resources: ["9-8-8: crisis line."],
    moderation_hours: "",
    urgent_hours: 4,
    store: {},
  }));
  await click(".o-linkup-LivechatHelp-button");
  await contains(".o-linkup-LivechatHelp-status[role='status']", {
    text: "Your request is already with the moderation team.",
  });
  await contains(".o-linkup-HelpNow-resources li", {
    text: "9-8-8: crisis line.",
  });
});

test("the visitor confirms the reflection of the member through the live chat", async () => {
  const { store, thread, guestId } = await openWelcomeConversation();
  onRpc("/linkup/v1/livechat/reflet/confirm", async (request) => {
    const { params } = await request.json();
    expect.step(`confirm ${params.reflet_id}`);
    return true;
  });
  onRpc("/linkup/v1/livechat/reflet/info", () => ({ available: true }));
  store.insert({
    "linkup.reflet": [
      {
        id: 50,
        kind: "initial",
        state: "sent",
        livechat: true,
        author: { id: thread.operator.id, type: "partner" },
        recipient: { id: guestId, type: "guest" },
        category_id: { id: 2, code: "emotions" },
        you_said: "a run on Saturday mornings",
        understood: "you look for company",
      },
    ],
  });
  const message = store.Message.insert({
    id: 500,
    body: "<p>A member sent you a reflection.</p>",
    thread,
    author: thread.operator,
    linkup_reflet_id: { id: 50 },
  });
  thread.messages.add(message);
  await contains(".o-linkup-RefletCard[data-role='recipient']");
  await contains(".o-linkup-RefletActions-inaccurate", { count: 0 });
  await contains(".o-linkup-Safety-report", { count: 0 });
  await click(".o-linkup-RefletActions-confirm");
  await expect.waitForSteps(["confirm 50"]);
});

test("strict: the visitor writes a reflection to the member", async () => {
  const { thread } = await openWelcomeConversation();
  onRpc("/linkup/v1/livechat/reflet/info", () => ({
    available: true,
    can_send: true,
    recipient_name: "Nicolas",
    draft: {
      id: 9,
      category_id: 2,
      you_said: "the chores wear me out",
      understood: "you are exhausted",
      real_world_declared: false,
      real_world_date: false,
    },
    reflet_ids: [],
  }));
  let draft = null;
  onRpc("/linkup/v1/livechat/reflet/draft", async (request) => {
    draft = (await request.json()).params;
    return 9;
  });
  onRpc("/linkup/v1/livechat/reflet/send", () => {
    expect.step("send");
    return 9;
  });
  Object.assign(thread, {
    linkup_livechat_kind: "welcome",
    linkup_can_reflect: true,
    linkup_start_rule: "strict",
    linkup_start_rule_satisfied: false,
  });
  await contains(".o-linkup-StartRule[data-mode='strict']");
  await click(".o-linkup-StartRule-reflet");
  await contains(".o-linkup-RefletForm-youSaid", {
    value: "the chores wear me out",
  });
  await click(
    ".o-linkup-RefletForm-realWorld input[name='real_world_declared']"
  );
  await click(".o-linkup-RefletForm-send");
  await expect.waitForSteps(["send"]);
  expect(draft.vals.you_said).toBe("the chores wear me out");
  expect(draft.vals.real_world_declared).toBe(true);
  await contains(".o-linkup-RefletComposer-notice", {
    text: "Reflection sent to Nicolas.",
  });
});

test("a member logged in is sent to Discuss by the welcome widget", async () => {
  await startServer();
  await loadDefaultEmbedConfig();
  patchWithCleanup(session.livechatData.options, {
    init: {
      available_for_me: true,
      rule: {},
      storeData: {},
      linkup_kind: "welcome",
      linkup_redirect: "/odoo/discuss",
    },
  });
  patchWithCleanup(browser.location, {
    assign: (url) => expect.step(`assign ${url}`),
  });
  await start({ authenticateAs: false });
  await mountWithCleanup(LivechatButton);
  await contains(
    ".o-livechat-LivechatButton[aria-label='Open LinkUp in Discuss']"
  );
  await click(".o-livechat-LivechatButton");
  await expect.waitForSteps(["assign /odoo/discuss"]);
});
