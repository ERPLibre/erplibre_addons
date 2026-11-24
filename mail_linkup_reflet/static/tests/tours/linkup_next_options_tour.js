import { registry } from "@web/core/registry";

const OPTIONS =
  ".o-mail-Message .o-linkup-RefletCard[data-kind='answer_exact'][data-role='recipient'] .o-linkup-RefletActions[data-mode='options']";

/**
 * Sam, in French, holds the three options after the exact answer of
 * France. "Parler de soi" shows the call and the video call first, then the
 * theme and the text; Besoins fills "J'ai besoin de :", and the sending
 * gives France a disclosure to reformulate (P4, LU-F-040, LU-F-043 CA1,
 * LU-F-044 RM1).
 */
registry.category("web_tour.tours").add("linkup_talk_about_oneself_tour", {
  steps: () => [
    {
      trigger: ".o-mail-Discuss-threadName[title='France']",
    },
    {
      trigger: `${OPTIONS} .o-linkup-RefletActions-end`,
    },
    {
      trigger: `${OPTIONS} .o-linkup-RefletActions-self`,
      run: "click",
    },
    {
      trigger:
        ".o-linkup-RefletActions-form[data-form='self'] .o-linkup-RefletActions-video",
      run() {
        const form = this.anchor.closest(".o-linkup-RefletActions-form");
        const call = form.querySelector(".o-linkup-RefletActions-call");
        const picker = form.querySelector(".o-linkup-CategoryPicker-option");
        const text = form.querySelector(".o-linkup-RefletActions-text");
        const following = Node.DOCUMENT_POSITION_FOLLOWING;
        if (
          !call ||
          !(call.compareDocumentPosition(picker) & following) ||
          !(call.compareDocumentPosition(text) & following)
        ) {
          throw new Error(
            "The call buttons do not come before the theme and the text."
          );
        }
      },
    },
    {
      trigger:
        ".o-linkup-RefletActions-form[data-form='self'] .o-linkup-CategoryPicker-option[data-code='needs']",
      run: "click",
    },
    {
      trigger:
        ".o-linkup-CategoryPicker-option[data-code='needs'][aria-pressed='true']",
      run() {
        const text = document.querySelector(
          ".o-linkup-RefletActions-text"
        ).value;
        if (!text.startsWith("J'ai besoin de :")) {
          throw new Error(`The starter of Besoins is missing: "${text}"`);
        }
      },
    },
    {
      trigger: ".o-linkup-RefletActions-text",
      run: "edit J'ai besoin de : plus de concentration.",
    },
    {
      trigger:
        ".o-linkup-RefletActions-form[data-form='self'] .o-linkup-RefletActions-send",
      run: "click",
    },
    {
      trigger:
        ".o-mail-Message .o-linkup-RefletCard[data-kind='self_disclosure'][data-role='author'] .o-linkup-RefletCard-bodyText:contains(plus de concentration)",
    },
  ],
});

/**
 * France, in French, holds the three options after an exact answer of Sam
 * to her reformulation. She reaches "Terminer ça là" with the keyboard: the
 * focused button opens its form on `Enter`, the closing sentence is
 * written for her, and `Enter` on the send button posts it (P4, LU-F-041,
 * LU-NF-020).
 */
registry.category("web_tour.tours").add("linkup_end_it_here_tour", {
  steps: () => [
    {
      trigger: ".o-mail-Discuss-threadName[title='Sam']",
    },
    {
      trigger: `${OPTIONS} .o-linkup-RefletActions-end`,
      run() {
        this.anchor.focus();
      },
    },
    {
      trigger: `${OPTIONS} .o-linkup-RefletActions-end:focus`,
      run: "press Enter",
    },
    {
      trigger:
        ".o-linkup-RefletActions-form[data-form='close'] .o-linkup-RefletActions-text",
      run() {
        if (this.anchor.value !== "Merci pour notre discussion.") {
          throw new Error(
            `The closing sentence is missing: "${this.anchor.value}"`
          );
        }
        this.anchor
          .closest("form")
          .querySelector(".o-linkup-RefletActions-send")
          .focus();
      },
    },
    {
      trigger:
        ".o-linkup-RefletActions-form[data-form='close'] .o-linkup-RefletActions-send:focus",
      run: "press Enter",
    },
    {
      trigger:
        ".o-mail-Message .o-linkup-RefletCard[data-kind='close'][data-role='author']",
    },
  ],
});
