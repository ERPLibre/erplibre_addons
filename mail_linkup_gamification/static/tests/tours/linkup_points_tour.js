import { registry } from "@web/core/registry";

const RECEIVED =
  ".o-mail-Message .o-linkup-RefletCard[data-kind='initial'][data-role='recipient']";

/**
 * France, in French, confirms the reflection Sam sent her: "+1000" rises
 * on the screen and is announced; "Mes points", opened from the sidebar of
 * Discuss, lists the confirmation shared with Sam (LU-F-091, LU-F-103).
 */
registry.category("web_tour.tours").add("linkup_points_confirm_tour", {
  steps: () => [
    {
      trigger: ".o-mail-Discuss-threadName[title='Sam']",
    },
    {
      trigger: `${RECEIVED}[data-state='sent'] .o-linkup-RefletActions-confirm`,
      run: "click",
    },
    {
      trigger:
        ".o-linkup-PointsBurst[data-kind='gain'][data-points='1000']:contains(C'est un lien !)",
    },
    {
      trigger: ".o-linkup-PointsOverlay-live:contains(Tu gagnes)",
    },
    {
      trigger: ".o-linkup-SidebarSection-myPoints",
      run: "click",
    },
    {
      trigger:
        ".o-linkup-MyPoints-line[data-code='reflect_confirmed'] .o-linkup-MyPoints-lineCounterpart:contains(Sam)",
    },
    {
      trigger: ".o-linkup-MyPoints-linePoints:contains(1)",
    },
  ],
});

/**
 * Sam opens "Mes points" from his energy in the Reflet view: the
 * confirmation and the sending of his reflection, both shared with
 * France, are paid.
 */
registry.category("web_tour.tours").add("linkup_points_author_tour", {
  steps: () => [
    {
      trigger: ".o-linkup-RefletView .o-linkup-Energy-bubble",
      run: "click",
    },
    {
      trigger:
        ".o-linkup-MyPoints-line[data-code='reflect_confirmed'] .o-linkup-MyPoints-lineCounterpart:contains(France)",
    },
    {
      trigger:
        ".o-linkup-MyPoints-line[data-code='reflect_sent'] .o-linkup-MyPoints-lineCounterpart:contains(France)",
    },
    {
      trigger: ".o-linkup-MyPoints-rankName:contains(Étincelle)",
    },
  ],
});
