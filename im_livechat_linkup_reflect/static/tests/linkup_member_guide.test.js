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
  getService,
  makeServerError,
  onRpc,
  serverState,
} from "@web/../tests/web_test_helpers";

import { defineLinkupLivechatModels } from "./linkup_livechat_test_helpers";

describe.current.tags("desktop");
defineLinkupLivechatModels();

/** The conversation of the guide of the current member with the chatbot. */
async function setupGuide(guide) {
  const pyEnv = await startServer();
  const botId = pyEnv["res.partner"].create({ name: "LinkUp" });
  const channelId = pyEnv["discuss.channel"].create({
    name: "LinkUp guide",
    channel_type: "livechat",
    livechat_active: true,
    livechat_operator_id: botId,
    channel_member_ids: [
      Command.create({ partner_id: serverState.partnerId }),
      Command.create({ partner_id: botId }),
    ],
    linkup_livechat_kind: "welcome",
    linkup_guide: guide,
  });
  return { pyEnv, channelId };
}

test("the last step of the first-use tour opens the guide in Discuss", async () => {
  const { channelId } = await setupGuide({
    step_type: "linkup_category",
    expects: "choice",
    answers: [
      { id: 7, name: "Emotions" },
      { id: 8, name: "Needs" },
    ],
  });
  onRpc("linkup.reflet", "linkup_start_guide", () => {
    expect.step("start_guide");
    return { channel_id: channelId, store: {} };
  });
  onRpc("/mail/message/post", async (request) => {
    const { params } = await request.json();
    expect.step(`post ${params.post_data.body} ${params.selected_answer_id}`);
  });
  await start();
  await openDiscuss();
  const tour = getService("linkup.tour");
  tour.start();
  tour.index = tour.steps.length - 1;
  await click(".o-linkup-Tour-guide", {
    text: "Write my first reflection with the guide",
  });
  await expect.waitForSteps(["start_guide"]);
  await contains(".o-linkup-Tour", { count: 0 });
  await contains(".o-linkup-GuideAnswers-hint", {
    text: "Choose the category of what you were told.",
  });
  await contains(".o-linkup-GuideAnswers-answer", { count: 2 });
  await click(".o-linkup-GuideAnswers-answer", { text: "Emotions" });
  await expect.waitForSteps(["post Emotions 7"]);
});

test("a text step names its answer, and a refused answer shows its reason", async () => {
  const { channelId } = await setupGuide({
    step_type: "linkup_understood",
    expects: "text",
    answers: [],
  });
  onRpc("/mail/message/post", () => {
    throw makeServerError({
      message: "Fill in “I understood that”.",
      context: {
        linkup_code: "linkup.validation",
        linkup_field: "understood",
      },
    });
  });
  await start();
  await openDiscuss(channelId);
  await contains(".o-linkup-GuideAnswers-hint", {
    text: "Type what you understood.",
  });
  await contains(".o-mail-Composer-input[placeholder='I understood that…']");
  await insertText(".o-mail-Composer-input", "x");
  await click(".o-mail-Composer-send:enabled");
  await contains(".o-linkup-GuideAnswers-error[role='alert']");
  await contains(".o-mail-Message", { count: 0 });
});
