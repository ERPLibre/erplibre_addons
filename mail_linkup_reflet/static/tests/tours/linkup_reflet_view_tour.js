import { registry } from "@web/core/registry";

/**
 * Sam, in French, lands in the Reflet view, his home action, drags the
 * Emotions category onto France, fills the form that opens for her and
 * sends; the link of the sent reflection opens the conversation of France,
 * where the card waits for her confirmation (T-24, LU-F-010 to 016).
 */
registry.category("web_tour.tours").add("linkup_reflet_view_tour", {
  steps: () => [
    {
      trigger: ".o-linkup-RefletView-contact:contains(France)",
    },
    {
      trigger:
        ".o-linkup-RefletView .o-linkup-HelpBar-category[data-code='emotions']",
      run: (helpers) =>
        helpers.drag_and_drop(".o-linkup-RefletView-contact:contains(France)", {
          position: { top: 12, left: 40 },
          relative: true,
        }),
    },
    {
      trigger: ".o-linkup-RefletView-recipient:contains(France)",
    },
    {
      trigger:
        ".o-linkup-RefletForm-title:contains(Tu m'as parlé de tes émotions)",
    },
    {
      trigger: ".o-linkup-RefletForm-youSaid:focus",
      run: "edit que la charge des tâches ménagères plus un travail t'épuise.",
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
      trigger: ".o-linkup-RefletView-notice:contains(France)",
    },
    {
      trigger: ".o-linkup-RefletView-placeholder",
    },
    {
      trigger: ".o-linkup-RefletView-sentChat",
      run: "click",
    },
    {
      trigger: ".o-mail-Discuss-threadName[title='France']",
    },
    {
      trigger:
        ".o-mail-Message .o-linkup-RefletCard[data-state='sent'][data-role='author'] .o-linkup-RefletCard-understood:contains(tu es épuisée.)",
    },
  ],
});
