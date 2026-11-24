import {Component, onWillUnmount, reactive, useEffect, useRef, useState} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

/** Name of the first-use tour in `web_tour.tours`. */
export const LINKUP_FIRST_USE_TOUR = "linkup_first_use_tour";

/** Delay between two placements of the bubble, in ms. */
const LINKUP_TOUR_PLACE_DELAY = 250;

// The five steps of the first-use tour (LU-F-083 RM1), as tour steps of
// the web client: each one names its element (`trigger`, a list of
// selectors in order of preference) and its text (`content`). The bubble
// of `LinkupTour` shows them with "Next" and "Skip the tour"; run as an
// automatic tour, the steps check that each element is on the screen.
registry.category("web_tour.tours").add(LINKUP_FIRST_USE_TOUR, {
    url: "/odoo/discuss",
    steps: () => [
        {
            id: "section",
            trigger: ".o-linkup-SidebarSection",
            content: _t("The Reflet view gathers your reflections, person by person; the help explains each category."),
        },
        {
            id: "help-bar",
            trigger: ".o-linkup-RefletComposer .o-linkup-HelpBar, .o-linkup-HelpBar",
            content: _t(
                "Here a conversation starts with the reflection of a real exchange: choose what you were told about, then rephrase it."
            ),
        },
        {
            id: "free-text",
            trigger: ".o-linkup-StartRule, .o-mail-Composer-input",
            content: _t("The free text of the conversation."),
        },
        {
            id: "panel",
            trigger: ".o-linkup-Panel-content, button[name='linkup-panel']",
            content: _t("The state of your link, your recent reflections and “You add to my happiness”."),
        },
        {
            id: "guide",
            trigger: ".o-linkup-GuideButton",
            content: _t(
                "Press “?” to read what each element does. The help of the categories stays in the LinkUp menu."
            ),
        },
    ],
});

/** The titles of the steps, by id. */
function linkupTourTitles() {
    return {
        section: _t("Your LinkUp views"),
        "help-bar": _t("Start with a reflection"),
        panel: _t("Your LinkUp panel"),
        guide: _t("The guide, at any time"),
    };
}

/**
 * The first element of the page that matches one of the selectors of a
 * trigger, in their order, and is on the screen.
 *
 * @param {string} trigger
 * @returns {HTMLElement|null}
 */
export function linkupTourAnchor(trigger) {
    for (const selector of trigger.split(",")) {
        const el = [...document.querySelectorAll(selector.trim())].find((node) => node.getClientRects().length);
        if (el) {
            return el;
        }
    }
    return null;
}

/**
 * The first-use tour of LinkUp: which step shows, and its end.
 *
 * `res.users._init_store_data` sets `Store.linkup_tour_pending` while the
 * tour is on in the settings and the member has neither finished nor
 * skipped it; the patch of Discuss (`discuss_patch.js`) then starts it the
 * first time Discuss opens. Finishing or skipping it calls
 * `res.users.linkup_tour_consume`, so it no longer starts on any device.
 * `start` also replays it on demand.
 */
export const linkupTourService = {
    dependencies: ["orm", "mail.store"],
    start(env, {orm, "mail.store": store}) {
        const tour = reactive({
            running: false,
            index: 0,
            steps: [],
            start() {
                const entry = registry.category("web_tour.tours").get(LINKUP_FIRST_USE_TOUR, null);
                this.steps = entry ? entry.steps() : [];
                this.index = 0;
                this.running = this.steps.length > 0;
            },
            /** Start the tour if it is pending and not running yet. */
            startIfPending() {
                if (store.linkup_tour_pending && !this.running) {
                    this.start();
                }
            },
            next() {
                if (this.index + 1 >= this.steps.length) {
                    return this.stop();
                }
                this.index++;
            },
            /**
             * End the tour, finished or skipped, and remember it on the
             * server; the bubble goes once the server has answered.
             */
            async stop() {
                try {
                    if (store.linkup_tour_pending) {
                        store.linkup_tour_pending = false;
                        await orm.silent.call("res.users", "linkup_tour_consume", []);
                    }
                } finally {
                    this.running = false;
                }
            },
        });
        return tour;
    },
};

registry.category("services").add("linkup.tour", linkupTourService);

/**
 * The bubble of the first-use tour: "Step n of 5", a title, a text, "Next"
 * (or "Finish") and "Skip the tour". It sits next to the element of its
 * step, which it outlines, and in the middle of the screen when that
 * element is absent. It takes the focus at each step. The panel step opens
 * the LinkUp panel of the conversation when it is closed.
 */
export class LinkupTour extends Component {
    static template = "mail_linkup_reflet.LinkupTour";
    static props = {};

    setup() {
        super.setup();
        this.tour = useState(useService("linkup.tour"));
        this.root = useRef("root");
        this.state = useState({style: ""});
        this.anchor = null;
        this.timer = null;
        useEffect(
            (running, index) => {
                if (!running) {
                    this.setAnchor(null);
                    return;
                }
                if (this.step?.id === "panel" && !document.querySelector(".o-linkup-Panel-content")) {
                    document.querySelector("button[name='linkup-panel']")?.click();
                }
                this.place();
                this.root.el?.focus();
                this.timer = setInterval(() => this.place(), LINKUP_TOUR_PLACE_DELAY);
                return () => clearInterval(this.timer);
            },
            () => [this.tour.running, this.tour.index]
        );
        onWillUnmount(() => {
            clearInterval(this.timer);
            this.setAnchor(null);
        });
    }

    get step() {
        return this.tour.steps[this.tour.index];
    }

    get count() {
        return this.tour.steps.length;
    }

    get isLast() {
        return this.tour.index + 1 >= this.count;
    }

    get stepLabel() {
        return _t("Step %(step)s of %(count)s", {step: this.tour.index + 1, count: this.count});
    }

    /** The mode of the start rule shown in the conversation, if any. */
    get startRuleMode() {
        return document.querySelector(".o-linkup-StartRule")?.dataset.mode || "";
    }

    get title() {
        if (this.step?.id === "free-text") {
            return this.startRuleMode === "strict" ? _t("Free text locked") : _t("Free text open");
        }
        return linkupTourTitles()[this.step?.id] || "";
    }

    get text() {
        if (this.step?.id === "free-text") {
            return this.startRuleMode === "strict"
                ? _t("In strict mode, free text opens once the other member confirms a reflection.")
                : _t("You can write freely; a confirmed reflection creates the link.");
        }
        return this.step?.content || "";
    }

    /** @param {HTMLElement|null} el */
    setAnchor(el) {
        if (this.anchor !== el) {
            this.anchor?.classList.remove("o-linkup-Tour-anchor");
            el?.classList.add("o-linkup-Tour-anchor");
            this.anchor = el;
        }
    }

    /** Put the bubble below its element, or above it, inside the screen. */
    place() {
        const step = this.step;
        const anchor = step ? linkupTourAnchor(step.trigger) : null;
        this.setAnchor(anchor);
        const bubble = this.root.el;
        let style;
        if (!anchor || !bubble) {
            style = "top: 50%; left: 50%; transform: translate(-50%, -50%);";
        } else {
            const rect = anchor.getBoundingClientRect();
            const width = bubble.offsetWidth;
            const height = bubble.offsetHeight;
            const margin = 12;
            const below = rect.bottom + margin + height <= window.innerHeight;
            const top = below ? rect.bottom + margin : Math.max(margin, rect.top - margin - height);
            const left = Math.min(Math.max(margin, rect.left), Math.max(margin, window.innerWidth - width - margin));
            style = `top: ${Math.round(top)}px; left: ${Math.round(left)}px;`;
        }
        if (style !== this.state.style) {
            this.state.style = style;
        }
    }

    onKeydown(ev) {
        if (ev.key === "Escape") {
            ev.preventDefault();
            ev.stopPropagation();
            this.tour.stop();
        }
    }
}

registry.category("main_components").add("mail_linkup_reflet.LinkupTour", {
    Component: LinkupTour,
});
