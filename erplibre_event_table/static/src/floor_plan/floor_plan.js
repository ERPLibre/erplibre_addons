/** @odoo-module **/
// Copyright 2026 TechnoLibre - Mathieu Benoit
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import {Component, onWillStart, onWillUpdateProps, useEffect, useExternalListener, useRef, useState} from "@odoo/owl";
import {browser} from "@web/core/browser/browser";
import {Dropdown} from "@web/core/dropdown/dropdown";
import {DropdownItem} from "@web/core/dropdown/dropdown_item";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {useDraggable} from "@web/core/utils/draggable";
import {makeDraggableHook} from "@web/core/utils/draggable_hook_builder_owl";
import {useService} from "@web/core/utils/hooks";
import {pick} from "@web/core/utils/objects";
import {standardWidgetProps} from "@web/views/widgets/standard_widget_props";
import {standardActionServiceProps} from "@web/webclient/actions/action_service";
import {
    CONNECTOR_WIDTH,
    GRID_SIZE,
    SEAT_RING,
    dropPosition,
    findDropTarget,
    floorSize,
    listLabelLength,
    listReservedHeight,
    listWidth,
    listWrapsToTwoLines,
    resizeTable,
    seatPositions,
    visualTableSize,
} from "@erplibre_event_table/floor_plan/geometry";

/**
 * Drags a whole table block without following the cursor: the core's own
 * useDraggable forces followCursor and puts `position: fixed !important` on
 * the dragged element, which would pull the block out of its container and
 * strand its seats, badges and names behind. pos_restaurant builds its own
 * hook for the same reason.
 */
const useTableDraggable = makeDraggableHook({
    name: "useTableDraggable",
    onComputeParams({ctx}) {
        ctx.followCursor = false;
    },
    onDragStart: ({ctx}) => pick(ctx.current, "element"),
    onDrag: ({ctx}) => pick(ctx.current, "element"),
    onDrop: ({ctx}) => pick(ctx.current, "element"),
});

/**
 * Reads a floor plan round by round: tables placed on the floor, their
 * seats and occupant names, the tray of people without a seat this round,
 * and a conflict badge on any table the server flagged. Editing a table's
 * position or size goes through useTableDraggable; moving a person between
 * tables, or into and out of the tray, goes through the core's own
 * useDraggable, or the dragless menu on each chip.
 */
export class EventTableFloorPlan extends Component {
    static template = "erplibre_event_table.EventTableFloorPlan";
    static components = {Dropdown, DropdownItem};
    static props = {
        resModel: String,
        resId: [Number, Boolean],
        reloadKey: {type: [String, Number], optional: true},
        fullscreen: {type: Boolean, optional: true},
        onDataChanged: {type: Function, optional: true},
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.floorRef = useRef("floor");
        this.rootRef = useRef("root");
        this.state = useState({
            payload: null,
            round: 1,
            highlightParticipantId: 0,
            editLayout: false,
            // Two display switches local to this component, exactly like
            // `zoom`: neither is ever written to the database nor carried in
            // the payload. `showNames` draws or withholds the side lists and
            // their connectors; `editParticipants` is what puts a ⋮ on each
            // table and on each name, so the plan reads as read-only until it
            // is asked for.
            showNames: true,
            editParticipants: false,
            zoom: 1,
            requestId: 0,
        });
        // Layout writes (position, size, shape) chain on this single
        // promise: an orm.write still in flight when action_move_participant
        // answers would read the table's old position back from the
        // database and put it back on screen.
        this.layoutWrite = Promise.resolve();
        // Set by a pointerdown on a resize handle, cleared on pointerup;
        // plain instance state, not reactive, since only the table's own
        // width and height need to trigger a redraw while resizing.
        this.resizeState = null;
        // Non-reactive on purpose: a test reads it after a drop to prove
        // that target detection still saw something, which is exactly the
        // guard against the pe-none countermeasure of onDragStart below
        // failing to restore hover.
        this.lastDropCandidates = [];
        // Raised by the three percentage buttons, cleared by "Fit to window":
        // true means the user has named a scale, and the automatic fit leaves
        // it alone from then on. Plain instance state, not reactive, since
        // nothing drawn reads it.
        this.zoomPinned = false;
        onWillStart(() => this.loadData());
        // `nextProps` carries the values the component is about to receive;
        // `this.props` is still the OLD ones at this point in Owl's
        // lifecycle, so the request is built from the argument, not from
        // `this.props` (the pattern core's RecordSelector uses for the
        // same reason).
        onWillUpdateProps((nextProps) => {
            if (nextProps.resId !== this.props.resId || nextProps.reloadKey !== this.props.reloadKey) {
                return this.loadData(nextProps);
            }
        });

        // Fits the room to its pane after any patch that REPLACES the
        // payload: the mount, a reload, a display option coming back from
        // the server, a move. Each of those can change the room's footprint,
        // and the fit has to read the pane after the patch, once the new
        // payload is on screen and measurable.
        //
        // Dragging or resizing a table MUTATES the payload in place and
        // leaves its identity alone, so no fit runs mid-gesture — which is
        // the point: dropPosition and onResizeMove divide by the zoom to undo
        // the room's transform, so a zoom moving under a drag would write a
        // wrong position or size to the database. `editLayout` is a
        // dependency rather than a bare guard so that leaving edit mode, once
        // the tables have been moved about, fits the room they now occupy.
        useEffect(
            () => this.fitToWindow({auto: true}),
            () => [this.state.payload, this.state.editLayout]
        );

        this.tableDraggable = useTableDraggable({
            ref: this.floorRef,
            elements: ".o_event_table_block",
            handle: ".o_event_table_surface",
            enable: () => this.state.editLayout,
            onDragStart: ({x, y, element}) => {
                const rect = element.getBoundingClientRect();
                // The gap between the pointer and the block's own corner,
                // kept fixed for the rest of the drag: dropPosition rebuilds
                // the block's position from the pointer alone.
                this.tableGrab = {x: x - rect.left, y: y - rect.top};
                this.draggedTable = this.tableByElement(element);
                // The position before this drag optimistically moves it on
                // screen: writeLayout restores this if the database refuses
                // the write.
                this.tablePrevious = {position_h: this.draggedTable.x, position_v: this.draggedTable.y};
            },
            onDrag: ({x, y}) => {
                const floor = this.floorRef.el;
                const position = dropPosition(
                    {x, y},
                    this.tableGrab,
                    floor.getBoundingClientRect(),
                    {left: floor.scrollLeft, top: floor.scrollTop},
                    this.state.zoom
                );
                this.draggedTable.x = position.x;
                this.draggedTable.y = position.y;
            },
            onDrop: () => {
                const table = this.draggedTable;
                this.writeLayout(table, {position_h: table.x, position_v: table.y}, this.tablePrevious);
            },
        });

        this.personDraggable = useDraggable({
            ref: this.rootRef,
            elements: ".o_event_table_person",
            ignore: ".o_event_table_person_menu",
            enable: () =>
                Boolean(this.state.payload) && this.state.payload.plan.can_move_participants && !this.state.editLayout,
            onDragStart: ({addStyle}) => {
                // The core puts pe-none on <body> for the whole drag, a
                // Bootstrap utility marked !important; pointer-events is
                // inherited, so document.elementsFromPoint would return
                // nothing and every drop would be a silent non-event. The
                // reserve sits outside the floor in the DOM, so hover is
                // restored on the plan's own root, the one container both
                // share, rather than on the floor alone.
                addStyle(this.rootRef.el, {pointerEvents: "auto"});
            },
            onDrop: ({x, y, element}) => {
                const draggedId = Number(element.dataset.participantId);
                // Viewport coordinates on purpose: elementsFromPoint expects
                // them, and none of the dropPosition corrections (grid,
                // zoom, scroll) apply on this detection path.
                this.lastDropCandidates = document.elementsFromPoint(x, y);
                const target = findDropTarget(this.lastDropCandidates, draggedId);
                this.handleDrop(draggedId, target);
            },
        });

        useExternalListener(window, "pointermove", (ev) => this.onResizeMove(ev));
        useExternalListener(window, "pointerup", (ev) => this.onResizeEnd(ev));
    }

    /**
     * Fetches the payload for `props.resId`, serialised by an incrementing
     * request id: a reply only ever applies if it is still the answer to
     * the last request issued. No call is made without an id, which is
     * what lets an unsaved record show its own message instead.
     */
    async loadData(props = this.props) {
        if (!props.resId) {
            return;
        }
        const requestId = ++this.state.requestId;
        const payload = await this.orm.call(props.resModel, "get_floor_plan_data", [props.resId]);
        this.applyPayload(payload, requestId);
    }

    /**
     * Applies a fetched payload, unless a fresher request has already been
     * issued in the meantime. Public because a test replays a stale reply
     * directly, without having to orchestrate two concurrent orm calls.
     */
    applyPayload(payload, requestId) {
        if (requestId !== this.state.requestId) {
            return;
        }
        this.state.payload = payload;
        if (this.state.round > payload.plan.round_count) {
            this.state.round = 1;
        }
    }

    /**
     * The message to show instead of the floor, or an empty string when
     * the floor itself has something to draw. Checked in this order: an
     * unsaved record, no table configured yet, and no combination to read
     * seats from — each state can also justify the ones after it, so only
     * the first that applies is shown.
     */
    get emptyMessage() {
        if (!this.props.resId) {
            return _t("Save the record to draw the floor plan.");
        }
        if (!this.state.payload) {
            return "";
        }
        if (!this.state.payload.tables.length) {
            return _t("Configure the tables to draw the floor plan.");
        }
        if (!this.state.payload.combination) {
            return _t("Generate and choose a combination to see who sits where.");
        }
        return "";
    }

    get roundNumbers() {
        const count = this.state.payload.plan.round_count;
        return Array.from({length: count}, (_, index) => index + 1);
    }

    setRound(round) {
        // Every round already sits in the payload: switching is purely
        // local, no server call.
        this.state.round = round;
    }

    // The three percentage buttons name a scale. Pinning it here is what
    // keeps the automatic fit from taking it back on the next payload.
    setZoom(zoom) {
        this.zoomPinned = true;
        this.state.zoom = zoom;
    }

    /**
     * Scales the floor down (never up) so the whole room fits its pane on
     * BOTH axes: the smaller of the two ratios, capped at 1, since the point
     * is to shrink an oversized room and never to blow up a small one past
     * its native size.
     *
     * `auto` marks the call made from the effect in setup() rather than by
     * the "Fit to window" button. An automatic call stands down in front of a
     * scale the user named (this.zoomPinned) and while the layout is being
     * edited; the button is the gesture that asks for the fit back, so it
     * clears the pin.
     *
     * The two axes are measured from DIFFERENT elements, because only one of
     * them carries a budget the zoom is free to read. Width: the pane's own
     * clientWidth is the room the flex row leaves it once the 220px tray
     * takes its share, whatever width floorStyle declares — `flex: 1 1 auto`
     * with `min-width: 0` (floor_plan.scss) makes the rendered box follow the
     * row rather than the declaration. Height does NOT work the same way:
     * floorStyle declares an explicit height, and an explicit height wins
     * over the cross-axis stretch, so the pane's clientHeight only ever
     * reports back the zoom this is trying to compute. The height budget is
     * therefore taken from the element that CAPS the plan — the widget
     * wrapper, which stops at 70vh, or the fullscreen action, which stops at
     * the window (floor_plan.scss) — measured from the pane's own top edge
     * down to that cap's bottom, which is the band the pane has to live in.
     * The pane's border and horizontal scrollbar come off that band, since a
     * room sized to the whole of it would land in a content box smaller by
     * exactly that much.
     */
    fitToWindow({auto = false} = {}) {
        const el = this.floorRef.el;
        // The parent is the element that caps the plan's height: the widget
        // wrapper or the fullscreen action, both of which bound it without
        // reading the room's own size back, which is what keeps the height
        // below from being the circular measurement clientHeight would give.
        const cap = this.rootRef.el && this.rootRef.el.parentElement;
        if (!el || !cap || !this.state.payload) {
            return;
        }
        if (auto && (this.zoomPinned || this.state.editLayout)) {
            return;
        }
        if (!auto) {
            this.zoomPinned = false;
        }
        const size = this.roomSize;
        const chrome = el.offsetHeight - el.clientHeight;
        const width = el.clientWidth;
        const height = cap.getBoundingClientRect().bottom - el.getBoundingClientRect().top - chrome;
        // An element not yet laid out — a hidden tab, a deferred render —
        // answers 0 or less on either axis. A zoom computed from that is 0,
        // which would hide the whole room, so the current one stands instead.
        if (width <= 0 || height <= 0) {
            return;
        }
        this.state.zoom = Math.min(1, width / size.width, height / size.height);
    }

    toggleEditLayout() {
        this.state.editLayout = !this.state.editLayout;
    }

    // Withholding the lists changes nothing the fit measures: floorSize
    // (geometry.js) reserves SEAT_RING + CONNECTOR_WIDTH + listWidth beside
    // every table whatever is drawn there, and its Python twin
    // _grid_positions spaces the tables on that same reservation. The room
    // keeps its footprint, so the effect in setup() has no reason to take
    // this switch as a dependency, and the reservation stays out of
    // floorSize, where a local switch would put the two twins out of step.
    toggleShowNames() {
        this.state.showNames = !this.state.showNames;
    }

    toggleEditParticipants() {
        this.state.editParticipants = !this.state.editParticipants;
    }

    /**
     * Puts every table back on the grid the server lays out, then reads the
     * plan again: action_rearrange_tables answers nothing of its own, so the
     * new positions reach the screen only through a fresh payload. This is
     * the one button of the three that WRITES, and the remedy for a floor
     * whose tables were placed under an older spacing and whose lists now
     * overlap their neighbour.
     *
     * Waits on any layout write in flight first (see this.layoutWrite), or a
     * drag still being saved would put one table back where it was. The
     * automatic fit that follows the new payload still stands down in front
     * of a scale the user named: nothing here clears this.zoomPinned.
     */
    async rearrangeTables() {
        // Read before the await, as movePerson does: the pager can move this
        // component to another record while the call is in flight, and the
        // reload has to answer for the record the rearrange actually hit.
        const resModel = this.props.resModel;
        const resId = this.props.resId;
        await this.layoutWrite;
        await this.orm.call(resModel, "action_rearrange_tables", [resId]);
        await this.loadData({resModel, resId});
        if (this.props.onDataChanged) {
            this.props.onDataChanged();
        }
    }

    tableByElement(element) {
        const tableId = Number(element.dataset.tableId);
        return this.state.payload.tables.find((table) => table.id === tableId);
    }

    /**
     * Writes one table's layout fields, chained after any write already in
     * flight so two edits on the same or different tables never race each
     * other or a participant move (see the comment on this.layoutWrite).
     * `previousValues` are the fields as the caller found them before
     * optimistically applying `values` to the reactive table; if orm.write
     * rejects, they are written back so the screen stops claiming a
     * position, size or shape the database refused.
     */
    writeLayout(table, values, previousValues) {
        this.layoutWrite = this.layoutWrite
            .then(() => this.orm.write("event.table", [table.id], values))
            .catch((error) => {
                Object.assign(table, previousValues);
                // Swallowed here, not left rejected: a plain .then() with
                // no rejection handler forwards a rejection instead of
                // running, so an uncaught failure here would skip every
                // orm.write chained after it (see the comment on
                // this.layoutWrite in setup()). The error still needs to
                // reach the user, so it is handed to a bare Promise.reject
                // that nothing here awaits or catches: Odoo's own
                // unhandledrejection listener shows it exactly as it would
                // an uncaught orm.write failure.
                Promise.reject(error);
            });
        return this.layoutWrite;
    }

    toggleShape(table) {
        const previous = {shape: table.shape};
        table.shape = table.shape === "round" ? "square" : "round";
        this.writeLayout(table, {shape: table.shape}, previous);
    }

    // Built here, not as a template attribute: the label depends on the
    // table's current shape, and a dynamic title or text written inside a
    // template expression escapes the extractor lot F runs against the
    // glossary.
    shapeToggleLabel(table) {
        return table.shape === "round" ? _t("Square shape") : _t("Round shape");
    }

    /**
     * A corner handle has no reason to follow the cursor, so resizing skips
     * the draggable hooks entirely and tracks the pointer by hand: a
     * pointerdown here starts it, pointermove and pointerup are caught on
     * the window by the external listeners set up in setup().
     */
    startResize(ev, table) {
        ev.preventDefault();
        ev.stopPropagation();
        this.resizeState = {
            table,
            pointerId: ev.pointerId,
            startX: ev.clientX,
            startY: ev.clientY,
            startWidth: table.width,
            startHeight: table.height,
        };
    }

    onResizeMove(ev) {
        if (!this.resizeState || ev.pointerId !== this.resizeState.pointerId) {
            return;
        }
        const {table, startX, startY, startWidth, startHeight} = this.resizeState;
        // Screen pixels moved, converted to floor pixels: the block the
        // pointer drags across is itself scaled by the zoom.
        const dx = (ev.clientX - startX) / this.state.zoom;
        const dy = (ev.clientY - startY) / this.state.zoom;
        const size = resizeTable(startWidth, startHeight, dx, dy);
        table.width = size.width;
        table.height = size.height;
    }

    onResizeEnd(ev) {
        if (!this.resizeState || ev.pointerId !== this.resizeState.pointerId) {
            return;
        }
        const {table, startWidth, startHeight} = this.resizeState;
        this.resizeState = null;
        this.writeLayout(table, {width: table.width, height: table.height}, {width: startWidth, height: startHeight});
    }

    /**
     * Opens the fullscreen action for the underlying plan. Restricted to a
     * plan resModel: the action's contract takes a plan id, and a
     * combination preview has none of its own to hand it.
     */
    async openFullScreen() {
        await this.action.doAction({
            type: "ir.actions.client",
            tag: "erplibre_event_table.floor_plan",
            params: {plan_id: this.props.resId},
        });
    }

    exitFullScreen() {
        browser.history.back();
    }

    get participantsById() {
        const byId = {};
        for (const participant of this.state.payload.participants) {
            byId[participant.id] = participant;
        }
        return byId;
    }

    get currentRoundData() {
        return this.state.payload.rounds.find((round) => round.round === this.state.round) || null;
    }

    /**
     * The occupants of one table for the round on screen, ordered by seat
     * number then by name so that an assigned seating stays stable and an
     * unassigned one still reads predictably.
     */
    peopleFor(table) {
        const round = this.currentRoundData;
        if (!round) {
            return [];
        }
        const byId = this.participantsById;
        return round.seats
            .filter((seat) => seat.table_id === table.id)
            .map((seat) => ({...byId[seat.participant_id], seat: seat.seat}))
            .sort((a, b) => a.seat - b.seat || a.name.localeCompare(b.name));
    }

    get trayPeople() {
        const round = this.currentRoundData;
        if (!round) {
            return [];
        }
        const byId = this.participantsById;
        return round.unseated.map((participantId) => byId[participantId]).sort((a, b) => a.name.localeCompare(b.name));
    }

    // Built here, not in the template: the count is dynamic, and a string
    // written inside a template expression escapes the extractor lot F
    // runs against the glossary.
    get trayTitle() {
        return _t("Not seated (%(count)s)", {count: this.trayPeople.length});
    }

    // Built here, not in the template: naming the table and its occupation
    // together is a dynamic sentence, and a string written inside a
    // template expression escapes the extractor lot F runs against the
    // glossary.
    sendToTableLabel(table) {
        return _t("Table %(number)s (%(taken)s / %(seats)s)", {
            number: table.number,
            taken: this.peopleFor(table).length,
            seats: table.seat_count,
        });
    }

    // Built here, not in the template: naming a table in a sentence is
    // dynamic, and a string written inside a template expression escapes the
    // extractor lot F runs against the glossary.
    seatHereLabel(table) {
        return _t("Seat someone at table %(number)s", {number: table.number});
    }

    /**
     * Routes a drop candidate to the matching server call: a chip swaps two
     * people, a seat asks for that seat, a bare table surface is a plain
     * move, the tray unseats, and no target at all does nothing. Called
     * from both the drag path (target.kind from findDropTarget) and the
     * dragless menu (a hand-built "table" target).
     */
    handleDrop(participantId, target) {
        if (!target) {
            return;
        }
        switch (target.kind) {
            case "participant":
                this.movePerson(participantId, target.tableId, {swapParticipantId: target.participantId});
                break;
            case "seat":
                this.movePerson(participantId, target.tableId, {seatNumber: target.seat});
                break;
            case "table":
                this.movePerson(participantId, target.tableId);
                break;
            case "tray":
                this.unseatPerson(participantId);
                break;
        }
    }

    sendToTable(participantId, tableId) {
        this.handleDrop(participantId, {kind: "table", tableId});
    }

    removeFromRound(participantId) {
        this.handleDrop(participantId, {kind: "tray"});
    }

    /**
     * Moves or swaps one participant for the round on screen. Waits on any
     * layout write in flight first (see this.layoutWrite), then replaces
     * the whole state with the payload the server answers and notifies the
     * embedding record. A UserError from the server surfaces through
     * Odoo's own dialog and leaves the state untouched: nothing here
     * catches it.
     */
    async movePerson(participantId, tableId, {seatNumber = false, swapParticipantId = false} = {}) {
        // Read before the await below, whose duration is arbitrary: a
        // round switch while a layout write is still in flight would
        // otherwise apply this move to the round now on screen instead of
        // the one the drag targeted, and resId/resModel are just as
        // exposed — onWillUpdateProps exists precisely because the pager
        // can move this component to another record while it stays
        // mounted, and a write still in flight then would land on that
        // OTHER plan instead. Either way the returned payload redraws
        // whatever is on screen at that point, so nothing would look
        // wrong on screen.
        const round = this.state.round;
        const resModel = this.props.resModel;
        const resId = this.props.resId;
        await this.layoutWrite;
        const requestId = ++this.state.requestId;
        const payload = await this.orm.call(
            resModel,
            "action_move_participant",
            [resId, round, participantId, tableId],
            {seat_number: seatNumber, swap_participant_id: swapParticipantId}
        );
        this.applyPayload(payload, requestId);
        if (this.props.onDataChanged) {
            this.props.onDataChanged();
        }
    }

    async unseatPerson(participantId) {
        // See the comment in movePerson: round, resModel and resId are
        // all captured before the await, not after.
        const round = this.state.round;
        const resModel = this.props.resModel;
        const resId = this.props.resId;
        await this.layoutWrite;
        const requestId = ++this.state.requestId;
        const payload = await this.orm.call(resModel, "action_unseat_participant", [resId, round, participantId]);
        this.applyPayload(payload, requestId);
        if (this.props.onDataChanged) {
            this.props.onDataChanged();
        }
    }

    // The size every piece of this table's own rendering geometry uses:
    // visual mode substitutes visualTableSize's own computed size for
    // the table's stored width/height (never the other way — the
    // stored values are untouched, see floorSize's own comment in
    // geometry.js), so the surface, the seats around it and their name
    // anchors all agree on the same dimensions. Reading table.width or
    // table.height directly anywhere else in this component would draw
    // that one piece against the OLD size while everything else here
    // used the new one.
    effectiveTableSize(table) {
        return this.state.payload.plan.visual_tables
            ? visualTableSize(
                  table.shape,
                  table.seat_count,
                  this.state.payload.plan.assign_seats,
                  this.state.payload.plan.show_company
              )
            : {width: table.width, height: table.height};
    }

    seatPositionsFor(table) {
        const {width, height} = this.effectiveTableSize(table);
        return seatPositions(table.shape, width, height, table.seat_count);
    }

    // The number written on a chair, turned back by exactly the angle
    // seatStyle turned the pad through, so the digits read upright
    // wherever that chair sits. UNCONDITIONAL, never guarded by a
    // threshold on the angle: a square table's chairs take 0, PI/2, PI
    // and -PI/2 within one ring, and any threshold would leave part of
    // them lying on their side.
    seatNumberStyle(seat) {
        return `transform: rotate(${-seat.angle}rad);`;
    }

    isSeatTaken(table, seatNumber) {
        const round = this.currentRoundData;
        if (!round) {
            return false;
        }
        return round.seats.some((seat) => seat.table_id === table.id && seat.seat === seatNumber);
    }

    conflictFor(tableId) {
        const round = this.currentRoundData;
        if (!round) {
            return null;
        }
        return round.conflicts.find((conflict) => conflict.table_id === tableId) || null;
    }

    /**
     * Built here rather than in the template: a string written inside a
     * template expression escapes the extraction that lot F runs against
     * the glossary. The `_t()` call itself must also stay OUTSIDE any
     * JS template literal substitution (`${...}`): the extractor's
     * lexer does not descend into one, so a call placed there is missed
     * the same way. Each label is therefore resolved to a plain string
     * first, then joined by concatenation.
     */
    /**
     * The whole label of a chip, for its tooltip.
     *
     * A chip clips its text to the list's width and marks the cut with an
     * ellipsis, so a long name is the one thing the plan can show a reader
     * without letting them read it. The company line is clipped by the
     * same width, so it follows when the plan shows companies. Returned
     * as plain text: `title` is the browser's own affordance and needs no
     * markup, and the value is a person's name, which is data and not a
     * string to translate.
     */
    personTitle(person) {
        const company = this.state.payload.plan.show_company && person.company;
        return company ? person.name + " — " + company : person.name;
    }

    conflictTitle(conflict) {
        const lines = [];
        if (conflict.company_pairs) {
            const label = _t("Colleagues at this table");
            lines.push(label + ": " + conflict.company_pairs);
        }
        if (conflict.repeated_pairs) {
            const label = _t("Repeated meetings at this table");
            lines.push(label + ": " + conflict.repeated_pairs);
        }
        if (conflict.table_returns) {
            const label = _t("Returns to this table");
            lines.push(label + ": " + conflict.table_returns);
        }
        return lines.join("\n");
    }

    occupancyText(table) {
        return `${this.peopleFor(table).length} / ${table.seat_count}`;
    }

    blockStyle(table) {
        return `left: ${table.x}px; top: ${table.y}px;`;
    }

    surfaceStyle(table) {
        const {width, height} = this.effectiveTableSize(table);
        return `width: ${width}px; height: ${height}px;`;
    }

    // Seats are centred on the point seatPositions returns, itself relative
    // to the table's own top-left corner.
    // The rotation turns the pad's whole sub-tree, the seat number
    // included — which is why that number carries a counter-rotation of
    // its own (seatNumberStyle). Outside visual mode the pad is a bare
    // circle, identical at any angle; the angle only becomes visible
    // once o_event_table_seat_chair gives the marker its backrest
    // (floor_plan.scss).
    seatStyle(seat) {
        return `left: ${seat.x}px; top: ${seat.y}px; transform: rotate(${seat.angle}rad);`;
    }

    // The height this table's list actually draws, which is what gives
    // the connector and its bracket their own. Counted in CHIPS: the
    // list holds the people SEATED here this round, never seat_count,
    // which is only the capacity floorSize and _grid_positions reserve
    // against — they place a table before anyone is seated, where this
    // draws one that already is. Reading LIST_LINE_HEIGHT directly
    // here, while the reservations counted the company line, would
    // leave the bracket stopping short of the names it embraces.
    //
    // Whether a chip wraps is asked of THAT CHIP'S own label, at the
    // very number the template prints beside the name (floor_plan.xml
    // numbers a list 1..N, or by the seat where one is attributed), and
    // the chips are added up one by one: a table of eight where a
    // single name wraps draws 21 px taller, not 168. The reservations
    // count the same chips from the server's side and pad the empty
    // seats, so what is drawn here always fits the room they kept.
    listHeight(table) {
        const people = this.peopleFor(table);
        const {show_company, show_full_names} = this.state.payload.plan;
        let wrapping = 0;
        people.forEach((person, index) => {
            if (listWrapsToTwoLines(show_full_names, listLabelLength(person.seat || index + 1, person.name))) {
                wrapping += 1;
            }
        });
        return listReservedHeight(people.length, wrapping, show_company);
    }

    // The list beside the table: clear of the chair ring on that side,
    // then clear of the connector. Aligned on the table's own TOP edge
    // rather than centred on it, which would let a long list reach above
    // the block's origin — where the room's top edge clips the first
    // names of the top row and no floorSize term could reserve the
    // space, since floorSize only ever measures downward from a table's
    // own y.
    namesStyle(table) {
        const {width} = this.effectiveTableSize(table);
        const column = listWidth(this.state.payload.plan.show_full_names);
        return `left: ${width + SEAT_RING + CONNECTOR_WIDTH}px; top: 0px; width: ${column}px;`;
    }

    // The box the connector is drawn in: from the table's seat ring
    // across to the list, and as tall as the list itself, which is what
    // lets one rule embrace a list of two names and one of twenty.
    connectorStyle(table) {
        const {width} = this.effectiveTableSize(table);
        return `left: ${width + SEAT_RING}px; top: 0px; width: ${CONNECTOR_WIDTH}px; height: ${this.listHeight(
            table
        )}px;`;
    }

    // Where the straight trait crosses that box: the middle of the span
    // the table and the list actually SHARE, since both start at the
    // block's own top. That is what keeps the trait touching the table
    // on one side and the bracket on the other whichever of the two is
    // shorter — measuring from the table's own centre would leave it
    // hanging past the end of a two-name list.
    connectorTraitStyle(table) {
        const {height} = this.effectiveTableSize(table);
        return `top: ${Math.min(height, this.listHeight(table)) / 2}px;`;
    }

    /**
     * Sizes the scrolling pane (.o_event_table_floor, t-ref="floor") to the
     * room's footprint AT THE CURRENT ZOOM: a transform never changes the
     * space its own element reserves in layout, only how it paints (see the
     * comment on .o_event_table_room in the stylesheet), so the pane that
     * the surrounding flex chain and fitToWindow measure has to declare the
     * zoomed size itself rather than inheriting it from a transform below.
     * The grid background (o_event_table_grid) lives on this same element,
     * so its tiles are resized here too, in step with the zoom, to keep
     * matching the room's own 10 px snap grid (GRID_SIZE).
     */
    // The room's footprint at its NATIVE size, zoom excluded. Read by the
    // pane's declared size (floorStyle), by the room's own (roomStyle) and by
    // the fit, which all have to agree on one footprint: three copies of the
    // same five arguments is exactly how they would drift apart later.
    get roomSize() {
        return floorSize(
            this.state.payload.tables,
            80,
            this.state.payload.plan.visual_tables,
            this.state.payload.plan.assign_seats,
            this.state.payload.plan.show_company,
            this.state.payload.plan.show_full_names
        );
    }

    get floorStyle() {
        const size = this.roomSize;
        const zoom = this.state.zoom;
        const grid = GRID_SIZE * zoom;
        return (
            `width: ${size.width * zoom}px; height: ${size.height * zoom}px; ` + `background-size: ${grid}px ${grid}px;`
        );
    }

    /**
     * Lays out the room (.o_event_table_room) at its native, unzoomed size
     * and scales the whole thing with a transform. Tables keep native
     * coordinates regardless of zoom, which is what lets blockStyle and the
     * drag geometry (dropPosition) ignore the zoom for anything other than
     * the one division that undoes this transform.
     */
    get roomStyle() {
        const size = this.roomSize;
        return (
            `width: ${size.width}px; height: ${size.height}px; ` +
            `transform: scale(${this.state.zoom}); transform-origin: top left;`
        );
    }
}

/**
 * Embeds the floor plan as a form widget. `reloadKey` is `record.id`, not
 * `record.resId`: a `type="object"` button saves and then calls
 * `model.load()`, which rebuilds the root datapoint and changes its id, so
 * the reload follows; `record.load()` keeps the id, which is exactly what
 * keeps `onDataChanged` from looping.
 */
export class EventTableFloorPlanWidget extends Component {
    static template = "erplibre_event_table.EventTableFloorPlanWidget";
    static components = {EventTableFloorPlan};
    static props = {...standardWidgetProps};

    // Reloads the record after a move, unless it already carries unsaved
    // changes of its own: overwriting those would discard them silently.
    // isDirty() is asynchronous in Odoo 18 — skipping the await would hand
    // back a Promise, always truthy, and the record would never reload.
    onDataChanged = async () => {
        if (!(await this.props.record.isDirty())) {
            await this.props.record.load();
        }
    };
}
registry.category("view_widgets").add("event_table_floor_plan", {
    component: EventTableFloorPlanWidget,
});

export class EventTableFloorPlanAction extends Component {
    static template = "erplibre_event_table.EventTableFloorPlanAction";
    static components = {EventTableFloorPlan};
    static props = {...standardActionServiceProps};
}
registry.category("actions").add("erplibre_event_table.floor_plan", EventTableFloorPlanAction);
