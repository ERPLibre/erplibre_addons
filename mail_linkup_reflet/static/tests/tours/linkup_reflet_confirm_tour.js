import { registry } from "@web/core/registry";

const RECEIVED =
  ".o-mail-Message .o-linkup-RefletCard[data-kind='initial'][data-role='recipient']";

/**
 * France, in French, receives two reflections of Sam. On the first, the
 * focused card and the `←` key ask for a confirmation, then declare that
 * the exchange did not take place. On the second, `→` confirms it, and
 * "Oui, c'est exactement ça !" posts the exact answer with a word (T-18,
 * LU-F-021, LU-F-022, LU-F-023, LU-F-030, LU-NF-020).
 */
registry.category("web_tour.tours").add("linkup_reflet_confirm_tour", {
  steps: () => [
    {
      trigger: ".o-mail-Discuss-threadName[title='Sam']",
    },
    {
      trigger: `${RECEIVED}[data-state='sent']:has(.o-linkup-RefletCard-understood:contains(tu veux manger))`,
      run() {
        this.anchor.focus();
      },
    },
    {
      trigger: `${RECEIVED}:focus`,
      run: "press ArrowLeft",
    },
    {
      trigger: ".modal .o-linkup-RejectDialog-confirm",
      run: "click",
    },
    {
      trigger: `${RECEIVED}[data-state='rejected'] .o-linkup-RefletCard-footer:contains(Tu as indiqué que cet échange n'a pas eu lieu.)`,
    },
    {
      trigger: `${RECEIVED}[data-state='sent'] .o-linkup-RefletActions[data-mode='validate']`,
      run() {
        this.anchor.closest(".o-linkup-RefletCard").focus();
      },
    },
    {
      trigger: `${RECEIVED}[data-state='sent']:focus`,
      run: "press ArrowRight",
    },
    {
      trigger: `${RECEIVED}[data-state='confirmed'] .o-linkup-RefletCard-footer:contains(C'est un lien !)`,
    },
    {
      trigger: `${RECEIVED}[data-state='confirmed'] .o-linkup-RefletActions-exact:contains(c'est exactement ça)`,
      run: "click",
    },
    {
      trigger:
        ".o-linkup-RefletActions-form[data-form='exact'] .o-linkup-RefletActions-text",
      run: "edit C'est bien ça.",
    },
    {
      trigger:
        ".o-linkup-RefletActions-form[data-form='exact'] .o-linkup-RefletActions-send",
      run: "click",
    },
    {
      trigger:
        ".o-mail-Message .o-linkup-RefletCard[data-kind='answer_exact'][data-role='author'] .o-linkup-RefletCard-bodyText:contains(C'est bien ça.)",
    },
  ],
});
