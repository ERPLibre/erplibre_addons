import { registry } from "@web/core/registry";

/**
 * France, in French, opens Discuss for the first time: the first-use tour
 * starts at step 1 of 5, outlines each of its elements, tells that free
 * text is locked in strict mode, opens the LinkUp panel at its fourth step,
 * and goes away once finished (T-25, LU-F-083).
 */
registry.category("web_tour.tours").add("linkup_first_use_driver_tour", {
  steps: () => [
    {
      trigger:
        ".o-linkup-Tour[data-step='section'] .o-linkup-Tour-step:contains(Étape 1 sur 5)",
    },
    {
      trigger: ".o-linkup-SidebarSection.o-linkup-Tour-anchor",
    },
    {
      trigger: ".o-linkup-Tour[data-step='section'] .o-linkup-Tour-next",
      run: "click",
    },
    {
      trigger:
        ".o-linkup-RefletComposer .o-linkup-HelpBar.o-linkup-Tour-anchor",
    },
    {
      trigger: ".o-linkup-Tour[data-step='help-bar'] .o-linkup-Tour-next",
      run: "click",
    },
    {
      trigger:
        ".o-linkup-Tour[data-step='free-text'] .o-linkup-Tour-title:contains(Texte libre verrouillé)",
    },
    {
      trigger: ".o-linkup-Tour[data-step='free-text'] .o-linkup-Tour-next",
      run: "click",
    },
    {
      trigger: ".o-linkup-Panel-content.o-linkup-Tour-anchor",
    },
    {
      trigger: ".o-linkup-Tour[data-step='panel'] .o-linkup-Tour-next",
      run: "click",
    },
    {
      trigger: ".o-linkup-GuideButton.o-linkup-Tour-anchor",
    },
    {
      trigger:
        ".o-linkup-Tour[data-step='guide'] .o-linkup-Tour-next:contains(Terminer)",
      run: "click",
    },
    {
      trigger: "body:not(:has(.o-linkup-Tour))",
    },
  ],
});
