import {Settings} from "@mail/core/common/settings_model";
import {Store} from "@mail/core/common/store_service";

import {reactive} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {patch} from "@web/core/utils/patch";
import {formatInteger} from "@web/views/fields/formatters";

import {linkupPlaySound} from "@mail_linkup_reflet/core/common/linkup_signals";

/** How long a "+N" stays on the screen, in milliseconds. */
export const LINKUP_BURST_DURATION = 2400;
/** Within this delay, new points play no sound and add to one announcement. */
export const LINKUP_POINTS_GROUP_DELAY = 1500;
/** Reasons of a ledger line that concern the account, not a cap. */
const INELIGIBLE_REASONS = new Set(["new_account", "unverified"]);

// Set by `res.users._init_store_data` of this module for a LinkUp member.
patch(Store.prototype, {
    setup() {
        super.setup(...arguments);
        /** The energy of the member: their karma (LU-F-071 RM1). */
        this.linkup_karma = 0;
        /** The name of the rank of the member, or `false`. */
        this.linkup_rank = false;
        /** The points of each rule of the scale, by code. */
        this.linkup_points_rules = {};
        /** The id of the newest ledger line the client knows of. */
        this.linkup_points_last_id = 0;
    },
});

patch(Settings.prototype, {
    setup() {
        super.setup(...arguments);
        this.linkup_hide_gamification = false;
    },
});

/**
 * A number of points with its sign: "+1,000", "−150", "0".
 *
 * @param {number} points
 * @returns {string}
 */
export function linkupSignedPoints(points) {
    const value = formatInteger(Math.abs(points || 0));
    if (points > 0) {
        return `+${value}`;
    }
    return points < 0 ? `−${value}` : value;
}

/**
 * What a screen reader says of a ledger line: "You earn 1000 points",
 * "You lose 150 points".
 *
 * @param {number} points
 * @returns {string}
 */
export function linkupPointsAnnouncement(points) {
    const count = formatInteger(Math.abs(points));
    return points < 0 ? _t("You lose %(count)s points", {count}) : _t("You earn %(count)s points", {count});
}

/**
 * The short name of the event of a rule, shown next to its "+N". It names
 * nobody, so the screen holds no name even with discreet notifications.
 *
 * @param {string} code a code of `linkup.points.rule`
 * @param {string} [fallback] the name of the rule, for a code not listed
 * @returns {string}
 */
export function linkupPointsEventLabel(code, fallback = "") {
    switch (code) {
        case "reflect_sent":
            return _t("Your reflection is confirmed");
        case "reflect_confirmed":
            return _t("That's a link!");
        case "reflect_rejected":
            return _t("The exchange did not take place");
        case "answer_exact":
            return _t("Reformulation confirmed");
        case "precision_sent":
            return _t("Precision sent");
        case "theme_guessed":
            return _t("Hidden theme found");
        case "continue_sent":
            return _t("Reflection continued");
        case "continue_confirmed":
            return _t("Continuation confirmed");
        case "call_answered":
            return _t("Call answered");
        case "virtual_round":
            return _t("Round of exchange");
    }
    return fallback;
}

/**
 * The label of the reason why a ledger line paid nothing.
 *
 * @param {string|false} reason a `cap_reason` of `linkup.points.ledger`
 * @returns {string}
 */
export function linkupCapReasonLabel(reason) {
    switch (reason) {
        case "new_account":
            return _t("Account too recent");
        case "unverified":
            return _t("Account not verified");
        case "pair_lifetime_cap":
            return _t("Cap of the pair");
        case "pair_weekly_cap":
            return _t("Weekly cap of the pair");
        case "pair_daily_cap":
            return _t("Daily cap of the pair");
        case "weekly_cap":
            return _t("Weekly cap");
        case "daily_cap":
            return _t("Daily cap");
        case "decay":
            return _t("Sequence exhausted");
    }
    return "";
}

/**
 * The points of the member on the screen (LU-F-091).
 *
 * Each ledger line of the member reaches the client on
 * `linkup.points/awarded`, and after each action on a reflection the
 * client also reads the lines newer than the last one it knows
 * (`linkup_my_points` with `after_id`), so that a late or lost bus still
 * shows the points of the action. A line shows once, whichever brought it
 * first, by its id:
 *
 * - a gain or a loss rises as "+N" or "−N" above the energy of the member
 *   when it is on the screen (`data-linkup-points-anchor`), otherwise in
 *   the top corner, and is announced in a polite live region; a gain
 *   plays `linkup-yeah`, once per group of lines, under the sound settings
 *   of the core (a reward sound, off by default), and never with discreet
 *   notifications;
 * - a capped line shows the information `linkup.cap_reached` (LU-F-093);
 * - a new rank (`linkup.points/rank`) or badge (`linkup.points/badge`) is
 *   shown and announced the same way, the server sending no email.
 *
 * The energy and the rank of the Store follow every line. With
 * `linkup_hide_gamification`, nothing shows, sounds nor is announced; the
 * Store is still kept up to date.
 */
export class LinkupPoints {
    /**
     * @param {Object} env
     * @param {Object} services
     */
    constructor(env, services) {
        this.env = env;
        this.store = services["mail.store"];
        this.notification = services.notification;
        this.orm = services.orm;
        /**
         * What the screens render: the bursts on the screen, the text of
         * the live region, and a counter of the lines received, for the
         * screens that list them.
         *
         * @type {{bursts: {id: number, kind: string, points?: number, value: string, text: string, anchored: boolean, style: string}[], announcement: string, version: number}}
         */
        this.state = reactive({bursts: [], announcement: "", version: 0});
        this._nextBurstId = 1;
        this._shown = new Set();
        this._pendingAnnouncements = [];
        this._lastSound = 0;
        this._lastCapNotice = 0;
        this._catchingUp = null;
    }

    get hidden() {
        return Boolean(this.store.settings?.linkup_hide_gamification);
    }

    /**
     * Take in a ledger line of the member, from the bus or from a reading.
     *
     * @param {Object} line the payload of `linkup.points/awarded`, or a line
     *  of `linkup_my_points`
     */
    receive(line) {
        if (typeof line.karma === "number") {
            this.store.linkup_karma = line.karma;
        }
        if (line.id) {
            if (this._shown.has(line.id)) {
                return;
            }
            this._shown.add(line.id);
            this.store.linkup_points_last_id = Math.max(this.store.linkup_points_last_id || 0, line.id);
        }
        this.state.version++;
        if (this.hidden || INELIGIBLE_REASONS.has(line.cap_reason)) {
            return;
        }
        if (line.capped) {
            this.noticeCap();
            return;
        }
        if (!line.points) {
            return;
        }
        this.addBurst({
            kind: line.points > 0 ? "gain" : "loss",
            points: line.points,
            value: linkupSignedPoints(line.points),
            text: linkupPointsEventLabel(line.rule_code, line.rule_name),
            announcement: linkupPointsAnnouncement(line.points),
        });
        if (line.points > 0) {
            this.playReward();
        }
    }

    /** @param {{rank_id: number|false, name: string|false, karma?: number}} payload */
    receiveRank(payload) {
        this.store.linkup_rank = payload.name || false;
        if (typeof payload.karma === "number") {
            this.store.linkup_karma = payload.karma;
        }
        if (!payload.name || this.hidden) {
            return;
        }
        const text = _t("New rank: %(name)s", {name: payload.name});
        this.addBurst({kind: "rank", value: "", text, announcement: text});
    }

    /** @param {{badge_id: number, name: string}} payload */
    receiveBadge(payload) {
        if (!payload.name || this.hidden) {
            return;
        }
        const text = _t("New badge: %(name)s", {name: payload.name});
        this.addBurst({kind: "badge", value: "", text, announcement: text});
    }

    /**
     * Read the ledger lines of the member newer than the last one shown,
     * once at a time. A failure leaves the bus to bring them.
     *
     * @returns {Promise<void>}
     */
    catchUp() {
        if (!this.store.linkup_is_member) {
            return Promise.resolve();
        }
        if (!this._catchingUp) {
            this._catchingUp = this._catchUp().finally(() => {
                this._catchingUp = null;
            });
        }
        return this._catchingUp;
    }

    async _catchUp() {
        let result;
        try {
            result = await this.orm.silent.call("linkup.points.ledger", "linkup_my_points", [], {
                limit: 20,
                after_id: this.store.linkup_points_last_id || 0,
            });
        } catch {
            return;
        }
        for (const line of result.lines || []) {
            this.receive(line);
        }
        this.store.linkup_karma = result.balance;
        this.store.linkup_points_last_id = Math.max(this.store.linkup_points_last_id || 0, result.last_id || 0);
    }

    /**
     * Show a "+N", a "−N", a rank or a badge, rising above the energy of
     * the member when it is on the screen.
     *
     * @param {{kind: string, points?: number, value: string, text: string, announcement: string}} burst
     */
    addBurst({announcement, ...burst}) {
        const id = this._nextBurstId++;
        const bursts = this.state.bursts;
        const offset = bursts.length;
        bursts.push({...burst, id, ...this._burstPlacement(offset)});
        this.announce(announcement);
        setTimeout(() => {
            const index = bursts.findIndex((item) => item.id === id);
            if (index >= 0) {
                bursts.splice(index, 1);
            }
        }, LINKUP_BURST_DURATION);
    }

    /**
     * The position of a burst: above the visible energy of the member, or
     * in the top corner; each burst still on the screen pushes the next one
     * down by a row.
     *
     * @param {number} offset the number of bursts on the screen
     * @returns {{anchored: boolean, style: string}} whether the burst rises
     *  above the energy, and its inline style, empty for the top corner
     */
    _burstPlacement(offset) {
        const anchor = [...document.querySelectorAll("[data-linkup-points-anchor]")].find(
            (el) => el.getClientRects().length > 0
        );
        const shift = `${offset * 2.5}rem`;
        if (!anchor) {
            return {anchored: false, style: offset ? `margin-top: ${shift};` : ""};
        }
        const rect = anchor.getBoundingClientRect();
        const left = Math.round(rect.left + rect.width / 2);
        const top = Math.round(rect.top);
        return {anchored: true, style: `left: ${left}px; top: calc(${top}px + ${shift}); right: auto;`};
    }

    /**
     * Give a text to the live region; texts within the grouping delay are
     * read together.
     *
     * @param {string} text
     */
    announce(text) {
        this._pendingAnnouncements.push(text);
        this.state.announcement = this._pendingAnnouncements.join(" ");
        const pending = this._pendingAnnouncements;
        setTimeout(() => {
            if (this._pendingAnnouncements === pending) {
                this._pendingAnnouncements = [];
            }
        }, LINKUP_POINTS_GROUP_DELAY);
    }

    /**
     * Play `linkup-yeah` once for the lines of one event. Discreet
     * notifications (`linkup_notify_discreet`, LU-F-092 RM4) keep it
     * silent; the "+N" still shows.
     */
    playReward() {
        const now = Date.now();
        if (this.store.settings?.linkup_notify_discreet || now - this._lastSound < LINKUP_POINTS_GROUP_DELAY) {
            return;
        }
        if (linkupPlaySound(this.env.services, "linkup-yeah")) {
            this._lastSound = now;
        }
    }

    /** Tell once per event that a cap left the action without points. */
    noticeCap() {
        const now = Date.now();
        if (now - this._lastCapNotice < LINKUP_POINTS_GROUP_DELAY) {
            return;
        }
        this._lastCapNotice = now;
        this.notification.add(_t("Sent. No more points today for this action."), {
            type: "info",
            className: "o-linkup-CapNotice",
        });
    }
}

export const linkupPointsService = {
    dependencies: ["bus_service", "mail.store", "mail.sound_effects", "notification", "orm"],
    start(env, services) {
        const points = new LinkupPoints(env, services);
        const bus = services.bus_service;
        bus.subscribe("linkup.points/awarded", (payload) => points.receive(payload));
        bus.subscribe("linkup.points/rank", (payload) => points.receiveRank(payload));
        bus.subscribe("linkup.points/badge", (payload) => points.receiveBadge(payload));
        return points;
    },
};

registry.category("services").add("linkup.points", linkupPointsService);
