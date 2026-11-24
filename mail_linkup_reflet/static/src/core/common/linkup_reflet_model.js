import {Record} from "@mail/core/common/record";

/**
 * The card of a reflection, as `linkup.reflet._to_store` sends it.
 *
 * The card is the same for every reader; `revealed_category_ids`,
 * `primary_category_id` and `recipient_ignored` reach only the reader they
 * belong to. The role of the current user follows from `author` and
 * `recipient`.
 */
export class LinkupReflet extends Record {
    static _name = "linkup.reflet";
    static id = "id";

    /** @type {number} */
    id;
    /** @type {"initial"|"precision"|"continue"|"self_disclosure"|"answer_exact"|"close"} */
    kind;
    /** @type {string} */
    state;
    /** @type {"none"|"exact"|"precision"} */
    response_state;
    /** @type {"none"|"pending"|"found"|"missed"} */
    guess_state;
    /** @type {number} */
    round_index;
    /** @type {string} */
    sent_date;
    /** @type {string} */
    read_date;
    /** @type {string} */
    answered_date;
    author = Record.one("Persona");
    recipient = Record.one("Persona");
    /** @type {number} */
    parent_id;
    /** @type {number} */
    message_id;
    /** @type {boolean} */
    holds_turn;
    category_id = Record.one("linkup.category");
    guessed_category_id = Record.one("linkup.category");
    revealed_category_ids = Record.many("linkup.category");
    primary_category_id = Record.one("linkup.category");
    /** @type {string|false} */
    you_said;
    /** @type {string|false} */
    understood;
    /** @type {string|false} */
    body_text;
    /** @type {boolean} */
    real_world_declared;
    /** @type {string|false} */
    real_world_date;
    /** @type {boolean} */
    recipient_ignored;

    /** @returns {boolean} */
    get isSelfAuthor() {
        return Boolean(this.author?.eq(this.store.self));
    }

    /** @returns {boolean} */
    get isSelfRecipient() {
        return Boolean(this.recipient?.eq(this.store.self));
    }
}
LinkupReflet.register();
