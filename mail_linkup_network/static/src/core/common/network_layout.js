/**
 * The geometry of the graph of the Network view (LU-F-070 RM3): a radial
 * layout computed in the client, in the units of the `viewBox` of its SVG.
 * The nodes come strongest first; the first one sits above the member and
 * the next ones follow clockwise.
 */

/** The `viewBox` of the graph, wide on a large screen, tall on a small one. */
export const LINKUP_GRAPH_SIZES = {
    wide: {width: 640, height: 480},
    narrow: {width: 360, height: 480},
};

/** The distance kept between a node and the edge of the graph. */
const MARGIN = 56;
/** Beyond this number of nodes, every other node sits on an inner ring. */
const ONE_RING_MAX = 12;
/** The radius of the inner ring, as a part of the outer one. */
const INNER_RING = 0.6;
/** The width of a line, from the weakest link to the strongest. */
const LINE_WIDTH = {min: 1.5, span: 6};

/**
 * The positions of `count` nodes around the centre of the graph, on an
 * ellipse that fills it; with more than `ONE_RING_MAX` nodes, the odd ones
 * sit on an inner ring, so that 50 nodes keep apart.
 *
 * @param {number} count
 * @param {{width: number, height: number}} size the `viewBox` of the graph
 * @returns {{x: number, y: number}[]}
 */
export function linkupRadialLayout(count, {width, height}) {
    const cx = width / 2;
    const cy = height / 2;
    const rx = Math.max(cx - MARGIN, 0);
    const ry = Math.max(cy - MARGIN, 0);
    const twoRings = count > ONE_RING_MAX;
    const positions = [];
    for (let index = 0; index < count; index++) {
        const angle = (index / count) * Math.PI * 2 - Math.PI / 2;
        const scale = twoRings && index % 2 ? INNER_RING : 1;
        positions.push({
            x: Math.round(cx + Math.cos(angle) * rx * scale),
            y: Math.round(cy + Math.sin(angle) * ry * scale),
        });
    }
    return positions;
}

/**
 * The strength of a link, from 0 to 1: its energy over the strongest one.
 * A negative energy counts as none.
 *
 * @param {number} energy
 * @param {number} max the energy of the strongest link
 * @returns {number}
 */
export function linkupStrength(energy, max) {
    if (!(max > 0) || !(energy > 0)) {
        return 0;
    }
    return Math.min(energy / max, 1);
}

/**
 * The width of the line of a link, in the units of the `viewBox`.
 *
 * @param {number} strength from 0 to 1
 * @returns {number}
 */
export function linkupLineWidth(strength) {
    return Math.round((LINE_WIDTH.min + strength * LINE_WIDTH.span) * 10) / 10;
}

/**
 * A point of the `viewBox` as a percentage of the graph, for the buttons
 * laid over the SVG.
 *
 * @param {{x: number, y: number}} point
 * @param {{width: number, height: number}} size
 * @returns {string} the inline style that places the button
 */
export function linkupPlace(point, {width, height}) {
    const left = Math.round((point.x / width) * 10000) / 100;
    const top = Math.round((point.y / height) * 10000) / 100;
    return `left: ${left}%; top: ${top}%;`;
}
