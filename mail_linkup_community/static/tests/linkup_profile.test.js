import {
  click,
  contains,
  insertText,
  start,
  startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import {
  getService,
  makeServerError,
  onRpc,
  serverState,
} from "@web/../tests/web_test_helpers";

import {
  consentRow,
  defineLinkupCommunityModels,
  profileInfo,
} from "./linkup_community_test_helpers";

describe.current.tags("desktop");
defineLinkupCommunityModels();

async function openProfile(section) {
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.profile",
    context: section ? { linkup_section: section } : {},
  });
  await contains(".o-linkup-Profile-identity");
}

test("the profile shows its three sections and saves the pseudonym", async () => {
  await startServer();
  onRpc("res.users", "linkup_profile_info", () => profileInfo());
  onRpc("res.users", "linkup_profile_write", ({ args }) => {
    expect.step(JSON.stringify(args[0]));
    return profileInfo({ name: args[0].name });
  });
  await start();
  await openProfile("privacy");
  await contains("#o-linkup-Profile-privacyTitle:focus");
  await contains(".o-linkup-Profile h1", { text: "My profile" });
  await contains(".o-linkup-Profile-code", { text: "ABCDE-FGHJK" });
  await contains(".o-linkup-Profile-age", { text: "25 to 34" });
  await contains(".o-linkup-Profile-residence", { text: "Canada" });
  await contains("#o-linkup-Profile-scope-code:checked");
  // The terms are given and cannot be withdrawn; the notifications can.
  await contains("#o-linkup-Profile-consent-terms:checked:disabled");
  await contains(
    "#o-linkup-Profile-consent-notifications:not(:checked):enabled"
  );
  await insertText(".o-linkup-Profile-name", " L.");
  await click(".o-linkup-Profile-saveIdentity");
  await expect.waitForSteps(['{"name":"Camille L.","lang":"en_US"}']);
  await contains(".o-linkup-Profile-identity .o-linkup-Profile-notice", {
    text: "Saved.",
  });
  await contains(".o-linkup-Profile-name", { value: "Camille L." });
});

test("a consent is withdrawn at once, and a refusal shows its message", async () => {
  await startServer();
  onRpc("res.users", "linkup_profile_info", () => profileInfo());
  onRpc("linkup.consent", "action_revoke", ({ args }) => {
    expect.step(`revoke ${args[0].join(",")}`);
    return profileInfo().consents.map((row) =>
      row.purpose === "sensitive_data"
        ? consentRow("sensitive_data", { granted: false })
        : row
    );
  });
  onRpc("res.users", "linkup_profile_write", () => {
    throw makeServerError({
      context: { linkup_code: "linkup.validation", linkup_field: "phone" },
    });
  });
  await start();
  await openProfile();
  await click("#o-linkup-Profile-consent-sensitive_data");
  await expect.waitForSteps(["revoke sensitive_data"]);
  await contains("#o-linkup-Profile-consent-sensitive_data:not(:checked)");
  await contains(".o-linkup-Profile-privacy .o-linkup-Profile-notice", {
    text: "Consent withdrawn.",
  });
  await insertText(".o-linkup-Profile-phone", "call me");
  await click(".o-linkup-Profile-saveContact");
  await contains(".o-linkup-Profile-contact .o-linkup-Profile-error", {
    text: "Enter a valid phone number.",
  });
});

test("my data: the export link, then a deletion asked and cancelled", async () => {
  await startServer();
  onRpc("res.users", "linkup_profile_info", () => profileInfo());
  onRpc("res.users", "linkup_request_deletion", () => {
    expect.step("request");
    return {
      deletion_requested: "2026-11-06 12:00:00",
      deletion_date: "2026-12-06 12:00:00",
      deletion_grace_days: 30,
    };
  });
  onRpc("res.users", "linkup_cancel_deletion", () => {
    expect.step("cancel");
    return {
      deletion_requested: false,
      deletion_date: false,
      deletion_grace_days: 30,
    };
  });
  await start();
  await openProfile("data");
  await contains("#o-linkup-Profile-dataTitle:focus");
  await contains(".o-linkup-Profile-export[href='/linkup/v1/me/export']");
  await click(".o-linkup-Profile-delete");
  await contains(".modal-body");
  await click(".modal-footer .btn-primary", { text: "Delete my account" });
  await expect.waitForSteps(["request"]);
  await contains(".o-linkup-Profile-deletionText");
  await click(".o-linkup-Profile-cancelDeletion");
  await expect.waitForSteps(["cancel"]);
  await contains(".o-linkup-Profile-data .o-linkup-Profile-notice", {
    text: "Deletion cancelled: your account stays as it is.",
  });
  await contains(".o-linkup-Profile-delete");
});

test("the menu of the avatar opens the profile on a section", async () => {
  await startServer();
  onRpc("res.users", "linkup_profile_info", () => profileInfo());
  await start();
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.reflet_view",
  });
  await click(".o-linkup-ProfileMenu-toggle");
  for (const entry of ["email", "phone", "photo", "privacy"]) {
    await contains(
      `.o-linkup-ProfileMenu-entry[data-entry='${entry}']:not([aria-disabled])`
    );
  }
  await click(".o-linkup-ProfileMenu-entry[data-entry='phone']");
  await contains("#o-linkup-Profile-contactTitle:focus");
});

test("the Reflet view asks the missing consents, then the verification", async () => {
  const pyEnv = await startServer();
  pyEnv["res.users"].write([serverState.userId], {
    linkup_email_verified: false,
    linkup_consent_missing_codes: "terms,privacy,sensitive_data",
  });
  onRpc("linkup.consent", "action_grant", ({ args }) => {
    expect.step(`grant ${args[0].join(",")}`);
    return [];
  });
  onRpc("res.users", "linkup_resend_verification", () => {
    expect.step("resend");
    return { verified: false, email: "c***@example.com" };
  });
  await start();
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.reflet_view",
  });
  await contains(".o-linkup-ConsentNotice-accept:disabled");
  await contains(".o-linkup-ConsentNotice .form-check-input:not(:checked)", {
    count: 3,
  });
  await click("#o-linkup-ConsentNotice-terms");
  await click("#o-linkup-ConsentNotice-privacy");
  await contains(".o-linkup-ConsentNotice-accept:disabled");
  await click("#o-linkup-ConsentNotice-sensitive_data");
  await click(".o-linkup-ConsentNotice-accept:enabled");
  await expect.waitForSteps(["grant terms,privacy,sensitive_data"]);
  await contains(".o-linkup-ConsentNotice", { count: 0 });
  await click(".o-linkup-VerifyNotice-resend");
  await expect.waitForSteps(["resend"]);
  await contains(".o-linkup-CommunityNotice-notice", {
    text: "A new link was sent to c***@example.com.",
  });
});

test("NewLink by phone shows the share link to copy", async () => {
  await startServer();
  await start();
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.reflet_view",
  });
  await click(".o-linkup-RefletView-newlink");
  await click("#o-linkup-Newlink-channelPhone");
  await contains(".o-linkup-Newlink-email", { count: 0 });
  await insertText(".o-linkup-Newlink-phone", "12");
  await click(".o-linkup-Newlink-next");
  await contains(".o-linkup-Newlink-error", {
    text: "Enter a valid phone number.",
  });
  await insertText(".o-linkup-Newlink-phone", "514 555 0123", {
    replace: true,
  });
  await click(".o-linkup-Newlink-next");
  await contains(".o-linkup-Newlink[data-step='reflet']");
});
