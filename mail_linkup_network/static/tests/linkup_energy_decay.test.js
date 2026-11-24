import { contains, openDiscuss, start } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { getService } from "@web/../tests/web_test_helpers";

import {
  defineLinkupNetworkModels,
  mockNetwork,
  setupNetwork,
} from "./linkup_network_test_helpers";

describe.current.tags("desktop");
defineLinkupNetworkModels();

const VIEW = ".o-linkup-NetworkView";

test("the energy shown is the karma less its decay, and follows new points", async () => {
  const { users } = await setupNetwork();
  mockNetwork(users, { decay: 1563 });
  await start();
  const store = getService("mail.store");
  // The server gives the decay of the energy at the opening (Q-41).
  store.linkup_energy_decay = 1563;
  await openDiscuss();
  await contains(".o-linkup-SidebarSection-networkView", {
    text: "Network view (60,000)",
  });
  await getService("action").doAction(
    "mail_linkup_network.action_linkup_network"
  );
  await contains(`${VIEW}-energyValue`, { text: "60,000" });
  // A new line raises the karma: the energy follows with its full weight.
  store.linkup_karma = 62563;
  await contains(`${VIEW}-energyValue`, { text: "61,000" });
});

test("the decay follows the energy the server computes for the graph", async () => {
  const { users } = await setupNetwork();
  // A day passed since the opening: the server decays the energy further.
  mockNetwork(users, { decay: 2563 });
  await start();
  const store = getService("mail.store");
  store.linkup_energy_decay = 1563;
  await openDiscuss();
  await contains(".o-linkup-SidebarSection-networkView", {
    text: "Network view (60,000)",
  });
  await getService("action").doAction(
    "mail_linkup_network.action_linkup_network"
  );
  await contains(`${VIEW}-energyValue`, { text: "59,000" });
  expect(store.linkupEnergy).toBe(59000);
});
