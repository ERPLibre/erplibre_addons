import {
  click,
  contains,
  openDiscuss,
  start,
  startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { mockPermission } from "@odoo/hoot-mock";
import { browser } from "@web/core/browser/browser";
import { ConnectionLostError } from "@web/core/network/rpc";
import { ORM } from "@web/core/orm_service";
import {
  Command,
  makeServerError,
  onRpc,
  patchWithCleanup,
  serverState,
} from "@web/../tests/web_test_helpers";

import {
  LINKUP_CLIENT_CODES,
  LINKUP_SERVER_CODES,
  linkupClientError,
  linkupErrorInfo,
} from "@mail_linkup_reflet/core/common/linkup_errors";

import { defineLinkupModels, mockLinkupReading } from "./linkup_test_helpers";

describe.current.tags("desktop");
defineLinkupModels();

/** The message of each code of the catalogue (LU-F-093). */
const MESSAGES = {
  network: "Connection lost, try again.",
  session: "Your session expired: log in again.",
  media_denied: "Allow the microphone or the camera to call.",
  "linkup.unavailable": "Sending is not possible.",
  "linkup.already_answered": "This reflection has already been answered.",
  "linkup.expired": "This reflection is no longer available.",
  "linkup.rate_limited": "Too many attempts for now, try again later.",
  "linkup.start_rule": "Start with a reflection of a real exchange.",
  "linkup.not_verified": "Confirm your email address first.",
  "linkup.consent_required": "Accept the conditions of LinkUp first.",
  "linkup.invite_expired": "This invitation has expired.",
  "linkup.invite_used": "This invitation has already been used.",
  "linkup.invite_cancelled": "This invitation was cancelled.",
  "linkup.validation": "Check the reflection before sending it.",
};

/** A reflection France sent to the current user, in their chat. */
async function setupReceived(values = {}) {
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
  const messageId = pyEnv["mail.message"].create({
    author_id: franceId,
    body: "<p>Neutral sentence of the carrier.</p>",
    message_type: "comment",
    model: "discuss.channel",
    res_id: channelId,
  });
  const refletId = pyEnv["linkup.reflet"].create({
    kind: "initial",
    state: "sent",
    author_id: franceUserId,
    recipient_id: serverState.userId,
    category_id: pyEnv["linkup.category"].search([
      ["code", "=", "emotions"],
    ])[0],
    you_said: "the chores and a job wear you out",
    understood: "you are exhausted",
    channel_id: channelId,
    message_id: messageId,
    ...values,
  });
  mockLinkupReading();
  return { pyEnv, channelId, refletId };
}

const CARD = ".o-mail-Message .o-linkup-RefletCard";

test("every code of the catalogue has its message", async () => {
  // The messages are translated: the translations are loaded first.
  await startServer();
  await start();
  const codes = [...LINKUP_SERVER_CODES, ...LINKUP_CLIENT_CODES];
  expect(codes.sort()).toEqual(Object.keys(MESSAGES).sort());
  for (const code of LINKUP_SERVER_CODES) {
    const info = linkupErrorInfo(
      makeServerError({ context: { linkup_code: code } })
    );
    expect(info.code).toBe(code);
    expect(String(info.message)).toBe(MESSAGES[code]);
  }
  const network = linkupErrorInfo(new ConnectionLostError("/web/dataset"));
  expect(network.code).toBe("network");
  expect(String(network.message)).toBe(MESSAGES.network);
  const session = linkupErrorInfo(
    makeServerError({ errorName: "odoo.http.SessionExpiredException" })
  );
  expect(session.code).toBe("session");
  expect(String(session.message)).toBe(MESSAGES.session);
  expect(String(linkupClientError("media_denied").message)).toBe(
    MESSAGES.media_denied
  );
  // An error that is not one of LinkUp goes to the error dialog.
  expect(linkupErrorInfo(makeServerError({ message: "Other" }))).toBe(null);
});

test("a lost connection offers to try again, which runs the action again", async () => {
  const { channelId } = await setupReceived();
  let fail = true;
  patchWithCleanup(ORM.prototype, {
    call(model, method) {
      if (method === "action_confirm") {
        expect.step(`action_confirm${fail ? " lost" : ""}`);
        if (fail) {
          fail = false;
          return Promise.reject(new ConnectionLostError("/web/dataset"));
        }
      }
      return super.call(...arguments);
    },
  });
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-RefletActions-confirm");
  await contains(
    ".o-linkup-RefletActions-error[data-code='network'] .o-linkup-ErrorAlert-message",
    { text: "Connection lost, try again." }
  );
  await contains(".o-linkup-ErrorAlert-retry", { text: "Try again" });
  // Nothing is shown as done while the server did not answer.
  await contains(`${CARD}[data-state='sent']`);
  await click(".o-linkup-ErrorAlert-retry");
  await contains(`${CARD}[data-state='confirmed']`);
  await contains(".o-linkup-RefletActions-error", { count: 0 });
  expect.verifySteps(["action_confirm lost", "action_confirm"]);
});

test("an expired session asks to log in again", async () => {
  const { channelId } = await setupReceived();
  onRpc("linkup.reflet", "action_confirm", () => {
    throw makeServerError({
      errorName: "odoo.http.SessionExpiredException",
      message: "Session expired",
    });
  });
  patchWithCleanup(browser.location, {
    reload: () => expect.step("reload"),
  });
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-RefletActions-confirm");
  await contains(
    ".o-linkup-RefletActions-error[data-code='session'] .o-linkup-ErrorAlert-message",
    { text: "Your session expired: log in again." }
  );
  await click(".o-linkup-ErrorAlert-login");
  expect.verifySteps(["reload"]);
});

test("a reflection withdrawn while it is shown says so and loses its buttons", async () => {
  const { pyEnv, channelId, refletId } = await setupReceived();
  onRpc("linkup.reflet", "action_confirm", () => {
    // The author withdrew it a moment before.
    pyEnv["linkup.reflet"].write([refletId], { state: "withdrawn" });
    throw makeServerError({
      message: "This reflection is no longer available.",
      context: { linkup_code: "linkup.expired" },
    });
  });
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-RefletActions-confirm");
  await contains(".o-linkup-RefletActions-error[data-code='linkup.expired']", {
    text: "This reflection is no longer available.",
  });
  await contains(`${CARD}.o-linkup-RefletCard-isMuted[data-state='withdrawn']`);
  await contains(".o-linkup-RefletActions-confirm", { count: 0 });
  await contains(".o-linkup-RefletCard-youSaid", { count: 0 });
});

test("a reflection answered elsewhere is read again from the server", async () => {
  const { pyEnv, channelId, refletId } = await setupReceived();
  onRpc("linkup.reflet", "action_confirm", () => {
    // Another tab confirmed it a moment before.
    pyEnv["linkup.reflet"].write([refletId], {
      state: "confirmed",
      holds_turn: true,
    });
    throw makeServerError({
      message: "This reflection has already been answered.",
      context: { linkup_code: "linkup.already_answered" },
    });
  });
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-RefletActions-confirm");
  await contains(
    ".o-linkup-RefletActions-error[data-code='linkup.already_answered']",
    { text: "This reflection has already been answered." }
  );
  await contains(`${CARD}[data-state='confirmed']`);
  await contains(".o-linkup-RefletActions[data-mode='answer']");
});

test("a call the browser refuses is not started", async () => {
  const { channelId } = await setupReceived({
    kind: "answer_exact",
    category_id: false,
    you_said: false,
    understood: false,
    holds_turn: true,
  });
  mockPermission("microphone", "denied");
  await start();
  await openDiscuss(channelId);
  await click(".o-linkup-RefletActions-self");
  await click(".o-linkup-RefletActions-call");
  await contains(".o-linkup-RefletActions-error[data-code='media_denied']", {
    text: "Allow the microphone or the camera to call.",
  });
  await contains(".o-discuss-Call", { count: 0 });
});
