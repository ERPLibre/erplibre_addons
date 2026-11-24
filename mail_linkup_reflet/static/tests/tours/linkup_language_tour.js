import {registry} from "@web/core/registry";

/**
 * The same path in each language of LinkUp (LU-NF-025): the member lands
 * in the Reflet view, opens the conversation of France from her row, and
 * reads the reflection France wrote in French under the title of its
 * category in the language of the member. Each tour checks the texts of
 * its language; neither finds the texts of the other.
 */
const TEXTS = {
    linkup_english_tour: {
        view: "Reflet view",
        card: "You told me about your emotions",
        other: "Vue Reflet",
    },
    linkup_french_tour: {
        view: "Vue Reflet",
        card: "Tu m'as parlé de tes émotions",
        other: "Reflet view",
    },
};

for (const [name, texts] of Object.entries(TEXTS)) {
    registry.category("web_tour.tours").add(name, {
        steps: () => [
            {
                trigger: `.o-linkup-RefletView h1:contains(${texts.view})`,
            },
            {
                trigger: `.o-linkup-RefletView:not(:has(h1:contains(${texts.other})))`,
            },
            {
                trigger: ".o-linkup-RefletView-contact:contains(France) .o-linkup-RefletView-openChat",
                run: "click",
            },
            {
                trigger: ".o-mail-Discuss-threadName[title='France']",
            },
            {
                trigger: `.o-mail-Message .o-linkup-RefletCard[data-role='recipient'] .o-linkup-RefletCard-title:contains(${texts.card})`,
            },
        ],
    });
}
