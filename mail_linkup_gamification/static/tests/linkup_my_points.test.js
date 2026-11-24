import {
  click,
  contains,
  openDiscuss,
  start,
  startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { queryAllTexts, select } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { getService, onRpc, serverState } from "@web/../tests/web_test_helpers";

import {
  defineLinkupPointsModels,
  ledgerLine,
  myPointsResult,
} from "./linkup_points_test_helpers";

describe.current.tags("desktop");
defineLinkupPointsModels();

const LINES = [
  ledgerLine(3, { points: 1000 }),
  ledgerLine(2, {
    rule_code: "reflect_sent",
    rule_name: "Reflection sent",
    points: 100,
  }),
  ledgerLine(1, {
    rule_code: "reflect_sent",
    rule_name: "Reflection sent",
    points: 0,
    capped: true,
    cap_reason: "daily_cap",
    counterpart: { id: 8, name: "Jacques" },
  }),
];

/**
 * Answer `linkup_my_points` from `LINES`, as the server filters them, and
 * record each reading as a step.
 */
function mockMyPoints(values = {}) {
  onRpc("linkup.points.ledger", "linkup_my_points", ({ kwargs }) => {
    expect.step(
      `read ${kwargs.offset} ${kwargs.rule_code || "-"} ${
        kwargs.counterpart_id || "-"
      }`
    );
    let lines = LINES.filter(
      (line) =>
        (!kwargs.rule_code || line.rule_code === kwargs.rule_code) &&
        (!kwargs.counterpart_id ||
          line.counterpart?.id === kwargs.counterpart_id)
    );
    const total = lines.length;
    lines = lines.slice(kwargs.offset, kwargs.offset + kwargs.limit);
    return myPointsResult(lines, {
      total,
      badges: [
        {
          id: 1,
          name: "First link",
          description: "You confirmed a first link with another member.",
          level: "bronze",
        },
      ],
      counterparts: [
        { id: 7, name: "France" },
        { id: 8, name: "Jacques" },
      ],
      ...values,
    });
  });
}

async function openMyPoints() {
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.my_points",
  });
  await contains(".o-linkup-MyPoints-body");
}

test("“My points” shows the energy, the rank, the badges and the history", async () => {
  await startServer();
  mockMyPoints();
  await start();
  await openMyPoints();
  await expect.waitForSteps(["read 0 - -"]);
  await contains(".o-linkup-MyPoints h1", { text: "My points" });
  await contains(".o-linkup-MyPoints-balanceValue", { text: "1,100" });
  await contains(".o-linkup-MyPoints-rankName", { text: "Spark" });
  await contains(".o-linkup-MyPoints-nextRank", {
    text: "1,400 points to Flame.",
  });
  expect(".o-linkup-MyPoints-progress").toHaveAttribute("aria-valuenow", "44");
  await contains(".o-linkup-MyPoints-badgeName", { text: "First link" });
  await contains(".o-linkup-MyPoints-line", { count: 3 });
  expect(queryAllTexts(".o-linkup-MyPoints-lineEvent")).toEqual([
    "Reflection confirmed",
    "Reflection sent",
    "Reflection sent",
  ]);
  expect(queryAllTexts(".o-linkup-MyPoints-lineCounterpart")).toEqual([
    "France",
    "France",
    "Jacques",
  ]);
  expect(queryAllTexts(".o-linkup-MyPoints-linePoints")).toEqual([
    "+1,000",
    "+100",
    "0",
  ]);
  await contains(
    ".o-linkup-MyPoints-line[data-capped='true'] .o-linkup-MyPoints-lineReason",
    { text: "Daily cap" }
  );
  await contains(".o-linkup-MyPoints-count", { text: "3 of 3 lines" });
  await contains(".o-linkup-MyPoints-scaleRule", { count: 3 });
  await contains(".o-linkup-MyPoints-table caption", {
    text: "History of my points",
  });
});

test("the history filters on an event and on a person", async () => {
  await startServer();
  mockMyPoints();
  await start();
  await openMyPoints();
  await expect.waitForSteps(["read 0 - -"]);
  await select("reflect_sent", { target: ".o-linkup-MyPoints-filterRule" });
  await expect.waitForSteps(["read 0 reflect_sent -"]);
  await contains(".o-linkup-MyPoints-line", { count: 2 });
  await select("8", { target: ".o-linkup-MyPoints-filterCounterpart" });
  await expect.waitForSteps(["read 0 reflect_sent 8"]);
  await contains(".o-linkup-MyPoints-line", { count: 1 });
  await select("reflect_confirmed", {
    target: ".o-linkup-MyPoints-filterRule",
  });
  await expect.waitForSteps(["read 0 reflect_confirmed 8"]);
  await contains(".o-linkup-MyPoints-empty", {
    text: "No line matches these filters.",
  });
});

test("“Show more” reads the next page", async () => {
  await startServer();
  onRpc("linkup.points.ledger", "linkup_my_points", ({ kwargs }) => {
    expect.step(`read ${kwargs.offset}`);
    const all = Array.from({ length: 25 }, (_, index) =>
      ledgerLine(25 - index)
    );
    return myPointsResult(
      all.slice(kwargs.offset, kwargs.offset + kwargs.limit),
      {
        total: 25,
      }
    );
  });
  await start();
  await openMyPoints();
  await contains(".o-linkup-MyPoints-line", { count: 20 });
  await contains(".o-linkup-MyPoints-count", { text: "20 of 25 lines" });
  await click(".o-linkup-MyPoints-more");
  await contains(".o-linkup-MyPoints-line", { count: 25 });
  await contains(".o-linkup-MyPoints-more", { count: 0 });
  expect.verifySteps(["read 0", "read 20"]);
});

test("a member without points reads why the history is empty", async () => {
  await startServer();
  onRpc("linkup.points.ledger", "linkup_my_points", () =>
    myPointsResult([], { balance: 0, rank: false })
  );
  await start();
  await openMyPoints();
  await contains(".o-linkup-MyPoints-empty", {
    text: "No points yet. Your first confirmed reflection brings some.",
  });
  await contains(".o-linkup-MyPoints-rankName", { text: "No rank yet" });
  await contains(".o-linkup-MyPoints-noBadge", { text: "No badge yet." });
});

test("a line brought by the bus reads the history again", async () => {
  const pyEnv = await startServer();
  mockMyPoints();
  await start();
  await openMyPoints();
  await expect.waitForSteps(["read 0 - -"]);
  const [partner] = pyEnv["res.partner"].read(serverState.partnerId);
  pyEnv["bus.bus"]._sendone(partner, "linkup.points/awarded", {
    id: 40,
    points: 250,
    karma: 1350,
    rule_code: "answer_exact",
    capped: false,
  });
  await expect.waitForSteps(["read 0 - -"]);
});

test("the guide explains the elements of “My points”", async () => {
  await startServer();
  mockMyPoints();
  await start();
  await openMyPoints();
  await click(".o-linkup-MyPoints .o-linkup-GuideButton");
  await contains(".o-linkup-GuideSheet-title", { text: "My energy" });
  await click(".o-linkup-MyPoints-rank");
  await contains(".o-linkup-GuideSheet-title", { text: "Rank" });
  await click(".o-linkup-MyPoints-filters");
  await contains(".o-linkup-GuideSheet-title", { text: "Filters" });
  expect.verifySteps(["read 0 - -"]);
  await click(".o-linkup-MyPoints .o-linkup-GuideButton");
  await contains(".o-linkup-GuideSheet", { count: 0 });
});

test("the sidebar of Discuss and the energy bubble open “My points”", async () => {
  await startServer();
  mockMyPoints();
  await start();
  await openDiscuss();
  await click(".o-linkup-SidebarSection-myPoints", { text: "My points" });
  await contains(".o-linkup-MyPoints-body");
  await getService("action").doAction({
    type: "ir.actions.client",
    tag: "linkup.reflet_view",
  });
  await click(".o-linkup-Energy-bubble");
  await contains(".o-linkup-MyPoints-body");
  await animationFrame();
  expect.verifySteps(["read 0 - -", "read 0 - -"]);
});
