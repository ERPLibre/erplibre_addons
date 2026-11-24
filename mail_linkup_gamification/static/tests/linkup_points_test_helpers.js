import { defineActions, defineModels } from "@web/../tests/web_test_helpers";

import { linkupModels } from "@mail_linkup_reflet/../tests/linkup_test_helpers";

import { LinkupReflet } from "./mock_server/mock_models/linkup_reflet";
import { ResUsers } from "./mock_server/mock_models/res_users";
import { ResUsersSettings } from "./mock_server/mock_models/res_users_settings";

export function defineLinkupPointsModels() {
  defineActions([
    {
      id: 9100,
      xml_id: "mail_linkup_gamification.action_linkup_my_points",
      name: "My points",
      type: "ir.actions.client",
      tag: "linkup.my_points",
    },
  ]);
  return defineModels({
    ...linkupModels,
    LinkupReflet,
    ResUsers,
    ResUsersSettings,
  });
}

/**
 * A page of `linkup_my_points` as the server gives it, with `lines` and
 * the values of `values`.
 */
export function myPointsResult(lines = [], values = {}) {
  return {
    balance: 1100,
    total: lines.length,
    last_id: Math.max(0, ...lines.map((line) => line.id)),
    rank: { id: 1, name: "Spark", karma_min: 1 },
    next_rank: { id: 2, name: "Flame", karma_min: 2500 },
    badges: [],
    rules: [
      { code: "reflect_sent", name: "Reflection sent", points: 100 },
      { code: "reflect_confirmed", name: "Reflection confirmed", points: 1000 },
      { code: "reflect_rejected", name: "Reflection rejected", points: -150 },
    ],
    counterparts: [],
    lines,
    ...values,
  };
}

/** A ledger line of `linkup_my_points`. */
export function ledgerLine(id, values = {}) {
  return {
    id,
    date: "2026-10-26 14:03:00",
    rule_code: "reflect_confirmed",
    rule_name: "Reflection confirmed",
    points: 1000,
    capped: false,
    cap_reason: false,
    counterpart: { id: 7, name: "France" },
    reflet_id: 1,
    ...values,
  };
}
