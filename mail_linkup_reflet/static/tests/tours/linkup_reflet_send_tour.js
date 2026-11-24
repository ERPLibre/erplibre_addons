import { registry } from "@web/core/registry";

/**
 * Sam, in French, opens the direct conversation of France, chooses
 * Emotions in the Help bar, fills the form, declares the exchange in
 * person and sends: the card of the carrier message shows the reflection
 * waiting for the confirmation of France (T-03, T-28, LU-F-012 to 017).
 */
registry.category("web_tour.tours").add("linkup_reflet_send_tour", {
  steps: () => [
    {
      trigger: ".o-mail-Discuss-threadName[title='France']",
    },
    {
      trigger: ".o-linkup-HelpBar-category[data-code='emotions']",
      run: "click",
    },
    {
      trigger:
        ".o-linkup-RefletForm-title:contains(Tu m'as parlé de tes émotions)",
    },
    {
      trigger: ".o-linkup-RefletForm-youSaid",
      run: "edit que la charge de s'occuper de toutes les tâches ménagères plus un travail t'épuise.",
    },
    {
      trigger: ".o-linkup-RefletForm-understood",
      run: "edit tu es épuisée.",
    },
    {
      trigger: ".o-linkup-RefletForm-realWorld input[type='checkbox']",
      run: "click",
    },
    {
      trigger: ".o-linkup-RefletForm-send:enabled",
      run: "click",
    },
    {
      trigger: ".o-linkup-RefletComposer-notice:contains(France)",
    },
    {
      trigger:
        ".o-mail-Message .o-linkup-RefletCard[data-state='sent'][data-role='author'] .o-linkup-RefletCard-badge:contains(En attente)",
    },
    {
      trigger:
        ".o-mail-Message .o-linkup-RefletCard .o-linkup-RefletCard-title:contains(Tu m'as parlé de tes émotions)",
    },
    {
      trigger:
        ".o-mail-Message .o-linkup-RefletCard-understood:contains(tu es épuisée.)",
    },
  ],
});
