import {Message} from "@mail/core/common/message";

import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";

import {LinkupCategoryIcon} from "@mail_linkup_reflet/core/common/linkup_category_icon";

patch(Message, {
    components: {...Message.components, LinkupCategoryIcon},
});

/**
 * The answers of a step of the chatbot are buttons, reached with the
 * keyboard; an answer of the category step of the reflection guide shows
 * the icon of its category (`linkup_category_code`) and is an element of
 * the guide mode, which explains the category.
 */
patch(Message.prototype, {
    get linkupHasCategoryAnswers() {
        return Boolean(this.props.message.chatbotStep?.answers.some((answer) => answer.linkup_category_code));
    },

    get linkupAnswersLabel() {
        return this.linkupHasCategoryAnswers ? _t("Categories") : _t("Answers");
    },
});
