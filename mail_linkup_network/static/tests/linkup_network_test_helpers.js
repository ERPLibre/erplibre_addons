import { startServer } from "@mail/../tests/mail_test_helpers";
import { expect } from "@odoo/hoot";
import {
  defineActions,
  defineModels,
  onRpc,
  serverState,
} from "@web/../tests/web_test_helpers";

import { linkupModels } from "@mail_linkup_reflet/../tests/linkup_test_helpers";
import { ResUsers } from "@mail_linkup_gamification/../tests/mock_server/mock_models/res_users";
import { ResUsersSettings } from "@mail_linkup_gamification/../tests/mock_server/mock_models/res_users_settings";

import { LinkupReflet } from "./mock_server/mock_models/linkup_reflet";

/** "My partners" of the member, as the deck gives them (#113). */
export const PARTNERS = [
  ["France", 32450],
  ["Jacques", 12459],
  ["Jean", 6909],
];

export function defineLinkupNetworkModels() {
  defineActions([
    {
      id: 9200,
      xml_id: "mail_linkup_network.action_linkup_network",
      name: "Network view",
      type: "ir.actions.client",
      tag: "linkup.network_view",
    },
    {
      id: 9201,
      xml_id: "mail_linkup_reflet.action_linkup_home",
      name: "Reflet view",
      type: "ir.actions.client",
      tag: "linkup.reflet_view",
    },
    {
      id: 9202,
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
 * Start the mock server with the member, whose energy is 61,563, and the
 * three contacts of `PARTNERS`, each with an active link.
 *
 * @returns {Promise<{pyEnv: Object, users: Object<string, {userId: number, partnerId: number}>}>}
 */
export async function setupNetwork() {
  const pyEnv = await startServer();
  pyEnv["res.users"].write([serverState.userId], { linkup_karma: 61563 });
  const users = {};
  for (const [name] of PARTNERS) {
    const partnerId = pyEnv["res.partner"].create({ name });
    const userId = pyEnv["res.users"].create({
      name,
      partner_id: partnerId,
      linkup_active_link: true,
    });
    users[name] = { userId, partnerId };
  }
  return { pyEnv, users };
}

/**
 * Answer `get_network_graph`, `get_ranking` and `get_link_card` from the
 * contacts of `setupNetwork`, as the server does, and record each call as a
 * step: `graph <level>`, `ranking <kind> <period>`, `card <name> <reflets
 * only>`.
 *
 * - X1 adds the grey line France–Jean; X3 keeps the first two.
 * - Jacques puts the member in the light.
 * - "The most active" lists France and Jean only, who show their energy.
 * - The card of Jean is unavailable, as a block makes it.
 *
 * @param {Object} users as `setupNetwork` gives them
 * @param {{steps?: boolean, decay?: number}} [options] `steps` records the
 *  calls; `decay` is taken from the energy of the member in the graph, as
 *  the server decays it (Q-41)
 */
export function mockNetwork(users, { steps = false, decay = 0 } = {}) {
  const step = (text) => steps && expect.step(text);
  const contact = (name) => ({
    user_id: users[name].userId,
    partner_id: users[name].partnerId,
    name,
    highlight: name === "Jacques",
  });
  onRpc("linkup.link", "get_network_graph", ({ kwargs }) => {
    step(`graph ${kwargs.level}`);
    const shown = kwargs.level === "x3" ? PARTNERS.slice(0, 2) : PARTNERS;
    const nodes = shown.map(([name, energy]) => ({
      ...contact(name),
      energy,
    }));
    const edges = nodes.map((node) => ({
      source: serverState.userId,
      target: node.user_id,
      kind: "direct",
      energy: node.energy,
    }));
    if (kwargs.level === "x1") {
      edges.push({
        source: users.France.userId,
        target: users.Jean.userId,
        kind: "contacts",
      });
    }
    return {
      level: kwargs.level,
      me: {
        user_id: serverState.userId,
        partner_id: serverState.partnerId,
        name: "Mitchell Admin",
        energy: 61563 - decay,
      },
      nodes,
      edges,
      more: false,
    };
  });
  onRpc("linkup.link", "get_ranking", ({ kwargs }) => {
    step(`ranking ${kwargs.kind} ${kwargs.period}`);
    const rows =
      kwargs.kind === "active"
        ? [
            ["France", 87300],
            ["Jean", 31900],
          ]
        : PARTNERS;
    return {
      kind: kwargs.kind,
      period: kwargs.period,
      rows: rows.map(([name, value], index) => ({
        ...contact(name),
        position: index + 1,
        value,
      })),
    };
  });
  onRpc("linkup.link", "get_link_card", ({ args, kwargs }) => {
    const [userId] = args;
    const [name, energy] =
      PARTNERS.find(([key]) => users[key].userId === userId) || [];
    step(`card ${name} ${kwargs.reflets_only}`);
    if (!name || name === "Jean") {
      return { available: false };
    }
    const entries = [
      {
        message_id: 1,
        date: "2026-10-26 14:03:00",
        mine: true,
        reflet_id: false,
        text: "See you at the garden",
      },
      {
        message_id: 2,
        date: "2026-10-26 15:10:00",
        mine: false,
        reflet_id: false,
        text: "Gladly",
      },
    ];
    return {
      available: true,
      ...contact(name),
      energy,
      first_link_date: "2026-09-01 10:00:00",
      channel_id: false,
      highlight_sent: false,
      highlight_received: name === "Jacques",
      entries: kwargs.reflets_only ? [] : entries,
      store: {},
    };
  });
}
