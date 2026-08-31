/** @odoo-module **/
import {
    computeTargetAngle,
    computeAbsoluteTarget,
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
