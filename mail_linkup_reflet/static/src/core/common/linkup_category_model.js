import {Record} from "@mail/core/common/record";

/**
 * A category of communication of the Help bar.
 *
 * The cards of the reflections name their category by its code only: the
 * texts are read by `Store.fetchLinkupCategories`, in the language of the
 * current user, and fill the same records.
 */
export class LinkupCategory extends Record {
    static _name = "linkup.category";
    static id = "id";

    /** @type {number} */
    id;
    /** @type {string} */
    code;
    /** @type {string} */
    name;
    /** @type {string} */
    definition;
    /** @type {string} */
    example_do;
    /** @type {string} */
    example_dont;
    /** @type {string} */
    reflet_title;
    /** @type {string} */
    starter_self;
    /** @type {string} */
    starter_reflect;
    /** @type {number} */
    sequence;
    /** @type {boolean} */
    in_reflet_bar;
    /** @type {number} */
    reflet_bar_sequence;
    /** @type {boolean} */
    is_cnv;
}
LinkupCategory.register();
