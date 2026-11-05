import { registry } from "@web/core/registry";

/**
 * Sam, in French, writes and sends a reflection from the Reflet view with
 * the keyboard only (T-18, P1, LU-F-016 RM2, LU-NF-020): `Enter` on
 * Emotions of the Help bar opens the card with the focus in its first
 * field; `Tab` and `Shift+Tab` walk the fields up to "Envoyer à…", whose
 * `Enter` opens the list of contacts; `Enter` there chooses France, who
 * requires the declaration of the exchange in person: the focus lands on
 * it, `Space` checks it and `Enter` sends. The focus then reaches the link
 * of the card sent, whose `Enter` opens the conversation of France. France
 * confirms with the arrows in `linkup_reflet_confirm_tour` (P2).
 */
registry.category("web_tour.tours").add("linkup_keyboard_only_tour", {
  steps: () => [
    {
      trigger:
        ".o-linkup-RefletView .o-linkup-HelpBar-category[data-code='emotions']",
      run() {
        this.anchor.focus();
      },
    },
    {
      trigger: ".o-linkup-HelpBar-category[data-code='emotions']:focus",
      run: "press Enter",
    },
    {
      trigger: ".o-linkup-RefletForm-youSaid:focus",
      run: "edit que la charge des tâches ménagères plus un travail t'épuise.",
    },
    {
      trigger: ".o-linkup-RefletForm-youSaid:focus",
      run: "press Tab",
    },
    {
      trigger: ".o-linkup-RefletForm-understood:focus",
      run: "edit tu es épuisée.",
    },
    {
      trigger: ".o-linkup-RefletForm-understood:focus",
      run: "press Shift+Tab",
    },
    {
      trigger: ".o-linkup-RefletForm-youSaid:focus",
      run: "press Shift+Tab",
    },
    {
      trigger: ".o-linkup-RefletView-sendTo:focus",
      run: "press Enter",
    },
    {
      trigger:
        ".o-linkup-RefletView-picker:focus .o-linkup-RefletView-option.o-isActive:contains(France)",
      run: "press Enter",
    },
    {
      trigger: ".o-linkup-RefletForm-realWorld input[type='checkbox']:focus",
      run: "press Space",
    },
    {
      trigger:
        ".o-linkup-RefletForm-realWorld input[type='checkbox']:checked:focus",
      run: "press Enter",
    },
    {
      trigger: ".o-linkup-RefletView-notice:contains(France)",
    },
    {
      trigger: ".o-linkup-RefletView-sentChat:focus",
      run: "press Enter",
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
