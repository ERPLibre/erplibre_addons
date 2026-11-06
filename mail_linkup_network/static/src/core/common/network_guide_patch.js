import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";

import {LinkupGuideSheet} from "@mail_linkup_reflet/core/common/linkup_guide";

/**
 * The texts of the guide for the elements of the Network view and of the
 * quick replies to a request for action, by the value of their
 * `data-linkup-guide`. `noShow` keeps "Show" from pressing an element that
 * would leave the view or write: "Show" then gives it the focus.
 *
 * @param {number} topCount the partners the density X3 keeps
 */
export function linkupNetworkGuideTexts(topCount) {
    return {
        "network-back": {
            title: _t("Back"),
            text: _t("Leave the Network view for the previous screen."),
            behavior: _t("Outside the guide, this button goes back; Escape does the same out of a field."),
            noShow: true,
        },
        "network-energy": {
            title: _t("My energy"),
            text: _t(
                "The total of the points your links earned you: confirmed reflections, exact reformulations, calls. It is neither a number of friends nor a number of messages."
            ),
            behavior: _t("Outside the guide, this bubble closes a card or a ranking and brings you back to the graph."),
        },
        "network-x1": {
            title: _t("X1 · two levels"),
            text: _t("Your direct links, and the grey lines between your contacts who both agree to show their links."),
            behavior: _t("Outside the guide, this button draws the graph at this density."),
        },
        "network-x2": {
            title: _t("X2 · direct links"),
            text: _t("Your direct links only: the grey lines disappear."),
            behavior: _t("Outside the guide, this button draws the graph at this density."),
        },
        "network-x3": {
            title: _t("X3 · the strongest"),
            text: _t("Your %(count)s strongest partners only.", {count: topCount}),
            behavior: _t("Outside the guide, this button draws the graph at this density."),
        },
        "network-cycle": {
            title: _t("Density of the graph"),
            text: _t(
                "X1: your links and the grey lines between your contacts; X2: your direct links; X3: your %(count)s strongest partners.",
                {count: topCount}
            ),
            behavior: _t("Outside the guide, each press goes to the next density: X1 → X2 → X3 → X1."),
        },
        "network-list": {
            title: _t("Rankings"),
            text: _t("“The most active” and “My partners”, among your contacts only."),
            behavior: _t(
                "Outside the guide, each press shows “The most active”, then “My partners”, then the graph again; the energy bubble also brings the graph back."
            ),
        },
        "network-center": {
            title: _t("You, in the centre"),
            text: _t(
                "The graph is always centred on you: each line goes from you to a person you share a confirmed link with."
            ),
            behavior: _t("It does not move."),
        },
        "network-node": {
            title: _t("A person"),
            text: _t(
                "A circle is a person you share a confirmed link with; the stronger the link, the larger the circle."
            ),
            behavior: _t(
                "Outside the guide, pressing it opens the card of the link. The arrow keys move from one person to the next."
            ),
        },
        "network-line": {
            title: _t("The line of a link"),
            text: _t("Its width shows the points you received in this link."),
            behavior: _t("Outside the guide, pressing the line opens the card of the link."),
        },
        "network-thickness": {
            title: _t("Width of the line"),
            text: _t("The points you received in the link with the person: the energy of the link, as you see it."),
            behavior: _t("It grows with each confirmed exchange of the pair."),
        },
        "network-halo": {
            title: _t("Golden halo"),
            text: _t("This person sent you “You add to my happiness”."),
            behavior: _t(
                "The halo shows around their circle, in the graph and in the rankings, until your next exchange."
            ),
        },
        "network-grey": {
            title: _t("Grey lines"),
            text: _t(
                "The links between your contacts. A choice of privacy: a line shows only when both people agree to show their links."
            ),
            behavior: _t("Visible in X1 only; they disappear in X2 and X3."),
        },
        "network-text-list": {
            title: _t("The graph as a list"),
            text: _t(
                "The same people as the graph, in text, with the energy of each link and the contacts they share."
            ),
            behavior: _t("Outside the guide, this button unfolds the list; each name opens the card of the link."),
        },
        "network-partners": {
            title: _t("My partners"),
            text: _t("Your contacts ranked by the energy of the link with you."),
            behavior: _t("Outside the guide, this tab shows the ranking; a row opens the card of the link."),
        },
        "network-active": {
            title: _t("The most active"),
            text: _t(
                "Your contacts who show their energy, ranked by it, rounded to the hundred and without penalties. Never the whole community."
            ),
            behavior: _t("Outside the guide, this tab shows the ranking; a row opens the card of the link."),
        },
        "network-period": {
            title: _t("Period"),
            text: _t("For “The most active”: count every point, or those of the last 30 days only."),
            behavior: _t("Outside the guide, choosing a period reads the ranking again."),
        },
        "network-row": {
            title: _t("A row of the ranking"),
            text: _t("Its position, the person and their points."),
            behavior: _t("Outside the guide, pressing it opens the card of the link: call, video call, conversation."),
        },
        "network-privacy": {
            title: _t("What my links see"),
            text: _t("Your links see neither your links nor your energy unless you allow it."),
            behavior: _t("Outside the guide, each box allows or withdraws it at once."),
            noShow: true,
        },
        "network-card-energy": {
            title: _t("Energy of the link"),
            text: _t("The points you received in the events of this pair: the same value as in “My partners”."),
            behavior: _t("The other person sees the points they received, which may differ."),
        },
        "network-call": {
            title: _t("Call"),
            text: _t("A voice call with this person."),
            behavior: _t("Outside the guide, this button opens your conversation and starts the call."),
            noShow: true,
        },
        "network-video": {
            title: _t("Video call"),
            text: _t("A video call with this person."),
            behavior: _t("Outside the guide, this button opens your conversation and starts the video call."),
            noShow: true,
        },
        "network-chat": {
            title: _t("Open the conversation"),
            text: _t("Your direct conversation with this person, in Discuss."),
            behavior: _t("Outside the guide, this button opens it."),
            noShow: true,
        },
        "network-highlight": {
            title: _t("You add to my happiness"),
            text: _t("Thank this person without words: their avatar shines until your next exchange."),
            behavior: _t(
                "Outside the guide, this button puts the person in the light. A new press while it shines has no effect."
            ),
            noShow: true,
        },
        "network-new-reflet": {
            title: _t("New reflection"),
            text: _t("Start a reflection of an exchange you had with this person."),
            behavior: _t("Outside the guide, this button opens the Reflet view with this person as the recipient."),
            noShow: true,
        },
        "network-thread": {
            title: _t("Your exchanges"),
            text: _t("What you both read in your conversation: yours on the right, theirs on the left."),
            behavior: _t("The oldest first."),
        },
        "network-reflets-only": {
            title: _t("Reflections only"),
            text: _t("Keep only the reflections of the pair in the thread."),
            behavior: _t(
                "Outside the guide, this button filters the thread, and a second press shows everything again."
            ),
        },
        "network-happiness": {
            title: _t("You add to my happiness"),
            text: _t("Thank someone without words: their avatar shines until your next exchange."),
            behavior: _t(
                "Outside the guide, this button opens the list of your contacts: the arrow keys move, Enter chooses, Escape closes."
            ),
        },
        "network-reflet-view": {
            title: _t("Reflet view"),
            text: _t("The view where you make a reflection of an exchange in person."),
            behavior: _t("Outside the guide, this button opens it."),
            noShow: true,
        },
        "network-newlink": {
            title: _t("+ NewLink"),
            text: _t("Invite a person who is not on LinkUp yet, from a real exchange."),
            behavior: _t("Outside the guide, this button opens the invitation in the Reflet view."),
            noShow: true,
        },
        "reflet-view-network": {
            title: _t("Network view"),
            text: _t("The graph of your links, their energy and the rankings of your contacts."),
            behavior: _t("Outside the guide, this button opens it."),
            noShow: true,
        },
        "action-agree": {
            title: _t("Agreed"),
            text: _t("Accept the request: “Agreed.” is posted in your conversation."),
            behavior: _t("Outside the guide, this button posts the answer once. It earns and costs no point."),
            noShow: true,
        },
        "action-propose": {
            title: _t("Let's propose something else"),
            text: _t("Answer the request in your own words."),
            behavior: _t("Outside the guide, this button opens the form of your answer."),
        },
        "action-not-now": {
            title: _t("Not for now"),
            text: _t("Decline for now, without having to explain: “Not for now.” is posted in your conversation."),
            behavior: _t("Outside the guide, this button posts the answer once. Nobody loses any point."),
            noShow: true,
        },
    };
}

patch(LinkupGuideSheet.prototype, {
    get texts() {
        const own = linkupNetworkGuideTexts(this.store.linkup_network_top_count || 2)[this.key];
        return own || super.texts;
    },
});
