/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {browser} from "@web/core/browser/browser";

// How far, in pixels, the pointer moves with its button down before a
// press becomes a drag: a shorter move stays a click.
export const DRAG_THRESHOLD = 4;
// The band, in pixels, at the top and at the bottom of the canvas where a
// drag scrolls it, and the most it scrolls in one frame, at the very edge.
export const EDGE = 60;
export const EDGE_SPEED = 24;
// What a press on a drag source leaves to its own default: a field to type
// in, the insertion list of a « + ».
const IGNORED = "input, textarea, select, [contenteditable=''], [contenteditable=true], .o_erplibre_studio_insert_list";

/**
 * The drag of the editor, carried by pointer events instead of the HTML5
 * drag and drop. No drag session of the browser runs, so the mouse wheel
 * scrolls the canvas while an item moves, in every browser: during a
 * native drag session, Chrome under Linux takes no wheel event and
 * scrolls nothing.
 *
 * ``press`` (a pointerdown on a palette item, a block of the canvas or a
 * row of the plan) arms it; the drag starts once the pointer moves
 * DRAG_THRESHOLD pixels, so a click stays a click. While it runs, the
 * element under the pointer receives the dragenter, dragover, dragleave
 * and drop events the hooks and the drop scopes of the canvas take, as a
 * native drag sends them, without a dataTransfer: the drop slot keeps its
 * rules (the innermost scope under the pointer, its hook nearest to the
 * pointer), and only a dragover a handler prevents lets the release drop.
 *
 * A real pointer event is hit-tested (``elementFromPoint``): Firefox may
 * hand the moves of a pressed button to the element pressed. A synthetic
 * one carries no real pointer, so its own target stands.
 *
 * A scroll of the canvas, by the wheel or by the edge (EDGE, faster nearer
 * the border), sends a dragover again at the pointer: the slot follows the
 * content that moves under it. Escape, a pointercancel or the window
 * losing the focus cancel the drag; the click the browser fires after the
 * release reaches nothing. A ghost, the glyph and the name of the item,
 * follows the pointer.
 */
export class PointerDrag {
    /**
     * ``start(item)`` begins the drag of ``item`` in the editor and says
     * whether it runs; ``end()`` ends it; ``scroller()`` gives the element
     * the edge scrolls, or null; ``host()`` the element that holds the
     * ghost (else the body); ``ghost()`` gives what the ghost shows,
     * {glyph, label}, or null.
     */
    constructor({start, end, scroller, host, ghost}) {
        Object.assign(this, {start, end, scroller, host, ghost});
        // The press or the drag in progress: {event, item, x0, y0, x, y,
        // started, over, accepted, ghostEl}; null for none.
        this.current = null;
        this.frame = null;
        this.listeners = [
            ["pointermove", (ev) => this.onMove(ev), true],
            ["pointerup", (ev) => this.onUp(ev), true],
            ["pointercancel", () => this.cancel(), true],
            ["keydown", (ev) => this.onKeydown(ev), true],
            ["scroll", () => this.route(), true],
            ["selectstart", (ev) => ev.preventDefault(), true],
            ["dragstart", (ev) => ev.preventDefault(), true],
            ["blur", (ev) => ev.target === window && this.cancel(), false],
        ];
        this.clickGuard = [
            ["click", (ev) => this.eatClick(ev), true],
            ["pointerdown", () => this.unguard(), true],
            ["keydown", () => this.unguard(), true],
        ];
        this.guarded = false;
    }

    /** Whether a drag runs (past the threshold). */
    get dragging() {
        return Boolean(this.current && this.current.started);
    }

    /**
     * A pointerdown on the source of ``item``: arm the drag. The left
     * button of a mouse or of a pen only; a touch keeps scrolling the page.
     * The handlers of nested sources hear the same event: the innermost
     * one arms, the others find it armed.
     */
    press(ev, item) {
        if (this.current && this.current.event === ev) {
            return;
        }
        if (ev.button !== 0 || ev.pointerType === "touch" || (ev.target.closest && ev.target.closest(IGNORED))) {
            return;
        }
        this.stop();
        this.current = {
            event: ev,
            item,
            x0: ev.clientX,
            y0: ev.clientY,
            x: ev.clientX,
            y: ev.clientY,
            started: false,
            over: null,
            accepted: false,
            ghostEl: null,
        };
        for (const [type, listener, capture] of this.listeners) {
            browser.addEventListener(type, listener, capture);
        }
    }

    onMove(ev) {
        const drag = this.current;
        if (!drag) {
            return;
        }
        drag.x = ev.clientX;
        drag.y = ev.clientY;
        if (!drag.started && !this.begin()) {
            return;
        }
        this.placeGhost();
        this.route(ev.isTrusted ? null : ev.target);
        this.edgeScroll();
    }

    /**
     * Start the drag once the pointer is DRAG_THRESHOLD pixels away from
     * the press; false while it is nearer, or when the editor refuses it.
     */
    begin() {
        const drag = this.current;
        if (Math.hypot(drag.x - drag.x0, drag.y - drag.y0) < DRAG_THRESHOLD) {
            return false;
        }
        if (!this.start(drag.item)) {
            this.stop();
            return false;
        }
        drag.started = true;
        const selection = document.getSelection();
        if (selection) {
            selection.removeAllRanges();
        }
        drag.ghostEl = this.makeGhost();
        return true;
    }

    /**
     * Send the drag events to the element under the pointer: a dragleave
     * to the element it leaves and a dragenter to the one it enters, then
     * a dragover. ``target`` names that element; else the pointer
     * position finds it.
     */
    route(target = null) {
        const drag = this.current;
        if (!drag || !drag.started) {
            return;
        }
        const el = target || document.elementFromPoint(drag.x, drag.y);
        if (el !== drag.over) {
            const previous = drag.over;
            drag.over = el;
            if (previous && previous.isConnected) {
                this.send(previous, "dragleave", el);
            }
            if (el) {
                this.send(el, "dragenter", previous);
            }
        }
        if (this.current === drag) {
            drag.accepted = Boolean(el) && this.send(el, "dragover");
        }
    }

    /** Dispatch the drag event ``type`` on ``el``; true when a handler prevents it. */
    send(el, type, relatedTarget = null) {
        const drag = this.current;
        const EventClass = window.DragEvent || window.MouseEvent;
        const event = new EventClass(type, {
            bubbles: true,
            cancelable: true,
            composed: true,
            clientX: drag ? drag.x : 0,
            clientY: drag ? drag.y : 0,
            relatedTarget,
        });
        return !el.dispatchEvent(event);
    }

    /** The release: a drop where the last dragover was taken, then the end of the drag. */
    onUp(ev) {
        const drag = this.current;
        if (!drag) {
            return;
        }
        if (!drag.started) {
            this.stop();
            return;
        }
        drag.x = ev.clientX;
        drag.y = ev.clientY;
        this.route(ev.isTrusted ? null : ev.target);
        if (this.current === drag && drag.accepted && drag.over) {
            this.send(drag.over, "drop");
        }
        this.end();
        this.stop();
    }

    /** Escape cancels a drag; it goes no further. */
    onKeydown(ev) {
        if (ev.key !== "Escape") {
            return;
        }
        if (this.dragging) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        this.cancel();
    }

    /** Cancel the press or the drag: nothing drops. */
    cancel() {
        if (this.dragging) {
            this.end();
        }
        this.stop();
    }

    /**
     * Forget the press or the drag: its listeners, its ghost, its edge
     * scroll. A drag that ran guards against the click that follows its
     * release. Calling it again does nothing.
     */
    stop() {
        const drag = this.current;
        if (!drag) {
            return;
        }
        this.current = null;
        for (const [type, listener, capture] of this.listeners) {
            browser.removeEventListener(type, listener, capture);
        }
        if (this.frame) {
            browser.cancelAnimationFrame(this.frame);
            this.frame = null;
        }
        if (drag.ghostEl) {
            drag.ghostEl.remove();
        }
        if (drag.started) {
            this.guard();
        }
    }

    // ── the click after a drag ──────────────────────────────────────────

    /**
     * The release of a drag fires a click on the element that holds both
     * the source and the place of the drop, which would select it: the
     * next click goes nowhere, unless a pointerdown or a key comes first.
     */
    guard() {
        if (this.guarded) {
            return;
        }
        this.guarded = true;
        for (const [type, listener, capture] of this.clickGuard) {
            browser.addEventListener(type, listener, capture);
        }
    }

    unguard() {
        if (!this.guarded) {
            return;
        }
        this.guarded = false;
        for (const [type, listener, capture] of this.clickGuard) {
            browser.removeEventListener(type, listener, capture);
        }
    }

    eatClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.unguard();
    }

    // ── the scroll at the edge ──────────────────────────────────────────

    /**
     * How many pixels the canvas scrolls in a frame for the pointer where
     * it is: negative in the top band, positive in the bottom band, more
     * the nearer the border; 0 elsewhere.
     */
    edgeSpeed() {
        const drag = this.current;
        const el = this.scroller();
        if (!drag || !drag.started || !el) {
            return 0;
        }
        const rect = el.getBoundingClientRect();
        if (drag.x < rect.left || drag.x > rect.right) {
            return 0;
        }
        const top = drag.y - rect.top;
        const bottom = rect.bottom - drag.y;
        if (top >= 0 && top < EDGE) {
            return -Math.ceil((EDGE_SPEED * (EDGE - top)) / EDGE);
        }
        if (bottom >= 0 && bottom < EDGE) {
            return Math.ceil((EDGE_SPEED * (EDGE - bottom)) / EDGE);
        }
        return 0;
    }

    /** Scroll a frame from now while the pointer stays in a band of the edge. */
    edgeScroll() {
        if (!this.frame && this.edgeSpeed()) {
            this.frame = browser.requestAnimationFrame(() => this.edgeStep());
        }
    }

    /**
     * Scroll the canvas by ``edgeSpeed`` and place the drop again; the
     * next frame follows while the canvas moves. Once it reaches its end,
     * the next pointermove starts it again.
     */
    edgeStep() {
        this.frame = null;
        const speed = this.edgeSpeed();
        const el = this.scroller();
        if (!speed || !el) {
            return;
        }
        const before = el.scrollTop;
        el.scrollTop = before + speed;
        if (el.scrollTop === before) {
            return;
        }
        this.route();
        if (this.current) {
            this.frame = browser.requestAnimationFrame(() => this.edgeStep());
        }
    }

    // ── the ghost ───────────────────────────────────────────────────────

    /** The ghost under the pointer, hidden from assistive technology. */
    makeGhost() {
        const item = this.ghost();
        const el = document.createElement("div");
        el.className = "o_erplibre_studio_drag_ghost";
        el.setAttribute("aria-hidden", "true");
        if (item) {
            const glyph = document.createElement("span");
            glyph.className = "o_erplibre_studio_drag_ghost_glyph";
            glyph.textContent = item.glyph;
            const label = document.createElement("span");
            label.className = "o_erplibre_studio_drag_ghost_label";
            label.textContent = item.label;
            el.append(glyph, label);
        }
        (this.host() || document.body).appendChild(el);
        return el;
    }

    /** Move the ghost below and right of the pointer, out of its way. */
    placeGhost() {
        const drag = this.current;
        if (drag && drag.ghostEl) {
            drag.ghostEl.style.transform = `translate(${drag.x + 12}px, ${drag.y + 12}px)`;
        }
    }
}
