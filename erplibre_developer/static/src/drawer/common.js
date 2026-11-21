/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onWillUnmount, useEffect, useRef, useState} from "@odoo/owl";
import {browser} from "@web/core/browser/browser";
import {deserializeDateTime, formatDateTime} from "@web/core/l10n/dates";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";

/** The abstract model that answers the RPC calls of the drawer. */
export const MODEL = "erplibre.developer";
const {DateTime} = luxon;

/** A server datetime (UTC, « YYYY-MM-DD HH:MM:SS ») in the user's timezone. */
export function formatServerDateTime(value) {
    return value ? formatDateTime(deserializeDateTime(value)) : "";
}

/**
 * A server datetime (UTC, « YYYY-MM-DD HH:MM:SS ») relative to now, in the
 * user's language (« 3 days ago »); "" when ``value`` is not a date.
 */
export function formatRelativeServerDateTime(value) {
    const date = value ? deserializeDateTime(value) : null;
    return date && date.isValid ? date.toRelative() || "" : "";
}

/** An ISO 8601 date with its offset (``git log %aI``) in the user's timezone. */
export function formatIsoDateTime(value) {
    const date = value ? DateTime.fromISO(value) : null;
    return date && date.isValid ? formatDateTime(date.setZone("default")) : value || "";
}

/**
 * An ISO 8601 date (``git log %aI``) relative to now, in the user's
 * language (« 2 hours ago »); "" when ``value`` is not a date.
 */
export function formatRelativeIso(value) {
    const date = value ? DateTime.fromISO(value) : null;
    return date && date.isValid ? date.toRelative() || "" : "";
}

/** The first 12 characters of a commit hash, "" without one. */
export function shortSha(sha) {
    return (sha || "").slice(0, 12);
}

// The colours of Odoo's tags, ``.o_tag.o_tag_color_<n>``: 1 to 11, 0 being
// « no colour ». Their light and dark variants come with the theme.
export const MODULE_COLOR_COUNT = 11;

/**
 * The tag colour of a module, 1 to ``MODULE_COLOR_COUNT``: a hash of its
 * name (FNV-1a), so a module keeps its colour across pages and sessions.
 * Two modules may share one; the name always shows beside it.
 */
export function moduleColor(name) {
    let hash = 0x811c9dc5;
    for (const char of name || "") {
        hash ^= char.codePointAt(0);
        hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return (hash % MODULE_COLOR_COUNT) + 1;
}

/**
 * Whether the items of ``modules`` dim under the module filter ``filter``
 * (a module name, or null for none): they do when none of them is it.
 */
export function isDimmed(filter, modules) {
    return Boolean(filter) && !(modules || []).includes(filter);
}

// The last named step of an XPath: field, button, page, or the smart
// buttons box (``div[@name='button_box']``).
const NAMED_STEP = /(field|button|page|div)\[@name=['"]([\w.]+)['"]\]/g;

/**
 * The node a spec targets, from the last named step of its XPath: {tag,
 * name} (``tag`` one of field, button, page, div), or null when that step
 * names none.
 */
export function specTarget(spec) {
    const steps = [...(spec.expr || "").matchAll(NAMED_STEP)];
    const last = steps[steps.length - 1];
    return last ? {tag: last[1], name: last[2]} : null;
}

/**
 * What a spec does, in words: the attributes it sets, or the nodes it
 * brings (``content``, ``content_more`` left out), each as its tag and its
 * string or name. "" when the spec says nothing more than its position.
 */
export function specNote(spec) {
    if (spec.position === "attributes") {
        return (spec.attributes || []).length ? _t("attributes: %s", spec.attributes.join(", ")) : "";
    }
    const nodes = (spec.content || []).map((node) => [node.tag, node.string || node.name].filter(Boolean).join(" "));
    if (spec.content_more) {
        nodes.push(_t("%s more", spec.content_more));
    }
    if (spec.position === "replace") {
        return nodes.length ? _t("replaces with: %s", nodes.join(", ")) : _t("removes the node");
    }
    return nodes.length ? _t("adds: %s", nodes.join(", ")) : "";
}

/**
 * What hovering an applied view outlines in the page, as the items of the
 * service's ``highlight``: the node each spec targets (label « name ·
 * position · module »), the fields, buttons and pages a spec brings
 * (« name · added · module »), then the other fields of ``view.fields``
 * (« name · module »). Each node appears once, with its first label.
 */
export function viewHighlightItems(view) {
    const items = [];
    const seen = new Set();
    const module = view.module || "";
    const add = (kind, name, parts) => {
        const key = `${kind}:${name}`;
        if (!name || seen.has(key)) {
            return;
        }
        seen.add(key);
        items.push({kind, name, label: [name, ...parts].filter(Boolean).join(" · ")});
    };
    for (const spec of view.specs || []) {
        const target = specTarget(spec);
        if (target) {
            const {tag, name} = target;
            if (tag !== "div") {
                add(tag, name, [spec.position, module]);
            } else if (name === "button_box") {
                add("button_box", name, [spec.position, module]);
            }
        }
        for (const node of spec.content || []) {
            if (["field", "button", "page"].includes(node.tag)) {
                add(node.tag, node.name, [_t("added"), module]);
            }
        }
    }
    for (const name of view.fields || []) {
        add("field", name, [module]);
    }
    return items;
}

/**
 * What hovering a module outlines in the page, as the items of the
 * service's ``highlight``: what its views touch (``viewHighlightItems``),
 * then the fields it defines or overrides (« name · type · module »). Each
 * node appears once, with its first label.
 */
export function moduleHighlightItems(info, module) {
    const items = [];
    const seen = new Set();
    const add = (item) => {
        const key = `${item.kind || "field"}:${item.name}`;
        if (!seen.has(key)) {
            seen.add(key);
            items.push(item);
        }
    };
    for (const view of (info && info.views) || []) {
        if (view.module === module) {
            viewHighlightItems(view).forEach(add);
        }
    }
    for (const field of (info && info.fields) || []) {
        const defined = field.defined_in && field.defined_in.module === module;
        if (defined || (field.override_modules || []).includes(module)) {
            add({kind: "field", name: field.name, label: [field.name, field.type, module].join(" · ")});
        }
    }
    return items;
}

// One token of an arch line: a comment, the opening of a tag (``<``,
// ``</`` or ``<?`` and its name), an attribute with its quoted value, the
// end of a tag, white space, a run of text, or else one character. The
// last alternative takes any character the others leave, so the tokens of
// a line always join back into the line.
const ARCH_TOKEN =
    /(<!--.*?(?:-->|$))|(<[/?]?)([\w.:-]+)|([\w.:-]+)(=)("[^"]*"|'[^']*')|(\/?>|\?>)|(\s+|[^<>\s"'=/?]+)|([\s\S])/g;

/**
 * The tokens of one line of XML, for the colouring of an arch: a list of
 * {text, kind}, ``kind`` one of comment, punct, tag, attr, value and text.
 * The ``text`` of the tokens joined gives ``line`` back. A value quoted
 * over several lines is not recognised: its lines show as text.
 */
export function tokenizeArchLine(line) {
    const tokens = [];
    const push = (text, kind) => {
        const last = tokens[tokens.length - 1];
        if (last && last.kind === kind && kind === "text") {
            last.text += text;
        } else {
            tokens.push({text, kind});
        }
    };
    for (const match of line.matchAll(ARCH_TOKEN)) {
        const [, comment, open, tag, attr, equal, value, close, text, other] = match;
        if (comment !== undefined) {
            push(comment, "comment");
        } else if (open !== undefined) {
            push(open, "punct");
            push(tag, "tag");
        } else if (attr !== undefined) {
            push(attr, "attr");
            push(equal, "punct");
            push(value, "value");
        } else if (close !== undefined) {
            push(close, "punct");
        } else {
            push(text !== undefined ? text : other, "text");
        }
    }
    return tokens;
}

// Past this many lines, an arch shows as plain text: one token per line.
export const ARCH_COLOR_MAX_LINES = 3000;

/**
 * The lines of an arch for the drawer: [{n, text, tokens}], ``n`` from 1.
 * ``texts`` is the list of the lines; past ``ARCH_COLOR_MAX_LINES`` each
 * line keeps a single text token.
 */
export function archLines(texts) {
    const color = texts.length <= ARCH_COLOR_MAX_LINES;
    return texts.map((text, index) => ({
        n: index + 1,
        text,
        tokens: color ? tokenizeArchLine(text) : [{text, kind: "text"}],
    }));
}

// How long the copy button shows « Path copied », in milliseconds.
const COPIED_DELAY = 2000;

/** A file and a line: copied to the clipboard, or opened in the IDE. */
export class SourceLocation extends Component {
    static template = "erplibre_developer.SourceLocation";
    static props = {
        file: {type: [String, Boolean], optional: true},
        fileRel: {type: [String, Boolean], optional: true},
        line: {type: Number, optional: true},
        ide: {type: Boolean, optional: true},
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        // Without a clipboard (no secure context), the path shows in a
        // selected field of the drawer, to copy by hand.
        // ``copied`` turns the copy button into « Path copied » for
        // ``COPIED_DELAY``.
        this.copyState = useState({manual: false, copied: false});
        this.copiedTimer = null;
        onWillUnmount(() => browser.clearTimeout(this.copiedTimer));
        this.manualRef = useRef("manual");
        useEffect(
            (el) => {
                if (el) {
                    el.focus();
                    el.select();
                }
            },
            () => [this.manualRef.el]
        );
    }

    get text() {
        const line = this.props.line ? `:${this.props.line}` : "";
        return `${this.props.fileRel || this.props.file}${line}`;
    }

    get copyLabel() {
        return this.copyState.copied ? _t("Path copied") : _t("Copy the path");
    }

    get fullText() {
        const line = this.props.line ? `:${this.props.line}` : "";
        return `${this.props.file}${line}`;
    }

    async copy() {
        try {
            await browser.navigator.clipboard.writeText(this.fullText);
            this.copyState.manual = false;
            this.copyState.copied = true;
            browser.clearTimeout(this.copiedTimer);
            this.copiedTimer = browser.setTimeout(() => {
                this.copyState.copied = false;
            }, COPIED_DELAY);
            this.notification.add(_t("Path copied."), {type: "info"});
        } catch {
            this.copyState.manual = true;
            this.notification.add(this.fullText, {title: _t("Copy this path"), type: "warning"});
        }
    }

    closeManual() {
        this.copyState.manual = false;
    }

    async openInIde() {
        await this.orm.call(MODEL, "action_open_in_ide", [this.props.file, this.props.line || 0]);
    }
}

/**
 * The recent commits of a module, as ``loadCommits`` of the drawer stores
 * them: ``{loading, clone_rel, commits: [{sha, subject, author, date}],
 * error}``, each date relative with the full date as its title. Nothing
 * renders while ``commits`` is undefined (never asked). ``id`` is the id
 * of the block, for the ``aria-controls`` of its toggle.
 */
export class Commits extends Component {
    static template = "erplibre_developer.Commits";
    static props = {
        commits: {type: Object, optional: true},
        id: {type: String, optional: true},
    };

    shortSha(sha) {
        return shortSha(sha);
    }

    commitDate(value) {
        return formatIsoDateTime(value);
    }

    commitWhen(value) {
        return formatRelativeIso(value) || formatIsoDateTime(value);
    }
}
