import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";

/**
 * The moderation on the bus:
 *
 * - `linkup.moderation/urgent` reaches a moderator who may process a new
 *   urgent report (LU-F-114 RM4): a notification that stays until closed,
 *   with "Open the moderation"; it names neither the reporter nor the
 *   content, which the server does not send;
 * - `linkup.moderation/notice` reaches a member a decision concerns
 *   (LU-F-116 RM3): a notification with "Read it", which opens the safety
 *   section of their profile.
 *
 * The counters of the Store follow, for the banners.
 */
export const linkupModerationService = {
    dependencies: ["bus_service", "mail.store", "notification", "action"],
    start(env, services) {
        const store = services["mail.store"];
        const {action, notification} = services;

        services.bus_service.subscribe("linkup.moderation/urgent", () => {
            store.linkup_moderation_urgent = (store.linkup_moderation_urgent || 0) + 1;
            notification.add(_t("An urgent report waits in the moderation queue."), {
                title: _t("LinkUp moderation"),
                type: "warning",
                sticky: true,
                buttons: [
                    {
                        name: _t("Open the moderation"),
                        primary: true,
                        onClick: () => action.doAction("mail_linkup_community.action_linkup_moderation"),
                    },
                ],
            });
        });

        services.bus_service.subscribe("linkup.moderation/notice", () => {
            store.linkup_notice_unseen = (store.linkup_notice_unseen || 0) + 1;
            notification.add(_t("A decision of the moderation concerns you."), {
                title: _t("LinkUp"),
                type: "info",
                sticky: true,
                buttons: [
                    {
                        name: _t("Read it"),
                        primary: true,
                        onClick: () => linkupOpenSafety(action),
                    },
                ],
            });
        });
        return {};
    },
};

/**
 * Open the safety section of the profile of the member.
 *
 * @param {Object} action the action service
 */
export function linkupOpenSafety(action) {
    return action.doAction({
        type: "ir.actions.client",
        tag: "linkup.profile",
        context: {linkup_section: "safety"},
    });
}

registry.category("services").add("linkup.moderation", linkupModerationService);
