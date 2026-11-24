import { registry } from "@web/core/registry";

const VIEW = ".o-linkup-NetworkView";

/**
 * Sam opens the Network view from the sidebar of Discuss: his three
 * contacts surround him, with the grey line of the two who show their
 * links. The line of the link with France opens its card with the energy
 * of "My partners", and a press outside closes it (LU-F-075 CA1). X3 keeps
 * his two strongest partners; a node opens the card of the link, the
 * energy bubble closes it, and "Back" returns to Discuss (LU-F-070 to
 * LU-F-076).
 */
registry.category("web_tour.tours").add("linkup_network_tour", {
  steps: () => [
    {
      trigger: ".o-linkup-SidebarSection-networkView",
      run: "click",
    },
    {
      trigger: `${VIEW}-canvas[data-level='x1'] ${VIEW}-node[data-index='2']`,
    },
    {
      trigger: `${VIEW}-canvas[data-grey-count='1']`,
    },
    {
      trigger: `${VIEW}-lineHit[aria-label='Link with France']`,
      run: "click",
    },
    {
      trigger: `${VIEW}-card[data-available='true'] ${VIEW}-cardEnergyValue:contains(32,450)`,
    },
    {
      trigger: `${VIEW}-card ${VIEW}-video`,
    },
    {
      trigger: `${VIEW}-card ${VIEW}-highlight`,
    },
    {
      trigger: `${VIEW}-row[data-user-id] ${VIEW}-rowValue:contains(32,450)`,
    },
    {
      trigger: `${VIEW}-summary`,
      run: "click",
    },
    {
      trigger: `${VIEW}:not(:has(${VIEW}-card))`,
    },
    {
      trigger: `${VIEW}-level[data-level='x3']`,
      run: "click",
    },
    {
      trigger: `${VIEW}-canvas[data-level='x3']:not(:has(${VIEW}-node[data-index='2'])) ${VIEW}-node[data-index='1']`,
    },
    {
      trigger: `${VIEW}-canvas[data-grey-count='0']`,
    },
    {
      trigger: `${VIEW}-node[data-index='0']`,
      run: "click",
    },
    {
      trigger: `${VIEW}-card[data-available='true'] ${VIEW}-call`,
    },
    {
      trigger: `${VIEW}-card ${VIEW}-openChat`,
    },
    {
      trigger: `${VIEW}-energy`,
      run: "click",
    },
    {
      trigger: `${VIEW}:not(:has(${VIEW}-card))`,
    },
    {
      trigger: `${VIEW}-row:contains(France)`,
      run: "click",
    },
    {
      trigger: `${VIEW}-card[data-available='true'] ${VIEW}-cardTitle:contains(France)`,
    },
    {
      trigger: `${VIEW}-cardClose`,
      run: "click",
    },
    {
      trigger: `${VIEW}:not(:has(${VIEW}-card))`,
    },
    {
      trigger: `${VIEW}-back`,
      run: "click",
    },
    {
      trigger: ".o-mail-Discuss .o-linkup-SidebarSection-networkView",
    },
  ],
});
