import {Thread} from "@mail/core/common/thread_model";

import {patch} from "@web/core/utils/patch";

/**
 * The start rule of a conversation, as `discuss.channel._channel_basic_info`
 * gives it: `linkup_start_rule` is the effective mode (`strict`,
 * `incitative` or `off`), `linkup_start_rule_satisfied` tells whether a
 * confirmed reflection opened the conversation. The server sends them again
 * when a link of the pair becomes active, and checks the rule on every post.
 */
patch(Thread.prototype, {
    setup() {
        super.setup(...arguments);
        this.linkup_start_rule = undefined;
        this.linkup_start_rule_satisfied = undefined;
    },

    /** Free text is refused until a reflection is confirmed. */
    get linkupStartRuleLocked() {
        return this.linkup_start_rule === "strict" && this.linkup_start_rule_satisfied === false;
    },

    /** Free text is open, and a reflection is suggested. */
    get linkupStartRuleSuggested() {
        return this.linkup_start_rule === "incitative" && this.linkup_start_rule_satisfied === false;
    },
});
