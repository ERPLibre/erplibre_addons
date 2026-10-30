# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Dessin du cachet d'une case de signature : cadre guilloché, emblème
sceau-plume, image de la signature et lignes de méta-données.

Tout se mesure en points PDF, origine en bas à gauche de la page.
``layout`` calcule la géométrie à partir de la case et du nombre de lignes,
sans rien dessiner : ``draw`` la suit, et le rectangle ``outer`` qu'elle rend
est aussi celui d'un champ de signature PAdES, qui coupe tout dessin hors de
lui.
"""

import math
from io import BytesIO

from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth

ERPLIBRE_COLORS = ("#280353", "#f15928")
TEXT_COLOR = "#2b2b2b"
TEXT_FONT = "Helvetica"
CODE_FONT = "Courier"
# Hauteur d'une ligne de texte, en multiple de la taille de police.
LINE_SPACING = 1.3
# Longueur d'onde visée du guilloché, en points ; ``_waves`` l'ajuste pour
# qu'un nombre entier d'ondes fasse le tour, ce qui ferme le tracé sans
# cassure.
WAVE_LENGTH = 9.0
WAVE_WIDTH = 0.4
# Pas d'échantillonnage du périmètre, en points.
WAVE_STEP = 0.25


def _clamp(value, low, high):
    return max(low, min(high, value))


def layout(x, y, width, height, line_count, frame, placement):
    """Rend la géométrie du cachet de la case ``(x, y, width, height)``.

    :param int line_count: nombre de lignes de méta-données
    :param bool frame: le cadre et l'emblème sont dessinés
    :param str placement: ``inside`` met les lignes dans une bande en bas
        de la case, et l'image rétrécit au-dessus ; ``below`` les met sous
        la case, et l'image garde la case
    :return: dict de rectangles ``(x, y, largeur, hauteur)`` et de mesures :

        * ``outer`` : contient tout le dessin ; c'est la case avec
          ``inside``, la case prolongée vers le bas avec ``below``
        * ``image`` : la zone où l'image tient, proportions gardées
        * ``font_size``, ``baselines`` (de la première ligne à la
          dernière), ``text_x``, ``text_width``
        * ``padding`` : la marge du cadre, où courent les ondes
        * ``emblem`` : ``(cx, cy, rayon)``, ou None sans cadre

    Avec ``inside``, la police rétrécit, jusqu'à 3 points, tant que la
    bande prend plus de 60 % de la hauteur utile : l'image garde au moins
    40 % de la case.
    """
    padding = _clamp(min(width, height) * 0.08, 3.0, 7.0) if frame else 0.5
    font_size = _clamp(height * 0.085, 4.5, 7.0)
    if placement == "inside" and line_count:
        room = (height - 2 * padding) * 0.6
        needed = line_count * LINE_SPACING + 0.4
        font_size = min(font_size, max(3.0, room / needed))
    line_height = font_size * LINE_SPACING
    gap = font_size * 0.4 if line_count else 0.0
    text_height = line_count * line_height
    if placement == "below" and line_count:
        extension = gap + text_height + padding
        outer = (x, y - extension, width, height + extension)
        image = (x + padding, y, width - 2 * padding, height - padding)
        text_top = y - gap
    else:
        outer = (x, y, width, height)
        text_top = y + padding + text_height
        image_bottom = text_top + gap
        image = (
            x + padding,
            image_bottom,
            width - 2 * padding,
            y + height - padding - image_bottom,
        )
    baselines = [
        text_top
        - (index + 1) * line_height
        + (line_height - font_size) / 2
        + font_size * 0.22
        for index in range(line_count)
    ]
    emblem = None
    if frame:
        radius = _clamp(min(width, height) * 0.12, 4.5, 11.0)
        outer_top = outer[1] + outer[3]
        emblem = (outer[0] + radius + 0.3, outer_top - radius - 0.3, radius)
    return {
        "outer": outer,
        "image": image,
        "font_size": font_size,
        "baselines": baselines,
        "text_x": x + padding + font_size * 0.3,
        "text_width": max(0.0, width - 2 * padding - font_size * 0.6),
        "padding": padding,
        "emblem": emblem,
    }


def _perimeter(x, y, width, height, radius):
    """Rend les points ``(s, px, py, nx, ny)`` du pourtour d'un rectangle
    aux coins arrondis de ``radius``, tous les ``WAVE_STEP`` points : ``s``
    est la distance parcourue depuis le coin bas-gauche, ``(nx, ny)`` la
    normale sortante. Le tour se fait dans le sens trigonométrique."""
    right, top = x + width, y + height
    pieces = [
        ("line", (x + radius, y), (right - radius, y), (0.0, -1.0)),
        ("arc", (right - radius, y + radius), -90.0),
        ("line", (right, y + radius), (right, top - radius), (1.0, 0.0)),
        ("arc", (right - radius, top - radius), 0.0),
        ("line", (right - radius, top), (x + radius, top), (0.0, 1.0)),
        ("arc", (x + radius, top - radius), 90.0),
        ("line", (x, top - radius), (x, y + radius), (-1.0, 0.0)),
        ("arc", (x + radius, y + radius), 180.0),
    ]
    points = []
    travelled = 0.0
    for piece in pieces:
        if piece[0] == "line":
            __, (x0, y0), (x1, y1), (nx, ny) = piece
            length = math.hypot(x1 - x0, y1 - y0)
            steps = max(1, int(length / WAVE_STEP))
            for step in range(steps):
                ratio = step / steps
                points.append(
                    (
                        travelled + length * ratio,
                        x0 + (x1 - x0) * ratio,
                        y0 + (y1 - y0) * ratio,
                        nx,
                        ny,
                    )
                )
        else:
            __, (cx, cy), start = piece
            length = math.pi * radius / 2
            steps = max(1, int(length / WAVE_STEP))
            for step in range(steps):
                angle = math.radians(start + 90.0 * step / steps)
                points.append(
                    (
                        travelled + length * step / steps,
                        cx + radius * math.cos(angle),
                        cy + radius * math.sin(angle),
                        math.cos(angle),
                        math.sin(angle),
                    )
                )
        travelled += length
    return points, travelled


def _waves(can, outer, padding, colors):
    """Dessine le guilloché dans la marge de ``outer`` : deux ondes de
    phases opposées, une par couleur, qui se croisent à chaque
    demi-période, et un filet fin à l'intérieur."""
    inset = padding / 2
    x, y, width, height = outer
    radius = min(padding * 1.2, width / 4, height / 4)
    points, length = _perimeter(
        x + inset, y + inset, width - 2 * inset, height - 2 * inset, radius
    )
    amplitude = padding * 0.3
    periods = max(4, round(length / WAVE_LENGTH))
    can.saveState()
    can.setLineWidth(WAVE_WIDTH)
    can.setLineJoin(1)
    for color, phase in zip(colors, (0.0, math.pi), strict=True):
        path = can.beginPath()
        for index, (s, px, py, nx, ny) in enumerate(points):
            offset = amplitude * math.sin(
                2 * math.pi * periods * s / length + phase
            )
            point = (px + nx * offset, py + ny * offset)
            if index:
                path.lineTo(*point)
            else:
                path.moveTo(*point)
        path.close()
        can.setStrokeColor(HexColor(color))
        can.drawPath(path, stroke=1, fill=0)
    hairline = inset + amplitude + 0.9
    can.setLineWidth(0.3)
    can.setStrokeColor(HexColor(colors[0]))
    can.roundRect(
        x + hairline,
        y + hairline,
        width - 2 * hairline,
        height - 2 * hairline,
        max(0.0, radius - (hairline - inset)),
        stroke=1,
        fill=0,
    )
    can.restoreState()


def _emblem(can, cx, cy, radius, colors):
    """Dessine le sceau-plume centré en ``(cx, cy)`` : un disque de la
    première couleur, un anneau blanc, une plume de la seconde couleur
    pointée vers le bas à gauche, et un paraphe blanc qui part de sa
    pointe. Un halo blanc efface d'abord les ondes sous le disque."""
    can.saveState()
    can.setFillColor(white)
    can.circle(cx, cy, radius * 1.18, stroke=0, fill=1)
    can.setFillColor(HexColor(colors[0]))
    can.circle(cx, cy, radius, stroke=0, fill=1)
    can.setStrokeColor(white)
    can.setLineWidth(radius * 0.05)
    can.circle(cx, cy, radius * 0.84, stroke=1, fill=0)

    can.saveState()
    can.translate(cx + radius * 0.08, cy + radius * 0.1)
    can.rotate(-45)
    can.scale(radius, radius)
    nib = can.beginPath()
    nib.moveTo(-0.2, 0.5)
    nib.lineTo(0.2, 0.5)
    nib.lineTo(0.2, 0.2)
    nib.curveTo(0.2, -0.05, 0.06, -0.3, 0.0, -0.62)
    nib.curveTo(-0.06, -0.3, -0.2, -0.05, -0.2, 0.2)
    nib.close()
    can.setFillColor(HexColor(colors[1]))
    can.drawPath(nib, stroke=0, fill=1)
    can.setStrokeColor(white)
    can.setLineWidth(0.05)
    can.line(0.0, -0.55, 0.0, -0.02)
    can.setFillColor(white)
    can.circle(0.0, 0.06, 0.07, stroke=0, fill=1)
    can.restoreState()

    # La pointe de la plume, après la rotation : (-0.36, -0.34) × rayon.
    flourish = can.beginPath()
    flourish.moveTo(cx - radius * 0.36, cy - radius * 0.34)
    flourish.curveTo(
        cx - radius * 0.15,
        cy - radius * 0.62,
        cx + radius * 0.12,
        cy - radius * 0.18,
        cx + radius * 0.3,
        cy - radius * 0.45,
    )
    flourish.curveTo(
        cx + radius * 0.4,
        cy - radius * 0.58,
        cx + radius * 0.52,
        cy - radius * 0.42,
        cx + radius * 0.6,
        cy - radius * 0.36,
    )
    can.setStrokeColor(white)
    can.setLineWidth(radius * 0.06)
    can.setLineCap(1)
    can.drawPath(flourish, stroke=1, fill=0)
    can.restoreState()


def _fit(text, font, size, width):
    """Rend ``text`` coupé, avec « … », pour tenir dans ``width`` points."""
    if stringWidth(text, font, size) <= width:
        return text
    while text and stringWidth(text + "…", font, size) > width:
        text = text[:-1]
    return text + "…" if text else ""


def draw(can, geometry, image_data, lines, colors, frame):
    """Dessine le cachet sur ``can`` selon ``geometry``, que rend ``layout``.

    :param bytes image_data: l'image de la signature, que reportlab lit ;
        elle garde ses proportions, centrée dans ``geometry["image"]``, et
        sa transparence
    :param list lines: ``(texte, monospace)`` de haut en bas ; un texte
        trop long est coupé à la largeur de la case
    :param tuple colors: deux couleurs ``#rrggbb`` : la première pour
        l'onde, le filet et le disque, la seconde pour l'autre onde et la
        plume
    :param bool frame: dessine le guilloché et l'emblème

    L'image est posée après l'emblème : l'encre de la signature n'est
    jamais cachée.
    """
    if frame:
        _waves(can, geometry["outer"], geometry["padding"], colors)
        _emblem(can, *geometry["emblem"], colors)
    x, y, width, height = geometry["image"]
    if width > 0 and height > 0:
        can.drawImage(
            ImageReader(BytesIO(image_data)),
            x,
            y,
            width,
            height,
            mask="auto",
            preserveAspectRatio=True,
            anchor="c",
        )
    size = geometry["font_size"]
    can.setFillColor(HexColor(TEXT_COLOR))
    for (text, monospace), baseline in zip(
        lines, geometry["baselines"], strict=True
    ):
        font = CODE_FONT if monospace else TEXT_FONT
        can.setFont(font, size)
        can.drawString(
            geometry["text_x"],
            baseline,
            _fit(text, font, size, geometry["text_width"]),
        )
