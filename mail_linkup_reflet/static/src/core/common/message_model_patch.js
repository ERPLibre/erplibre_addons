import {Message} from "@mail/core/common/message_model";
import {Record} from "@mail/core/common/record";

import {patch} from "@web/core/utils/patch";

/**
 * A carrier message holds the card of its reflection.
 *
 * Its body is the neutral sentence of the notifications; the card replaces
 * it in the thread, so the body is not drawn. A carrier is never empty and
 * never edited: the server owns its body.
 */
patch(Message.prototype, {
    setup() {
        super.setup(...arguments);
        this.linkup_reflet_id = Record.one("linkup.reflet");
    },

    computeIsEmpty() {
        return super.computeIsEmpty() && !this.linkup_reflet_id;
    },

    get hasTextContent() {
        return !this.linkup_reflet_id && super.hasTextContent;
    },

    get editable() {
        return !this.linkup_reflet_id && super.editable;
    },
});
