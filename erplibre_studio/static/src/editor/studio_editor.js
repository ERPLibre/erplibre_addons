/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onPatched, onWillStart, useState} from "@odoo/owl";
import {ConfirmationDialog} from "@web/core/confirmation_dialog/confirmation_dialog";
import {Dropdown} from "@web/core/dropdown/dropdown";
import {useDropdownState} from "@web/core/dropdown/dropdown_hooks";
import {deserializeDateTime, formatDateTime} from "@web/core/l10n/dates";
import {_t} from "@web/core/l10n/translation";
import {browser} from "@web/core/browser/browser";
import {useHotkey} from "@web/core/hotkeys/hotkey_hook";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {useSetupAction} from "@web/search/action_hook";
import {View} from "@web/views/view";
import {StudioCanvas} from "./studio_canvas";
import {StudioChangeRemovalDialog, StudioConfirmDialog} from "./studio_confirm";
import {parseGroupValue} from "./studio_groups";
import {PERMS, StudioModelDialog, accessGroup, accessRows} from "./studio_models";
import {StudioSecuritySpace, pickModel, securityModels} from "./studio_security";
import {INSPECTOR_TABS, StudioInspector} from "./studio_inspector";
import {StudioOutline, outlineLabel} from "./studio_outline";
import {StudioPalette} from "./studio_palette";
import {StudioModelsSpace} from "./studio_models_space";
import {StudioModelPreview} from "./studio_preview";
import {StudioReview} from "./studio_review";
import {LANE_ZONE_PREFIX, VIEW_LANES, laneLabel, laneOf, laneOfZone, writableColorRules} from "./studio_timeline";
import {StudioPropertiesDialog} from "./studio_properties";
import {StudioRelationDialog, X2MANY_TYPES, fieldTypeFits} from "./studio_relations";
import {
    DATE_TYPES,
    DRAGGING_CLASS,
    GEO_TYPES,
    MODEL,
    RIBBON_COLORS,
    allBlocks,
    axesOf,
    blockTrail,
    canDragBlock,
    canRemoveBlock,
    canSelectBlock,
    columnLabel,
    conditionValue,
    fieldTypeLabel,
    findBlock,
    graphLaneLabel,
    graphLanes,
    isGhost,
    namedKeys,
    newFieldLabel,
    pivotLanes,
    searchColumns,
    searchEndHook,
} from "./studio_utils";

// The helpers live in studio_utils.js; this module re-exports them, where
// the tests and the other modules import them from.
export {
    DRAGGING_CLASS,
    allBlocks,
    attributeLabel,
    blockTrail,
    changeKeysInside,
    conditionValue,
    fieldTypeLabel,
    fieldWidgets,
    findBlock,
    graphAxes,
    graphLanes,
    isBaseInvisible,
    isGhost,
    isTrue,
    namedKeys,
    pivotAxes,
    pivotLanes,
    searchColumns,
    selectionToText,
    textToSelection,
    valueLabel,
} from "./studio_utils";
export {StudioBlock} from "./studio_canvas";
export {outlineRows} from "./studio_outline";
export {INSPECTOR_TABS} from "./studio_inspector";

// The spaces of the rail, in its order: the view on screen, the models of
// the project, its security (access rights, rules, apps and groups), the
// review of its changes.
export const SPACES = ["view", "models", "security", "review"];
// The tabs of the security space, each one a panel of the editor.
export const SECURITY_TABS = ["access", "rules", "apps"];
// The tabs of the left panel of the view space: the palette, the plan.
export const LEFT_TABS = ["palette", "plan"];
// The display levels of the editor, as the server stores them on the
// settings of the user (res.users.settings).
export const DISPLAY_LEVELS = ["simple", "detailed"];
// The ``reason_code`` of the view types the menu of views lists « to add »:
// a type the model has no view of, which the project can add; a timeline
// once web_timeline is installed; a type a model not created yet gets
// once applied; an activity view once the model has activities; a map
// once the model has the field web_view_leaflet_map reads; a GeoEngine
// view once the model has a geo field.
export const ADDABLE_REASONS = [
    "no_view",
    "needs_module",
    "apply_first",
    "needs_activity",
    "needs_field",
    "needs_geo_field",
];
// The view types a spreadsheet of spreadsheet_oca reads, as the server
// (arch.SPREADSHEET_VIEW_TYPES) accepts them in send_to_spreadsheet.
export const SPREADSHEET_VIEW_TYPES = ["list", "pivot", "graph"];
// The palette items of the section « Layout » (LAYOUT_ITEMS of the palette).
export const LAYOUT_KINDS = ["group", "page", "separator"];
// The classes of the element a StudioBlock renders, one per kind of block
// (erplibre_studio.Block).
const BLOCK_CLASSES = [
    "o_erplibre_studio_node",
    "o_erplibre_studio_notebook",
    "o_erplibre_studio_container",
    "o_erplibre_studio_other",
];
// The tags a new notebook may go in (arch.NOTEBOOK_PARENTS).
export const NOTEBOOK_PARENTS = ["sheet", "page"];

/**
 * The studio editor: a client action on one view of a model. The server
 * holds the draft; every drop or property change is one operation, and the
 * editor renders the payload it answers. The editor holds the state and
 * the calls to the server; its parts render from the props it gives them
 * and change the draft through its methods: the palette (StudioPalette),
 * the canvas of the view type (StudioCanvas), the properties of the
 * selection (StudioInspector). The panels of the project (access rights,
 * rules, apps, preview of a model) render in its context.
 *
 * Its shell: a top bar (where the view is, the views of its model, the
 * project, Undo, Preview, Apply and its menu), a rail of spaces
 * (``state.space``) that decides what the centre shows, and a status bar.
 * Apply of the top bar opens the review space (StudioReview), whose last
 * button applies the draft.
 */
export class StudioEditor extends Component {
    static template = "erplibre_studio.Editor";
    static components = {
        StudioCanvas,
        StudioPalette,
        StudioOutline,
        StudioInspector,
        View,
        StudioModelPreview,
        StudioSecuritySpace,
        StudioModelsSpace,
        StudioReview,
        Dropdown,
    };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.menuService = useService("menu");
        const params = (this.props.action && this.props.action.params) || {};
        // Back through the breadcrumbs, ``props.state`` holds what
        // ``getLocalState`` exported when an action left the editor: the
        // view and the project on screen then, which the editor reopens
        // rather than the view of its action.
        const back = (this.props.state && this.props.state.studioView) || null;
        this.params = {
            resModel: params.res_model,
            viewId: params.view_id || false,
            viewType: params.view_type || "form",
            actionId: params.action_id || false,
        };
        if (back) {
            Object.assign(this.params, {resModel: back.resModel, viewId: back.viewId, viewType: back.viewType});
        }
        useSetupAction({
            getLocalState: () => ({studioView: {...this.params, projectId: this.state.projectId}}),
        });
        // The view the editor was opened on: where the canvas goes back to
        // when the model on screen leaves the project.
        this.launch = {resModel: params.res_model, viewId: params.view_id || false, viewType: params.view_type || "form"};
        // The move change the last keyboard move made or merged into, {id,
        // from}: ``from`` is the path of the block before that change (see
        // ``moveByKeyboard``); null when there is none.
        this.keyboardMove = null;
        // Ctrl+Z (Cmd+Z on macOS) removes the last change of the view on
        // screen, as the undo button does; the hotkey service leaves it to
        // the browser inside a text field.
        useHotkey("control+z", () => this.projectAction("action_undo"), {
            isAvailable: () => this.canUndo,
        });
        this.state = useState({
            loading: true,
            busy: false,
            error: null,
            data: {},
            projectId: (back ? back.projectId : params.project_id) || false,
            selected: null,
            dragging: null,
            hook: null,
            preview: false,
            pages: {},
            newProject: {name: "", module_name: ""},
            comodels: null,
            // The tab of the left panel of the view space (LEFT_TABS).
            leftTab: "palette",
            // The tab of the inspector of the view space (INSPECTOR_TABS).
            inspectorTab: "properties",
            // The state of the palette, kept while a panel hides it: its
            // search, whether the existing fields show (null: as the view
            // decides), whether every type shows, the interval of a date
            // field dropped as a grouping, the ribbon a drop adds.
            palette: {
                filter: "",
                existing: null,
                more: false,
                interval: "month",
                ribbon: {title: "", bg_color: RIBBON_COLORS[0]},
            },
            // The state of the plan: its text filter, « Modified » only,
            // the paths of the folded containers.
            outline: {filter: "", changedOnly: false, collapsed: {}},
            template: null,
            filterForm: null,
            colors: null,
            // The lane of a timeline or of a calendar the inspector shows
            // (VIEW_LANES), null for none.
            timelineLane: null,
            // The layer of a GeoEngine view the inspector shows: its id,
            // « new » for the form of a new one, null for none.
            geoLayer: null,
            // The space the rail shows (SPACES): the centre of the editor.
            space: "view",
            // The id of the model line whose form the editor opens once the
            // review applies the draft (« Apply and open »), else false.
            openAfterApply: false,
            // The tab the security space opens on: the last one shown.
            securityTab: "access",
            // What the security space shows: the model chosen in its list
            // (null: the model on screen, else the first one), the access
            // row its inspector shows (« project:<id> » or « existing:<id> »).
            security: {model: null, row: null},
            // What the models space shows: the model chosen in its list
            // (null: the model on screen, else the first one), whether its
            // inspector unfolds the advanced section.
            modelsSpace: {model: null, advanced: false},
            // What the centre shows instead of the canvas: the preview of a
            // model in the view space, a tab of SECURITY_TABS in the
            // security space; null for none.
            panel: null,
            // What the dialogs and the panels offer (get_studio_choices).
            choices: null,
            accessAdd: this.newAccessRow(),
            accessExisting: {},
            ruleForm: null,
            ruleCheck: null,
            // Why the server refused the last Save of the rule form.
            ruleError: null,
            // The preview of a model not created yet: {lineId, viewType,
            // mode, data, key}, shown by the panel « preview ».
            modelPreview: null,
            // Why the server refused the last call of the panel « apps ».
            panelError: null,
            // The keys of the technical name inputs whose unsaved value
            // does not apply (StudioFieldName): each one blocks Apply.
            localNameBlockers: new Set(),
            // What the live region of the editor says (``announce``).
            announce: "",
            // The display level (DISPLAY_LEVELS): « simple » shows the view
            // as a user sees it, « detailed » adds its technical names.
            level: "simple",
        });
        this.previewCount = 0;
        // The menus of the top bar, closed by their items once chosen.
        this.menus = {
            project: useDropdownState(),
            apply: useDropdownState(),
            views: useDropdownState(),
        };
        // What runs once the editor renders again (``afterRender``).
        this.renderCallback = null;
        onPatched(() => {
            const callback = this.renderCallback;
            this.renderCallback = null;
            if (callback) {
                callback();
            }
        });
        onWillStart(() => this.load());
    }

    get data() {
        return this.state.data;
    }

    /** The editor itself, for the parts it renders. */
    get editor() {
        return this;
    }

    get viewType() {
        return this.data.view_type || this.params.viewType;
    }

    get layout() {
        return this.data.layout || {};
    }

    get root() {
        return this.data.blocks;
    }

    /**
     * The project the selector shows, or null: while « Choose a project… »
     * or « New project… » is selected, no edit reaches a project.
     */
    get project() {
        const project = this.data.project;
        return project && project.id === this.state.projectId ? project : null;
    }

    /** Whether the undo button, and Ctrl+Z, can remove a change of the view on screen. */
    get canUndo() {
        return Boolean(
            this.project && !this.state.busy && this.state.space === "view" && (this.data.changes || []).length
        );
    }

    /** The panel the canvas shows instead of the view, while a project is selected. */
    get panel() {
        return this.project ? this.state.panel : null;
    }

    fieldInfo(name) {
        return (this.data.fields || {})[name] || {};
    }

    // ── display level ───────────────────────────────────────────────────

    /** Whether the editor shows the technical names (the « detailed » level). */
    get detailed() {
        return this.state.level === "detailed";
    }

    /** The level of the payload ``data`` when it carries one; else the level stays. */
    takeLevel(data) {
        if (data && DISPLAY_LEVELS.includes(data.display_level)) {
            this.state.level = data.display_level;
        }
    }

    /**
     * Show the editor at ``level`` at once, and remember it for the account
     * of the user. The call neither replaces the payload nor makes the
     * editor busy; a refusal puts the former level back.
     */
    async setLevel(level) {
        const before = this.state.level;
        if (level === before || !DISPLAY_LEVELS.includes(level)) {
            return;
        }
        this.state.level = level;
        try {
            await this.orm.call(MODEL, "set_display_level", [level]);
        } catch (error) {
            if (this.state.level === level) {
                this.state.level = before;
            }
            this.notification.add(this.errorMessage(error), {type: "danger"});
        }
    }

    /** The text of the inherited views of the view on screen, for the Detailed level. */
    get inheritedText() {
        const inherited = (this.data.view && this.data.view.inherited) || {};
        if (!inherited.views) {
            return "";
        }
        return _t("+ %(views)s inherited view(s) from %(modules)s module(s)", {
            views: inherited.views,
            modules: inherited.modules || 0,
        });
    }

    // ── server ──────────────────────────────────────────────────────────

    errorMessage(error) {
        return (error.data && error.data.message) || error.message || String(error);
    }

    /**
     * Call ``method`` of the editor and show the payload it answers. On an
     * error, ``onError(message)`` when given, else a notification; answer
     * null.
     */
    async call(method, args, kwargs = {}, onError = null) {
        this.state.busy = true;
        let data;
        try {
            data = await this.orm.call(MODEL, method, args, kwargs);
        } catch (error) {
            const message = this.errorMessage(error);
            if (onError) {
                onError(message);
            } else {
                this.notification.add(message, {type: "danger"});
            }
            return null;
        } finally {
            this.state.busy = false;
        }
        this.state.data = data;
        this.takeLevel(data);
        this.state.projectId = (data.project && data.project.id) || false;
        this.state.error = null;
        if (!this.formIsCurrent(this.state.filterForm, data.project)) {
            // Its target was located in a draft that is gone.
            this.state.filterForm = null;
        }
        await this.refreshModelPreview();
        return data;
    }

    async load() {
        if (!this.params.resModel) {
            this.state.loading = false;
            this.state.error = _t("Open the studio from the debug menu of a view.");
            return;
        }
        try {
            const data = await this.orm.call(MODEL, "get_editor_data", [
                this.params.resModel,
                this.params.viewId,
                this.params.viewType,
                this.state.projectId,
            ]);
            this.state.data = data;
            this.takeLevel(data);
            this.params.viewId = data.view.id;
            this.launch.viewId = this.launch.viewId || data.view.id;
            this.state.projectId = (data.project && data.project.id) || false;
        } catch (error) {
            this.state.error = this.errorMessage(error);
        } finally {
            this.state.loading = false;
        }
    }

    viewArgs() {
        return [this.params.resModel, this.params.viewId, this.params.viewType];
    }

    /** Back to the canvas of the view space, without selection, form or preview. */
    resetCanvas() {
        this.state.panel = null;
        this.state.space = "view";
        this.state.modelPreview = null;
        Object.assign(this.state, {
            selected: null,
            filterForm: null,
            colors: null,
            template: null,
            preview: false,
            timelineLane: null,
            geoLayer: null,
        });
    }

    /**
     * Edit the view ``viewId`` (false: the default one) of ``viewType`` of
     * ``resModel``, in the same project. Answer whether it opened.
     */
    async openView(resModel, viewId, viewType) {
        if (this.state.busy) {
            return false;
        }
        const projectId = this.project ? this.project.id : false;
        this.state.busy = true;
        try {
            const data = await this.orm.call(MODEL, "get_editor_data", [resModel, viewId, viewType, projectId], {
                pick_project: Boolean(projectId),
            });
            Object.assign(this.params, {resModel, viewType, viewId: data.view.id});
            this.resetCanvas();
            this.state.data = data;
            this.takeLevel(data);
            const keep = this.state.projectId === "new" ? "new" : false;
            this.state.projectId = (data.project && data.project.id) || keep;
            return true;
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
            return false;
        } finally {
            this.state.busy = false;
        }
    }

    /**
     * Edit the default view of another type of the same model, in the same
     * project; the view space shows it.
     */
    async switchViewType(viewType) {
        this.menus.views.close();
        if (this.state.busy) {
            return;
        }
        if (viewType === this.params.viewType) {
            this.openSpace("view");
            return;
        }
        // The preview stays on: it shows the view chosen.
        const preview = this.previewOn;
        if ((await this.openView(this.params.resModel, false, viewType)) && preview) {
            await this.togglePreview();
        }
    }

    /**
     * The view types of the model on screen the editor opens, as the tabs
     * of the top bar show them: [{type, label, changes, pending, added,
     * xml_id}]. From ``view_list`` of the payload, else from its
     * ``view_types``. ``added``: a view the project adds, ``pending``
     * until Apply creates it.
     */
    get viewTabs() {
        const list = this.data.view_list;
        if (list) {
            return list
                .filter((entry) => entry.editable)
                .map((entry) => ({
                    type: entry.type,
                    label: entry.label,
                    changes: entry.changes || 0,
                    pending: entry.pending,
                    added: Boolean(entry.added),
                    xml_id: entry.xml_id || false,
                }));
        }
        return (this.data.view_types || []).map((type) => ({
            type,
            label: this.viewTypeLabel(type),
            changes: 0,
            pending: false,
            added: false,
            xml_id: false,
        }));
    }

    /** The label of the views of the model on screen. */
    get viewTabsLabel() {
        return _t("Views of %(model)s", {model: this.data.model_name || this.data.model || ""});
    }

    /** The title of the count of changes of a view tab. */
    changesTitle(count) {
        return _t("%(count)s change(s) of the project in this view", {count});
    }

    /**
     * The view types the editor does not open on the model on screen, with
     * why not: the entries of ``view_list`` that are not editable.
     */
    get unavailableViews() {
        return (this.data.view_list || []).filter((entry) => !entry.editable);
    }

    /**
     * The view types of the « To add » section of the menu of views: those
     * the project can add (``no_view``), and those it could once a module
     * is installed or the model applied, with why not.
     */
    get addableViews() {
        return this.unavailableViews.filter((entry) => ADDABLE_REASONS.includes(entry.reason_code));
    }

    /** The view types the studio does not edit, with why not. */
    get unsupportedViews() {
        return this.unavailableViews.filter((entry) => !ADDABLE_REASONS.includes(entry.reason_code));
    }

    /** What a view of ``viewType`` shows, for the menu of views. */
    viewTypeDescription(viewType) {
        return (
            {
                form: _t("One record on a page: its fields in groups and tabs."),
                list: _t("The records as rows, one column per field."),
                kanban: _t("The records as cards, in columns by grouping."),
                search: _t("The filters, groupings and fields of the search."),
                pivot: _t("Cross analysis: rows, columns and measures."),
                graph: _t("A bar, line or pie chart of the records, grouped and measured."),
                timeline: _t("A chronological band, provided by web_timeline (OCA)."),
                calendar: _t("The records as events on a day, week, month or year grid."),
                hierarchy: _t("An organization chart: each record under its parent, provided by web_hierarchy."),
                activity: _t("The records with their planned activities, one column per activity type (mail)."),
                leaflet_map: _t("Markers on a map, provided by web_view_leaflet_map (OCA)."),
                geoengine: _t("A map of geo fields with layers, provided by base_geoengine (OCA)."),
            }[viewType] || ""
        );
    }

    /**
     * Add the ``viewType`` view of the model on screen to the project, then
     * edit it: until Apply creates it, it exists in the draft only.
     */
    async addView(viewType) {
        this.menus.views.close();
        if (this.state.busy || !this.project) {
            return false;
        }
        const data = await this.viewCall("add_view", [this.project.id, this.params.resModel, viewType], {
            revision: this.project.revision,
        });
        return Boolean(data);
    }

    /**
     * Call ``method``, whose answer is the payload of another view, and
     * edit that view; on {view_gone}, leave for the home menu. Answer the
     * payload, or null on an error.
     */
    async viewCall(method, args, kwargs) {
        this.state.busy = true;
        let data;
        try {
            data = await this.orm.call(MODEL, method, args, kwargs);
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
            return null;
        } finally {
            this.state.busy = false;
        }
        if (data.view_gone) {
            await this.action.doAction("home");
            return null;
        }
        Object.assign(this.params, {resModel: data.model, viewType: data.view_type, viewId: data.view.id});
        this.resetCanvas();
        this.state.data = data;
        this.takeLevel(data);
        this.state.projectId = (data.project && data.project.id) || false;
        this.state.error = null;
        return data;
    }

    /**
     * The view the project adds that is on screen, as the payload gives
     * it ({line_id, applied, name, xml_id}), or false.
     */
    get addedView() {
        return (this.data.view && this.data.view.added) || false;
    }

    /** What the banner of a view the project adds says. */
    get addedViewNotice() {
        const view = this.viewTypeLabel(this.viewType);
        if (this.addedView.applied) {
            return _t("%(view)s view created by the project. Revert removes it with the rest of the draft.", {
                view,
            });
        }
        return _t("%(view)s view added to the project, with the default settings: Apply creates it.", {view});
    }

    /**
     * Take the view on screen, which the project adds, out of the draft
     * with its changes, once confirmed. Before Apply created it, the
     * editor goes back to another view of the model.
     */
    removeAddedView() {
        const added = this.addedView;
        if (this.state.busy || !this.project || !added) {
            return;
        }
        const body = added.applied
            ? _t(
                  "The %(view)s view leaves the draft with its changes; the next Apply removes it from the database.",
                  {view: this.viewTypeLabel(this.viewType)}
              )
            : _t("The %(view)s view leaves the draft with its changes.", {view: this.viewTypeLabel(this.viewType)});
        this.dialog.add(ConfirmationDialog, {
            title: _t("Remove this view from the draft"),
            body,
            confirmLabel: _t("Remove"),
            confirm: async () => {
                await this.viewCall("remove_view", [this.project.id, added.line_id, ...this.viewArgs()], {
                    revision: this.project.revision,
                    fallback: this.launchArgs,
                });
            },
            cancel: () => {},
        });
    }

    /**
     * One operation on the draft. Operations run one at a time: each one
     * locates its nodes in the payload on screen, and names its revision
     * so that the server refuses it on a draft that changed meanwhile.
     * ``onError(message)``, when given, takes a refusal in place of the
     * notification (see ``call``).
     */
    async operate(operation, onError = null) {
        if (this.state.busy) {
            return null;
        }
        if (!this.project) {
            this.notification.add(_t("Choose or create a studio project first."), {type: "warning"});
            return null;
        }
        return this.call(
            "apply_operation",
            [this.project.id, ...this.viewArgs(), operation],
            {revision: this.project.revision},
            onError
        );
    }

    /** The view the editor was opened on, as ``project_action`` takes it. */
    get launchArgs() {
        const launch = this.launch;
        return [launch.resModel, launch.viewId, launch.viewType];
    }

    /** Whether the menus Apply made for ``before`` and ``after`` (two project payloads) differ. */
    menusChanged(before, after) {
        const menus = (project) => JSON.stringify((project && project.menus) || []);
        return menus(before) !== menus(after);
    }

    /**
     * Run ``action`` on the project and show the payload it answers.
     * ``digest``: the digest of the removal report the user confirmed, for
     * Apply and Revert. ``space``: the space the editor shows once the
     * action ran, set with its payload so that the space it leaves does
     * not render that payload.
     */
    async projectAction(action, {digest, space} = {}) {
        if (this.state.busy || !this.project) {
            return null;
        }
        const before = this.project;
        this.state.busy = true;
        let data = null;
        const kwargs = {revision: this.project.revision, fallback: this.launchArgs};
        if (digest) {
            kwargs.digest = digest;
        }
        try {
            data = await this.orm.call(MODEL, "project_action", [this.project.id, action, ...this.viewArgs()], kwargs);
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
            return null;
        } finally {
            this.state.busy = false;
        }
        if (data.notice) {
            this.notification.add(data.notice, {type: "warning", sticky: true});
        }
        if (["action_apply", "action_revert"].includes(action)) {
            // The applied views change what every view shows.
            this.env.bus.trigger("CLEAR-CACHES");
            if (this.menusChanged(before, data.project)) {
                await this.menuService.reload();
            }
        }
        if (data.view_gone) {
            // The model on screen and the one the editor was opened on are gone.
            await this.action.doAction("home");
            return null;
        }
        if (data.view_changed || data.model !== this.params.resModel || data.view.id !== this.params.viewId) {
            // Another view, or the view of a model not created yet that
            // Apply created.
            Object.assign(this.params, {resModel: data.model, viewType: data.view_type, viewId: data.view.id});
            if (data.view_changed) {
                this.resetCanvas();
            }
        }
        if (space) {
            this.closePanel();
            Object.assign(this.state, {space, selected: null, preview: false});
        }
        this.state.data = data;
        this.takeLevel(data);
        this.state.projectId = (data.project && data.project.id) || false;
        this.state.error = null;
        if (!this.formIsCurrent(this.state.filterForm, data.project)) {
            this.state.filterForm = null;
        }
        if (action !== "action_apply") {
            this.state.selected = null;
        }
        if (["action_discard", "action_revert"].includes(action)) {
            // Discard rebuilds the layers of a GeoEngine view under new ids.
            this.state.geoLayer = null;
        }
        await this.refreshModelPreview();
        return data;
    }

    /**
     * Revert the project, once the user confirmed what it removes from the
     * database: the report of the server, its digest sent with Revert.
     */
    async revertProject() {
        if (this.state.busy || !this.project) {
            return;
        }
        const answer = await this.readReport("get_revert_report");
        if (!answer) {
            return;
        }
        this.dialog.add(StudioConfirmDialog, {
            title: _t("Revert the project"),
            intro: _t(
                "Revert removes from the database everything the project created; its lines and its changes stay as a draft:"
            ),
            report: answer.report,
            digest: answer.digest,
            refused: answer.refused || false,
            confirmLabel: _t("Revert"),
            confirm: async (digest) => Boolean(await this.projectAction("action_revert", {digest})),
            reload: () => this.readReport("get_revert_report"),
        });
    }

    /**
     * The answer of the report ``method`` (get_apply_report,
     * get_revert_report, get_option_removal_report) of the project, with
     * ``args`` after its id, or null.
     */
    async readReport(method, args = []) {
        this.state.busy = true;
        try {
            return await this.orm.call(MODEL, method, [this.project.id, ...args]);
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
            return null;
        } finally {
            this.state.busy = false;
        }
    }

    /** Whether the project has something in the database to revert. */
    get canRevert() {
        return Boolean(this.project && (this.project.applied || this.project.state !== "draft"));
    }

    /**
     * Show the project ``value``: the id of a project, « new » for the form
     * of a new project, or « » for none. The view space shows the view
     * without the panels of the former project.
     */
    async selectProject(value) {
        this.menus.project.close();
        if (this.state.busy) {
            return;
        }
        value = String(value || "");
        this.state.selected = null;
        this.closePanel();
        this.state.space = "view";
        const projectId = parseInt(value) || false;
        if (projectId) {
            await this.showInProject(projectId);
            return;
        }
        // No project, or one to create: the view without any draft.
        const data = await this.showInProject(false, {pick_project: false});
        if (data && value === "new") {
            this.state.projectId = "new";
        }
    }

    /**
     * The views ``showInProject`` tries in another project, in order: the
     * view on screen; when it is a view the project on screen adds and
     * Apply has not created, which exists in that draft only, the view the
     * editor was opened on, then the form of the model.
     */
    get projectSwitchViews() {
        const added = this.addedView;
        if (!added || added.applied) {
            return [this.viewArgs()];
        }
        const launch = this.launchArgs;
        const views = launch[0] && launch.join() !== this.viewArgs().join() ? [launch] : [];
        return [...views, [this.params.resModel, false, "form"]];
    }

    /**
     * Show in the project ``projectId`` (false: none) the first view of
     * ``projectSwitchViews`` its payload answers; ``kwargs`` go to
     * get_editor_data. Answer the payload, or null: the error of the last
     * view tried is notified, the editor stays as it was.
     */
    async showInProject(projectId, kwargs = {}) {
        const views = this.projectSwitchViews;
        for (const [index, view] of views.entries()) {
            const last = index === views.length - 1;
            const data = await this.call("get_editor_data", [...view, projectId], kwargs, last ? null : () => {});
            if (data) {
                Object.assign(this.params, {resModel: data.model, viewType: data.view_type, viewId: data.view.id});
                return data;
            }
        }
        return null;
    }

    async createProject() {
        const {name, module_name} = this.state.newProject;
        try {
            const projectId = await this.orm.call(MODEL, "create_project", [name, module_name]);
            this.state.newProject = {name: "", module_name: ""};
            await this.showInProject(projectId);
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
        }
    }

    // ── drag and drop ───────────────────────────────────────────────────

    startDrag(ev, item) {
        if (this.state.busy) {
            ev.preventDefault();
            return;
        }
        if (!this.project) {
            ev.preventDefault();
            this.notification.add(_t("Choose or create a studio project first."), {type: "warning"});
            return;
        }
        this.state.dragging = item;
        if (ev.dataTransfer) {
            ev.dataTransfer.effectAllowed = "move";
            ev.dataTransfer.setData("text/plain", item.path || item.ttype || item.name || item.kind || "");
        }
        document.body.classList.add(DRAGGING_CLASS);
    }

    endDrag() {
        this.state.dragging = null;
        this.state.hook = null;
        document.body.classList.remove(DRAGGING_CLASS);
    }

    hookKey(target, position, zone) {
        return `${zone || ""}:${position}:${target}`;
    }

    /**
     * Whether the dragged ``item`` can land in ``zone``: a column of a
     * search view, an axis of a pivot or a graph, the loaded fields of a timeline,
     * the tabs of a notebook (« pages », a tab only), or the arch tree (no
     * zone). A tab lands in the arch tree only where the server accepts
     * a new notebook for it: on a hook (``target``, ``position``) whose
     * container is a sheet or a tab (``tabHook``). The server checks the
     * rest.
     */
    accepts(item, zone, target, position) {
        if (!item) {
            return false;
        }
        if (zone === "pages" || item.kind === "page") {
            if (this.viewType !== "form" || item.kind !== "page") {
                return false;
            }
            return zone === "pages" || (!zone && this.tabHook(target, position));
        }
        if (item.kind === "group") {
            return this.viewType === "form" && !zone;
        }
        const lane = laneOfZone(zone);
        if (lane) {
            if (item.kind === "new") {
                return Boolean(this.laneNewAttribute(lane, item.ttype));
            }
            return item.kind === "existing" && Boolean(this.laneAttribute(lane, item.name));
        }
        const viewType = this.viewType;
        if (item.kind === "widget") {
            return viewType === "kanban" && !zone;
        }
        if (item.kind === "new" && !fieldTypeFits(item.ttype, viewType)) {
            return false;
        }
        if (item.kind === "separator") {
            return (viewType === "search" && zone !== "fields") || (viewType === "form" && !zone);
        }
        if (viewType === "search") {
            if (item.kind === "existing" && zone === "group_bys") {
                return Boolean(this.fieldInfo(item.name).groupable);
            }
            return true;
        }
        if (["pivot", "graph"].includes(viewType)) {
            const axes = item.kind === "existing" ? item.axes || [] : axesOf(viewType, this.fieldInfo(item.name));
            return axes.includes(zone);
        }
        if (viewType === "geoengine" && item.kind === "existing" && GEO_TYPES.includes(this.fieldInfo(item.name).type)) {
            // geo_refusal of the server: a geo field is loaded beside the
            // info box, never in it.
            return zone === "loaded";
        }
        if (zone === "loaded") {
            return item.kind === "existing";
        }
        if (item.special === "dms_list") {
            return viewType === "form" && !zone && this.dmsTreeHook(target, position);
        }
        return true;
    }

    /**
     * Whether the documents tree of dms_field can go at the hook
     * (``target``, ``position``): right in a tab or in the sheet of a
     * form, as the server's ``_dms_tree_attrs`` requires.
     */
    dmsTreeHook(target, position) {
        const trail = blockTrail(this.root, target);
        const container = position === "inside" ? trail.at(-1) : trail.at(-2);
        return Boolean(container) && ["page", "sheet"].includes(container.tag);
    }

    /**
     * Whether a new notebook can go at the hook (``target``, ``position``)
     * of the arch tree: its container (``target`` itself for « inside »,
     * else the parent of ``target``) is one of NOTEBOOK_PARENTS, as the
     * server's ``notebook_refusal`` requires.
     */
    tabHook(target, position) {
        const trail = blockTrail(this.root, target);
        const container = position === "inside" ? trail.at(-1) : trail.at(-2);
        return Boolean(container) && NOTEBOOK_PARENTS.includes(container.tag);
    }

    overHook(ev, target, position, zone) {
        if (!this.accepts(this.state.dragging, zone, target, position)) {
            return;
        }
        ev.preventDefault();
        if (ev.dataTransfer) {
            ev.dataTransfer.dropEffect = "move";
        }
        this.state.hook = this.hookKey(target, position, zone);
    }

    leaveHook(target, position, zone) {
        if (this.state.hook === this.hookKey(target, position, zone)) {
            this.state.hook = null;
        }
    }

    /** The operation a drop of ``item`` on a hook makes, or null. */
    dropOperation(item, target, position, zone) {
        const viewType = this.viewType;
        if (item.kind === "node") {
            if (item.path === target) {
                return null;
            }
            const operation = {type: "move", source: item.path, target, position};
            if (["pivot", "graph"].includes(viewType) && zone) {
                operation.axis = zone;
            }
            return operation;
        }
        if (item.kind === "new") {
            return {
                type: "add_field",
                target,
                position,
                field: {ttype: item.ttype, field_description: newFieldLabel(item.ttype)},
            };
        }
        if (item.kind === "widget") {
            return {type: "add_widget", target, position, widget: item.widget, attrs: {...this.state.palette.ribbon}};
        }
        if (item.kind === "separator") {
            return {type: "add_separator", target, position};
        }
        if (item.kind === "group") {
            return {type: "add_group", target, position};
        }
        if (item.kind === "page") {
            return {type: "add_page", target, position};
        }
        const isDate = DATE_TYPES.includes(this.fieldInfo(item.name).type);
        if (viewType === "search" && zone === "group_bys") {
            const operation = {type: "add_group_by", target, position, field_name: item.name};
            if (isDate) {
                operation.interval = this.state.palette.interval;
            }
            return operation;
        }
        const operation = {type: "add_existing_field", target, position, field_name: item.name};
        if (item.special) {
            // The field shows as a documents tree (« dms_list »).
            operation.special = item.special;
        }
        if (["pivot", "graph"].includes(viewType)) {
            operation.axis = zone;
            if (isDate && zone !== "measure") {
                operation.interval = this.state.palette.interval;
            }
        }
        return operation;
    }

    async dropOnHook(ev, target, position, zone) {
        ev.preventDefault();
        const item = this.state.dragging;
        this.endDrag();
        if (!item || this.state.busy || !this.accepts(item, zone, target, position)) {
            return;
        }
        const lane = laneOfZone(zone);
        if (lane) {
            // A field dropped on a lane of a timeline, of a calendar or of
            // a map becomes its attribute; a new field of a lane of a map
            // is created and becomes its attribute in one change.
            const operation =
                item.kind === "new"
                    ? {
                          type: "add_field",
                          target,
                          position: "inside",
                          attribute: this.laneNewAttribute(lane, item.ttype),
                          field: {ttype: item.ttype, field_description: laneLabel(lane, this.viewType)},
                      }
                    : {type: "set_attribute", target, attribute: this.laneAttribute(lane, item.name), value: item.name};
            if (await this.operate(operation)) {
                Object.assign(this.state, {timelineLane: lane, selected: null, inspectorTab: "properties"});
            }
            return;
        }
        if (item.kind === "existing" && this.viewType === "search" && zone === "filters") {
            // A filter on a field needs its condition first.
            this.openFilterForm(target, position, item.name);
            return;
        }
        if (item.kind === "new" && item.ttype === "properties") {
            // A properties field needs its many2one and where its
            // properties are defined.
            await this.openPropertiesDialog(target, position);
            return;
        }
        if (item.kind === "new" && X2MANY_TYPES.includes(item.ttype)) {
            // A relation needs its comodel, and its inverse or its table.
            await this.openRelationDialog(item.ttype, target, position);
            return;
        }
        const operation = this.dropOperation(item, target, position, zone);
        if (operation) {
            await this.operateAndSelect(operation, item);
        }
    }

    /**
     * Add the palette ``item`` without a drag (a click, Enter or Space on
     * it). A selected container that takes drops (a group, a tab page)
     * gets it at its end, on its own « inside » hook. Another selected
     * block gets it right after it: the hook before its next sibling that
     * the draft does not remove, else the hook at the end of its
     * container. With nothing selected,
     * or when none of those hooks takes the item (a row of groups shows
     * no hook of its own), it goes on the last hook of the canvas that
     * takes it. A tab goes at the end of the tabs of the notebook that
     * holds the selection, else of the first notebook of the form; only
     * a form without a notebook gets a new one, on the hooks above. The
     * drop on that hook then runs as a drop of a drag does.
     */
    async addFromPalette(item) {
        if (this.state.busy) {
            return;
        }
        if (!this.project) {
            this.notification.add(_t("Choose or create a studio project first."), {type: "warning"});
            return;
        }
        if (this.viewType === "leaflet_map") {
            // A map has lanes only: the selected lane when it takes the
            // item, else the first one that does.
            const keys = (VIEW_LANES.leaflet_map || []).map((lane) => lane.key);
            const selected = this.state.timelineLane;
            const order = keys.includes(selected) ? [selected, ...keys.filter((k) => k !== selected)] : keys;
            const zone = order.map((key) => `${LANE_ZONE_PREFIX}${key}`).find((z) => this.accepts(item, z));
            if (!zone) {
                this.notification.add(_t("No place of this view takes this item."), {type: "warning"});
                return;
            }
            this.state.dragging = item;
            await this.dropOnHook({preventDefault: () => {}}, this.root.path, "lane", zone);
            return;
        }
        const canvas = document.querySelector(".o_erplibre_studio_canvas");
        const hooks = [...((canvas && canvas.querySelectorAll(".o_erplibre_studio_hook")) || [])]
            .map((el) => {
                const {target, position, zone} = el.dataset;
                return {target, position, zone: zone || undefined};
            })
            .filter((hook) => this.accepts(item, hook.zone, hook.target, hook.position));
        const wanted = [];
        const trail = this.state.selected ? blockTrail(this.root, this.state.selected) : [];
        const selected = trail[trail.length - 1];
        const tabs = item.kind === "page" ? hooks.filter((h) => h.zone === "pages") : [];
        if (tabs.length) {
            const notebook = [...trail].reverse().find((b) => b.tag === "notebook");
            const hook = (notebook && tabs.find((h) => h.target === notebook.path)) || tabs[0];
            this.state.dragging = item;
            await this.dropOnHook({preventDefault: () => {}}, hook.target, hook.position, hook.zone);
            return;
        }
        if (selected && selected.kind === "container" && selected.drop) {
            wanted.push({target: selected.path, position: "inside"});
        }
        if (trail.length > 1) {
            const parent = trail[trail.length - 2];
            const siblings = parent.children || [];
            // An element the draft removes takes no place (``isGhost``).
            const next = siblings
                .slice(siblings.indexOf(selected) + 1)
                .find((b) => !isGhost(b, this.viewType));
            if (next) {
                wanted.push({target: next.path, position: "before"});
            }
            wanted.push({target: parent.path, position: "inside"});
        }
        const hook =
            wanted
                .map((w) => hooks.find((h) => h.target === w.target && h.position === w.position))
                .find(Boolean) || hooks[hooks.length - 1];
        if (!hook) {
            this.notification.add(_t("No place of this view takes this item."), {type: "warning"});
            return;
        }
        this.state.dragging = item;
        await this.dropOnHook({preventDefault: () => {}}, hook.target, hook.position, hook.zone);
    }

    /**
     * Run ``operation`` and select what it added or moved: a new field, a
     * new named node, a new layout element (the block of the newest
     * change; of a new notebook, its tab), or the dragged one.
     */
    async operateAndSelect(operation, item = {}) {
        const before = new Set(Object.keys(this.data.fields || {}));
        const keys = namedKeys(this.root);
        const data = await this.operate(operation);
        if (!data) {
            return null;
        }
        let block = null;
        if (LAYOUT_KINDS.includes(item.kind)) {
            const newest = (data.changes || []).reduce((last, c) => (!last || c.id > last.id ? c : last), null);
            block = newest && newest.path ? findBlock(data.blocks, (b) => b.path === newest.path) : null;
            if (block && block.tag === "notebook") {
                block = (block.children || []).find((b) => b.tag === "page") || block;
            }
            if (block) {
                this.reveal(block.path);
                return data;
            }
        } else if (item.kind === "new") {
            // The first new field the view shows: a field may come with
            // another one created on its model, outside the view.
            block = Object.keys(data.fields)
                .filter((n) => !before.has(n))
                .map((n) => this.fieldBlock(data.blocks, n))
                .find(Boolean);
        } else if (item.name && ["add_existing_field", "move"].includes(operation.type)) {
            block = this.fieldBlock(data.blocks, item.name);
        }
        if (!block) {
            block = allBlocks(data.blocks).find((b) => b.name && !keys.has(`${b.kind}:${b.name}`));
        }
        this.state.selected = block ? block.path : null;
        return data;
    }

    /**
     * The block named ``name`` in ``root``: the one the user can move first,
     * since a QWeb view also lists the fields it only loads.
     */
    fieldBlock(root, name) {
        return (
            findBlock(root, (b) => b.name === name && b.kind !== "template" && b.movable !== false) ||
            findBlock(root, (b) => b.name === name && b.kind !== "template")
        );
    }

    // ── the filter form of a search view ────────────────────────────────

    operatorsOf(name) {
        const type = this.fieldInfo(name).type;
        return (this.layout.operators || {})[type] || [];
    }

    newCondition(name = "") {
        const operators = this.operatorsOf(name);
        const type = this.fieldInfo(name).type;
        return {field: name, operator: operators[0] || "=", value: type === "boolean" ? "True" : ""};
    }

    openFilterForm(target, position, name = "") {
        if (!this.project) {
            this.notification.add(_t("Choose or create a studio project first."), {type: "warning"});
            return;
        }
        if (!target) {
            ({target, position} = searchEndHook(this.root, "filters"));
        }
        const label = name ? this.fieldInfo(name).string || name : "";
        this.state.selected = null;
        this.state.filterForm = {
            target,
            position,
            label,
            conditions: [this.newCondition(name)],
            projectId: this.project.id,
            revision: this.project.revision,
        };
    }

    /**
     * Whether the filter form ``form`` still fits the draft of ``project``:
     * its target is a path of the revision it opened on.
     */
    formIsCurrent(form, project) {
        return Boolean(!form || (project && project.id === form.projectId && project.revision === form.revision));
    }

    async createFilter() {
        const form = this.state.filterForm;
        if (!form || this.state.busy) {
            return;
        }
        if (!this.formIsCurrent(form, this.project)) {
            this.state.filterForm = null;
            this.notification.add(_t("The draft changed since the filter form opened: drop the field again."), {
                type: "warning",
            });
            return;
        }
        const conditions = form.conditions
            .filter((c) => c.field)
            .map((c) => ({
                field: c.field,
                operator: c.operator,
                value: conditionValue(this.fieldInfo(c.field).type, c.value),
            }));
        const data = await this.operateAndSelect({
            type: "add_filter",
            target: form.target,
            position: form.position,
            label: form.label,
            conditions,
        });
        if (data) {
            this.state.filterForm = null;
        }
    }

    // ── relation fields ─────────────────────────────────────────────────

    /**
     * The dialog of a new ``ttype`` field (one2many, many2many) dropped on
     * the hook ``target`` / ``position``: Create adds it there.
     */
    async openRelationDialog(ttype, target, position) {
        if (!this.project) {
            return;
        }
        let comodels;
        try {
            comodels = await this.orm.call(MODEL, "get_comodels", [this.project.id]);
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
            return;
        }
        const projectId = this.project.id;
        const model = this.params.resModel;
        this.dialog.add(StudioRelationDialog, {
            ttype,
            model,
            modelLabel: this.data.model_name || model,
            comodels,
            projectModels: this.projectModels.map((m) => m.model),
            loadChoices: (comodel, label) =>
                this.orm.call(MODEL, "get_relation_choices", [projectId, model, comodel, ttype], {label}),
            save: async (field) =>
                Boolean(await this.operateAndSelect({type: "add_field", target, position, field}, {kind: "new"})),
            checkName: (comodel, name, label) => this.checkFieldName(comodel, name, false, label),
        });
    }

    /**
     * The dialog of a new properties field dropped on the hook ``target`` /
     * ``position``: Create adds it there, with its many2one when the view
     * lacks it.
     */
    openPropertiesDialog(target, position) {
        if (!this.project) {
            return;
        }
        const projectId = this.project.id;
        const model = this.params.resModel;
        this.dialog.add(StudioPropertiesDialog, {
            model,
            modelLabel: this.data.model_name || model,
            loadChoices: () => this.orm.call(MODEL, "get_properties_choices", [projectId, model]),
            save: async (field) =>
                Boolean(await this.operateAndSelect({type: "add_field", target, position, field}, {kind: "new"})),
            checkName: (comodel, name, label) => this.checkFieldName(comodel, name, false, label),
        });
    }

    // ── selection and properties ────────────────────────────────────────

    onCanvasClick() {
        if (!this.state.preview) {
            this.state.selected = null;
        }
    }

    /**
     * Walk the blocks of the canvas from the keyboard: from the button of
     * a block (``.o_erplibre_studio_pick``), Down or Right focuses the next
     * one in document order, Up or Left the previous one, Home and End the
     * first and the last. Each block stays a tab stop of its own; Enter or
     * Space on its button selects it. The keys of ``onBlockKey`` act on
     * the block itself. Another key with a modifier, or a key on another
     * element of the canvas, passes through.
     */
    onCanvasKey(ev) {
        if (!ev.target.classList.contains("o_erplibre_studio_pick") || ev.ctrlKey || ev.metaKey) {
            return;
        }
        if (this.onBlockKey(ev) || ev.altKey) {
            return;
        }
        const picks = [...ev.currentTarget.querySelectorAll(".o_erplibre_studio_pick")];
        const index = picks.indexOf(ev.target);
        const next = {
            ArrowDown: index + 1,
            ArrowRight: index + 1,
            ArrowUp: index - 1,
            ArrowLeft: index - 1,
            Home: 0,
            End: picks.length - 1,
        }[ev.key];
        if (next === undefined) {
            return;
        }
        ev.preventDefault();
        const pick = picks[Math.min(Math.max(next, 0), picks.length - 1)];
        if (pick) {
            pick.focus();
        }
    }

    /**
     * The keys that act on the block whose button is ``ev.target``:
     * Alt+Up and Alt+Down move it (``moveByKeyboard``; a key held down
     * moves it once), Delete removes it (``removeByKeyboard``), Escape
     * unselects what is selected while the focus stays. Answer whether
     * the key was one of them.
     */
    onBlockKey(ev) {
        const holder = ev.target.closest("[data-path]");
        const path = holder && holder.dataset.path;
        if (!path || ev.shiftKey) {
            return false;
        }
        if (ev.altKey) {
            if (!["ArrowUp", "ArrowDown"].includes(ev.key)) {
                return false;
            }
            ev.preventDefault();
            if (!ev.repeat) {
                this.moveByKeyboard(path, ev.key === "ArrowUp" ? -1 : 1);
            }
            return true;
        }
        if (ev.key === "Delete") {
            ev.preventDefault();
            this.removeByKeyboard(path);
            return true;
        }
        if (ev.key === "Escape" && this.state.selected) {
            ev.preventDefault();
            this.state.selected = null;
            return true;
        }
        return false;
    }

    /**
     * Say ``text`` through the live region of the editor
     * (``.o_erplibre_studio_live``): the region empties, then takes the
     * text on the next frame, so that a screen reader says a message that
     * repeats the last one again.
     */
    announce(text) {
        this.state.announce = "";
        browser.requestAnimationFrame(() => {
            this.state.announce = text;
        });
    }

    /**
     * The element of the canvas that renders the block at ``path``, or
     * null. The tab of a notebook page and the crumbs of the selection
     * carry a path too: only the element of a StudioBlock counts.
     */
    blockElement(path) {
        const canvas = document.querySelector(".o_erplibre_studio_canvas");
        const blocks = BLOCK_CLASSES.map((name) => `.${name}`).join(", ");
        const selector = `:is(${blocks})[data-path="${CSS.escape(path)}"]`;
        return (canvas && canvas.querySelector(selector)) || null;
    }

    /** The buttons of the blocks of the canvas, in document order. */
    canvasPicks() {
        const canvas = document.querySelector(".o_erplibre_studio_canvas");
        return [...((canvas && canvas.querySelectorAll(".o_erplibre_studio_pick")) || [])];
    }

    /**
     * The hooks of the canvas the keyboard moves ``block`` to: {up, down},
     * each one {target, position, zone} or null. ``up`` is the nearest
     * hook before the element of the block in document order, ``down``
     * the nearest one after it, among those that take the block
     * (``accepts``) and change its place: the hooks inside the block, the
     * tab hooks of a notebook, and the hooks of its own column that leave
     * it where it is (right before or after it, at the end of its
     * container when it is the last child) are left out. An element the
     * draft removes (``isGhost``) takes no place: the hook before it is
     * left out, and the place of the block reads past it. A search view
     * keeps a block in its column: a filter in the column of the fields
     * stays a filter. Only the hooks on screen count: a tab page not
     * shown holds none, so a block enters it only once it shows.
     */
    keyboardHooks(block) {
        const canvas = document.querySelector(".o_erplibre_studio_canvas");
        const el = this.blockElement(block.path);
        if (!canvas || !el) {
            return {up: null, down: null};
        }
        const item = {kind: "node", path: block.path, name: block.name};
        const trail = blockTrail(this.root, block.path);
        const parent = trail[trail.length - 2];
        // An element the draft removes takes no place: a move past it
        // alone would change nothing the view shows.
        const ghost = (b) => isGhost(b, this.viewType);
        const siblings = ((parent && parent.children) || []).filter((b) => b === block || !ghost(b));
        const ghostPaths = new Set(allBlocks(this.root).filter(ghost).map((b) => b.path));
        const index = siblings.indexOf(block);
        const still = new Set([`before:${block.path}`, `after:${block.path}`]);
        if (index >= 0 && index + 1 < siblings.length) {
            still.add(`before:${siblings[index + 1].path}`);
        }
        if (index > 0) {
            still.add(`after:${siblings[index - 1].path}`);
        }
        if (parent && index === siblings.length - 1) {
            still.add(`inside:${parent.path}`);
        }
        const lane = el.closest("[data-zone]");
        const zone = (lane && lane.dataset.zone) || "";
        let up = null;
        let down = null;
        for (const hookEl of canvas.querySelectorAll(".o_erplibre_studio_hook")) {
            const {target, position} = hookEl.dataset;
            const hookZone = hookEl.dataset.zone || "";
            if (el.contains(hookEl) || hookZone === "pages" || target === block.path || ghostPaths.has(target)) {
                continue;
            }
            if (hookZone === zone ? still.has(`${position}:${target}`) : this.viewType === "search") {
                continue;
            }
            if (!this.accepts(item, hookZone || undefined, target, position)) {
                continue;
            }
            const hook = {target, position, zone: hookZone || undefined};
            if (el.compareDocumentPosition(hookEl) & Node.DOCUMENT_POSITION_PRECEDING) {
                up = hook;
            } else if (!down) {
                down = hook;
            }
        }
        return {up, down};
    }

    /**
     * Where the block at ``path`` of the payload ``data`` stands, for the
     * live region: {index, count, container}, its place from 1 among the
     * blocks of its column (``zone``, a search, a pivot or a graph view) or of
     * its container, and the label of that column or container. Null when
     * no block has that path.
     */
    blockPlace(data, path, zone) {
        const trail = blockTrail(data.blocks, path);
        const block = trail[trail.length - 1];
        if (!block) {
            return null;
        }
        let blocks;
        let container;
        if (zone && this.viewType === "search") {
            blocks = searchColumns(data.blocks)[zone] || [];
            container = columnLabel(zone);
        } else if (zone && this.viewType === "pivot") {
            blocks = pivotLanes(data)[zone] || [];
            container = columnLabel(zone);
        } else if (zone && this.viewType === "graph") {
            blocks = graphLanes(data)[zone] || [];
            container = graphLaneLabel(zone);
        } else {
            const parent = trail[trail.length - 2];
            blocks = (parent && parent.children) || [block];
            container = parent ? outlineLabel(parent) : "";
        }
        return {index: blocks.indexOf(block) + 1, count: blocks.length, container};
    }

    /**
     * Move the block at ``path`` one place up (``direction`` -1) or down
     * (+1): onto the hook ``keyboardHooks`` gives, through the operation a
     * drop of the block there makes. While the last change of the view is
     * the one the previous keyboard move of this block made, the operation
     * carries ``merge``: the server folds the move into that change, or
     * removes it when the block is back where it stood, so a series of
     * moves is one change of the draft; a drop, an undo or another block
     * starts a new one. A block of a tab page not shown shows first. The
     * block stays selected; with ``focus``, its button takes the focus
     * back once the canvas renders again (the move gives it a new
     * element). The live region says where it went, or that it cannot go
     * further. Answer the path of the block once moved, or null: an
     * unnamed block gets a new path, the one the move change carries, or
     * the one it had before the series when the change left the draft.
     */
    async moveByKeyboard(path, direction, {focus = true} = {}) {
        if (this.state.busy || !this.project || this.state.preview || this.panel) {
            return null;
        }
        const block = findBlock(this.root, (b) => b.path === path);
        if (!block || !canDragBlock(block, this.viewType)) {
            return null;
        }
        if (!this.blockElement(path)) {
            this.reveal(path);
            for (let frame = 0; frame < 3 && !this.blockElement(path); frame++) {
                await new Promise((resolve) => browser.requestAnimationFrame(resolve));
            }
        }
        const hooks = this.keyboardHooks(block);
        const hook = direction < 0 ? hooks.up : hooks.down;
        const label = outlineLabel(block);
        if (!hook) {
            this.announce(_t("%(block)s cannot move further.", {block: label}));
            return null;
        }
        const item = {kind: "node", path, name: block.name};
        const operation = this.dropOperation(item, hook.target, hook.position, hook.zone);
        const previous = this.data.changes || [];
        const last = previous.at(-1);
        const series = this.keyboardMove;
        const merge = Boolean(operation && series && last && last.id === series.id && last.path === path);
        if (merge) {
            operation.merge = true;
        }
        const data = await this.operate(operation);
        if (!data) {
            return null;
        }
        const changes = data.changes || [];
        const known = new Set(previous.map((c) => c.id));
        const added = changes.some((c) => !known.has(c.id));
        const merged = merge && !added && changes.find((c) => c.id === last.id);
        const newest =
            merged ||
            changes
                .filter((c) => c.type === "move")
                .reduce((latest, c) => (!latest || c.id > latest.id ? c : latest), null);
        let newPath;
        if (merge && !added && !merged) {
            // Back where it stood: the merged change left the draft.
            newPath = series.from;
            this.keyboardMove = null;
        } else {
            const named = !(newest && newest.path) && block.name && this.fieldBlock(data.blocks, block.name);
            newPath = (newest && newest.path) || (named && named.path) || null;
            this.keyboardMove = newest && {id: newest.id, from: merged ? series.from : path};
        }
        this.state.selected = newPath;
        const place = newPath && this.blockPlace(data, newPath, hook.zone);
        if (place) {
            this.announce(
                _t("%(block)s moved: position %(index)s of %(count)s in %(container)s.", {block: label, ...place})
            );
        }
        if (focus && newPath) {
            this.focusBlock(newPath);
        }
        return newPath;
    }

    /**
     * Run ``callback`` once the editor renders again: the DOM then shows
     * the payload of the last answer. A block that changes its place in
     * a list leaves the DOM for a moment, which takes its focus away, so
     * the focus goes back only after that render. To call right after a
     * state change that renders, before the next frame; one callback at a
     * time, the last one wins.
     */
    afterRender(callback) {
        this.renderCallback = callback;
    }

    /**
     * Focus the button of the block at ``path`` once the canvas renders
     * again: the block's own, or the one of the title of a container.
     */
    focusBlock(path) {
        this.afterRender(() => {
            const el = this.blockElement(path);
            const own = ":scope > .o_erplibre_studio_pick";
            const title = ":scope > .o_erplibre_studio_container_title > .o_erplibre_studio_pick";
            const pick = el && el.querySelector(`${own}, ${title}`);
            if (pick) {
                pick.focus();
            }
        });
    }

    /**
     * Remove the block at ``path`` as « Remove from the view » does
     * (``removeSelected``, which may ask first). Once it left, directly or
     * after the dialog, the live region says Ctrl+Z brings it back; with
     * ``focus``, the button that takes its place in the canvas takes the
     * focus (the next block, else the new last one); ``onRemoved`` runs.
     * Answer whether it left: true, false when it stays, null while a
     * dialog asks.
     */
    async removeByKeyboard(path, {focus = true, onRemoved = null} = {}) {
        if (this.state.busy || !this.project || this.state.preview || this.panel) {
            return false;
        }
        const block = findBlock(this.root, (b) => b.path === path);
        if (!canRemoveBlock(block, this.root, this.viewType)) {
            return false;
        }
        const index = this.canvasPicks().indexOf(document.activeElement);
        const label = outlineLabel(block);
        this.state.selected = path;
        const removed = () => {
            this.announce(_t("%(block)s removed. Ctrl+Z undoes it.", {block: label}));
            if (focus && index >= 0) {
                this.afterRender(() => {
                    const picks = this.canvasPicks();
                    const pick = picks[Math.min(index, picks.length - 1)];
                    if (pick) {
                        pick.focus();
                    }
                });
            }
            if (onRemoved) {
                onRemoved();
            }
        };
        return this.removeSelected({onRemoved: removed});
    }

    /**
     * Select the block at ``path``, or unselect it when it is the
     * selection; the inspector shows the properties of a new selection.
     */
    select(path) {
        this.state.selected = this.state.selected === path ? null : path;
        this.state.colors = null;
        if (this.state.selected) {
            this.state.inspectorTab = "properties";
            this.state.timelineLane = null;
            this.state.geoLayer = null;
        }
    }

    /**
     * Select the block at ``path`` and bring it on screen: the notebook
     * pages and the kanban template that hold it show, the containers of
     * the plan above it unfold, the canvas scrolls to it, the inspector
     * shows its properties. A QWeb template shows without being selected
     * (``canSelectBlock``).
     */
    reveal(path) {
        const trail = blockTrail(this.root, path);
        if (!trail.length) {
            return;
        }
        if (canSelectBlock(trail[trail.length - 1])) {
            this.state.selected = path;
            this.state.colors = null;
            this.state.inspectorTab = "properties";
            this.state.timelineLane = null;
            this.state.geoLayer = null;
        }
        trail.forEach((block, index) => {
            const child = trail[index + 1];
            if (child && block.tag === "notebook") {
                const pages = (block.children || []).filter((b) => b.tag === "page");
                const page = pages.indexOf(child);
                if (page >= 0) {
                    this.state.pages[block.path] = page;
                }
            }
            if (child) {
                delete this.state.outline.collapsed[block.path];
            }
        });
        const templates = this.layout.templates || {};
        const template = Object.keys(templates).find((name) => trail.some((b) => b.path === templates[name]));
        if (template) {
            this.state.template = template;
        }
        this.scrollToBlock(path);
    }

    /** Scroll the canvas to the block at ``path`` once it renders. */
    scrollToBlock(path) {
        browser.requestAnimationFrame(() => {
            const canvas = document.querySelector(".o_erplibre_studio_canvas");
            const node = canvas && canvas.querySelector(`[data-path="${CSS.escape(path)}"]`);
            if (node && node.scrollIntoView) {
                node.scrollIntoView({block: "nearest"});
            }
        });
    }

    /**
     * The trail of the selection above the canvas: [{path, label}], from
     * the first block under the view down to the selected one.
     */
    get selectionTrail() {
        return blockTrail(this.root, this.state.selected)
            .slice(1)
            .map((block) => ({path: block.path, label: outlineLabel(block)}));
    }

    /** How many blocks of the view on screen a draft change touches. */
    get changedBlockCount() {
        return allBlocks(this.root).filter((b) => b.changed).length;
    }

    /**
     * Reveal the block of ``change`` (a change of the payload): its
     * ``path`` is false when the canvas shows no block for it (a removed
     * node, a change in error).
     */
    revealChange(change) {
        if (change && change.path) {
            this.reveal(change.path);
        }
    }

    /** Show the tab ``tab`` of the inspector (INSPECTOR_TABS). */
    setInspectorTab(tab) {
        if (INSPECTOR_TABS.includes(tab)) {
            this.state.inspectorTab = tab;
        }
    }

    /** Show the tab ``tab`` of the left panel (LEFT_TABS). */
    setLeftTab(tab) {
        if (LEFT_TABS.includes(tab)) {
            this.state.leftTab = tab;
        }
    }

    // ── the lanes of a timeline or a calendar, the colors of a timeline ──

    /**
     * Show the lane ``key`` of the timeline or the calendar on screen
     * (VIEW_LANES) in the inspector.
     */
    selectLane(key) {
        if (laneOf(this.viewType, key)) {
            Object.assign(this.state, {
                timelineLane: key,
                selected: null,
                colors: null,
                geoLayer: null,
                inspectorTab: "properties",
            });
        }
    }

    // ── the layers of a GeoEngine view ──────────────────────────────────

    /**
     * Show the layer ``id`` of the GeoEngine view on screen in the
     * inspector, « new » for the form of a new one, null for none; the
     * layer shown is hidden again.
     */
    selectGeoLayer(id) {
        const geoLayer = id === null || this.state.geoLayer === id ? null : id;
        Object.assign(this.state, {geoLayer, selected: null, colors: null, timelineLane: null});
        if (geoLayer !== null) {
            this.state.inspectorTab = "properties";
        }
    }

    /**
     * Save the layer ``values`` (geoLayerValues of studio_geo_layers):
     * the inspector then shows the layer saved.
     */
    async saveGeoLayer(values) {
        const data = await this.projectCall("save_geo_layer", [values]);
        if (data && data.saved_geo_layer) {
            this.state.geoLayer = data.saved_geo_layer;
        }
        return data;
    }

    /**
     * Remove the layer ``layer`` of the GeoEngine view once the user
     * confirms; once applied, the next Apply removes it from the database.
     */
    removeGeoLayer(layer) {
        const added = (this.data.view && this.data.view.added) || {};
        const body = added.applied
            ? _t("The layer %(layer)s leaves the draft; the next Apply removes it from the map.", {
                  layer: layer.name,
              })
            : _t("The layer %(layer)s leaves the draft.", {layer: layer.name});
        this.dialog.add(ConfirmationDialog, {
            title: _t("Remove this layer"),
            body,
            confirmLabel: _t("Remove"),
            confirm: async () => {
                if (await this.projectCall("remove_geo_layer", [layer.id])) {
                    this.state.geoLayer = null;
                }
            },
            cancel: () => {},
        });
    }

    /**
     * The attribute of the lane ``key`` the field ``name`` fits, by the
     * values the server offers for its kind (``choices``); null for none.
     */
    laneAttribute(key, name) {
        const lane = laneOf(this.viewType, key);
        const settable = (this.data.settable || {})[this.root && this.root.tag] || {};
        const choices = this.data.choices || {};
        const fits = (attribute) =>
            (choices[settable[attribute]] || []).some(([value]) => value === name);
        return ((lane && lane.attributes) || []).find(fits) || null;
    }

    /**
     * The attribute of the lane ``key`` a new field of ``ttype`` becomes:
     * on a map, the attribute of a lane whose ``new_field_types`` (layout)
     * hold the type; null for none.
     */
    laneNewAttribute(key, ttype) {
        const lane = laneOf(this.viewType, key);
        const types = this.layout.new_field_types || {};
        return ((lane && lane.attributes) || []).find((attribute) => (types[attribute] || []).includes(ttype)) || null;
    }

    newColorRule() {
        return {color: "#ec7063", field: "", operator: (this.layout.color_operators || ["=="])[0], value: ""};
    }

    /**
     * Edit the color rules of the timeline: those of the view when the
     * editor writes them again (writableColorRules), then a new one when
     * ``add`` or when there is none. Saving replaces every rule.
     */
    editColors(add = false) {
        const rules = (writableColorRules(this.layout.colors || []) || []).map((rule) => ({
            ...rule,
            value: String(rule.value),
        }));
        if (add || !rules.length) {
            rules.push(this.newColorRule());
        }
        this.state.colors = rules;
    }

    /** Show the colors lane with a new rule to write. */
    addColorRule() {
        if (!this.project || this.state.busy) {
            return;
        }
        this.selectLane("colors");
        this.editColors(true);
    }

    /** Write the color rules of the timeline without the one at ``index``. */
    async deleteColorRule(index) {
        const rules = writableColorRules(this.layout.colors || []);
        if (!rules || !rules[index]) {
            return;
        }
        rules.splice(index, 1);
        if (await this.setNodeAttribute(this.root, "colors", rules.length ? rules : "")) {
            this.state.colors = null;
        }
    }

    get selectedBlock() {
        return this.state.selected && findBlock(this.data.blocks, (b) => b.path === this.state.selected);
    }

    /** Whether ``block`` is the root of the view. */
    isRoot(block) {
        return Boolean(block && this.root && block.path === this.root.path);
    }

    /**
     * Set ``attribute`` of the node of ``block`` to ``value``. ``extra``
     * adds keys to the operation (``option_fields`` of the options of a
     * widget); ``onError`` goes to ``operate``. Answer the payload, or
     * null when the server refuses.
     */
    async setNodeAttribute(block, attribute, value, extra = {}, onError = null) {
        if (!block || this.state.busy) {
            return;
        }
        const data = await this.operate(
            {type: "set_attribute", target: block.path, attribute, value, ...extra},
            onError
        );
        this.reselect(data, block);
        return data;
    }

    async setAttribute(type, value) {
        const block = this.selectedBlock;
        if (!block || this.state.busy) {
            return;
        }
        const data = await this.operate({type, target: block.path, value});
        this.reselect(data, block);
    }

    /**
     * Update the selected field with ``values``. Answer whether the draft
     * took them: false while busy, and when the server refused them.
     */
    async updateField(values) {
        const block = this.selectedBlock;
        if (!block || this.state.busy) {
            return false;
        }
        const before = new Set(Object.keys(this.data.fields || {}));
        const data = await this.operate({type: "update_field", field_name: block.name, field: values});
        // A new label renames a field whose name follows it.
        const name = data && this.renamedField(before, data, block.name);
        this.reselect(data, name ? {...block, name} : block);
        return Boolean(data);
    }

    /**
     * The name the field ``old`` has in ``data``, ``before`` being the
     * names of the fields before the operation: ``old`` when it is still
     * there, else the one new field of the project that took its place, or
     * null.
     */
    renamedField(before, data, old) {
        const fields = data.fields || {};
        if (old in fields) {
            return old;
        }
        const added = Object.keys(fields).filter((name) => !before.has(name) && fields[name].project);
        return added.length === 1 ? added[0] : null;
    }

    // ── technical names of the new fields ───────────────────────────────

    /**
     * What the technical name ``name`` of a new field of ``model`` gives
     * (``check_field_name``): {name, proposed, status, message, detail,
     * checks, rule}. ``current``: the name of the field renamed, ``label``
     * its label. A read: the editor stays usable meanwhile; an error
     * answers the status « invalid » with its message.
     */
    async checkFieldName(model, name, current, label) {
        const refused = (message) => ({name, proposed: false, status: "invalid", message, detail: "", checks: []});
        if (!this.project) {
            return refused(_t("Choose or create a studio project first."));
        }
        try {
            return await this.orm.call(MODEL, "check_field_name", [this.project.id, model, name], {
                field_name: current || false,
                label: label || false,
            });
        } catch (error) {
            return refused(this.errorMessage(error));
        }
    }

    // ── technical names of the new models ───────────────────────────────

    /**
     * The rule the technical names of new models follow on this database
     * (``model_name_rule`` of the payload): {prefix_required, mode, label,
     * text, detail}, or null when the payload has none, which the parts
     * read as the production rule (x_ required).
     */
    get modelNameRule() {
        return (this.data && this.data.model_name_rule) || null;
    }

    /**
     * What the technical name ``name`` of a new model gives
     * (``check_model_name``): {name, proposed, status, message, detail,
     * checks, rule}. ``lineId``: the model line renamed, ``label`` its
     * label. A read; an error answers the status « invalid » with its
     * message and ``error`` set, which no part takes as a verdict on the
     * name.
     */
    async checkModelName(name, lineId, label) {
        const refused = (message) => ({
            name,
            proposed: false,
            status: "invalid",
            message,
            detail: "",
            checks: [],
            error: true,
        });
        if (!this.project) {
            return refused(_t("Choose or create a studio project first."));
        }
        try {
            return await this.orm.call(MODEL, "check_model_name", [this.project.id, name], {
                line_id: lineId || false,
                label: label || false,
            });
        } catch (error) {
            return refused(this.errorMessage(error));
        }
    }

    /**
     * Rename the new field ``old`` of the model on screen to ``name``, or,
     * with ``auto``, to the name its label proposes, which it then follows;
     * select its block under the new name. Answer that name, or null when
     * the server refused.
     */
    async renameField(old, name, {auto = false} = {}) {
        if (this.state.busy) {
            return null;
        }
        const before = new Set(Object.keys(this.data.fields || {}));
        const data = await this.operate({
            type: "rename_field",
            field_name: old,
            new_name: name || null,
            auto: Boolean(auto),
        });
        if (!data) {
            return null;
        }
        const renamed = (name && name in (data.fields || {}) ? name : null) || this.renamedField(before, data, old);
        const block = renamed && this.fieldBlock(data.blocks, renamed);
        this.state.selected = block ? block.path : null;
        return renamed;
    }

    /** Count, or stop counting, the input ``key`` among the names that block Apply. */
    setLocalNameBlocker(key, blocked) {
        const blockers = this.state.localNameBlockers;
        if (blocked && !blockers.has(key)) {
            blockers.add(key);
        } else if (!blocked && blockers.has(key)) {
            blockers.delete(key);
        }
    }

    /**
     * How many technical names block Apply: those of the draft the server
     * counts, and the unsaved values of the inputs that do not apply.
     */
    get nameBlockerCount() {
        const counts = (this.project && this.project.counts) || {};
        return (counts.name_blockers || 0) + this.state.localNameBlockers.size;
    }

    get nameBlockerText() {
        return _t("%(count)s technical name(s) block Apply", {count: this.nameBlockerCount});
    }

    /** The title of Apply in the top bar: what blocks it, else what it does. */
    get applyBarTitle() {
        return this.nameBlockerCount ? this.nameBlockerText : _t("Review the draft, then write it to the database");
    }

    /**
     * Remove the selected block. A block the draft adds that holds other
     * changes (a group, a tab and what was dropped into it) leaves with
     * them once the user confirms: no undo brings them back. ``onRemoved``
     * runs once the block left, directly or after the dialog. Answer true
     * when the block left, false when it stays, null while the dialog
     * asks.
     */
    async removeSelected({onRemoved = null} = {}) {
        const block = this.selectedBlock;
        if (!block || this.state.busy) {
            return false;
        }
        const remove = async () => {
            if (await this.operate({type: "remove", target: block.path})) {
                this.state.selected = null;
                if (onRemoved) {
                    onRemoved();
                }
                return true;
            }
            return false;
        };
        if (block.changed_inside && this.addedByDraft(block)) {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Remove this element from the draft"),
                body: _t("The changes made inside it leave the draft with it."),
                confirmLabel: _t("Remove"),
                // A false answer would keep the dialog open.
                confirm: async () => {
                    await remove();
                },
                cancel: () => {},
            });
            return null;
        }
        return remove();
    }

    /**
     * Undo the change ``changeId`` of the draft, wherever it sits.
     * ``get_change_removal`` says what leaves with it: a refusal shows as
     * a notification; a change that leaves alone and that no Apply wrote
     * goes at once, as Ctrl+Z does; otherwise a dialog lists what leaves
     * and removes it once confirmed. ``onRemoved`` runs with the payload
     * once the change left, directly or after the dialog.
     */
    async removeChange(changeId, {onRemoved = null} = {}) {
        if (this.state.busy || !this.project) {
            return;
        }
        this.state.busy = true;
        let removal;
        try {
            removal = await this.orm.call(MODEL, "get_change_removal", [this.project.id, changeId]);
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
            return;
        } finally {
            this.state.busy = false;
        }
        if (removal.refused) {
            this.notification.add(removal.refused, {type: "danger"});
            return;
        }
        const remove = async (expected) => {
            const data = await this.doRemoveChange(changeId, expected);
            if (data && onRemoved) {
                onRemoved(data);
            }
            return data;
        };
        if (!removal.items.length && !removal.applied) {
            await remove([changeId]);
            return;
        }
        this.dialog.add(StudioChangeRemovalDialog, {
            removal,
            confirm: () => remove([removal.change.id, ...removal.items.map((i) => i.id)]),
        });
    }

    /**
     * The id of the change of the draft that removes ``block`` from the
     * view (``isGhost``): the one of kind « hidden » among its changes,
     * else its only change; false when none is known.
     */
    removalChange(block) {
        const keys = (block && block.changes) || [];
        const change = (this.data.changes || []).find((c) => keys.includes(c.id) && c.kind === "hidden");
        if (change) {
            return change.id;
        }
        return keys.length === 1 && Number.isInteger(keys[0]) ? keys[0] : false;
    }

    /**
     * Restore ``block``, an element the draft removes (``isGhost``): undo
     * the change that removes it (``removeChange``, which asks first when
     * other changes leave with it). Once it left, the block is back where
     * it was: it takes the selection, the live region says it, and its
     * button takes the focus.
     */
    async restoreBlock(block) {
        const changeId = this.removalChange(block);
        if (!changeId) {
            return;
        }
        const label = outlineLabel(block);
        await this.removeChange(changeId, {
            onRemoved: async (data) => {
                const found =
                    (block.name && this.fieldBlock(data.blocks, block.name)) ||
                    findBlock(data.blocks, (b) => b.path === block.path);
                this.announce(_t("%(label)s restored.", {label}));
                if (!found) {
                    return;
                }
                this.state.selected = found.path;
                // The removed line and the restored block share their
                // path: the focus waits for the block to replace the line.
                for (let frame = 0; frame < 5; frame++) {
                    await new Promise((resolve) => browser.requestAnimationFrame(resolve));
                    const el = this.blockElement(found.path);
                    if (el && !el.classList.contains("o_erplibre_studio_ghost")) {
                        el.querySelector(
                            ":scope > .o_erplibre_studio_pick, :scope > .o_erplibre_studio_container_title > .o_erplibre_studio_pick"
                        )?.focus();
                        return;
                    }
                }
            },
        });
    }

    /**
     * Remove the change ``changeId`` with the changes ``expected`` (its
     * ids and those of what leaves with it, as the user saw them); the
     * server refuses a list that no longer matches. A selection whose
     * block left the view goes. Answer the payload, or null.
     */
    async doRemoveChange(changeId, expected) {
        const data = await this.projectCall("remove_change", [changeId, expected]);
        if (data && this.state.selected && !blockTrail(this.root, this.state.selected).length) {
            this.state.selected = null;
        }
        return data;
    }

    /**
     * Whether the draft adds ``block``: a change of kind « new » marks it,
     * or, for a tab, the notebook that holds it.
     */
    addedByDraft(block) {
        const isNew = (b) => (b.change_kinds || []).includes("new");
        if (isNew(block)) {
            return true;
        }
        const trail = blockTrail(this.root, block.path);
        const parent = trail[trail.length - 2];
        return block.tag === "page" && Boolean(parent) && isNew(parent);
    }

    reselect(data, block) {
        if (!data) {
            return;
        }
        const found = block.name
            ? this.fieldBlock(data.blocks, block.name)
            : findBlock(data.blocks, (b) => b.path === block.path);
        this.state.selected = found && !this.isRoot(found) ? found.path : null;
    }

    /** The models a many2one can point to, the pending models of the project too. */
    async loadComodels() {
        const projectId = this.project ? this.project.id : false;
        this.state.comodels = await this.orm.call(MODEL, "get_comodels", [projectId]);
    }

    // ── models of the project ───────────────────────────────────────────

    /**
     * Call ``method`` on the project with ``params``, then the view on
     * screen and the revision, as every editor call on the draft.
     */
    async projectCall(method, params, onError = null) {
        if (this.state.busy || !this.project) {
            return null;
        }
        return this.call(
            method,
            [this.project.id, ...params, ...this.viewArgs()],
            {
                revision: this.project.revision,
            },
            onError
        );
    }

    /** What the dialogs and the panels offer, read again at each opening. */
    async loadChoices() {
        const projectId = this.project ? this.project.id : false;
        try {
            this.state.choices = await this.orm.call(MODEL, "get_studio_choices", [projectId]);
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
            this.state.choices = null;
        }
        return this.state.choices;
    }

    /** The models the project creates, as the payload lists them. */
    get projectModels() {
        return (this.project && this.project.models) || [];
    }

    /** The label of ``viewType``: the one of ``view_list``, else of the editor. */
    viewTypeLabel(viewType) {
        const entry = (this.data.view_list || []).find((e) => e.type === viewType);
        if (entry) {
            return entry.label;
        }
        const labels = {
            form: _t("Form"),
            list: _t("List"),
            search: _t("Search"),
            kanban: _t("Kanban"),
            pivot: _t("Pivot"),
            graph: _t("Graph"),
            timeline: _t("Timeline"),
            calendar: _t("Calendar"),
            hierarchy: _t("Hierarchy"),
            activity: _t("Activity"),
            leaflet_map: _t("Map (Leaflet)"),
            geoengine: _t("GeoEngine"),
        };
        return labels[viewType] || viewType;
    }

    /** The label of ``model``: a model of the project, else of the database. */
    modelLabel(model) {
        const line = this.projectModels.find((m) => m.model === model);
        if (line) {
            return line.name;
        }
        const item = this.choiceModels.find((m) => m[0] === model);
        return item ? item[1] : model;
    }

    /** The dialog of a new model, or of the model line ``line``. */
    async openModelDialog(line = null) {
        if (!this.project) {
            this.notification.add(_t("Choose or create a studio project first."), {type: "warning"});
            return;
        }
        const choices = await this.loadChoices();
        if (!choices) {
            return;
        }
        this.dialog.add(StudioModelDialog, {
            project: this.project,
            choices,
            line,
            taken: [
                ...(choices.taken_models || []),
                ...choices.models.map((m) => m[0]),
                ...this.projectModels.map((m) => m.model),
            ],
            rule: this.modelNameRule,
            checkName: (name, label) => this.checkModelName(name, line && line.id, label),
            save: (values) => (line ? this.updateModel(line, values) : this.createModel(values)),
        });
    }

    /** Add a model to the project; the models space then shows it. */
    async createModel(values) {
        const data = await this.projectCall("create_model", [values]);
        if (data) {
            this.state.modelsSpace.model = (data.created_model && data.created_model.model) || values.model || null;
        }
        return Boolean(data);
    }

    /**
     * Write ``values`` (any of name, model, chatter, menu, order,
     * archivable, manual_order) on the model line ``line``; the models
     * space follows a new technical name.
     */
    async updateModel(line, values) {
        const data = await this.projectCall("update_model", [line.id, values]);
        if (data && values.model && this.state.modelsSpace.model === line.model) {
            this.state.modelsSpace.model = values.model;
        }
        return Boolean(data);
    }

    /**
     * Turn the option ``key`` (labelled ``label``) of the model line
     * ``line`` off, once its field exists in the database: a dialog shows
     * what the next Apply removes with it (get_option_removal_report) and
     * its effects on the records; « Turn off » writes the option off. A
     * refusal of the server replaces the button. Without an answer of the
     * server, the option stays on.
     */
    async confirmOptionRemoval(line, key, label) {
        if (this.state.busy || !this.project) {
            return;
        }
        const args = [line.id, key];
        const answer = await this.readReport("get_option_removal_report", args);
        if (!answer) {
            return;
        }
        const intro = answer.waiting
            ? _t(
                  "The installed generated module defines the field of this option: it leaves the database once the module is generated again and upgraded, with:"
              )
            : _t("Turning this option off removes at the next Apply, after its confirmation:");
        this.dialog.add(StudioConfirmDialog, {
            title: _t("Turn off %(option)s", {option: label}),
            intro,
            report: answer.report,
            refused: answer.refused || false,
            confirmLabel: _t("Turn off"),
            confirm: async () => this.updateModel(line, {[key]: false}),
            // This report has no digest (update_model checks none): the
            // dialog compares false with false and flags only a change of
            // the refusal.
            reload: async () => {
                const again = await this.readReport("get_option_removal_report", args);
                return again && {...again, digest: false};
            },
        });
    }

    /** Show the model ``model`` in the models space. */
    selectModelEntry(model) {
        this.state.modelsSpace.model = model;
    }

    /** Show the rights of the model ``model`` in the security space. */
    async openSecurityModel(model) {
        this.state.security.model = model;
        this.state.security.row = null;
        if (this.state.space === "security" && this.state.panel === "access") {
            await this.loadAccessExisting([model]);
            return;
        }
        await this.openSecurity("access");
    }

    get pendingViewTitle() {
        return _t("Edit this view before Apply creates the model");
    }

    removeModel(line) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Remove the model"),
            body: _t(
                "Remove %(model)s from the project, with its access rows, its rules and the changes of its views? " +
                    "Once applied, it leaves the database with its records.",
                {model: line.model}
            ),
            confirmLabel: _t("Remove"),
            confirm: async () => {
                const data = await this.projectCall("remove_model", [line.id]);
                if (data && line.model === this.params.resModel) {
                    // Apply removes the model on screen: back to the view
                    // the editor was opened on, or out of the editor when
                    // that view is of the model too.
                    if (this.launch.resModel === line.model) {
                        await this.close();
                    } else {
                        await this.openView(...this.launchArgs);
                    }
                }
            },
            cancel: () => {},
        });
    }

    /**
     * Edit the default ``viewType`` view of the model line ``line``: the
     * view Apply created for it, or, before Apply, the default view the
     * model will have, whose changes Apply moves to the created view.
     */
    async openModel(line, viewType = "form") {
        if (!line.applied) {
            return this.openView(line.model, false, viewType);
        }
        const viewId = line.views && line.views[viewType];
        if (!viewId) {
            return false;
        }
        return this.openView(line.model, viewId, viewType);
    }

    /**
     * « Apply and open » of a model not created yet: the review of the
     * draft, whose Apply then edits the form of the model line ``line``.
     */
    async applyAndOpen(line) {
        await this.openSpace("review");
        if (this.state.space === "review") {
            this.state.openAfterApply = line.id;
        }
    }

    // ── the spaces of the rail ──────────────────────────────────────────

    /**
     * The entries of the rail: [{id, label, icon, count, disabled}]. Every
     * space but the view needs a project. ``count``: the models of the
     * project, its access rows, rules and groups, the total of its items.
     */
    get spaces() {
        const project = this.project;
        const counts = (project && project.counts) || {};
        const size = (key) => (counts[key] !== undefined ? counts[key] : ((project && project[key]) || []).length);
        return [
            {id: "view", label: _t("View"), icon: "fa-columns", count: 0, disabled: false},
            {id: "models", label: _t("Models"), icon: "fa-database", count: project ? size("models") : 0},
            {
                id: "security",
                label: _t("Security"),
                icon: "fa-shield",
                count: project ? size("access") + size("rules") + size("groups") : 0,
            },
            {id: "review", label: _t("Review"), icon: "fa-list-alt", count: project ? this.changeCount : 0},
        ].map((space) => ({...space, disabled: space.id !== "view" && !project}));
    }

    get chooseProjectTitle() {
        return _t("Choose or create a studio project first.");
    }

    /**
     * The key of the review space: it reads the review again for each
     * revision and state of the project.
     */
    get reviewKey() {
        const project = this.project;
        return project ? `${project.id}:${project.revision}:${project.state}` : "none";
    }

    /** Show the space ``space`` of the rail; the security space opens on its last tab. */
    async openSpace(space) {
        if (this.state.busy) {
            return;
        }
        if (space !== "review") {
            this.state.openAfterApply = false;
        }
        if (space === "security") {
            await this.openSecurity(this.state.securityTab);
            return;
        }
        if (space !== "view" && !this.project) {
            return;
        }
        if (space === this.state.space && this.state.panel !== "preview") {
            return;
        }
        this.closePanel();
        Object.assign(this.state, {space, selected: null, preview: false});
    }

    /** Show the tab ``panel`` (SECURITY_TABS) of the security space. */
    async openSecurity(panel) {
        if (this.state.busy) {
            return;
        }
        if (this.state.space === "security" && this.state.panel === panel) {
            return;
        }
        if (!this.project || !(await this.loadChoices())) {
            return;
        }
        const entering = this.state.space !== "security";
        Object.assign(this.state, {
            space: "security",
            securityTab: panel,
            selected: null,
            preview: false,
            panel,
            ruleForm: null,
            ruleCheck: null,
            ruleError: null,
            modelPreview: null,
            panelError: null,
        });
        if (entering) {
            // The rows of the other modules are read again at each entry.
            this.state.accessExisting = {};
            this.state.security.row = null;
        }
        if (entering || panel === "access") {
            await this.loadAccessExisting([this.securityModel].filter(Boolean));
        }
    }

    /** The models of the security space (securityModels). */
    get securityModels() {
        return securityModels(this.project, (model) => this.modelLabel(model));
    }

    /** The model the security space shows (pickModel), or null. */
    get securityModel() {
        return pickModel(this.securityModels, this.state.security.model, this.params.resModel);
    }

    /** Show the model ``model`` in the security space, with the rows of the other modules on it. */
    async selectSecurityModel(model) {
        if (model === this.securityModel && this.state.security.model) {
            return;
        }
        this.state.security.model = model;
        this.state.security.row = null;
        if (this.state.ruleForm && this.state.ruleForm.model !== model) {
            this.closeRuleForm();
        }
        await this.loadAccessExisting([model]);
    }

    /**
     * Close the panel the centre shows; a security space without a panel
     * goes back to the view.
     */
    closePanel() {
        if (this.state.space === "security") {
            this.state.space = "view";
        }
        Object.assign(this.state, {
            panel: null,
            ruleForm: null,
            ruleCheck: null,
            ruleError: null,
            modelPreview: null,
            panelError: null,
        });
    }

    // ── access rights and record rules ──────────────────────────────────

    get choiceModels() {
        return (this.state.choices && this.state.choices.models) || [];
    }

    /** The row being added; ``group_id`` holds the value of the group select. */
    newAccessRow() {
        return {model: "", group_id: "", perm_read: true, perm_write: false, perm_create: false, perm_unlink: false};
    }

    /** The access rows of the other modules on ``models``, shown read-only. */
    async loadAccessExisting(models) {
        const projectId = this.project && this.project.id;
        for (const model of models) {
            if (model in this.state.accessExisting) {
                continue;
            }
            try {
                this.state.accessExisting[model] = await this.orm.call(MODEL, "get_access_existing", [
                    projectId,
                    model,
                ]);
            } catch (error) {
                this.notification.add(this.errorMessage(error), {type: "danger"});
                return;
            }
        }
    }

    /** Replace the access rows of the project: one call, one change of the draft. */
    async setAccess(rows) {
        return this.projectCall("set_access", [rows]);
    }

    async toggleAccess(row, perm) {
        const rows = accessRows(this.project.access);
        const index = this.project.access.findIndex((r) => r.id === row.id);
        rows[index][perm] = !rows[index][perm];
        await this.setAccess(rows);
    }

    /** Remove an access row: the grid drops a row that gives no right. */
    async removeAccess(row) {
        const rows = accessRows(this.project.access.filter((r) => r.id !== row.id));
        await this.setAccess(rows);
    }

    async addAccess() {
        const add = this.state.accessAdd;
        const group = parseGroupValue(add.group_id);
        if (!add.model || !group) {
            return;
        }
        const value = String(add.group_id);
        if (this.project.access.some((r) => r.model === add.model && accessGroup(r)[0] === value)) {
            this.notification.add(_t("This group has a row on this model already: change its rights in the grid."), {
                type: "warning",
            });
            return;
        }
        const row = {model: add.model, ...group};
        for (const perm of PERMS) {
            row[perm] = Boolean(add[perm]);
        }
        if (!PERMS.some((perm) => row[perm])) {
            this.notification.add(_t("An access row gives at least one right."), {type: "warning"});
            return;
        }
        if (await this.setAccess([...accessRows(this.project.access), row])) {
            this.state.accessAdd = this.newAccessRow();
            // The grid shows the model of the new row.
            this.state.security.model = row.model;
            await this.loadAccessExisting([row.model]);
        }
    }

    /** The form of the rule ``rule`` of the payload, or of a new rule. */
    editRule(rule = null) {
        const models = [this.securityModel, ...this.projectModels.map((m) => m.model)].filter(Boolean);
        this.state.ruleForm = rule
            ? {
                  id: rule.id,
                  name: rule.name,
                  model: rule.model,
                  domain: rule.domain,
                  group_ids: rule.groups.map((g) => g[0]),
                  group_line_ids: (rule.group_lines || []).map((g) => g[0]),
                  global_rule: Boolean(rule.global_rule),
                  // The groups the rule names that left the database:
                  // saving the rule from the form records its groups again.
                  missing_groups: [...(rule.missing_groups || [])],
                  ...Object.fromEntries(PERMS.map((perm) => [perm, rule[perm]])),
              }
            : {
                  id: false,
                  name: "",
                  model: models[0] || "",
                  domain: "[]",
                  group_ids: [],
                  group_line_ids: [],
                  global_rule: false,
                  missing_groups: [],
                  ...Object.fromEntries(PERMS.map((perm) => [perm, true])),
              };
        this.state.ruleCheck = null;
        this.state.ruleError = null;
    }

    closeRuleForm() {
        this.state.ruleForm = null;
        this.state.ruleCheck = null;
        this.state.ruleError = null;
    }

    addRuleGroup(ev) {
        const group = parseGroupValue(ev.target.value);
        ev.target.value = "";
        const form = this.state.ruleForm;
        if (group && group.group_id && !form.group_ids.includes(group.group_id)) {
            form.group_ids.push(group.group_id);
        } else if (group && group.group_line_id && !form.group_line_ids.includes(group.group_line_id)) {
            form.group_line_ids.push(group.group_line_id);
        }
    }

    removeRuleGroup(value) {
        const form = this.state.ruleForm;
        const group = parseGroupValue(value) || {};
        form.group_ids = form.group_ids.filter((id) => id !== group.group_id);
        form.group_line_ids = form.group_line_ids.filter((id) => id !== group.group_line_id);
    }

    /** « Global »: the rule applies to every user, and names no group. */
    setRuleGlobal(checked) {
        const form = this.state.ruleForm;
        form.global_rule = checked;
        if (checked) {
            form.group_ids = [];
            form.group_line_ids = [];
        }
    }

    ruleCheckText(check) {
        if (!check.ok) {
            return check.error;
        }
        if (check.count === false) {
            return _t("The domain reads well; Apply checks its fields once it created the model.");
        }
        return _t("The domain applies: %(count)s record(s) match it.", {count: check.count});
    }

    /** The domain of the form, as the server evaluates it for a rule. */
    async checkRule() {
        const form = this.state.ruleForm;
        if (!form || !this.project) {
            return;
        }
        const {model, domain} = form;
        try {
            const result = await this.orm.call(MODEL, "check_rule_domain", [this.project.id, model, domain]);
            this.state.ruleCheck = {...result, model, domain};
        } catch (error) {
            this.state.ruleCheck = {ok: false, error: this.errorMessage(error), model, domain};
        }
    }

    /**
     * Save the rule of the form. A refusal shows at the top of the form
     * until the next Save or Cancel: it may be about the domain, the model,
     * the groups or the draft itself.
     */
    async saveRule() {
        const form = this.state.ruleForm;
        if (!form) {
            return;
        }
        this.state.ruleError = null;
        const {missing_groups, ...values} = form; // eslint-disable-line no-unused-vars
        const data = await this.projectCall("save_rule", [values], (message) => {
            this.state.ruleError = message;
        });
        if (data) {
            this.closeRuleForm();
            // The cards show the rules of the model of the saved rule.
            this.state.security.model = values.model;
        }
    }

    /**
     * Save the rule ``rule`` of the payload with ``changes`` (perm_*,
     * domain): one change of the draft. Saving records its groups again,
     * so a group that left the database is no longer named. An open form
     * of the rule shows it as saved.
     */
    async saveRuleValues(rule, changes = {}) {
        const values = {
            id: rule.id,
            name: rule.name,
            model: rule.model,
            domain: rule.domain,
            group_ids: rule.groups.map((g) => g[0]),
            group_line_ids: (rule.group_lines || []).map((g) => g[0]),
            global_rule: Boolean(rule.global_rule),
            ...Object.fromEntries(PERMS.map((perm) => [perm, Boolean(rule[perm])])),
            ...changes,
        };
        const data = await this.projectCall("save_rule", [values]);
        const form = this.state.ruleForm;
        if (data && form && form.id === rule.id) {
            const saved = (data.project.rules || []).find((r) => r.id === rule.id);
            if (saved) {
                this.editRule(saved);
            }
        }
        return data;
    }

    async removeRule(rule) {
        if (this.state.ruleForm && this.state.ruleForm.id === rule.id) {
            this.closeRuleForm();
        }
        await this.projectCall("remove_rule", [rule.id]);
    }

    // ── preview of a model not created yet ──────────────────────────────

    /** The model line of the project whose model is ``model``, or null. */
    modelLine(model) {
        return this.projectModels.find((line) => line.model === model) || null;
    }

    /**
     * Show the preview of the model line ``line``, not created yet, in
     * ``viewType`` and ``mode`` (« simulation », « real »). The server
     * answers its views and fields; nothing is written.
     */
    async openModelPreview(line, viewType = "form", mode = "simulation") {
        if (this.state.busy || !this.project) {
            return;
        }
        this.state.busy = true;
        let data;
        try {
            data = await this.orm.call(MODEL, "get_model_preview", [this.project.id, line.id, viewType, mode]);
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
            return;
        } finally {
            this.state.busy = false;
        }
        Object.assign(this.state, {
            space: "view",
            selected: null,
            preview: false,
            panel: "preview",
            ruleForm: null,
            filterForm: null,
            modelPreview: {lineId: line.id, viewType, mode, data, key: ++this.previewCount},
        });
    }

    /**
     * After a change of the draft, the preview on screen follows it: shown
     * again from the new draft (the real mode while the approval stands),
     * or closed, with a notice, once its model left the project or Apply
     * created it.
     */
    async refreshModelPreview() {
        const preview = this.state.modelPreview;
        if (!preview || this.state.panel !== "preview" || !this.project) {
            return;
        }
        const line = this.previewLine;
        if (!line || line.applied) {
            this.closePanel();
            this.notification.add(
                line
                    ? _t("The model %(model)s exists now: its preview is closed.", {model: line.model})
                    : _t("The model of the preview left the project: its preview is closed."),
                {type: "info"}
            );
            return;
        }
        const mode = preview.mode === "real" && this.project.approved ? "real" : "simulation";
        await this.openModelPreview(line, preview.viewType, mode);
    }

    /** The model line of the preview on screen, while it is in the project. */
    get previewLine() {
        const preview = this.state.modelPreview;
        return (preview && this.projectModels.find((line) => line.id === preview.lineId)) || null;
    }

    /** Show the preview on screen in another view type or mode. */
    async switchModelPreview(viewType, mode) {
        const line = this.previewLine;
        if (line) {
            await this.openModelPreview(line, viewType, mode);
        }
    }

    /** Approve, or withdraw the approval of, the real preview; then show the preview again. */
    async approvePreview(approve = true) {
        // The preview follows: back to the simulation once the approval is withdrawn.
        await this.projectAction(approve ? "action_approve" : "action_unapprove");
    }

    // ── toolbar ─────────────────────────────────────────────────────────

    /**
     * The preview of the view on screen: the real view with the draft, or
     * for a model not created yet, its model preview. A GeoEngine view the
     * project adds has no map before Apply: a notice says so.
     */
    async togglePreview() {
        if (this.state.busy) {
            return;
        }
        if (this.state.space !== "view") {
            // The preview shows the view: back to its space, preview on.
            this.closePanel();
            Object.assign(this.state, {space: "view", selected: null, preview: false});
        }
        const added = this.addedView;
        if (this.viewType === "geoengine" && added && !added.applied && !this.state.preview) {
            // base_geoengine reads the layers of the view from the database.
            this.notification.add(this.geoMapNotice, {type: "info"});
            return;
        }
        if (this.data.view && this.data.view.pending) {
            if (this.state.panel === "preview") {
                this.closePanel();
                return;
            }
            const line = this.modelLine(this.params.resModel);
            if (line) {
                await this.openModelPreview(line, this.viewType);
            }
            return;
        }
        this.state.preview = !this.state.preview;
    }

    /**
     * The props of the preview: the real view with the draft context. A
     * search view shows above the list of the model.
     */
    get previewProps() {
        const context = {[this.data.preview_key]: this.project ? this.project.preview_value : false};
        const props = {
            resModel: this.params.resModel,
            type: this.params.viewType,
            viewId: this.params.viewId,
            context,
            display: {controlPanel: false},
            loadIrFilters: false,
            loadActionMenus: false,
        };
        if (this.params.viewType === "form") {
            props.resId = this.data.sample_res_id || false;
            props.preventEdit = true;
        } else if (this.params.viewType === "search") {
            Object.assign(props, {type: "list", viewId: false, searchViewId: this.params.viewId, display: {}});
        } else if (["timeline", "activity", "leaflet_map"].includes(this.params.viewType)) {
            // web_timeline reads the fields of its attributes (start, end,
            // grouping) from the fields get_views answers, and the activity
            // view reads write_date for an image of activity_image, a field
            // its arch does not name; the search view brings every field of
            // the model. A map reads its records with searchRead.
            props.searchViewId = false;
        }
        return props;
    }

    /** Why a GeoEngine view the project adds shows no map before Apply. */
    get geoMapNotice() {
        return _t("The map shows once Apply creates the view and its layers.");
    }

    get draftPreviewTitle() {
        return _t("Show the view as its editor sees the draft");
    }

    get pendingPreviewTitle() {
        return _t("Preview the model before Apply creates it: nothing is saved");
    }

    get previewKey() {
        return `${this.params.viewType}:${this.project ? this.project.preview_value : "none"}`;
    }

    /** Whether the centre shows a preview: of the view, or of a model not created yet. */
    get previewOn() {
        return this.state.space === "view" && (this.state.preview || this.state.panel === "preview");
    }

    /** The label of the preview on screen, for the status bar; false for none. */
    get previewLabel() {
        if (this.state.space !== "view") {
            return false;
        }
        if (this.state.panel === "preview" && this.state.modelPreview) {
            return this.state.modelPreview.mode === "real"
                ? _t("Preview: real, rolled back")
                : _t("Preview: simulation, nothing is written");
        }
        return this.state.preview ? _t("Preview: the view with the draft") : false;
    }

    /**
     * What the inspector shows of the preview on screen, null for none:
     * {kind, mode, model, approved, approvedBy, approvedDate, stale}.
     * « model »: the preview of a model not created yet, in « simulation »
     * or « real » mode, the latter once approved; « view »: the view of
     * the database rendered with the draft.
     */
    get previewInfo() {
        if (!this.previewOn || !this.project) {
            return null;
        }
        const preview = this.state.modelPreview;
        if (this.state.panel !== "preview" || !preview) {
            return {kind: "view", mode: "view"};
        }
        const project = this.project;
        return {
            kind: "model",
            mode: preview.data.mode || preview.mode,
            model: (this.previewLine || {}).model || "",
            approved: Boolean(project.approved),
            approvedBy: project.approved_by ? project.approved_by[1] : "",
            approvedDate: project.approved_date ? formatDateTime(deserializeDateTime(project.approved_date)) : "",
            stale: Boolean(!project.approved && project.approved_by),
        };
    }

    /** Back to the canvas from the preview on screen. */
    async leavePreview() {
        if (this.state.panel === "preview") {
            this.closePanel();
        } else {
            this.state.preview = false;
        }
    }

    /** The state of the project in the status bar. */
    get statusText() {
        const project = this.project;
        if (project.state !== "draft") {
            return _t("%(state)s · the database has the draft", {state: project.state_label});
        }
        if (!project.applied) {
            return _t("%(state)s · %(count)s change(s) not applied", {
                state: project.state_label,
                count: this.changeCount,
            });
        }
        return _t("%(state)s · changed since the last Apply", {state: project.state_label});
    }

    /** How many items the draft of the project holds: what Apply writes. */
    get changeCount() {
        const project = this.project;
        if (!project) {
            return 0;
        }
        const counts = project.counts || {};
        return counts.total !== undefined ? counts.total : project.item_count || 0;
    }

    /** The date of the last Apply of the project, in the format of the user; false for none. */
    get appliedDateLabel() {
        const value = this.project && this.project.applied_date;
        return value ? formatDateTime(deserializeDateTime(value)) : false;
    }

    /** When the project was last applied, for the status bar. */
    get appliedText() {
        const date = this.appliedDateLabel;
        return date ? _t("Last Apply: %(date)s", {date}) : _t("Never applied");
    }

    /** Apply, from the top bar: the review of the draft, whose last button applies it. */
    async applyFromBar() {
        this.menus.apply.close();
        await this.openSpace("review");
    }

    /**
     * Apply the draft the review shows, with ``digest``, the digest of the
     * removal report on screen; once applied, back to the view space, on
     * the form of the model ``openAfterApply`` names when Apply created
     * it. Answer the payload, or null.
     */
    async applyReviewed(digest) {
        const lineId = this.state.openAfterApply;
        const data = await this.projectAction("action_apply", {digest, space: "view"});
        if (!data) {
            return null;
        }
        this.state.openAfterApply = false;
        const line = lineId && ((data.project && data.project.models) || []).find((m) => m.id === lineId);
        if (line && line.applied) {
            await this.openModel(line, "form");
        }
        return data;
    }

    /**
     * Show the item of the review whose ``target`` is given: the block of a
     * change in the view space (its view opened first), a model in the
     * models space, an access row, a rule, an app or a group in its tab of
     * the security space.
     */
    async showReviewItem(target) {
        if (!target || this.state.busy) {
            return;
        }
        if (target.space === "view") {
            const params = this.params;
            const same =
                params.resModel === target.model &&
                params.viewType === target.view_type &&
                (!target.view_id || target.view_id === params.viewId);
            if (!same && !(await this.openView(target.model, target.view_id || false, target.view_type))) {
                return;
            }
            await this.openSpace("view");
            if (target.path) {
                this.reveal(target.path);
            }
        } else if (target.space === "models") {
            this.selectModelEntry(target.model);
            await this.openSpace("models");
        } else if (target.space === "security") {
            if (target.model) {
                this.state.security.model = target.model;
                this.state.security.row = null;
            }
            await this.openSecurity(target.tab || "access");
        }
    }

    /** Discard the draft, once confirmed: back to the last Apply. */
    discardDraft() {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Discard the draft"),
            body: _t(
                "Go back to the last Apply? The changes of the draft made since are lost; " +
                    "without an Apply, the draft is emptied."
            ),
            confirmLabel: _t("Discard"),
            confirm: async () => {
                await this.projectAction("action_discard");
            },
            cancel: () => {},
        });
    }

    /**
     * Run ``action`` of the menu of Apply (discard, revert, send to a
     * spreadsheet, open the project).
     */
    async runApplyMenu(action) {
        this.menus.apply.close();
        if (action === "discard") {
            await this.projectAction("action_discard");
        } else if (action === "revert") {
            await this.revertProject();
        } else if (action === "spreadsheet") {
            await this.sendToSpreadsheet();
        } else if (action === "project") {
            await this.openProject();
        }
    }

    /** Whether the view on screen is a list, a pivot or a graph: what a spreadsheet reads. */
    get spreadsheetViewType() {
        return SPREADSHEET_VIEW_TYPES.includes(this.viewType);
    }

    /**
     * Whether the view on screen exists in the database: neither the
     * pending default view of a model not created yet nor a view a view
     * line adds before Apply.
     */
    get viewApplied() {
        const view = this.data.view;
        return Boolean(view && !view.pending && !(view.added && !view.added.applied));
    }

    /**
     * Create a spreadsheet of spreadsheet_oca that reads the applied view on
     * screen, then open it: its client action fills the sheet and saves it
     * when the user leaves it. The notice of the server, that the draft
     * changes of the view are not in the sheet, shows as a warning.
     */
    async sendToSpreadsheet() {
        if (this.state.busy || !this.project) {
            return;
        }
        this.state.busy = true;
        let data;
        try {
            data = await this.orm.call(MODEL, "send_to_spreadsheet", [this.project.id, ...this.viewArgs()]);
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
            return;
        } finally {
            this.state.busy = false;
        }
        if (data.notice) {
            this.notification.add(data.notice, {type: "warning"});
        }
        await this.action.doAction(data.action);
    }

    async openProject() {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "erplibre.studio.project",
            res_id: this.project.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async close() {
        try {
            await this.action.restore();
        } catch {
            if (this.params.actionId) {
                await this.action.doAction(this.params.actionId);
            }
        }
    }
}

registry.category("actions").add("erplibre_studio.editor", StudioEditor);
