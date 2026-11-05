import {OutOfFocusService} from "@mail/core/common/out_of_focus_service";
import {Settings} from "@mail/core/common/settings_model";
import {soundEffects} from "@mail/core/common/sound_effects_service";
import {htmlToTextContentInline} from "@mail/utils/common/format";

import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {patch} from "@web/core/utils/patch";

/** The sounds of LinkUp, added to the service `mail.sound_effects`. */
export const LINKUP_SOUNDS = {
    "linkup-sent": {defaultVolume: 0.5, path: "/mail_linkup_reflet/static/src/audio/linkup_sent"},
    "linkup-received": {defaultVolume: 0.5, path: "/mail_linkup_reflet/static/src/audio/linkup_received"},
    "linkup-success": {defaultVolume: 0.5, path: "/mail_linkup_reflet/static/src/audio/linkup_success"},
    "linkup-yeah": {defaultVolume: 0.5, path: "/mail_linkup_reflet/static/src/audio/linkup_yeah"},
    "linkup-ting": {defaultVolume: 0.5, path: "/mail_linkup_reflet/static/src/audio/linkup_ting"},
};

/** The reward sounds, which `linkup_reward_sounds_enabled` turns on. */
export const LINKUP_REWARD_SOUNDS = new Set(["linkup-success", "linkup-yeah", "linkup-ting"]);

// The dictionary of the sounds is built by the constructor of SoundEffects,
// which a patch of its prototype does not reach: the service adds them to
// each instance it starts.
patch(soundEffects, {
    start() {
        const service = super.start(...arguments);
        for (const [name, sound] of Object.entries(LINKUP_SOUNDS)) {
            service.soundEffects[name] = {...sound};
        }
        return service;
    },
});

// The settings of `res.users.settings` the client reads before the server
// sends them: the defaults of the fields.
patch(Settings.prototype, {
    setup() {
        super.setup(...arguments);
        this.linkup_sound_enabled = true;
        this.linkup_reward_sounds_enabled = false;
        this.linkup_notify_reflet_received = true;
        this.linkup_notify_confirmed = true;
        this.linkup_notify_highlight = true;
        this.linkup_notify_discreet = false;
    },
});

/**
 * Play a LinkUp sound unless the member turned it off: every sound needs
 * `linkup_sound_enabled`, a reward sound also `linkup_reward_sounds_enabled`.
 * The sound always comes with a visible change.
 *
 * @param {Object} services the services of the environment
 * @param {string} name a key of `LINKUP_SOUNDS`
 * @returns {boolean} whether the sound was played
 */
export function linkupPlaySound(services, name) {
    const settings = services["mail.store"]?.settings;
    if (!settings?.linkup_sound_enabled) {
        return false;
    }
    if (LINKUP_REWARD_SOUNDS.has(name) && !settings.linkup_reward_sounds_enabled) {
        return false;
    }
    services["mail.sound_effects"].play(name);
    return true;
}

/** Whether the member muted their notifications in Discuss. */
function linkupIsMuted(settings) {
    return Boolean(settings?.mute_until_dt);
}

/**
 * The notification of a LinkUp event, as `sendNotification` takes it. With
 * discreet notifications (`linkup_notify_discreet`, LU-F-092 RM4), it names
 * nobody and shows no avatar: "LinkUp", "New LinkUp event".
 *
 * @param {Object} settings the settings of the member
 * @param {{message: string, title?: string, type?: string, icon?: string}} notification
 * @returns {Object}
 */
export function linkupNotification(settings, {message, title, type = "info", icon}) {
    if (settings?.linkup_notify_discreet) {
        return {message: _t("New LinkUp event"), sound: false, title: _t("LinkUp"), type: "info"};
    }
    return {message, sound: false, title: title || _t("LinkUp"), type, icon};
}

// A new carrier message reaches its recipient through `notifyMessageToUser`,
// which checks the mute of Discuss first. Its notification follows
// `linkup_notify_reflet_received`, and the sound of LinkUp replaces the
// sound of Discuss, so that a member who turned the LinkUp sounds off
// hears nothing. The unread counter of the conversation shows either way.
patch(OutOfFocusService.prototype, {
    async notify(message, thread) {
        if (!message.linkup_reflet_id) {
            return super.notify(...arguments);
        }
        const services = this.env.services;
        linkupPlaySound(services, "linkup-received");
        if (
            !services["mail.store"].settings?.linkup_notify_reflet_received ||
            (await this.hasServiceWorkInstalledAndPushSubscriptionActive())
        ) {
            return;
        }
        this.sendNotification(
            linkupNotification(services["mail.store"].settings, {
                message: htmlToTextContentInline(message.body),
                title: message.author?.name,
                icon: message.author?.avatarUrl,
            })
        );
    },
});

/**
 * The events of LinkUp that are not new messages, announced to the member
 * with a sound and a notification of the browser or of Discuss:
 *
 * - the confirmation of a reflection the member wrote, read in the cards
 *   the bus sends (`mail.record/insert`), once per reflection and session;
 * - a highlight received (`linkup.highlight/received`), whose card the
 *   service inserts in the Store.
 *
 * Each notification follows its setting and the mute of Discuss, and
 * names nobody with discreet notifications.
 *
 * `linkup-yeah` joins the reward of the points, which the scoring module
 * plays; nothing of this module plays it.
 */
export const linkupSignalsService = {
    dependencies: ["bus_service", "mail.store", "mail.out_of_focus", "mail.sound_effects"],
    start(env, services) {
        const store = services["mail.store"];
        const outOfFocus = services["mail.out_of_focus"];
        const celebrated = new Set();
        const isSelf = (persona) => Boolean(persona) && store.self?.type === "partner" && persona.id === store.self.id;

        services.bus_service.subscribe("mail.record/insert", (payload) => {
            for (const card of payload?.["linkup.reflet"] || []) {
                if (
                    card.kind !== "initial" ||
                    card.state !== "confirmed" ||
                    card.response_state !== "none" ||
                    !isSelf(card.author) ||
                    celebrated.has(card.id)
                ) {
                    continue;
                }
                celebrated.add(card.id);
                linkupPlaySound(env.services, "linkup-success");
                if (store.settings?.linkup_notify_confirmed && !linkupIsMuted(store.settings)) {
                    outOfFocus.sendNotification(
                        linkupNotification(store.settings, {
                            message: _t("Your reflection was confirmed: that's a link!"),
                            type: "success",
                        })
                    );
                }
            }
        });

        services.bus_service.subscribe("linkup.highlight/received", (payload) => {
            const {"linkup.highlight": highlights = []} = store.insert(payload, {html: true});
            for (const highlight of highlights) {
                if (!highlight.active || !highlight.recipient?.eq(store.self)) {
                    continue;
                }
                linkupPlaySound(env.services, "linkup-ting");
                if (store.settings?.linkup_notify_highlight && !linkupIsMuted(store.settings)) {
                    outOfFocus.sendNotification(
                        linkupNotification(store.settings, {
                            message: _t("%(name)s adds to your happiness.", {
                                name: highlight.sender?.name || _t("Someone"),
                            }),
                            icon: highlight.sender?.avatarUrl,
                        })
                    );
                }
            }
        });
        return {};
    },
};

registry.category("services").add("linkup.signals", linkupSignalsService);
