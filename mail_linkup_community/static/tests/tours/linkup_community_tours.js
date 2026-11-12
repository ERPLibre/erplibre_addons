import { registry } from "@web/core/registry";

// A new member accepts the consents of the banner of the Reflet view
// (LU-F-111): the button waits for the three boxes.
registry.category("web_tour.tours").add("linkup_consent_tour", {
  steps: () => [
    {
      trigger:
        ".o-linkup-ConsentNotice .o-linkup-ConsentNotice-accept:disabled",
    },
    {
      trigger: "#o-linkup-ConsentNotice-terms",
      run: "click",
    },
    {
      trigger: "#o-linkup-ConsentNotice-privacy",
      run: "click",
    },
    {
      trigger: "#o-linkup-ConsentNotice-sensitive_data",
      run: "click",
    },
    {
      trigger: ".o-linkup-ConsentNotice-accept:enabled",
      run: "click",
    },
    {
      trigger: ".o-linkup-CommunityNotice-notice",
    },
    {
      trigger: ".o-linkup-RefletView:not(:has(.o-linkup-ConsentNotice))",
    },
  ],
});

// The profile from the menu of the avatar (LU-F-080, LU-F-082): the
// pseudonym, the first-reflection scope, the withdrawal of a consent.
registry.category("web_tour.tours").add("linkup_profile_tour", {
  steps: () => [
    {
      trigger: ".o-linkup-ProfileMenu-toggle",
      run: "click",
    },
    {
      trigger:
        ".o-linkup-ProfileMenu-entry[data-entry='privacy']:not([aria-disabled])",
      run: "click",
    },
    {
      trigger: "#o-linkup-Profile-privacyTitle:focus",
    },
    {
      trigger: ".o-linkup-Profile-name",
      run: "edit Camille L.",
    },
    {
      trigger: ".o-linkup-Profile-saveIdentity",
      run: "click",
    },
    {
      trigger: ".o-linkup-Profile-identity .o-linkup-Profile-notice",
    },
    {
      trigger: "#o-linkup-Profile-scope-email_or_code",
      run: "click",
    },
    {
      trigger:
        ".o-linkup-Profile-privacy .o-linkup-Profile-notice:contains(Saved.)",
    },
    {
      trigger: ".o-linkup-Profile-code",
    },
    {
      trigger: "#o-linkup-Profile-consent-sensitive_data:checked",
      run: "click",
    },
    {
      trigger:
        ".o-linkup-Profile-privacy .o-linkup-Profile-notice:contains(Consent withdrawn.)",
    },
    {
      trigger: "#o-linkup-Profile-consent-sensitive_data:not(:checked)",
    },
  ],
});

// A member reports a message from its menu (LU-F-114 RM1): the reason, an
// optional comment, the acknowledgement.
registry.category("web_tour.tours").add("linkup_report_tour", {
  steps: () => [
    {
      trigger: ".o-mail-Message:contains(Linkup tour message)",
      run: "hover && click .o-mail-Message:contains(Linkup tour message) [title='Expand']",
    },
    {
      trigger:
        ".o-mail-Message-moreMenu [title='Report'], .o-mail-Message:contains(Linkup tour message) [title='Report']",
      run: "click",
    },
    {
      trigger: "#o-linkup-ReportDialog-reason-harassment",
      run: "click",
    },
    {
      trigger: ".o-linkup-ReportDialog-description",
      run: "edit Again and again.",
    },
    {
      trigger: ".o-linkup-ReportDialog-send",
      run: "click",
    },
    {
      trigger: ".o-linkup-ReportDialog-ack",
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

// A moderator processes the report in the console (LU-F-116): the content
// shown on demand, the report taken, a warning with its reason, the audit
// log.
registry.category("web_tour.tours").add("linkup_moderation_tour", {
  steps: () => [
    {
      trigger: ".o-linkup-Moderation-row .o-linkup-Moderation-open",
      run: "click",
    },
    {
      trigger: ".o-linkup-Moderation-showContent",
      run: "click",
    },
    {
      trigger: ".o-linkup-Moderation-reported:contains(Linkup tour message)",
    },
    {
      trigger: ".o-linkup-Moderation-auditRow[data-action='content_read']",
    },
    {
      trigger: ".o-linkup-Moderation-take",
      run: "click",
    },
    {
      trigger: ".o-linkup-Moderation-reason",
      run: "edit Insults in the group.",
    },
    {
      trigger: ".o-linkup-Moderation-decide-warn",
      run: "click",
    },
    {
      trigger: ".o-linkup-Moderation-auditRow[data-action='warn']",
    },
    {
      trigger: ".o-linkup-Moderation-back",
      run: "click",
    },
    {
      trigger: ".o-linkup-Moderation-empty",
    },
  ],
});

// A person signs up on /web/signup once the website holds an ALTCHA key:
// the widget of the form solves the proof of work, then the page answers
// "check your mailbox".
registry.category("web_tour.tours").add("linkup_signup_altcha_tour", {
  steps: () => [
    {
      trigger: ".oe_signup_form input[name='login']",
      run: "edit camille.tour@example.com",
    },
    {
      trigger: ".oe_signup_form input[name='name']",
      run: "edit Camille",
    },
    {
      trigger: ".oe_signup_form input[name='password']",
      run: "edit linkup-Signup-2026",
    },
    {
      trigger: ".oe_signup_form input[name='confirm_password']",
      run: "edit linkup-Signup-2026",
    },
    {
      trigger: "#linkup_terms",
      run: "click",
    },
    {
      trigger: "#linkup_privacy",
      run: "click",
    },
    {
      trigger: "#linkup_sensitive_data",
      run: "click",
    },
    {
      trigger: "#linkup_adult",
      run: "click",
    },
    {
      trigger: "#linkup_age_bracket",
      run: "select 25_34",
    },
    {
      trigger: "#linkup_resides_canada",
      run: "click",
    },
    {
      // The empty label of the row of the widget is decorative.
      trigger:
        ".oe_signup_form .o_altcha_widget_container label.s_website_form_label[aria-hidden='true']",
    },
    {
      trigger: ".oe_signup_form altcha-widget input[type='checkbox']",
      run: "click",
    },
    {
      trigger: ".oe_signup_form altcha-widget [data-state='verified']",
    },
    {
      trigger: ".oe_signup_form button[type='submit']",
      run: "click",
      expectUnloadPage: true,
    },
    {
      trigger: ".o-linkup-SignupSentPage",
    },
  ],
});
