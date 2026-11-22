/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onWillStart, status, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";
import {reportSections} from "./studio_confirm";
import {MODEL} from "./studio_utils";

// The filters of the review, in their order: every item, then the
// categories of the items (REVIEW_CATEGORIES of the server).
export const REVIEW_FILTERS = ["all", "fields", "views", "models", "security"];

/** The label of the review filter ``filter``. */
export function reviewFilterLabel(filter) {
    return (
        {
            all: _t("All"),
            fields: _t("Fields"),
            views: _t("Views"),
            models: _t("Models"),
            security: _t("Security"),
        }[filter] || filter
    );
}

/** The badge of a review item: what it is, by its type and category. */
export function reviewItemKind(item) {
    if (item.type === "change") {
        return item.category === "fields" ? _t("Field") : _t("View");
    }
    return (
        {
            model: _t("Model"),
            view: _t("New view"),
            access: _t("Right"),
            rule: _t("Rule"),
            group: _t("Group"),
            app: _t("App"),
        }[item.type] || item.type
    );
}

/** The items of the groups of a review, in their order. */
export function reviewItems(review) {
    return ((review && review.groups) || []).flatMap((group) => group.items);
}

/**
 * {all, fields, views, models, security}: how many of ``items`` each
 * filter shows.
 */
export function reviewCounts(items) {
    const counts = Object.fromEntries(REVIEW_FILTERS.map((filter) => [filter, 0]));
    for (const item of items) {
        counts.all++;
        counts[item.category] = (counts[item.category] || 0) + 1;
    }
    return counts;
}

/**
 * {fields, models, views, security}: what Apply writes of ``review``, from
 * the items the last Apply did not write as they are: the new fields, the
 * models, the views whose changes it writes, the access rows, rules, apps
 * and groups.
 */
export function reviewWrites(review) {
    const result = {fields: 0, models: 0, views: 0, security: 0};
    for (const group of (review && review.groups) || []) {
        const pending = group.items.filter((item) => !item.applied);
        if (group.kind === "view" && pending.length) {
            result.views++;
        }
        for (const item of pending) {
            if (item.category === "fields") {
                result.fields++;
            } else if (item.category === "models" || item.category === "security") {
                result[item.category]++;
            }
        }
    }
    return result;
}

/**
 * The review space: every item of the draft by view and by model, with
 * what stops it from applying, what Apply writes and what it removes from
 * the database, then Apply. ``get_review`` reads the review when the
 * component mounts; the editor mounts it again for each revision and
 * state of the project. Its actions go through the editor: Show reaches
 * the item in its space, Undo removes a change of a view with what
 * depends on it, Apply sends the digest of the removal report on screen,
 * Discard goes back to the last Apply.
 *
 * When something leaves the database, Apply waits for « I understand ».
 * When Apply fails, the review is read again; a removal report that
 * changed shows with a warning and needs « I understand » again.
 */
export class StudioReview extends Component {
    static template = "erplibre_studio.Review";
    static props = {
        editor: Object,
        project: Object,
        busy: Boolean,
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            error: null,
            review: null,
            filter: "all",
            // Whether the items the last Apply wrote as they are show too.
            showApplied: false,
            understood: false,
            stale: false,
        });
        onWillStart(() => this.load());
    }

    get editor() {
        return this.props.editor;
    }

    get review() {
        return this.state.review;
    }

    /** Read the review of the project; answer it, or null on an error. */
    async load() {
        this.state.loading = true;
        try {
            const review = await this.orm.call(MODEL, "get_review", [this.props.project.id]);
            Object.assign(this.state, {review, error: null});
            return review;
        } catch (error) {
            this.state.error = this.editor.errorMessage(error);
            return null;
        } finally {
            this.state.loading = false;
        }
    }

    // ── items ───────────────────────────────────────────────────────────

    /** The items of the review the last Apply did not write as they are. */
    get pendingItems() {
        return reviewItems(this.review).filter((item) => !item.applied);
    }

    /** How many items the last Apply wrote as they are. */
    get appliedCount() {
        return reviewItems(this.review).length - this.pendingItems.length;
    }

    /** The items the list shows: pending ones, and the others on demand. */
    isShown(item) {
        return !item.applied || this.state.showApplied;
    }

    /** The filters with their counts: [{id, label, count, pressed}]. */
    get filters() {
        const counts = reviewCounts(reviewItems(this.review).filter((item) => this.isShown(item)));
        return REVIEW_FILTERS.map((id) => ({
            id,
            label: reviewFilterLabel(id),
            count: counts[id] || 0,
            pressed: this.state.filter === id,
        }));
    }

    /** The groups of the list, each with the items the filter keeps. */
    get groups() {
        const filter = this.state.filter;
        return ((this.review && this.review.groups) || [])
            .map((group) => ({
                ...group,
                items: group.items.filter(
                    (item) => this.isShown(item) && (filter === "all" || item.category === filter)
                ),
            }))
            .filter((group) => group.items.length);
    }

    setFilter(filter) {
        this.state.filter = filter;
    }

    toggleApplied() {
        this.state.showApplied = !this.state.showApplied;
    }

    itemKind(item) {
        return reviewItemKind(item);
    }

    showLabel(item) {
        return _t("Show: %(item)s", {item: item.text});
    }

    async show(item) {
        await this.editor.showReviewItem(item.target);
    }

    /**
     * Undo the change ``item`` with what depends on it
     * (StudioEditor.removeChange); the review mounts again on the new
     * revision.
     */
    undo(item) {
        return this.editor.removeChange(item.id);
    }

    undoLabel(item) {
        return _t("Undo: %(item)s", {item: item.text});
    }

    // ── technical names ─────────────────────────────────────────────────

    /**
     * The new fields and the new models whose technical name stops Apply:
     * [{change_id | line_id, model, name, message}], a field naming its
     * change, a model its model line.
     */
    get nameBlockers() {
        return (this.review && this.review.name_blockers) || [];
    }

    get nameBlockersText() {
        return _t("%(count)s technical name(s) block Apply", {count: this.nameBlockers.length});
    }

    /** The technical names of the change or the model line ``item`` that stop Apply, or []. */
    nameProblems(item) {
        const key = {change: "change_id", model: "line_id"}[item.type];
        return key ? this.nameBlockers.filter((blocker) => blocker[key] === item.id) : [];
    }

    // ── summary ─────────────────────────────────────────────────────────

    get intro() {
        if (this.props.project.state !== "draft") {
            return _t("The database has the draft: nothing to apply.");
        }
        const count = this.pendingItems.length;
        if (!count && this.leaves) {
            return _t("Nothing new to write: Apply removes from the database what left the draft.");
        }
        return _t("%(count)s change(s) to apply. Nothing is written to the database before you confirm.", {
            count,
        });
    }

    /** What Apply writes: [{key, label, count}]. */
    get writes() {
        const counts = reviewWrites(this.review);
        return [
            {key: "fields", label: _t("Fields"), count: counts.fields},
            {key: "models", label: _t("Models"), count: counts.models},
            {key: "views", label: _t("Edited views"), count: counts.views},
            {key: "security", label: _t("Apps, groups and rights"), count: counts.security},
        ];
    }

    get appliedText() {
        return _t("%(count)s item(s) unchanged since the last Apply", {count: this.appliedCount});
    }

    // ── what leaves the database ────────────────────────────────────────

    get removal() {
        return (this.review && this.review.removal) || {};
    }

    get sections() {
        return reportSections(this.removal.report);
    }

    get changesRemoved() {
        return (this.removal.report && this.removal.report.changes_removed) || 0;
    }

    get changesRemovedText() {
        return _t("%(count)s change(s) of the default views go with these views.", {count: this.changesRemoved});
    }

    /** Whether Apply removes something from the database. */
    get leaves() {
        return Boolean(this.sections.length || this.changesRemoved);
    }

    /**
     * Whether what Apply removes holds data (records, field values, group
     * members): the server's ``confirm``, which then requires the digest
     * of this report. The checkbox « I understand » shows for it only.
     */
    get losesData() {
        return Boolean(this.removal.confirm);
    }

    // ── Apply ───────────────────────────────────────────────────────────

    get applyLabel() {
        const count = this.pendingItems.length;
        return count ? _t("Apply %(count)s change(s)", {count}) : _t("Apply");
    }

    /** Why Apply cannot run now, or "": the button is disabled with it. */
    get applyBlocker() {
        const project = this.props.project;
        if (!this.review || this.state.loading) {
            return _t("Loading…");
        }
        if (project.state !== "draft" || !project.item_count) {
            return _t("Nothing to apply.");
        }
        if (this.nameBlockers.length) {
            return this.nameBlockersText;
        }
        if (this.review.blocked) {
            return _t("Fix what Apply refuses first.");
        }
        if (this.losesData && !this.state.understood) {
            return _t("Check « I understand » first: something leaves the database.");
        }
        return "";
    }

    toggleUnderstood(ev) {
        this.state.understood = ev.target.checked;
    }

    async apply() {
        if (this.props.busy || this.applyBlocker) {
            return;
        }
        const digest = this.removal.digest || false;
        if (await this.editor.applyReviewed(digest)) {
            return;
        }
        if (status(this) === "destroyed") {
            return;
        }
        // Refused: what Apply removes may have changed meanwhile.
        const review = await this.load();
        if (review && review.removal && review.removal.digest !== digest) {
            this.state.stale = true;
            this.state.understood = false;
        }
    }

    discard() {
        this.editor.discardDraft();
    }
}
