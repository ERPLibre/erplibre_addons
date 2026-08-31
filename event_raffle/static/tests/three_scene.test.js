/** @odoo-module **/
import {
    computeTargetAngle,
    computeAbsoluteTarget,
    computeCanvasSize,
} from "@event_raffle/wheel/three_scene";
import { expect, test, describe } from "@odoo/hoot";

const TAU = Math.PI * 2;
const norm = (a) => ((a % TAU) + TAU) % TAU;

describe("computeTargetAngle", () => {
    test("adds full turns", () => {
        const a0 = computeTargetAngle(0, 4, 0);
        const a2 = computeTargetAngle(0, 4, 2);
        expect(Math.abs(a2 - a0 - 2 * TAU) < 1e-9).toBe(true);
    });

    test("places each segment under the top pointer", () => {
        const total = 6;
        const seg = TAU / total;
        for (let i = 0; i < total; i++) {
            const rot = computeTargetAngle(i, total, 3);
            // Mirrored texture: segment i center sits at mesh angle
            // -(i+0.5)*seg; after rotation it must reach the top pointer (π/2).
            const world = norm(-(i + 0.5) * seg + rot);
            const d = Math.abs(world - Math.PI / 2);
            expect(Math.min(d, TAU - d) < 1e-6).toBe(true);
        }
    });
});

describe("computeAbsoluteTarget", () => {
    test("lands correctly across accumulating spins", () => {
        const TAU = Math.PI * 2;
        const norm = (a) => ((a % TAU) + TAU) % TAU;
        let rot = 0;
        for (const [i, total, turns] of [[2, 5, 5], [0, 4, 5], [3, 7, 5], [1, 3, 0]]) {
            const target = computeAbsoluteTarget(rot, i, total, turns);
            const seg = TAU / total;
            // mirrored segment center must land under the top pointer (π/2)
            const landed = norm(-(i + 0.5) * seg + target);
            const d = Math.abs(landed - Math.PI / 2);
            expect(Math.min(d, TAU - d) < 1e-9).toBe(true);
            expect(target >= rot + turns * TAU - 1e-9).toBe(true);
            rot = target;
        }
    });
});

describe("computeCanvasSize", () => {
    const box = (o) => ({
        width: 1502, height: 545, viewportHeight: 757,
        devicePixelRatio: 1, maxTextureSize: 16384, ...o,
    });

    test("a canvas not laid out yet is skipped, not invented", () => {
        expect(computeCanvasSize(box({ width: 0, height: 0 }))).toBe(null);
        expect(computeCanvasSize(box({ height: 0 }))).toBe(null);
    });

    // The bug this module shipped with: _resize() writes the measured box into
    // the canvas width/height ATTRIBUTES, and in the embedded form view those
    // attributes were what sized the element. Any growth per call compounds.
    test("the buffer it asks for never exceeds the box it measured", () => {
        for (const dpr of [1, 1.25, 1.5, 2, 3]) {
            const s = computeCanvasSize(box({ devicePixelRatio: dpr }));
            expect(s.w).toBe(1502);
            expect(s.h).toBe(545);
            expect(s.pixelRatio <= 2).toBe(true);
        }
    });

    test("a height no one could look at is clamped and flagged", () => {
        // Small viewport: the 1200 px floor is the limit, so a short laptop
        // screen does not make the backstop trigger-happy.
        const laptop = computeCanvasSize(box({ height: 4000 }));
        expect(laptop.runaway).toBe(true);
        expect(laptop.h).toBe(1200);
        expect(laptop.measuredHeight).toBe(4000);
        // Tall screen: the viewport term takes over, so a legitimately tall
        // wheel on a portrait panel is still drawn at full size.
        const panel = computeCanvasSize(
            box({ viewportHeight: 2000, height: 3000 })
        );
        expect(panel.h).toBe(2400);
        expect(computeCanvasSize(box({ viewportHeight: 2000, height: 2000 }))
            .runaway).toBe(false);
        // A normal box is never flagged, at any viewport size.
        expect(computeCanvasSize(box()).runaway).toBe(false);
        expect(computeCanvasSize(box({ viewportHeight: 200 })).runaway)
            .toBe(false);
    });

    test("the pixel ratio keeps the buffer inside the GPU texture limit", () => {
        // Software WebGL reports 8192; a 3840 px wide canvas at dpr 2 would
        // ask for 7680 and, with the height, blow past it.
        const s = computeCanvasSize(
            box({ width: 3840, height: 1200, devicePixelRatio: 2,
                  maxTextureSize: 4096 })
        );
        expect(s.pixelRatio).toBe(4096 / 3840);
        expect(Math.floor(s.w * s.pixelRatio) <= 4096).toBe(true);
    });
});
