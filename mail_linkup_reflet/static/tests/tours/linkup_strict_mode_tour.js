import { registry } from "@web/core/registry";

/**
 * Sam, in French, opens the direct conversation of France, whom no
 * confirmed reflection links yet, in strict mode: the banner of the start
 * rule stands in place of the text field, and "Faire un reflet" gives the
 * focus to the Help bar (T-08, LU-F-061 CA1).
 */
registry.category("web_tour.tours").add("linkup_strict_mode_tour", {
  steps: () => [
    {
      trigger: ".o-mail-Discuss-threadName[title='France']",
    },
    {
      trigger:
        ".o-linkup-StartRule[data-mode='strict'] .o-linkup-StartRule-title:contains(Cette conversation commence par un reflet)",
    },
    {
      trigger: ".o-mail-Composer-input:not(:visible)",
    },
    {
      trigger: ".o-linkup-StartRule-reflet:contains(Faire un reflet)",
      run: "click",
    },
    {
      trigger: ".o-linkup-HelpBar-category:focus",
    },
  ],
});
