import {
  click,
  contains,
  insertText,
  start,
  startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import {
  dblclick,
  press,
  queryAll,
  queryAllTexts,
  queryFirst,
} from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
  Command,
  contains as webContains,
  getService,
  onRpc,
  patchWithCleanup,
  serverState,
} from "@web/../tests/web_test_helpers";

import { defineLinkupModels } from "./linkup_test_helpers";

describe.current.tags("desktop");
defineLinkupModels();

/**
 * France, who sent the current user a reflection not read yet, and
 * Jacques, linked to the current user; a direct conversation with each.
 */
async function setupContacts() {
  const pyEnv = await startServer();
  const users = {};
  for (const [name, values] of [
    ["France", {}],
    ["Jacques", { linkup_active_link: true }],
  ]) {
    const partnerId = pyEnv["res.partner"].create({ name });
    const userId = pyEnv["res.users"].create({
      name,
      partner_id: partnerId,
      ...values,
    });
    pyEnv["discuss.channel"].create({
      channel_member_ids: [
        Command.create({ partner_id: serverState.partnerId }),
        Command.create({ partner_id: partnerId }),
      ],
      channel_type: "chat",
    });
    users[name] = { partnerId, userId };
  }
  pyEnv["linkup.reflet"].create({
    author_id: users.France.userId,
    recipient_id: serverState.userId,
    state: "sent",
  });
  return { pyEnv, users };
}

async function openRefletView() {
  await start();
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.reflet_view",
  });
  await contains(".o-linkup-RefletView-body");
}

test("the view shows the Help bar, an empty card and the contacts in order", async () => {
  const { users } = await setupContacts();
  await openRefletView();
  await contains(".o-linkup-RefletView h1", { text: "Reflet view" });
  await contains(
    ".o-linkup-RefletView .o-linkup-HelpBar[aria-label='HELP — What were you told about?']"
  );
  await contains(".o-linkup-HelpBar-category", { count: 7 });
  await contains(".o-linkup-RefletView-placeholder");
  await contains(".o-linkup-RefletView-contact", { count: 2 });
  expect(queryAllTexts(".o-linkup-RefletView-name")).toEqual([
    "France",
    "Jacques",
  ]);
  // The unread reflection carries a label, not only a colour.
  await contains(
    `.o-linkup-RefletView-contact[data-user-id='${users.France.userId}'] .o-linkup-RefletView-unread`,
    { text: "1 unread" }
  );
  await contains(
    `.o-linkup-RefletView-contact[data-user-id='${users.Jacques.userId}'] .o-linkup-RefletView-unread`,
    { count: 0 }
  );
  await contains(
    ".o-linkup-RefletView-openChat[aria-label='Open the conversation with Jacques']"
  );
});

test("a member without contacts gets the first-use message", async () => {
  await startServer();
  await openRefletView();
  await contains(".o-linkup-RefletView-empty");
  await contains(".o-linkup-RefletView-contact", { count: 0 });
  await click(".o-linkup-HelpBar-category[data-code='needs']");
  await contains(".o-linkup-RefletView-sendTo:disabled");
});

test("dropping a category on a contact opens the form for that contact", async () => {
  const { users } = await setupContacts();
  await openRefletView();
  await webContains(
    ".o-linkup-RefletView .o-linkup-HelpBar-category[data-code='emotions']"
  ).dragAndDrop(
    `.o-linkup-RefletView-contact[data-user-id='${users.France.userId}']`
  );
  await contains(".o-linkup-RefletForm-title", {
    text: "You told me about your emotions",
  });
  await contains(".o-linkup-RefletView-recipient", { text: "To: France" });
  await contains(
    `.o-linkup-RefletView-contact.o-isSelected[data-user-id='${users.France.userId}']`
  );
  await contains(
    ".o-linkup-RefletView .o-linkup-HelpBar[aria-label='HELP — What did France tell you about?']"
  );
  // France has no confirmed link yet: the exchange in person is asked.
  await contains(".o-linkup-RefletForm-realWorld");
  expect(".o-linkup-RefletForm-youSaid").toBeFocused();
});

test("the keyboard chooses a category, then a contact in Send to… which sends", async () => {
  const { users } = await setupContacts();
  onRpc("linkup.reflet", "action_send", ({ args }) => {
    expect.step(`action_send ${args[1]}`);
  });
  await openRefletView();
  queryFirst(".o-linkup-HelpBar-category").focus();
  await press("ArrowRight");
  await animationFrame();
  expect(".o-linkup-HelpBar-category[data-code='emotions']").toBeFocused();
  await press("Enter");
  await contains(".o-linkup-RefletForm-title", {
    text: "You told me about your emotions",
  });
  await contains(".o-linkup-RefletView-recipient", {
    text: "Who told you this?",
  });
  await insertText(".o-linkup-RefletForm-youSaid", "the chores wear you out");
  await insertText(".o-linkup-RefletForm-understood", "you are exhausted");
  queryFirst(".o-linkup-RefletView-sendTo").focus();
  await press("Enter");
  await contains(
    ".o-linkup-RefletView-picker[role='listbox'][aria-label='Send to…']"
  );
  expect(".o-linkup-RefletView-picker").toBeFocused();
  await contains(".o-linkup-RefletView-option[aria-selected='true']", {
    text: "France",
  });
  await press("ArrowDown");
  await contains(".o-linkup-RefletView-option[aria-selected='true']", {
    text: "Jacques",
  });
  expect(".o-linkup-RefletView-picker").toHaveAttribute(
    "aria-activedescendant",
    `o-linkup-RefletView-option-${users.Jacques.userId}`
  );
  await press("Enter");
  await contains(".o-linkup-RefletView-notice", {
    text: "Reflection sent to Jacques.",
  });
  expect.verifySteps([`action_send ${users.Jacques.userId}`]);
  await contains(".o-linkup-RefletView-sentChat", {
    text: "Open the conversation with Jacques",
  });
  await contains(".o-linkup-RefletView-placeholder");
  await animationFrame();
  expect(".o-linkup-RefletView-sentChat").toBeFocused();
});

test("the guide closes Send to… and explains it instead of sending", async () => {
  await setupContacts();
  onRpc("linkup.reflet", "action_send", () => {
    expect.step("action_send");
  });
  await openRefletView();
  await click(".o-linkup-HelpBar-category[data-code='needs']");
  await insertText(".o-linkup-RefletForm-youSaid", "the chores wear you out");
  await insertText(".o-linkup-RefletForm-understood", "you are exhausted");
  await click(".o-linkup-RefletView-sendTo");
  await contains(".o-linkup-RefletView-picker");
  await click(".o-linkup-RefletView .o-linkup-GuideButton");
  await contains(".o-linkup-GuideSheet");
  await contains(".o-linkup-RefletView-picker", { count: 0 });
  await click(".o-linkup-RefletView-sendTo");
  await contains(".o-linkup-GuideSheet-title", { text: "Send to…" });
  await contains(".o-linkup-RefletView-picker", { count: 0 });
  await press("Escape");
  await contains(".o-linkup-GuideSheet", { count: 0 });
  expect.verifySteps([]);
});

test("Escape closes Send to…; sending without a recipient asks for one", async () => {
  await setupContacts();
  await openRefletView();
  await click(".o-linkup-HelpBar-category[data-code='needs']");
  await click(".o-linkup-RefletView-sendTo");
  await contains(".o-linkup-RefletView-picker");
  await press("Escape");
  await contains(".o-linkup-RefletView-picker", { count: 0 });
  expect(".o-linkup-RefletView-sendTo").toBeFocused();
  await insertText(".o-linkup-RefletForm-youSaid", "the chores wear you out");
  await insertText(".o-linkup-RefletForm-understood", "you are exhausted");
  await click(".o-linkup-RefletForm-send");
  await contains(".o-linkup-RefletForm-error[role='alert']", {
    text: "Choose the person who told you this.",
  });
  expect(".o-linkup-RefletView-sendTo").toBeFocused();
});

test("a contact opens its direct conversation in Discuss", async () => {
  await setupContacts();
  await openRefletView();
  await click(
    ".o-linkup-RefletView-openChat[aria-label='Open the conversation with France']"
  );
  await contains(".o-mail-Discuss-threadName[title='France']");
});

test("a contact without a conversation nor a confirmed link opens none", async () => {
  const pyEnv = await startServer();
  const partnerId = pyEnv["res.partner"].create({ name: "Luce" });
  pyEnv["res.users"].create({ name: "Luce", partner_id: partnerId });
  await openRefletView();
  await contains(".o-linkup-RefletView-contact", { count: 1 });
  // The server opens this conversation itself, to carry a reflection.
  await contains(".o-linkup-RefletView-openChat", { count: 0 });
});

test("the view restores the draft of the member", async () => {
  const { pyEnv } = await setupContacts();
  const [goals] = pyEnv["linkup.category"].search_read([
    ["code", "=", "goals"],
  ]);
  pyEnv["linkup.reflet"].create({
    author_id: serverState.userId,
    state: "draft",
    category_id: goals.id,
    you_said: "a garden",
  });
  await openRefletView();
  await contains(".o-linkup-RefletForm-title", {
    text: "You told me about your goal",
  });
  await contains(".o-linkup-RefletForm-youSaid", { value: "a garden" });
});

test("the avatar opens the menu of the settings, its eight entries first", async () => {
  await setupContacts();
  await openRefletView();
  await dblclick(".o-linkup-ProfileMenu-avatar");
  await contains(".o-linkup-ProfileMenu-menu[role='menu']");
  // A module that brings a screen adds its entries after these eight.
  expect(queryAllTexts(".o-linkup-ProfileMenu-label").slice(0, 8)).toEqual([
    "Help",
    "Email",
    "Phone",
    "Photo",
    "Sounds and notifications",
    "Privacy",
    "My data",
    "Blocked members",
  ]);
  expect(".o-linkup-ProfileMenu-entry[data-entry='help']").toBeFocused();
  // The entries without a screen yet say why, and lead nowhere.
  for (const entry of ["phone", "privacy", "data"]) {
    expect(
      `.o-linkup-ProfileMenu-entry[data-entry='${entry}']`
    ).toHaveAttribute("aria-disabled", "true");
  }
  await contains(
    ".o-linkup-ProfileMenu-entry[data-entry='data'] .o-linkup-ProfileMenu-hint",
    { text: "Comes with the export and the deletion of your data." }
  );
  await click(".o-linkup-ProfileMenu-entry[data-entry='phone']");
  await contains(".o-linkup-ProfileMenu-menu");
  await press("End");
  expect(queryAll(".o-linkup-ProfileMenu-entry").at(-1)).toBeFocused();
  await press("Escape");
  await contains(".o-linkup-ProfileMenu-menu", { count: 0 });
  expect(".o-linkup-ProfileMenu-toggle").toBeFocused();
  // "My profile" opens it too; the entries open the help, on a section.
  patchWithCleanup(getService("action"), {
    doAction(action, options) {
      const section = options?.additionalContext?.linkup_section;
      expect.step(section ? `${action} ${section}` : action);
    },
  });
  for (const entry of ["help", "sounds", "blocked"]) {
    await click(".o-linkup-ProfileMenu-toggle");
    await click(`.o-linkup-ProfileMenu-entry[data-entry='${entry}']`);
    await contains(".o-linkup-ProfileMenu-menu", { count: 0 });
  }
  expect.verifySteps([
    "mail_linkup_reflet.action_linkup_help",
    "mail_linkup_reflet.action_linkup_help settings",
    "mail_linkup_reflet.action_linkup_help blocked",
  ]);
});

test("the help opened on a section gives it the focus", async () => {
  await startServer();
  await start();
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.help",
    context: { linkup_section: "blocked" },
  });
  await contains(".o-linkup-Help-blocked");
  await animationFrame();
  expect("#o-linkup-Help-blockedTitle").toBeFocused();
});

test("Email and Photo of the menu open the preferences of the user", async () => {
  await setupContacts();
  onRpc("res.users", "action_get", () => {
    expect.step("action_get");
    return { type: "ir.actions.act_window", res_model: "res.users" };
  });
  await openRefletView();
  patchWithCleanup(getService("action"), {
    doAction(action) {
      expect.step(`${action.res_model} ${action.res_id}`);
    },
  });
  await click(".o-linkup-ProfileMenu-toggle");
  await click(".o-linkup-ProfileMenu-entry[data-entry='photo']");
  await expect.waitForSteps(["action_get", `res.users ${serverState.userId}`]);
});

test("dropping the happiness field on a contact puts them in the light", async () => {
  const { users } = await setupContacts();
  onRpc("linkup.highlight", "action_send", ({ args }) => {
    expect.step(`action_send ${JSON.stringify(args)}`);
  });
  await openRefletView();
  await webContains(".o-linkup-RefletView-happiness").dragAndDrop(
    `.o-linkup-RefletView-contact[data-user-id='${users.Jacques.userId}']`
  );
  await expect.waitForSteps([`action_send [${users.Jacques.userId}]`]);
  await contains(".o-linkup-RefletView-happinessNotice", {
    text: "Jacques sees your avatar on theirs until your next exchange.",
  });
  await contains(
    `.o-linkup-RefletView-contact[data-user-id='${users.Jacques.userId}'] .o-linkup-RefletView-highlightedByMe`
  );
  await contains(".o-linkup-RefletView-highlightedByMe", { count: 1 });
});

test("without a pointer, the happiness field opens the list of the contacts", async () => {
  const { users } = await setupContacts();
  onRpc("linkup.highlight", "action_send", ({ args }) => {
    expect.step(`action_send ${JSON.stringify(args)}`);
  });
  await openRefletView();
  queryFirst(".o-linkup-RefletView-happiness").focus();
  await press("Enter");
  await contains(
    ".o-linkup-RefletView-happinessList[role='listbox'][aria-label='Put someone in the light']"
  );
  expect(".o-linkup-RefletView-happinessList").toBeFocused();
  await press("ArrowDown");
  await contains(
    ".o-linkup-RefletView-happinessList .o-linkup-RefletView-option[aria-selected='true']",
    { text: "Jacques" }
  );
  await press("Escape");
  await contains(".o-linkup-RefletView-happinessList", { count: 0 });
  expect(".o-linkup-RefletView-happiness").toBeFocused();
  await press("Enter");
  await contains(".o-linkup-RefletView-happinessList");
  await press("Enter");
  await expect.waitForSteps([`action_send [${users.France.userId}]`]);
  await contains(".o-linkup-RefletView-happinessNotice", {
    text: "France sees your avatar on theirs until your next exchange.",
  });
});

test("a reflection sent and not read waits in the view, and is withdrawn there", async () => {
  const { pyEnv, users } = await setupContacts();
  pyEnv["linkup.reflet"].create({
    kind: "initial",
    author_id: serverState.userId,
    recipient_id: users.Jacques.userId,
    state: "sent",
    category_id: pyEnv["linkup.category"].search([["code", "=", "goals"]])[0],
    you_said: "a trip next summer",
    understood: "you want to rest",
  });
  onRpc("linkup.reflet", "action_withdraw", () => {
    expect.step("action_withdraw");
  });
  await openRefletView();
  await contains(".o-linkup-RefletView-sent .o-linkup-RefletCard", {
    count: 1,
  });
  await contains(".o-linkup-RefletView-sent .o-linkup-RefletCard-footer", {
    text: "Waiting for the confirmation of Jacques",
  });
  await click(".o-linkup-RefletView-sent .o-linkup-RefletActions-withdraw");
  await click(".o-linkup-WithdrawDialog-confirm");
  await expect.waitForSteps(["action_withdraw"]);
  await contains(".o-linkup-RefletView-sent", { count: 0 });
});
