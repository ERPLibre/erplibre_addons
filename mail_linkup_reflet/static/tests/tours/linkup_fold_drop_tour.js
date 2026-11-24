import { registry } from "@web/core/registry";

/**
 * Sam, in French, lands in the Reflet view, chooses Emotions and France,
 * fills the card and declares the exchange in person, then folds the card
 * with a double-click (LU-F-015) and drops the token on France, which sends
 * it (LU-F-016 RM1); the link of the sent reflection opens the conversation
 * of France, where the card waits for her confirmation.
 */
registry.category("web_tour.tours").add("linkup_fold_drop_tour", {
  steps: () => [
    {
      trigger:
        ".o-linkup-RefletView .o-linkup-HelpBar-category[data-code='emotions']",
      run: "click",
    },
    {
      trigger:
        ".o-linkup-RefletView-contact:contains(France) .o-linkup-RefletView-contactSelect",
      run: "click",
    },
    {
      trigger: ".o-linkup-RefletView-recipient:contains(France)",
    },
    {
      trigger: ".o-linkup-RefletForm-youSaid",
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
      trigger: ".o-linkup-RefletForm-fold:contains(Plier)",
    },
    {
      trigger:
        ".o-linkup-RefletForm-title:contains(Tu m'as parlé de tes émotions)",
      run: "dblclick",
    },
    {
      trigger: ".o-linkup-RefletView-token:focus svg[data-code='emotions']",
    },
    {
      trigger: ".o-linkup-RefletView-token",
      run: (helpers) =>
        helpers.drag_and_drop(".o-linkup-RefletView-contact:contains(France)", {
          position: { top: 12, left: 40 },
          relative: true,
        }),
    },
    {
      trigger: ".o-linkup-RefletView-notice:contains(France)",
    },
    {
      trigger: ".o-linkup-RefletView-placeholder",
    },
    {
      trigger: ".o-linkup-RefletView-sentChat:focus",
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
