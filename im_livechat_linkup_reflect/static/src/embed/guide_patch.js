import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";

import {LINKUP_GUIDE_ATTRIBUTE, LinkupGuideSheet, LinkupGuideState} from "@mail_linkup_reflet/core/common/linkup_guide";

/** The hosts of the shadow roots of the widget on the page. */
function linkupLivechatHosts() {
    return [...document.querySelectorAll(".o-livechat-root")].filter((host) => host.shadowRoot);
}

/**
 * The widget lives in a shadow root, which the guide mode of the page does
 * not see: its elements join the entries of the guide, after those of the
 * page; its host carries the class of the active guide, which the
 * stylesheet of the widget reads; a click inside it is read from the
 * element pressed, not from the host the event is retargeted to.
 */
patch(LinkupGuideState.prototype, {
    entries() {
        const inWidget = linkupLivechatHosts()
            .flatMap((host) => [...host.shadowRoot.querySelectorAll(`[${LINKUP_GUIDE_ATTRIBUTE}]`)])
            .filter((el) => el.getClientRects().length > 0);
        return [...super.entries(), ...inWidget];
    },

    open() {
        super.open(...arguments);
        for (const host of linkupLivechatHosts()) {
            host.classList.add("o-linkup-guideActive");
        }
    },

    close() {
        super.close(...arguments);
        for (const host of linkupLivechatHosts()) {
            host.classList.remove("o-linkup-guideActive");
        }
    },

    _guideTarget(ev) {
        const origin = ev.composedPath?.()[0];
        if (origin instanceof Element && origin !== ev.target) {
            return origin.closest(`[${LINKUP_GUIDE_ATTRIBUTE}]`);
        }
        return super._guideTarget(ev);
    },
});

/**
 * The texts of the guide for the elements of the widget, by the value of
 * their `data-linkup-guide`. `noShow` keeps "Show" from pressing an element
 * that acts: "Show" then gives it the focus.
 */
export function linkupWidgetGuideTexts() {
    return {
        "livechat-help-now": {
            title: _t("Need help now"),
            text: _t(
                "LinkUp is not an emergency service: the help resources of the territory, set by the administrator, come first."
            ),
            behavior: _t(
                "Outside the guide, this button shows the resources, reports the request as urgent and brings a person of the moderation into this conversation; without one available, the request waits in the queue."
            ),
            noShow: true,
        },
        "help-now": {
            title: _t("Help resources"),
            text: _t(
                "LinkUp is not an emergency service: the help resources of the territory, set by the administrator, come first."
            ),
            behavior: _t("Call or write to one of them at once when a life is in danger."),
        },
    };
}

patch(LinkupGuideSheet.prototype, {
    get texts() {
        return linkupWidgetGuideTexts()[this.key] || super.texts;
    },

    get behavior() {
        if (this.category && this.el.dataset.linkupGuideContext === "chatbot") {
            return _t("Outside the guide, this button answers the guide with this category.");
        }
        return super.behavior;
    },
});
