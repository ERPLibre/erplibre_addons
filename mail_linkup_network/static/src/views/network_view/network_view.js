import {Component, onWillStart, useEffect, useExternalListener, useRef, useState} from "@odoo/owl";

import {deserializeDateTime, formatDate, formatDateTime} from "@web/core/l10n/dates";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {user} from "@web/core/user";
import {useService} from "@web/core/utils/hooks";
import {imageUrl} from "@web/core/utils/urls";
import {formatInteger} from "@web/views/fields/formatters";

import {LinkupCategoryIcon} from "@mail_linkup_reflet/core/common/linkup_category_icon";
import {LinkupErrorAlert} from "@mail_linkup_reflet/core/common/linkup_error_alert";
import {linkupClientError, linkupErrorInfo, linkupMediaDenied} from "@mail_linkup_reflet/core/common/linkup_errors";
import {LinkupGuideButton} from "@mail_linkup_reflet/core/common/linkup_guide";
import {linkupPlaySound} from "@mail_linkup_reflet/core/common/linkup_signals";

import {
    LINKUP_GRAPH_SIZES,
    linkupLineWidth,
    linkupPlace,
    linkupRadialLayout,
    linkupStrength,
} from "../../core/common/network_layout";

/** Nodes asked of the server, its own bound (LU-F-070 RM3). */
export const LINKUP_NETWORK_LIMIT = 50;
/** Entries of the thread of a link card read at once. */
export const LINKUP_CARD_LIMIT = 20;
/** The densities, in the order of the cycle X1 → X2 → X3 → X1 (Q-40). */
export const LINKUP_LEVELS = ["x1", "x2", "x3"];
/**
 * The rankings, in the order of the tabs and of the cycle of the list
 * button on a small screen: the most active, my partners, then back to the
 * graph (Q-40).
 */
export const LINKUP_RANKINGS = ["active", "partners"];

/**
 * The Network view (client action `linkup.network_view`, LU-F-070 to
 * LU-F-076): the graph centred on the member, its density, the rankings of
 * the contacts and the card of a link, as `linkup.link` serves them
 * (`get_network_graph`, `get_ranking`, `get_link_card`).
 *
 * The graph is an SVG drawn in the client: the member in the centre, each
 * contact around, strongest first, the width of each line and the size of
 * each node growing with the energy of the link; X1 adds the grey lines the
 * server sends between two contacts who both show their links. The nodes
 * are buttons laid over the SVG, reached by a single `Tab` and walked with
 * the arrow keys; "The graph as a list" says the same in text, for a
 * screen reader. A node, the line of a link or a row of a ranking opens the
 * card of the link; a click outside the card, `Escape` or the energy
 * bubble closes it and gives the focus back to what opened it.
 *
 * The densities X1, X2 and X3 are three buttons on a large screen and one
 * round button that cycles on a small one, where the rankings open with the
 * list button instead of standing beside the graph: each press goes on to
 * the next ranking, then back to the graph. The period applies to "The
 * most active" only, so that "My partners" and the card of a link always
 * show the same energy (LU-F-071 RM2). The bottom left corner
 * holds the happiness field and the shortcut to the Reflet view (Q-10), the
 * bottom right "+ NewLink" (LU-F-076). "Back" and `Escape` out of a field
 * go back to the previous screen (LU-F-002 RM3).
 *
 * With "Hide the points and their animations", no number of points shows:
 * the lines and the nodes keep one size, "The most active" and the period
 * go, and "My partners" lists the contacts by name. A new ledger line of the
 * member reads the graph and the ranking again. In guide mode, a node, a
 * line or a row explains itself instead of opening the card.
 */
export class LinkupNetworkView extends Component {
    static template = "mail_linkup_network.LinkupNetworkView";
    static components = {LinkupCategoryIcon, LinkupErrorAlert, LinkupGuideButton};
    static props = ["*"];

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.store = useState(useService("mail.store"));
        this.ui = useState(useService("ui"));
        this.guide = useState(useService("linkup.guide"));
        this.points = useState(useService("linkup.points").state);
        this.root = useRef("root");
        this.cardRef = useRef("card");
        this.happinessRef = useRef("happiness");
        this.happinessListRef = useRef("happinessList");
        this.state = useState({
            loaded: false,
            loadError: null,
            level: "x1",
            graph: null,
            graphError: null,
            tab: "partners",
            period: "all",
            rankings: {partners: null, active: null},
            rankingError: null,
            rankingOpen: false,
            card: null,
            cardUserId: null,
            cardLoading: false,
            cardError: null,
            cardNotice: "",
            refletsOnly: false,
            focusIndex: 0,
            happinessOpen: false,
            happinessIndex: 0,
            happinessBusy: false,
            happinessError: null,
            happinessNotice: "",
            announcement: "",
            preferenceError: null,
            focusRequest: 0,
        });
        /** What the next rendering gives the focus to; see `requestFocus`. */
        this.focusTarget = null;
        /** The element that opened the card, which takes the focus back. */
        this.cardOpener = null;
        onWillStart(() => this.load());
        useEffect(
            () => this.applyFocus(),
            () => [this.state.focusRequest]
        );
        let first = true;
        useEffect(
            () => {
                if (first) {
                    first = false;
                    return;
                }
                this.reload();
            },
            () => [this.points.version]
        );
        useEffect(
            (guideActive) => {
                if (guideActive && this.state.happinessOpen) {
                    this.state.happinessOpen = false;
                }
            },
            () => [this.guide.active]
        );
        // On the document, not the window: the hotkey service listens on the
        // window and stops a key that a global hotkey takes, as the
        // "escape" of the website service; the document hears it first,
        // after the handlers of the elements.
        useExternalListener(document, "keydown", (ev) => this.onDocumentKeydown(ev));
        useExternalListener(window, "pointerdown", (ev) => this.onWindowPointerdown(ev));
    }

    // ------------------------------------------------------------------
    // Loading
    // ------------------------------------------------------------------

    /** Read the graph and the ranking of the open tab. */
    async load() {
        this.state.loadError = null;
        try {
            await Promise.all([this.loadGraph({raise: true}), this.loadRankings({raise: true})]);
            this.state.loaded = true;
        } catch (error) {
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.loadError = info;
        }
    }

    /** Read again what the view shows, after a new ledger line. */
    reload() {
        if (!this.state.loaded) {
            return;
        }
        this.loadGraph();
        this.loadRankings();
    }

    /**
     * Read the graph at the density of the view.
     *
     * @param {{raise?: boolean}} [options] `raise` lets a refusal through,
     *  for the first reading
     */
    async loadGraph({raise = false} = {}) {
        try {
            const graph = await this.orm.silent.call("linkup.link", "get_network_graph", [], {
                level: this.state.level,
                limit: LINKUP_NETWORK_LIMIT,
            });
            this.state.graph = graph;
            this.state.graphError = null;
            this.state.focusIndex = Math.min(this.state.focusIndex, Math.max(graph.nodes.length - 1, 0));
        } catch (error) {
            if (raise) {
                throw error;
            }
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.graphError = info;
        }
    }

    /**
     * Read "My partners", which also lists the contacts of the happiness
     * field, and "The most active" when it is the open tab.
     *
     * @param {{raise?: boolean}} [options]
     */
    async loadRankings({raise = false} = {}) {
        const kinds = ["partners"];
        if (this.state.tab === "active" && !this.pointsHidden) {
            kinds.push("active");
        }
        try {
            const results = await Promise.all(
                kinds.map((kind) =>
                    this.orm.silent.call("linkup.link", "get_ranking", [], {kind, period: this.rankingPeriod(kind)})
                )
            );
            for (const result of results) {
                this.state.rankings[result.kind] = result.rows;
            }
            this.state.rankingError = null;
        } catch (error) {
            if (raise) {
                throw error;
            }
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.rankingError = info;
        }
    }

    /**
     * The period of a ranking: the one chosen for "The most active"
     * (LU-F-073 RM1); "My partners" counts every line, as the card of a
     * link does.
     *
     * @param {"partners"|"active"} kind
     */
    rankingPeriod(kind) {
        return kind === "active" ? this.state.period : "all";
    }

    // ------------------------------------------------------------------
    // Member and points
    // ------------------------------------------------------------------

    get pointsHidden() {
        return Boolean(this.store.settings?.linkup_hide_gamification);
    }

    get selfName() {
        return this.state.graph?.me.name || this.store.self?.name || "";
    }

    get selfAvatarUrl() {
        return this.store.self?.avatarUrl;
    }

    /** @param {{partner_id: number}} contact */
    avatarUrl(contact) {
        return imageUrl("res.partner", contact.partner_id, "avatar_128");
    }

    /** The energy of the member, their decayed karma, as the Store follows it. */
    get energy() {
        return formatInteger(this.store.linkupEnergy ?? this.state.graph?.me.energy ?? 0);
    }

    get energyLabel() {
        if (this.pointsHidden) {
            return _t("Back to the graph");
        }
        return _t("My energy: %(points)s points. Back to the graph.", {points: this.energy});
    }

    /** @param {number} value */
    formatPoints(value) {
        return formatInteger(value || 0);
    }

    // ------------------------------------------------------------------
    // Graph
    // ------------------------------------------------------------------

    get size() {
        return this.ui.isSmall ? LINKUP_GRAPH_SIZES.narrow : LINKUP_GRAPH_SIZES.wide;
    }

    get viewBox() {
        return `0 0 ${this.size.width} ${this.size.height}`;
    }

    get canvasStyle() {
        return `aspect-ratio: ${this.size.width} / ${this.size.height};`;
    }

    get centre() {
        return {x: this.size.width / 2, y: this.size.height / 2};
    }

    get centreStyle() {
        return linkupPlace(this.centre, this.size);
    }

    get nodes() {
        return this.state.graph?.nodes || [];
    }

    /**
     * The nodes with their place: `x` and `y` in the `viewBox`, `style`
     * placing the button, `hit` the middle of the line, `strength` from 0
     * to 1 and `width` the width of the line. With the points hidden,
     * every link has the same strength.
     */
    get layoutNodes() {
        const nodes = this.nodes;
        const size = this.size;
        const positions = linkupRadialLayout(nodes.length, size);
        const max = Math.max(0, ...nodes.map((node) => node.energy || 0));
        const centre = this.centre;
        return nodes.map((node, index) => {
            const point = positions[index];
            const strength = this.pointsHidden ? 0.5 : linkupStrength(node.energy, max);
            const hit = {x: (centre.x + point.x) / 2, y: (centre.y + point.y) / 2};
            return {
                ...node,
                index,
                x: point.x,
                y: point.y,
                strength,
                width: linkupLineWidth(strength),
                style: `${linkupPlace(point, size)} --o-linkup-node-scale: ${(1 + strength * 0.6).toFixed(2)};`,
                hitStyle: linkupPlace(hit, size),
            };
        });
    }

    /** The grey lines of X1 between two contacts drawn on the graph. */
    get greyEdges() {
        const placed = new Map(this.layoutNodes.map((node) => [node.user_id, node]));
        return (this.state.graph?.edges || [])
            .filter((edge) => edge.kind === "contacts")
            .map((edge) => ({source: placed.get(edge.source), target: placed.get(edge.target)}))
            .filter((edge) => edge.source && edge.target)
            .map((edge) => ({
                key: `${edge.source.user_id}-${edge.target.user_id}`,
                x1: edge.source.x,
                y1: edge.source.y,
                x2: edge.target.x,
                y2: edge.target.y,
            }));
    }

    /**
     * The other contacts drawn that a contact is linked with, through the
     * grey lines.
     *
     * @param {{user_id: number}} node
     * @returns {string} their names, or `""`
     */
    alsoLinkedWith(node) {
        const names = new Map(this.nodes.map((other) => [other.user_id, other.name]));
        const linked = (this.state.graph?.edges || [])
            .filter((edge) => edge.kind === "contacts")
            .map((edge) =>
                edge.source === node.user_id ? edge.target : edge.target === node.user_id ? edge.source : null
            )
            .filter((id) => names.has(id))
            .map((id) => names.get(id));
        return linked.join(", ");
    }

    /** @param {Object} node */
    nodeLabel(node) {
        const parts = [
            this.pointsHidden
                ? _t("%(name)s. Open the card of the link.", {name: node.name})
                : _t("%(name)s, energy of the link %(points)s points. Open the card of the link.", {
                      name: node.name,
                      points: this.formatPoints(node.energy),
                  }),
        ];
        if (node.highlight) {
            parts.push(this.highlightLabel(node));
        }
        return parts.join(" ");
    }

    /** @param {{name: string}} node */
    lineLabel(node) {
        return _t("Link with %(name)s", {name: node.name});
    }

    /** @param {{name: string}} contact */
    highlightLabel(contact) {
        return _t("%(name)s adds to your happiness.", {name: contact.name});
    }

    /** One line of the graph as a list. */
    listEntry(node) {
        const parts = [node.name];
        if (!this.pointsHidden) {
            parts.push(_t("%(points)s points", {points: this.formatPoints(node.energy)}));
        }
        const also = this.alsoLinkedWith(node);
        if (also) {
            parts.push(_t("also linked with %(names)s", {names: also}));
        }
        if (node.highlight) {
            parts.push(this.highlightLabel(node));
        }
        return parts.join(" · ");
    }

    /** @param {string} level */
    levelName(level) {
        return level.toUpperCase();
    }

    /** @param {string} level */
    levelHint(level) {
        switch (level) {
            case "x1":
                return _t("Two levels: my links, and the links between my contacts who agree to show them");
            case "x2":
                return _t("My direct links only");
        }
        return _t("My %(count)s strongest partners", {count: this.topCount});
    }

    get topCount() {
        return this.store.linkup_network_top_count || 2;
    }

    get nextLevel() {
        const index = LINKUP_LEVELS.indexOf(this.state.level);
        return LINKUP_LEVELS[(index + 1) % LINKUP_LEVELS.length];
    }

    get cycleLabel() {
        return _t("Density %(level)s: %(hint)s. Press for %(next)s.", {
            level: this.levelName(this.state.level),
            hint: this.levelHint(this.state.level),
            next: this.levelName(this.nextLevel),
        });
    }

    get graphSummary() {
        const count = this.nodes.length;
        if (!count) {
            return _t("You have no active link yet. A confirmed reflection creates one.");
        }
        return _t("You, %(name)s, in the centre, and %(count)s people around you. %(level)s: %(hint)s.", {
            name: this.selfName,
            count,
            level: this.levelName(this.state.level),
            hint: this.levelHint(this.state.level),
        });
    }

    get moreLabel() {
        return _t("Only the %(count)s strongest links are drawn.", {count: this.nodes.length});
    }

    get listSummary() {
        return _t("The graph as a list (%(count)s)", {count: this.nodes.length});
    }

    /**
     * Change the density and read the graph again; the change is announced.
     *
     * @param {string} level
     */
    async setLevel(level) {
        if (level === this.state.level && this.state.graph) {
            return;
        }
        this.state.level = level;
        await this.loadGraph();
        this.state.announcement = _t("%(level)s: %(hint)s. %(count)s people shown.", {
            level: this.levelName(level),
            hint: this.levelHint(level),
            count: this.nodes.length,
        });
    }

    cycleLevel() {
        return this.setLevel(this.nextLevel);
    }

    /**
     * The arrow keys walk the nodes of the graph, `Home` and `End` reach
     * the first and the last; the node in focus is the only one `Tab`
     * stops on.
     *
     * @param {KeyboardEvent} ev
     */
    onGraphKeydown(ev) {
        const count = this.nodes.length;
        if (!count || !ev.target.closest?.(".o-linkup-NetworkView-node")) {
            return;
        }
        let index = this.state.focusIndex;
        switch (ev.key) {
            case "ArrowRight":
            case "ArrowDown":
                index = (index + 1) % count;
                break;
            case "ArrowLeft":
            case "ArrowUp":
                index = (index - 1 + count) % count;
                break;
            case "Home":
                index = 0;
                break;
            case "End":
                index = count - 1;
                break;
            default:
                return;
        }
        ev.preventDefault();
        this.state.focusIndex = index;
        this.requestFocus("node");
    }

    /** The energy bubble closes the card or the ranking and goes back to the graph. */
    backToGraph() {
        this.state.rankingOpen = false;
        this.state.happinessOpen = false;
        if (this.state.card || this.state.cardUserId) {
            this.cardOpener = null;
            this.closeCard();
        }
        this.requestFocus("node");
    }

    // ------------------------------------------------------------------
    // Rankings
    // ------------------------------------------------------------------

    /** The tabs of the rankings, without "The most active" when the points are hidden. */
    get tabs() {
        const tabs = {
            active: {kind: "active", label: _t("The most active"), guide: "network-active"},
            partners: {kind: "partners", label: _t("My partners"), guide: "network-partners"},
        };
        return LINKUP_RANKINGS.filter((kind) => kind === "partners" || !this.pointsHidden).map((kind) => tabs[kind]);
    }

    get currentTab() {
        return this.pointsHidden ? "partners" : this.state.tab;
    }

    /** The rows of the open tab; by name when the points are hidden. */
    get rows() {
        const rows = this.state.rankings[this.currentTab] || [];
        if (!this.pointsHidden) {
            return rows;
        }
        return [...rows].sort((a, b) => a.name.localeCompare(b.name));
    }

    get rankingHint() {
        if (this.pointsHidden) {
            return _t("The people you have an active link with.");
        }
        if (this.currentTab === "active") {
            return _t(
                "The energy of your contacts who show it, rounded to the hundred, without penalties. Never the whole community."
            );
        }
        return _t("The points you received with each person: the energy of your link.");
    }

    get rankingEmpty() {
        if (this.currentTab === "active") {
            return _t("None of your contacts shows their energy yet.");
        }
        return _t("You have no active link yet. A confirmed reflection creates one.");
    }

    /** @param {{name: string, value: number, position: number}} row */
    rowLabel(row) {
        if (this.pointsHidden) {
            return _t("%(name)s. Open the card of the link.", {name: row.name});
        }
        return _t("%(position)s. %(name)s, %(points)s points. Open the card of the link.", {
            position: row.position,
            name: row.name,
            points: this.formatPoints(row.value),
        });
    }

    /** @param {"partners"|"active"} kind */
    async selectTab(kind) {
        if (this.state.tab === kind) {
            return;
        }
        this.state.tab = kind;
        await this.loadRankings();
    }

    /**
     * The tabs of the rankings: the arrow keys move from one to the other.
     *
     * @param {KeyboardEvent} ev
     */
    onTabsKeydown(ev) {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(ev.key)) {
            return;
        }
        const tabs = this.tabs;
        const index = tabs.findIndex((tab) => tab.kind === this.currentTab);
        let next = index;
        if (ev.key === "ArrowRight") {
            next = (index + 1) % tabs.length;
        } else if (ev.key === "ArrowLeft") {
            next = (index - 1 + tabs.length) % tabs.length;
        } else if (ev.key === "Home") {
            next = 0;
        } else {
            next = tabs.length - 1;
        }
        ev.preventDefault();
        this.selectTab(tabs[next].kind);
        this.requestFocus("tab");
    }

    /** @param {Event} ev */
    async onChangePeriod(ev) {
        this.state.period = ev.target.value;
        await this.loadRankings();
    }

    /**
     * The list button of a small screen: it opens the first ranking, goes
     * on to the next one at each press, then closes them to show the graph
     * again (Q-40).
     */
    async toggleRanking() {
        const kinds = this.tabs.map((tab) => tab.kind);
        if (!this.state.rankingOpen) {
            this.state.rankingOpen = true;
            await this.selectTab(kinds[0]);
            this.requestFocus("tab");
            return;
        }
        const next = kinds[kinds.indexOf(this.currentTab) + 1];
        if (next) {
            await this.selectTab(next);
            this.requestFocus("tab");
            return;
        }
        this.state.rankingOpen = false;
    }

    /** What the list button shows next, for its label. */
    get listLabel() {
        if (!this.state.rankingOpen) {
            return _t("Rankings: show %(ranking)s", {ranking: this.tabs[0].label});
        }
        const tabs = this.tabs;
        const next = tabs[tabs.findIndex((tab) => tab.kind === this.currentTab) + 1];
        if (next) {
            return _t("Rankings: show %(ranking)s", {ranking: next.label});
        }
        return _t("Rankings: back to the graph");
    }

    // ------------------------------------------------------------------
    // Privacy (LU-NF-012)
    // ------------------------------------------------------------------

    /** The two preferences of the network, off by default. */
    get preferences() {
        return [
            {
                field: "linkup_links_visible",
                label: _t("My links are visible to my links"),
                help: _t("Draws a grey line in X1 between you and another contact who shows their links too."),
                checked: Boolean(this.store.linkup_links_visible),
            },
            {
                field: "linkup_energy_visible",
                label: _t("My energy is visible to my links"),
                help: _t("Lists you in “The most active” of your links, rounded and without penalties."),
                checked: Boolean(this.store.linkup_energy_visible),
            },
        ];
    }

    /**
     * Write a preference of the member on their own account; the Store
     * follows at once, and the bus tells the other tabs.
     *
     * @param {string} field
     * @param {Event} ev
     */
    async onChangePreference(field, ev) {
        if (this.guide.active) {
            return;
        }
        const value = ev.target.checked;
        this.state.preferenceError = null;
        try {
            await this.orm.silent.write("res.users", [user.userId], {[field]: value});
            this.store[field] = value;
        } catch (error) {
            ev.target.checked = !value;
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.preferenceError = info;
        }
    }

    // ------------------------------------------------------------------
    // Link card
    // ------------------------------------------------------------------

    /**
     * Open the card of the link with a contact, from a node, a line or a
     * row; the element pressed takes the focus back once it closes.
     *
     * @param {{user_id: number}} contact
     * @param {Event} [ev]
     */
    async openCard(contact, ev) {
        if (this.guide.active) {
            return;
        }
        this.cardOpener = ev?.currentTarget || document.activeElement;
        this.state.cardUserId = contact.user_id;
        this.state.refletsOnly = false;
        this.state.cardNotice = "";
        this.state.cardError = null;
        await this.loadCard();
        this.requestFocus("card");
    }

    async loadCard() {
        const userId = this.state.cardUserId;
        if (!userId) {
            return;
        }
        this.state.cardLoading = true;
        try {
            const card = await this.orm.silent.call("linkup.link", "get_link_card", [userId], {
                reflets_only: this.state.refletsOnly,
                limit: LINKUP_CARD_LIMIT,
            });
            if (this.state.cardUserId !== userId) {
                return;
            }
            if (card.store) {
                this.store.insert(card.store);
            }
            this.state.card = card;
        } catch (error) {
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.cardError = info;
            this.state.card = this.state.card || {available: false, user_id: userId};
        } finally {
            this.state.cardLoading = false;
        }
    }

    /** Close the card and give the focus back to what opened it. */
    closeCard() {
        this.state.card = null;
        this.state.cardUserId = null;
        this.state.cardError = null;
        this.state.cardNotice = "";
        const opener = this.cardOpener;
        this.cardOpener = null;
        if (opener?.isConnected) {
            opener.focus();
        }
    }

    async toggleRefletsOnly() {
        this.state.refletsOnly = !this.state.refletsOnly;
        await this.loadCard();
    }

    get card() {
        return this.state.card;
    }

    get cardTitle() {
        return _t("Link with %(name)s", {name: this.card?.name || ""});
    }

    get cardEnergyLabel() {
        return _t("Energy of the link: %(points)s points", {points: this.formatPoints(this.card?.energy)});
    }

    get firstLinkLabel() {
        const date = this.card?.first_link_date;
        return date ? _t("First link: %(date)s", {date: formatDate(deserializeDateTime(date))}) : "";
    }

    get callLabel() {
        return _t("Call %(name)s", {name: this.card?.name || ""});
    }

    get videoLabel() {
        return _t("Video call with %(name)s", {name: this.card?.name || ""});
    }

    get highlightActionLabel() {
        return this.card?.highlight_sent ? _t("In the light") : _t("Put in the light");
    }

    /** @param {{date: string}} entry */
    entryDate(entry) {
        return formatDateTime(deserializeDateTime(entry.date));
    }

    /** @param {{reflet_id: number|false}} entry */
    entryReflet(entry) {
        return entry.reflet_id ? this.store["linkup.reflet"].get(entry.reflet_id) : null;
    }

    /** @param {{mine: boolean}} entry */
    entryAuthor(entry) {
        return entry.mine ? _t("You") : this.card?.name || "";
    }

    /** The direct conversation of the card, created when the member has none yet. */
    async cardThread() {
        const card = this.card;
        let channelId = card?.channel_id;
        if (!channelId && card?.partner_id) {
            const chat = await this.store.getChat({partnerId: card.partner_id});
            channelId = chat?.id;
        }
        return channelId ? this.store.Thread.getOrFetch({model: "discuss.channel", id: channelId}) : null;
    }

    /** Open the direct conversation of the card in Discuss. */
    async openConversation() {
        const thread = await this.cardThread().catch(() => null);
        if (!thread) {
            this.state.cardError = linkupClientError("network");
            return null;
        }
        await this.action.doAction({
            type: "ir.actions.client",
            tag: "mail.action_discuss",
            context: {active_id: `discuss.channel_${thread.id}`},
        });
        return thread;
    }

    /**
     * Call the contact, or start a video call: the conversation opens in
     * Discuss with the call. Nothing starts while the browser refuses the
     * microphone, or the camera.
     *
     * @param {{camera?: boolean}} [options]
     */
    async startCall({camera = false} = {}) {
        this.state.cardError = null;
        if (await linkupMediaDenied({camera})) {
            this.state.cardError = linkupClientError("media_denied");
            return;
        }
        const thread = await this.openConversation();
        if (thread) {
            this.env.services["discuss.rtc"].toggleCall(thread, {camera});
        }
    }

    /** Put the contact of the card in the light (LU-F-051). */
    async highlightCard() {
        const card = this.card;
        if (!card?.available || card.highlight_sent) {
            return;
        }
        this.state.cardError = null;
        try {
            await this.orm.silent.call("linkup.highlight", "action_send", [card.user_id]);
            card.highlight_sent = true;
            this.state.cardNotice = _t("%(name)s sees your avatar on theirs until your next exchange.", {
                name: card.name,
            });
            linkupPlaySound(this.env.services, "linkup-sent");
        } catch (error) {
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.cardError = info;
        }
    }

    /** Open the Reflet view with the contact of the card as the recipient. */
    newReflet() {
        return this.action.doAction("mail_linkup_reflet.action_linkup_home", {
            additionalContext: {linkup_recipient_user_id: this.card.user_id},
        });
    }

    // ------------------------------------------------------------------
    // Navigation (LU-F-076)
    // ------------------------------------------------------------------

    openRefletView() {
        return this.action.doAction("mail_linkup_reflet.action_linkup_home");
    }

    openNewlink() {
        return this.action.doAction("mail_linkup_reflet.action_linkup_home", {
            additionalContext: {linkup_newlink: true},
        });
    }

    /** Back to the previous screen, or to Discuss when there is none. */
    async goBack() {
        try {
            await this.action.restore();
        } catch {
            await this.action.doAction("mail.action_discuss");
        }
    }

    /**
     * `Escape` closes what is open, from the list of the happiness field to
     * the card and the ranking; on the graph, out of a field, it goes back.
     * The guide and the dialogs answer it first.
     *
     * @param {KeyboardEvent} ev
     */
    onDocumentKeydown(ev) {
        if (ev.key !== "Escape" || ev.defaultPrevented || this.guide.active) {
            return;
        }
        if (document.querySelector(".modal")) {
            return;
        }
        if (this.state.happinessOpen) {
            ev.preventDefault();
            this.closeHappiness();
            return;
        }
        if (this.state.card || this.state.cardUserId) {
            ev.preventDefault();
            this.closeCard();
            return;
        }
        if (this.state.rankingOpen) {
            ev.preventDefault();
            this.state.rankingOpen = false;
            return;
        }
        const target = ev.target;
        if (target instanceof Element && target.closest("input, textarea, select, [contenteditable='true']")) {
            return;
        }
        ev.preventDefault();
        this.goBack();
    }

    /**
     * A press outside the card closes it; a node, a line or a row opens
     * another card instead.
     *
     * @param {PointerEvent} ev
     */
    onWindowPointerdown(ev) {
        if (!this.state.card || this.guide.active) {
            return;
        }
        const target = ev.target;
        if (!(target instanceof Element) || this.cardRef.el?.contains(target)) {
            return;
        }
        if (
            target.closest(
                ".o-linkup-NetworkView-node, .o-linkup-NetworkView-lineHit, .o-linkup-NetworkView-row, .o-linkup-NetworkView-listEntry, .o-linkup-GuideSheet, .modal, .o-linkup-NetworkView-energy"
            )
        ) {
            return;
        }
        this.cardOpener = null;
        this.closeCard();
    }

    // ------------------------------------------------------------------
    // You add to my happiness
    // ------------------------------------------------------------------

    /** The contacts of the happiness field: those of "My partners". */
    get contacts() {
        return this.state.rankings.partners || [];
    }

    get happinessHint() {
        return _t("Choose a person to thank them for an exchange that did you good.");
    }

    /** @param {{user_id: number}} contact */
    happinessOptionId(contact) {
        return `o-linkup-NetworkView-happinessOption-${contact.user_id}`;
    }

    get happinessActiveId() {
        const contact = this.contacts[this.state.happinessIndex];
        return contact ? this.happinessOptionId(contact) : undefined;
    }

    openHappiness() {
        if (this.guide.active || !this.contacts.length) {
            return;
        }
        this.state.happinessIndex = 0;
        this.state.happinessOpen = true;
        this.state.happinessError = null;
        this.state.happinessNotice = "";
        this.requestFocus("happinessList");
    }

    closeHappiness() {
        this.state.happinessOpen = false;
        this.requestFocus("happiness");
    }

    /** @param {{user_id: number, name: string}} contact */
    async highlightContact(contact) {
        if (this.guide.active || this.state.happinessBusy) {
            return;
        }
        this.state.happinessOpen = false;
        this.state.happinessBusy = true;
        this.state.happinessError = null;
        this.state.happinessNotice = "";
        try {
            await this.orm.silent.call("linkup.highlight", "action_send", [contact.user_id]);
            this.state.happinessNotice = _t("%(name)s sees your avatar on theirs until your next exchange.", {
                name: contact.name,
            });
            linkupPlaySound(this.env.services, "linkup-sent");
        } catch (error) {
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.happinessError = info;
        } finally {
            this.state.happinessBusy = false;
        }
        this.requestFocus("happiness");
    }

    /** @param {KeyboardEvent} ev */
    onHappinessKeydown(ev) {
        const count = this.contacts.length;
        let index = this.state.happinessIndex;
        switch (ev.key) {
            case "ArrowDown":
                index = (index + 1) % count;
                break;
            case "ArrowUp":
                index = (index - 1 + count) % count;
                break;
            case "Home":
                index = 0;
                break;
            case "End":
                index = count - 1;
                break;
            case "Enter":
            case " ":
                ev.preventDefault();
                ev.stopPropagation();
                if (this.contacts[index]) {
                    this.highlightContact(this.contacts[index]);
                }
                return;
            case "Escape":
                ev.preventDefault();
                ev.stopPropagation();
                this.closeHappiness();
                return;
            default:
                return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        this.state.happinessIndex = index;
    }

    // ------------------------------------------------------------------
    // Focus
    // ------------------------------------------------------------------

    /** @param {"node"|"tab"|"card"|"happiness"|"happinessList"} target */
    requestFocus(target) {
        this.focusTarget = target;
        this.state.focusRequest++;
    }

    applyFocus() {
        const target = this.focusTarget;
        this.focusTarget = null;
        const el = this.root.el;
        if (!target || !el) {
            return;
        }
        if (target === "node") {
            el.querySelector(`.o-linkup-NetworkView-node[data-index='${this.state.focusIndex}']`)?.focus();
        } else if (target === "tab") {
            el.querySelector(".o-linkup-NetworkView-tab[aria-selected='true']")?.focus();
        } else if (target === "card") {
            this.cardRef.el?.focus();
        } else if (target === "happiness") {
            this.happinessRef.el?.focus();
        } else if (target === "happinessList") {
            this.happinessListRef.el?.focus();
        }
    }
}

registry.category("actions").add("linkup.network_view", LinkupNetworkView);
