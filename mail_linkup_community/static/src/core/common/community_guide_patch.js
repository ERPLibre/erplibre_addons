import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";

import {LinkupGuideSheet} from "@mail_linkup_reflet/core/common/linkup_guide";

/**
 * The texts of the guide for the elements of the profile, of the banners
 * of the Reflet view, of NewLink by phone or code, of the report, of the
 * help in distress and of the console of the moderation, by the value of
 * their `data-linkup-guide`. `noShow` keeps "Show" from pressing an
 * element that writes: "Show" then gives it the focus.
 */
export function linkupCommunityGuideTexts() {
    return {
        "community-consent": {
            title: _t("Accept"),
            text: _t("The consents your account needs before a first reflection, each one apart."),
            behavior: _t(
                "Outside the guide, this button records the consents checked above, with their date and version."
            ),
            noShow: true,
        },
        "community-verify": {
            title: _t("Send the link again"),
            text: _t("A new link that confirms your email address, valid 24 hours."),
            behavior: _t("Outside the guide, this button sends the link; a second one waits a few minutes."),
            noShow: true,
        },
        "newlink-channel": {
            title: _t("How to reach this person"),
            text: _t(
                "By email, LinkUp sends the link; by phone, you send a share link yourself; by code, the member who gave it receives the reflection inside LinkUp."
            ),
            behavior: _t("Outside the guide, the choice changes the field below."),
        },
        "newlink-copy": {
            title: _t("Copy the link"),
            text: _t("The share link of this invitation, shown once."),
            behavior: _t("Outside the guide, this button copies the link; send it by text message."),
        },
        "profile-name": {
            title: _t("Pseudonym"),
            text: _t("The name the other members see; it need not be unique, and your legal name is never asked."),
            behavior: _t("Outside the guide, “Save” records it."),
            noShow: true,
        },
        "profile-photo": {
            title: _t("Photo"),
            text: _t("Only the members you share a confirmed link with see it; the others see your pseudonym."),
            behavior: _t("Outside the guide, this button opens the choice of an image."),
            noShow: true,
        },
        "profile-email": {
            title: _t("Email"),
            text: _t("Nobody else sees it. A new address is confirmed again by a link."),
            behavior: _t("Outside the guide, “Save” records it and sends the link."),
            noShow: true,
        },
        "profile-scope": {
            title: _t("Who may send me a first reflection"),
            text: _t("Nobody, people who have your code, or people who also know your email address."),
            behavior: _t("Outside the guide, the choice is recorded at once."),
            noShow: true,
        },
        "profile-code": {
            title: _t("My personal code"),
            text: _t("Give it to a person you met: with it, they send you a first reflection."),
            behavior: _t("Outside the guide, “New code” replaces it; the former one stops working."),
            noShow: true,
        },
        "profile-notices": {
            title: _t("Decisions of the moderation about me"),
            text: _t(
                "What the moderation decided after a report about you, and why; never who reported nor what they wrote."
            ),
            behavior: _t(
                "Outside the guide, “Contest this decision” opens a short text; another moderator reviews it."
            ),
            noShow: true,
        },
        "profile-reports": {
            title: _t("My reports"),
            text: _t(
                "The reports you made and where each one stands; the member you reported never learns it was you."
            ),
            behavior: _t("Nothing to press: the list follows the moderation."),
        },
        "profile-blocked": {
            title: _t("Blocked members"),
            text: _t("The members who can no longer reach you; they are not told."),
            behavior: _t("Outside the guide, “Unblock” lifts the block at once."),
            noShow: true,
        },
        "help-now": {
            title: _t("Need help now"),
            text: _t(
                "LinkUp is not an emergency service: the help resources of the territory, set by the administrator, come first."
            ),
            behavior: _t("These resources stay in the LinkUp help at all times; nothing is sent."),
        },
        "report-reason": {
            title: _t("Reason of the report"),
            text: _t("Nine reasons. A threat, a minor in danger or a person in distress are urgent."),
            behavior: _t(
                "An urgent reason tells the moderators at once and puts the report first; a member never sets the urgency."
            ),
        },
        "report-send": {
            title: _t("Send the report"),
            text: _t("The moderation receives it; the reported member never learns who reported."),
            behavior: _t("Outside the guide, this button sends the report and shows the acknowledgement."),
            noShow: true,
        },
        "moderation-summary": {
            title: _t("Counters of the queue"),
            text: _t("The reports to process, the urgent ones and the late ones, and the delay shown to the members."),
            behavior: _t("They follow the queue: an urgent report adds to them at once."),
        },
        "moderation-scope": {
            title: _t("To process or closed"),
            text: _t("The reports waiting for a decision, or the latest closed ones."),
            behavior: _t("Outside the guide, the choice reloads the list."),
        },
        "moderation-queue": {
            title: _t("Queue of the reports"),
            text: _t(
                "Urgent reports first, then by date. A report you made, about you, or about a member you share a link with is never in it."
            ),
            behavior: _t("Outside the guide, the reason opens the report, without its content."),
        },
        "moderation-steps": {
            title: _t("States of the report"),
            text: _t("New, In review, then Actioned or Dismissed; Appealed when the member contests the decision."),
            behavior: _t("“Take the report” moves it to In review and assigns it to you."),
        },
        "moderation-take": {
            title: _t("Take the report"),
            text: _t("Assigns the report to you: you then decide."),
            behavior: _t("Outside the guide, this button takes the report; the audit log tells it."),
            noShow: true,
        },
        "moderation-decisions": {
            title: _t("Decisions"),
            text: _t(
                "Dismiss, hide the content, warn, suspend for some days, or ban: the account is closed and a hash of its address kept 24 months."
            ),
            behavior: _t(
                "Each decision needs its reason, written to the audit log; the member is told of it and of the possible appeal."
            ),
            noShow: true,
        },
        "moderation-content": {
            title: _t("Reported content (logged access)"),
            text: _t("Only the reported content and its immediate context, never the rest of the conversation."),
            behavior: _t("Showing the content adds a row to the audit log, visible to the other moderators."),
            noShow: true,
        },
        "moderation-audit": {
            title: _t("Audit log"),
            text: _t("Who, when, what, why: every decision and every reading of content. Nobody changes it."),
            behavior: _t("Each decision and each reading of the content adds a row."),
        },
        "profile-export": {
            title: _t("Download my data"),
            text: _t(
                "A JSON file of everything LinkUp keeps about you: profile, consents, reflections, messages, points, links, reports."
            ),
            behavior: _t("Outside the guide, this button downloads the file; nobody else can download it."),
            noShow: true,
        },
        "profile-delete": {
            title: _t("Delete my account"),
            text: _t(
                "Your account is erased after a delay you can cancel: your pseudonym becomes “Deleted member”, your texts and messages are erased, your points stay without your name."
            ),
            behavior: _t("Outside the guide, this button asks for a confirmation, then sets the date of the deletion."),
            noShow: true,
        },
        "reflet-erase": {
            title: _t("Erase its content"),
            text: _t("A reflection you rejected lends you words you did not say: its texts can be erased for good."),
            behavior: _t("Outside the guide, this button asks for a confirmation."),
            noShow: true,
        },
        "profile-consents": {
            title: _t("My consents"),
            text: _t("Each consent, with the date and the version of the text you agreed to."),
            behavior: _t("Outside the guide, a switch grants or withdraws the consent at once."),
            noShow: true,
        },
    };
}

patch(LinkupGuideSheet.prototype, {
    get texts() {
        return linkupCommunityGuideTexts()[this.key] || super.texts;
    },
});
