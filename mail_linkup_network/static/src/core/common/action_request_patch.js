import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";

import {LinkupRefletActions} from "@mail_linkup_reflet/core/common/reflet_actions";
import {linkupPlaySound} from "@mail_linkup_reflet/core/common/linkup_signals";

/** The code of the category of a request for action. */
export const LINKUP_ACTION_CATEGORY = "action";
/** The kinds of reflection whose category may ask for an action. */
const ACTION_KINDS = ["initial", "continue", "self_disclosure"];

/**
 * Whether the current user may answer a reflection as a request for action
 * (LU-F-046): they are its recipient, nobody answered it yet, and its
 * category is Action, or, for a precision whose guess is made, one of the
 * themes it revealed. An initial reflection is answered once confirmed.
 *
 * @param {import("models").LinkupReflet} reflet
 * @returns {boolean}
 */
export function linkupIsActionRequest(reflet) {
    if (!reflet.isSelfRecipient || reflet.action_reply) {
        return false;
    }
    if (reflet.kind === "precision") {
        return (
            ["found", "missed"].includes(reflet.guess_state) &&
            reflet.revealed_category_ids.some((category) => category.code === LINKUP_ACTION_CATEGORY)
        );
    }
    if (!ACTION_KINDS.includes(reflet.kind) || reflet.category_id?.code !== LINKUP_ACTION_CATEGORY) {
        return false;
    }
    return reflet.kind === "initial" ? reflet.state === "confirmed" : ["sent", "confirmed"].includes(reflet.state);
}

/**
 * The three quick replies of a request for action, above the block of the
 * card: "Agreed" and "Not for now" post their sentence in the
 * conversation, once, without points; "Let's propose something else" opens
 * the form that answers in one's own words, "I would like to clarify…" or,
 * once the turn offers the options, "So if I understand correctly…". No
 * answer is required. Once answered, both parties read the answer.
 */
patch(LinkupRefletActions.prototype, {
    get linkupActionRequest() {
        return linkupIsActionRequest(this.reflet) && !this.state.form;
    },

    /** The form "Let's propose something else" opens, or `null`. */
    get linkupProposeForm() {
        switch (this.mode) {
            case "answer":
                return "precision";
            case "options":
                return "continue";
        }
        return null;
    },

    get linkupActionReplyLabel() {
        switch (this.reflet.action_reply) {
            case "agree":
                return _t("Answer to the request: Agreed.");
            case "not_now":
                return _t("Answer to the request: Not for now.");
        }
        return "";
    },

    /** @param {"agree"|"not_now"} reply */
    async answerActionRequest(reply) {
        const done = await this.call("action_answer_action_request", [reply]);
        if (done) {
            linkupPlaySound(this.env.services, "linkup-sent");
        }
        return done;
    },

    proposeOther() {
        const form = this.linkupProposeForm;
        if (form) {
            this.open(form);
        }
    },
});
