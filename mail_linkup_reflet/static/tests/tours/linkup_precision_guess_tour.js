import { registry } from "@web/core/registry";

const PRECISION = ".o-mail-Message .o-linkup-RefletCard[data-kind='precision']";

/**
 * France, in French, answers a confirmed reflection of Sam with "Je
 * voudrais préciser…": she hides Buts then Émotions, the text of her
 * precision staying empty until she writes it, and sends (LU-F-031,
 * LU-F-032 CA1). She uses the keyboard only: each button takes the focus
 * as `Tab` gives it, and `Enter` presses it (P3, LU-NF-020); Sam guesses
 * with the mouse below.
 */
registry.category("web_tour.tours").add("linkup_precision_send_tour", {
  steps: () => [
    {
      trigger: ".o-mail-Discuss-threadName[title='Sam']",
    },
    {
      trigger:
        ".o-mail-Message .o-linkup-RefletCard[data-state='confirmed'] .o-linkup-RefletActions-precise",
      run() {
        this.anchor.focus();
      },
    },
    {
      trigger: ".o-linkup-RefletActions-precise:focus",
      run: "press Enter",
    },
    {
      trigger:
        ".o-linkup-RefletActions-form[data-form='precision'] .o-linkup-CategoryPicker-option[data-code='goals']",
      run() {
        this.anchor.focus();
      },
    },
    {
      trigger: ".o-linkup-CategoryPicker-option[data-code='goals']:focus",
      run: "press Enter",
    },
    {
      trigger:
        ".o-linkup-CategoryPicker-option[data-code='goals'][aria-pressed='true']",
      run() {
        const text = document.querySelector(
          ".o-linkup-RefletActions-text"
        ).value;
        if (text !== "") {
          throw new Error(
            `A hidden theme filled the text of the precision: "${text}"`
          );
        }
      },
    },
    {
      trigger: ".o-linkup-CategoryPicker-option[data-code='emotions']",
      run() {
        this.anchor.focus();
      },
    },
    {
      trigger: ".o-linkup-CategoryPicker-option[data-code='emotions']:focus",
      run: "press Enter",
    },
    {
      trigger:
        ".o-linkup-CategoryPicker-option[data-code='emotions'][aria-pressed='true']",
    },
    {
      trigger: ".o-linkup-RefletActions-text",
      run: "edit Mon but est vraiment de trouver une personne pour faire avancer cette situation…",
    },
    {
      trigger:
        ".o-linkup-RefletActions-form[data-form='precision'] .o-linkup-RefletActions-send",
      run() {
        this.anchor.focus();
      },
    },
    {
      trigger:
        ".o-linkup-RefletActions-form[data-form='precision'] .o-linkup-RefletActions-send:focus",
      run: "press Enter",
    },
    {
      trigger: `${PRECISION}[data-role='author'][data-guess-state='pending'] .o-linkup-RefletCard-footer:contains(Thème caché : Buts)`,
    },
  ],
});

/**
 * Sam, in French, receives the precision of France: its theme is hidden,
 * and the Store of his web client holds no hidden theme of it. He guesses
 * Buts, which is found and revealed; the three options follow, and
 * "Continuer le reflet" with Demande d'action starts his reformulation
 * with "Ta demande d'action est que :" (LU-F-031 RM5, LU-F-033, LU-F-034,
 * LU-F-040, LU-F-042, LU-F-032 CA2).
 */
registry.category("web_tour.tours").add("linkup_precision_guess_tour", {
  steps: () => [
    {
      trigger: ".o-mail-Discuss-threadName[title='France']",
    },
    {
      trigger: `${PRECISION}[data-role='recipient'][data-guess-state='pending'] .o-linkup-RefletCard-header svg[data-code='hidden']`,
      run() {
        const store = odoo.__WOWL_DEBUG__.root.env.services["mail.store"];
        const precisions = Object.values(store["linkup.reflet"].records).filter(
          (reflet) => reflet.kind === "precision"
        );
        if (!precisions.length) {
          throw new Error("The Store holds no precision.");
        }
        for (const reflet of precisions) {
          if (
            reflet.revealed_category_ids.length ||
            reflet.primary_category_id ||
            reflet.guessed_category_id
          ) {
            throw new Error(
              "The Store of the recipient holds a hidden theme before the guess."
            );
          }
        }
        const header = this.anchor.closest(".o-linkup-RefletCard-header");
        if (header.querySelector("[data-code]:not([data-code='hidden'])")) {
          throw new Error(
            "The card of the recipient shows a hidden theme before the guess."
          );
        }
      },
    },
    {
      trigger: `${PRECISION} .o-linkup-RefletActions[data-mode='guess'] .o-linkup-CategoryPicker-option[data-code='goals']`,
      run: "click",
    },
    {
      trigger: `${PRECISION} .o-linkup-RefletActions-guess:enabled`,
      run: "click",
    },
    {
      trigger: `${PRECISION}[data-guess-state='found'] .o-linkup-RefletCard-header svg[data-code='goals']`,
    },
    {
      trigger: `${PRECISION} .o-linkup-RefletActions[data-mode='options'] .o-linkup-RefletActions-continue`,
      run: "click",
    },
    {
      trigger:
        ".o-linkup-RefletActions-form[data-form='continue'] .o-linkup-CategoryPicker-option[data-code='action']",
      run: "click",
    },
    {
      trigger:
        ".o-linkup-CategoryPicker-option[data-code='action'][aria-pressed='true']",
      run() {
        const text = document.querySelector(
          ".o-linkup-RefletActions-text"
        ).value;
        if (!text.startsWith("Ta demande d'action est que :")) {
          throw new Error(
            `The starter of Demande d'action is missing: "${text}"`
          );
        }
      },
    },
    {
      trigger: ".o-linkup-RefletActions-text",
      run: "edit Ta demande d'action est que : tu trouves quelqu'un pour avancer.",
    },
    {
      trigger:
        ".o-linkup-RefletActions-form[data-form='continue'] .o-linkup-RefletActions-send",
      run: "click",
    },
    {
      trigger:
        ".o-mail-Message .o-linkup-RefletCard[data-kind='continue'][data-role='author'] .o-linkup-RefletCard-header svg[data-code='action']",
    },
  ],
});
