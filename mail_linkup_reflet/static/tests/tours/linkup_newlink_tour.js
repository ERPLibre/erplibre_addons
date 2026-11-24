import { registry } from "@web/core/registry";

/**
 * Sam, in French, opens "+ NewLink" in the Reflet view, gives the address
 * and the name of a person who is not a member, writes the card of their
 * exchange, reads the preview of the email, which leaves the texts out,
 * and sends: the masked address shows, and the invitation waits in the
 * list under the contacts (T-29, LU-F-020 CA1).
 */
registry.category("web_tour.tours").add("linkup_newlink_tour", {
  steps: () => [
    {
      trigger: ".o-linkup-RefletView-newlink",
      run: "click",
    },
    {
      trigger: ".o-linkup-Newlink-email:focus",
      run: "edit camille.nouvelle@example.com",
    },
    {
      trigger: ".o-linkup-Newlink-name",
      run: "edit Camille",
    },
    {
      trigger: ".o-linkup-Newlink-next",
      run: "click",
    },
    {
      trigger:
        ".o-linkup-Newlink .o-linkup-HelpBar-category[data-code='emotions']",
      run: "click",
    },
    {
      trigger:
        ".o-linkup-RefletForm-title:contains(Tu m'as parlé de tes émotions)",
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
      trigger: ".o-linkup-RefletForm-send:enabled",
      run: "click",
    },
    {
      trigger:
        ".o-linkup-Newlink-preview .o-linkup-Newlink-noText:contains(Camille)",
    },
    {
      trigger: ".o-linkup-Newlink-mail:not(:contains(tu es épuisée))",
    },
    {
      trigger: ".o-linkup-Newlink-send:enabled",
      run: "click",
    },
    {
      trigger: ".o-linkup-Newlink-sentTo:contains(c***@example.com)",
    },
    {
      trigger: ".o-linkup-RefletView-invitation:contains(Camille)",
    },
  ],
});
