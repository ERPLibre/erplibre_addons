import {
  click,
  contains,
  openDiscuss,
  start,
  startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, test } from "@odoo/hoot";
import {
  Command,
  contains as webContains,
  serverState,
} from "@web/../tests/web_test_helpers";

import { defineLinkupModels } from "./linkup_test_helpers";

describe.current.tags("desktop");
defineLinkupModels();

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
  return { pyEnv, channelId, franceUserId };
}

test("the LinkUp panel sums up the link and lists the recent reflections", async () => {
  const { pyEnv, channelId, franceUserId } = await setupChat();
  const [team] = pyEnv["linkup.category"].search([["code", "=", "team"]]);
  pyEnv["linkup.reflet"].create({
    kind: "initial",
    state: "sent",
    author_id: serverState.userId,
    recipient_id: franceUserId,
    category_id: team,
    you_said: "the team needs a break",
    understood: "you want a pause",
    channel_id: channelId,
  });
  await start();
  await openDiscuss(channelId);
  await click(".o-mail-Discuss-header button[name='linkup-panel']");
  await contains(".o-mail-ActionPanel-header", { text: "LinkUp" });
  await contains(".o-linkup-Panel-link[data-state='pending']");
  await contains(".o-linkup-Panel-linkState", {
    text: "A reflection is waiting for an answer.",
  });
  await contains(".o-linkup-Panel-count", { text: "1 reflection" });
  await contains(".o-linkup-Panel-reflets .o-linkup-RefletCard", { count: 1 });
  await contains(".o-linkup-Panel-reflets .o-linkup-RefletCard-title", {
    text: "You told me about the team",
  });
});

test("the LinkUp panel of a pair without reflection", async () => {
  const { channelId } = await setupChat();
  await start();
  await openDiscuss(channelId);
  await click(".o-mail-Discuss-header button[name='linkup-panel']");
  await contains(".o-linkup-Panel-link[data-state='none']");
  await contains(".o-linkup-Panel-linkState", {
    text: "No reflection exchanged yet.",
  });
  await contains(".o-linkup-Panel-reflets", { text: "No reflection yet." });
});

test("the history of the pair filters by category and by state", async () => {
  const { pyEnv, channelId, franceUserId } = await setupChat();
  const category = (code) =>
    pyEnv["linkup.category"].search([["code", "=", code]])[0];
  for (const [code, state, fromFrance] of [
    ["emotions", "confirmed", false],
    ["goals", "sent", false],
    ["needs", "sent", true],
  ]) {
    pyEnv["linkup.reflet"].create({
      kind: "initial",
      state,
      author_id: fromFrance ? franceUserId : serverState.userId,
      recipient_id: fromFrance ? serverState.userId : franceUserId,
      category_id: category(code),
      you_said: `told about ${code}`,
      understood: `understood ${code}`,
      channel_id: channelId,
      read_date: "2026-01-01 10:00:00",
    });
  }
  await start();
  await openDiscuss(channelId);
  await click(".o-mail-Discuss-header button[name='linkup-panel']");
  await contains(".o-linkup-Panel-history .o-linkup-RefletCard", { count: 3 });
  await webContains(".o-linkup-Panel-historyCategory").select(
    String(category("goals"))
  );
  await contains(".o-linkup-Panel-history .o-linkup-RefletCard", { count: 1 });
  await contains(".o-linkup-Panel-history .o-linkup-RefletCard-title", {
    text: "You told me about your goal",
  });
  await webContains(".o-linkup-Panel-historyState").select("confirmed");
  await contains(".o-linkup-Panel-historyEmpty", {
    text: "No reflection matches these filters.",
  });
  await webContains(".o-linkup-Panel-historyCategory").select("");
  await contains(".o-linkup-Panel-history .o-linkup-RefletCard", { count: 1 });
  await contains(
    ".o-linkup-Panel-history .o-linkup-RefletCard[data-state='confirmed']"
  );
});
