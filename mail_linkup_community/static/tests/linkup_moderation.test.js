import {
  click,
  contains,
  insertText,
  start,
  startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { getService, onRpc } from "@web/../tests/web_test_helpers";

import { LinkupReportDialog } from "@mail_linkup_community/core/common/linkup_report_dialog";

import {
  defineLinkupCommunityModels,
  profileInfo,
} from "./linkup_community_test_helpers";

describe.current.tags("desktop");
defineLinkupCommunityModels();

const SUMMARY = { open: 2, urgent: 1, overdue: 0, urgent_hours: 24 };

/** A line of the queue, as `linkup_moderation_queue` gives it. */
function row(values = {}) {
  return {
    id: 7,
    date: "2026-10-26 14:41:00",
    reason: "harassment",
    urgent: false,
    member: "Sam",
    source: "reflet",
    state: "new",
    due_date: "2026-10-29 14:41:00",
    overdue: false,
    moderator: "",
    ...values,
  };
}

/** A report, as `linkup_moderation_detail` gives it. */
function detail(values = {}) {
  return {
    ...row(),
    reporter: "France",
    description: "Again and again.",
    action_taken: "none",
    decision_date: false,
    moderator_note: "",
    is_mine: false,
    can_hide: true,
    can_ban: true,
    appeal_text: "",
    history: { reports: 0 },
    audit: [],
    suspension_days: 7,
    ...values,
  };
}

async function openConsole() {
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.moderation",
  });
  await contains(".o-linkup-Moderation h1", { text: "Moderation" });
}

test("the queue lists the urgent reports first, and a report opens without its content", async () => {
  await startServer();
  onRpc("linkup.report", "linkup_moderation_queue", ({ kwargs }) => {
    expect.step(`queue ${kwargs.scope}`);
    return {
      rows: [
        row({ id: 8, reason: "distress", urgent: true, member: "Jacques" }),
        row({ source: "message", reason: "spam" }),
      ],
      summary: SUMMARY,
    };
  });
  let audit = [];
  onRpc("linkup.report", "linkup_moderation_detail", ({ args }) => {
    expect.step(`detail ${args[0]}`);
    return detail({ id: args[0], reason: "distress", urgent: true, audit });
  });
  onRpc("linkup.report", "linkup_moderation_content", ({ args }) => {
    expect.step(`content ${args[0]}`);
    audit = [
      {
        id: 1,
        date: "2026-10-26 15:02:00",
        actor: "Joanna",
        action: "content_read",
        reason: "Processing of the report",
      },
    ];
    return {
      source: "reflet",
      items: [
        {
          kind: "reflet",
          id: 3,
          author: "Sam",
          recipient: "France",
          date: "2026-10-26 14:03:00",
          reported: true,
          hidden: false,
          category: "Emotions",
          you_said: "the chores tire you",
          understood: "you are exhausted",
          body_text: "",
        },
      ],
    };
  });
  await start();
  await openConsole();
  await expect.waitForSteps(["queue open"]);
  await contains(".o-linkup-Moderation-counters", {
    text: "2 to process · 1 urgent · 0 late",
  });
  await contains(".o-linkup-Moderation-row", { count: 2 });
  await contains(".o-linkup-Moderation-row:first[data-urgent='true']");
  await click(
    ".o-linkup-Moderation-row[data-report-id='8'] .o-linkup-Moderation-open"
  );
  await expect.waitForSteps(["detail 8"]);
  await contains(".o-linkup-Moderation-detail h2", {
    text: "Person in distress or at risk for themselves",
  });
  await contains(".o-linkup-Moderation-reporter", { text: "France" });
  await contains(".o-linkup-Moderation-comment", { text: "Again and again." });
  await contains(".o-linkup-Moderation-take:enabled");
  await contains(".o-linkup-Moderation-decide-warn", { count: 0 });
  // The content stays hidden until asked for, and its reading is logged.
  await contains(".o-linkup-Moderation-item", { count: 0 });
  await contains(".o-linkup-Moderation-audit", {
    text: "No entry for this report.",
  });
  await click(".o-linkup-Moderation-showContent");
  await expect.waitForSteps(["content 8", "detail 8"]);
  await contains(".o-linkup-Moderation-reported .o-linkup-Moderation-youSaid", {
    text: "the chores tire you",
  });
  await contains(".o-linkup-Moderation-auditRow[data-action='content_read']", {
    text: "Joanna",
  });
  await click(".o-linkup-Moderation-back");
  await expect.waitForSteps(["queue open"]);
  await contains(".o-linkup-Moderation-row", { count: 2 });
});

test("a decision needs its reason, and an unavailable report reads as such", async () => {
  await startServer();
  onRpc("linkup.report", "linkup_moderation_queue", () => ({
    rows: [row()],
    summary: SUMMARY,
  }));
  onRpc("linkup.report", "linkup_moderation_detail", () => detail());
  onRpc("linkup.report", "action_moderation_take", () => {
    expect.step("take");
    return detail({ state: "in_review", is_mine: true, moderator: "Joanna" });
  });
  onRpc("linkup.report", "action_moderation_decide", ({ args, kwargs }) => {
    expect.step(`${args[1]} ${kwargs.reason} ${kwargs.days}`);
    return detail({
      state: "actioned",
      action_taken: "suspended",
      is_mine: true,
      moderator: "Joanna",
    });
  });
  await start();
  await openConsole();
  await click(".o-linkup-Moderation-open");
  await click(".o-linkup-Moderation-take");
  await expect.waitForSteps(["take"]);
  await contains(".o-linkup-Moderation-moderator", { text: "Joanna" });
  await click(".o-linkup-Moderation-decide-suspend");
  await contains(".o-linkup-Moderation-error", {
    text: "Give the reason of the decision: it goes to the audit log.",
  });
  expect.verifySteps([]);
  await insertText(".o-linkup-Moderation-reason", "Repeated insults");
  await insertText(".o-linkup-Moderation-days", "3", { replace: true });
  await click(".o-linkup-Moderation-decide-suspend");
  await expect.waitForSteps(["suspend Repeated insults 3"]);
  await contains(".o-linkup-Moderation-decision", { text: "Suspension" });
  await contains(".o-linkup-Moderation-actions", {
    text: "Sam is told of the decision (Suspension) and of the possible appeal.",
  });
  await contains(".o-linkup-Moderation-reason", { count: 0 });
});

test("the report of a person in distress shows the help at once", async () => {
  await startServer();
  onRpc("linkup.report", "action_create_report", ({ kwargs }) => {
    expect.step(`${kwargs.message_id} ${kwargs.reason} ${kwargs.description}`);
    return 12;
  });
  await start();
  getService("dialog").add(LinkupReportDialog, { messageId: 42, name: "Sam" });
  await contains(".o-linkup-ReportDialog-reason", { count: 9 });
  await contains(".o-linkup-ReportDialog-reason .badge", { count: 3 });
  await click(".o-linkup-ReportDialog-send");
  await contains(".o-linkup-ReportDialog-error", { text: "Choose a reason." });
  expect.verifySteps([]);
  await contains(".o-linkup-HelpNow", { count: 0 });
  await click("#o-linkup-ReportDialog-reason-distress");
  await contains(".o-linkup-HelpNow-resources li", {
    text: "9-8-8: suicide crisis helpline, by phone or text message, at any time (Canada).",
  });
  await insertText(
    ".o-linkup-ReportDialog-description",
    "She talks of leaving."
  );
  await click(".o-linkup-ReportDialog-send");
  await expect.waitForSteps(["42 distress She talks of leaving."]);
  await contains(".o-linkup-ReportDialog-ack", {
    text: "Thank you, your report is passed on to the moderation.",
  });
  await contains(".o-linkup-ReportDialog-urgent", {
    text: "Urgent report: the moderators are told at once. It is handled within 24 hours.",
  });
  await contains(".o-linkup-ReportDialog-ack .o-linkup-HelpNow");
});

test("the help opens on “Need help now” with the resources of the administrator", async () => {
  await startServer();
  await start();
  const store = getService("mail.store");
  store.linkup_help_resources = ["Line A: 1-800-000-0000"];
  store.linkup_moderation_hours = "every day, 9 to 21";
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.help",
    context: { linkup_section: "helpNow" },
  });
  await contains("#o-linkup-Help-helpNowTitle:focus");
  await contains(".o-linkup-HelpNow-resources li", { count: 1 });
  await contains(".o-linkup-HelpNow-resources li", {
    text: "Line A: 1-800-000-0000",
  });
  await contains(".o-linkup-HelpNow-hours", {
    text: "The moderation reads the reports: every day, 9 to 21. Outside these hours, use the resources above.",
  });
});

test("the profile lists the decisions, the reports and the blocks, and contests a decision", async () => {
  await startServer();
  const notice = {
    id: 5,
    date: "2026-10-27 10:00:00",
    decision: "warning",
    reason: "harassment",
    suspended_until: false,
    appeal_state: "none",
    can_appeal: true,
    seen: false,
  };
  onRpc("res.users", "linkup_profile_info", () =>
    profileInfo({
      notices: [notice],
      reports: [
        {
          id: 9,
          date: "2026-10-26 14:41:00",
          reason: "spam",
          urgent: false,
          source: "message",
          member: "Jacques",
          progress: "in_review",
        },
      ],
      blocked: [{ id: 1, user_id: 4, partner_id: 5, name: "Luce" }],
    })
  );
  onRpc("linkup.moderation.notice", "action_mark_seen", () => {
    expect.step("seen");
    return true;
  });
  onRpc("linkup.moderation.notice", "action_appeal", ({ args, kwargs }) => {
    expect.step(`appeal ${args[0]} ${kwargs.text}`);
    return { ...notice, appeal_state: "requested", can_appeal: false };
  });
  onRpc("linkup.block", "action_unblock", ({ kwargs }) => {
    expect.step(`unblock ${kwargs.user_id}`);
    return true;
  });
  onRpc("linkup.block", "linkup_blocked_members", () => []);
  await start();
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.profile",
    context: { linkup_section: "safety" },
  });
  await contains("#o-linkup-Profile-safetyTitle:focus");
  await expect.waitForSteps(["seen"]);
  await contains(".o-linkup-Profile-decision[data-decision='warning']", {
    text: "The moderation sent you a warning.",
  });
  await contains(".o-linkup-Profile-report", { text: "In review" });
  await click(".o-linkup-Profile-contest");
  await insertText(
    ".o-linkup-Profile-appealText",
    "I said nothing of the kind."
  );
  await click(".o-linkup-Profile-sendAppeal");
  await expect.waitForSteps(["appeal 5 I said nothing of the kind."]);
  await contains(".o-linkup-Profile-appealState", {
    text: "Your appeal is under review.",
  });
  await contains(".o-linkup-Profile-contest", { count: 0 });
  await click(".o-linkup-Profile-unblock", { text: "Unblock Luce" });
  await expect.waitForSteps(["unblock 4"]);
  await contains(".o-linkup-Profile-blocked", { text: "You block nobody." });
});
