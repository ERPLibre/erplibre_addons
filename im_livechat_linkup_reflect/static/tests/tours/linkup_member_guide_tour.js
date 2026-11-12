import { registry } from "@web/core/registry";

/**
 * A member opens Discuss for the first time: the last step of the
 * first-use tour proposes the guide of a first reflection, which opens a
 * conversation with the chatbot in Discuss; the member chooses Emotions,
 * types both texts in the composer, and the chatbot shows the review of
 * the draft (LU-F-125 RM5).
 */
registry.category("web_tour.tours").add("linkup_member_guide_tour", {
  steps: () => [
    {
      trigger: ".o-linkup-Tour[data-step='section'] .o-linkup-Tour-next",
      run: "click",
    },
    {
      trigger: ".o-linkup-Tour[data-step='help-bar'] .o-linkup-Tour-next",
      run: "click",
    },
    {
      trigger: ".o-linkup-Tour[data-step='free-text'] .o-linkup-Tour-next",
      run: "click",
    },
    {
      trigger: ".o-linkup-Tour[data-step='panel'] .o-linkup-Tour-next",
      run: "click",
    },
    {
      trigger: ".o-linkup-Tour[data-step='guide'] .o-linkup-Tour-guide",
      run: "click",
    },
    {
      trigger:
        ".o-linkup-GuideAnswers[data-step='linkup_category'] .o-linkup-GuideAnswers-answer:contains(Emotions)",
      run: "click",
    },
    {
      trigger: ".o-linkup-GuideAnswers[data-step='linkup_you_said']",
    },
    {
      trigger: ".o-mail-Composer-input",
      run: "edit The chores and a job wear me out",
    },
    {
      trigger: ".o-mail-Composer-input",
      run: "press Enter",
    },
    {
      trigger: ".o-linkup-GuideAnswers[data-step='linkup_understood']",
    },
    {
      trigger: ".o-mail-Composer-input",
      run: "edit you are exhausted",
    },
    {
      trigger: ".o-mail-Composer-input",
      run: "press Enter",
    },
    {
      trigger: ".o-mail-Message:contains(Nothing is sent: your draft waits)",
    },
    {
      trigger: "body:not(:has(.o-linkup-GuideAnswers))",
    },
  ],
});
