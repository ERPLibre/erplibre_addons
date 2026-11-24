import { registry } from "@web/core/registry";

/** The widget lives in a shadow root of the page. */
const WIDGET = ".o-livechat-root:shadow";

const message = (text) => `${WIDGET} .o-mail-Message:contains("${text}")`;

const answer = (text) =>
  `${WIDGET} .o-linkup-ChatbotAnswer:contains("${text}")`;

/** Open the widget and wait for the choices of the welcome. */
const openWidget = [
  {
    trigger: `${WIDGET} .o-livechat-LivechatButton`,
    run: "click",
  },
  {
    trigger: message("What would you like to do?"),
  },
  {
    trigger: answer("Need help now"),
  },
];

// A visitor follows the reflection guide of the welcome (LU-F-125): the
// category, then the two texts, typed in the composer; then talks to a
// member (LU-F-127), who joins, and sends them the reflection of the guide,
// restored from the draft of the visitor, in strict mode.
registry.category("web_tour.tours").add("linkup_livechat_guide_tour", {
  steps: () => [
    ...openWidget,
    {
      trigger: answer("Try a guided reflection"),
      run: "click",
    },
    {
      trigger: `${WIDGET} .o-linkup-ChatbotAnswers-isGrid .o-linkup-ChatbotAnswer:contains("Emotions")`,
      run: "click",
    },
    {
      trigger: `${WIDGET} .o-mail-Composer-input[placeholder="You told me…"]`,
      run: "edit The chores and a job wear me out",
    },
    {
      trigger: `${WIDGET} .o-mail-Composer-input[placeholder="You told me…"]`,
      run: "press Enter",
    },
    {
      trigger: `${WIDGET} .o-mail-Composer-input[placeholder="I understood that…"]`,
      run: "edit you are exhausted",
    },
    {
      trigger: `${WIDGET} .o-mail-Composer-input[placeholder="I understood that…"]`,
      run: "press Enter",
    },
    {
      trigger: message("Here is your reflection."),
    },
    {
      trigger: message("Nothing is sent"),
    },
    {
      trigger: `${WIDGET} .o-mail-ChatWindow-command[title='Restart Conversation']`,
      run: "click",
    },
    {
      trigger: answer("Talk to a member"),
      run: "click",
    },
    {
      trigger: `${WIDGET} .o-linkup-StartRule[data-mode='strict']`,
    },
    {
      trigger: `${WIDGET} .o-linkup-StartRule-reflet`,
      run: "click",
    },
    {
      trigger: `${WIDGET} .o-linkup-RefletForm-youSaid`,
      run() {
        if (this.anchor.value !== "The chores and a job wear me out") {
          throw new Error(
            `The draft of the guide is not restored: ${this.anchor.value}`
          );
        }
      },
    },
    {
      trigger: `${WIDGET} .o-linkup-RefletForm-realWorld input[name='real_world_declared']`,
      run: "click",
    },
    {
      trigger: `${WIDGET} .o-linkup-RefletForm-send`,
      run: "click",
    },
    {
      trigger: `${WIDGET} .o-linkup-RefletCard[data-state='sent'][data-role='author']`,
    },
  ],
});

// A visitor presses "Need help now" under the welcome conversation
// (LU-F-126): the resources show at once and a person of the moderation
// joins the conversation.
registry.category("web_tour.tours").add("linkup_livechat_help_now_tour", {
  steps: () => [
    ...openWidget,
    {
      trigger: `${WIDGET} .o-linkup-LivechatHelp-button`,
      run: "click",
    },
    {
      trigger: `${WIDGET} .o-linkup-HelpNow-resources li:contains("9-8-8")`,
    },
    {
      trigger: `${WIDGET} .o-linkup-LivechatHelp-status:contains("A person of the moderation joins you")`,
    },
    {
      trigger: message("A person of the moderation joins you"),
    },
  ],
});

// A member reports a message of a person in distress (LU-F-126): the
// acknowledgement says that a person of the moderation joins, and the
// conversation of distress opens.
registry
  .category("web_tour.tours")
  .add("linkup_livechat_distress_report_tour", {
    steps: () => [
      {
        trigger: ".o-mail-Message:contains(Linkup distress message)",
        run: "hover && click .o-mail-Message:contains(Linkup distress message) [title='Expand']",
      },
      {
        trigger:
          ".o-mail-Message-moreMenu [title='Report'], .o-mail-Message:contains(Linkup distress message) [title='Report']",
        run: "click",
      },
      {
        trigger: "#o-linkup-ReportDialog-reason-distress",
        run: "click",
      },
      {
        trigger: ".o-linkup-ReportDialog-send",
        run: "click",
      },
      {
        trigger:
          ".o-linkup-ReportDialog-distress:contains(A person of the moderation joins you)",
      },
      {
        trigger: ".o-mail-Thread:contains(not an emergency service)",
      },
      {
        trigger: ".o-linkup-ReportDialog-close",
        run: "click",
      },
      {
        trigger: "body:not(:has(.o-linkup-ReportDialog))",
      },
    ],
  });
