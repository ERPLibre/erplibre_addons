import { registry } from "@web/core/registry";

/**
 * France, in French, opens the LinkUp panel of her conversation with Sam
 * and puts him in the light with the mouse, after its confirmation (P5,
 * LU-F-050). The panel shows the highlight once the bus brings it, which
 * the test server does not run: the Python test reads the record.
 */
registry.category("web_tour.tours").add("linkup_happiness_send_tour", {
  steps: () => [
    {
      trigger: ".o-mail-Discuss-threadName[title='Sam']",
    },
    {
      trigger: ".o-mail-Discuss-header button[name='linkup-panel']",
      run: "click",
    },
    {
      trigger: ".o-linkup-Panel-highlightButton[aria-pressed='false']",
      run: "click",
    },
    {
      trigger: ".o-linkup-Panel-highlightConfirmButton",
      run: "click",
    },
    {
      trigger:
        ".o-linkup-Panel-happiness:not(:has(.o-linkup-Panel-highlightConfirm)):not(:has(.o-linkup-Panel-highlightError)) .o-linkup-Panel-highlightButton",
    },
  ],
});

/**
 * Sam, in French, lands in the Reflet view: the avatar of France rings his
 * own, and France in his contacts. With the keyboard only, he opens the
 * happiness field, walks its list and puts France in the light in turn
 * (P5, LU-F-050 CA2, LU-F-051, LU-NF-020).
 */
registry.category("web_tour.tours").add("linkup_happiness_receive_tour", {
  steps: () => [
    {
      trigger: ".o-linkup-RefletView-highlights .o-linkup-Highlights-avatar",
    },
    {
      trigger:
        ".o-linkup-RefletView-contact:contains(France) .o-linkup-RefletView-avatar.o-linkup-isHighlighted",
    },
    {
      trigger: ".o-linkup-RefletView-happiness:enabled",
      run() {
        this.anchor.focus();
      },
    },
    {
      trigger: ".o-linkup-RefletView-happiness:focus",
      run: "press Enter",
    },
    {
      trigger: ".o-linkup-RefletView-happinessList:focus",
      run: "press End",
    },
    {
      trigger:
        ".o-linkup-RefletView-happinessList .o-linkup-RefletView-option.o-isActive:contains(France)",
      run: "press Enter",
    },
    {
      trigger: ".o-linkup-RefletView-happinessNotice:contains(France)",
    },
  ],
});
