import {Component, onWillStart, useEffect, useState} from "@odoo/owl";

import {deserializeDateTime, formatDateTime} from "@web/core/l10n/dates";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {formatInteger} from "@web/views/fields/formatters";

import {LinkupGuideButton} from "@mail_linkup_reflet/core/common/linkup_guide";

import {linkupCapReasonLabel, linkupSignedPoints} from "../../core/common/points_service";

/** Lines read per page. */
export const LINKUP_MY_POINTS_PAGE = 20;

/**
 * The screen "My points" (client action `linkup.my_points`, LU-F-103): the
 * energy of the member, their rank and the way to the next one, their
 * badges, the point scale, and the history of their own ledger lines, most
 * recent first, as `linkup.points.ledger.linkup_my_points` gives them.
 *
 * The history filters on one event and on one person; "Show more" reads
 * the next page. A line that the bus brings while the screen is open
 * reads the first page again. The "?" button turns the guide mode on.
 * The screen shows even when the member hides the points elsewhere: it
 * is opened on purpose.
 */
export class LinkupMyPoints extends Component {
    static template = "mail_linkup_gamification.LinkupMyPoints";
    static components = {LinkupGuideButton};
    static props = ["*"];

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.points = useState(useService("linkup.points").state);
        this.state = useState({
            loaded: false,
            loadError: false,
            loading: false,
            data: null,
            lines: [],
            ruleCode: "",
            counterpartId: "",
        });
        onWillStart(() => this.load());
        let first = true;
        useEffect(
            () => {
                if (first) {
                    first = false;
                    return;
                }
                this.load();
            },
            () => [this.points.version]
        );
    }

    /**
     * Read the first page with the filters chosen, or the next page.
     *
     * @param {{more?: boolean}} [options]
     */
    async load({more = false} = {}) {
        this.state.loading = true;
        try {
            const data = await this.orm.silent.call("linkup.points.ledger", "linkup_my_points", [], {
                limit: LINKUP_MY_POINTS_PAGE,
                offset: more ? this.state.lines.length : 0,
                rule_code: this.state.ruleCode || false,
                counterpart_id: Number(this.state.counterpartId) || false,
            });
            this.state.data = data;
            this.state.lines = more ? [...this.state.lines, ...data.lines] : data.lines;
            this.state.loaded = true;
            this.state.loadError = false;
        } catch {
            this.state.loadError = true;
        } finally {
            this.state.loading = false;
        }
    }

    /** @param {Event} ev */
    onChangeRule(ev) {
        this.state.ruleCode = ev.target.value;
        this.load();
    }

    /** @param {Event} ev */
    onChangeCounterpart(ev) {
        this.state.counterpartId = ev.target.value;
        this.load();
    }

    /** @param {{id: number}} counterpart */
    isCounterpart(counterpart) {
        return String(counterpart.id) === this.state.counterpartId;
    }

    get balance() {
        return formatInteger(this.state.data?.balance || 0);
    }

    get rankName() {
        return this.state.data?.rank?.name || _t("No rank yet");
    }

    /** The way from the current rank to the next one, from 0 to 100. */
    get progress() {
        const data = this.state.data;
        const next = data?.next_rank;
        if (!next) {
            return 100;
        }
        const from = data.rank?.karma_min || 0;
        const span = next.karma_min - from;
        if (span <= 0) {
            return 100;
        }
        return Math.max(0, Math.min(100, Math.round(((data.balance - from) / span) * 100)));
    }

    get nextRankLabel() {
        const data = this.state.data;
        const next = data?.next_rank;
        if (!next) {
            return _t("Highest rank reached.");
        }
        return _t("%(points)s points to %(rank)s.", {
            points: formatInteger(Math.max(0, next.karma_min - data.balance)),
            rank: next.name,
        });
    }

    get scale() {
        return (this.state.data?.rules || []).filter((rule) => rule.points);
    }

    get isFiltered() {
        return Boolean(this.state.ruleCode || this.state.counterpartId);
    }

    get countLabel() {
        return _t("%(shown)s of %(total)s lines", {
            shown: this.state.lines.length,
            total: this.state.data?.total || 0,
        });
    }

    get hasMore() {
        return this.state.lines.length < (this.state.data?.total || 0);
    }

    /** @param {{date: string}} line */
    lineDate(line) {
        return formatDateTime(deserializeDateTime(line.date));
    }

    /** @param {{points: number}} line */
    linePoints(line) {
        return linkupSignedPoints(line.points);
    }

    /** @param {{capped: boolean, cap_reason: string|false}} line */
    lineReason(line) {
        return line.capped ? linkupCapReasonLabel(line.cap_reason) : "";
    }

    /** @param {{points: number}} rule */
    rulePoints(rule) {
        return linkupSignedPoints(rule.points);
    }
}

registry.category("actions").add("linkup.my_points", LinkupMyPoints);
