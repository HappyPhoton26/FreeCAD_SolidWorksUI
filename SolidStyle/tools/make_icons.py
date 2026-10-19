#!/usr/bin/env python3
"""Generates SolidStyle's SolidWorks-flavoured icon set (original artwork) into
solidstyle/icons/sw/<FreeCADCommand>.svg.   Run:  python3 tools/make_icons.py

Visual language: features are yellow, the existing part is light grey, sketch
geometry is dark lines with blue points, relations are green badges, directions
and reference geometry are blue."""
import math
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "solidstyle", "icons", "sw")

YEL = ("#ffe066", "#f5b800", "#cc8f00")
GRY = ("#eceef1", "#c3c8cf", "#9aa1ab")
BLU = "#2a6fdb"
LBL = "#9cc3f5"
INK = "#333"
RED = "#d62f2f"
GRN = "#2f9e4f"
SW = 1.6  # outline width


def svg(body):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
            + body + "</svg>\n")


def pts(p):
    return " ".join("%.1f,%.1f" % q for q in p)


def poly(p, fill, stroke=INK, w=SW, extra=""):
    return '<polygon points="%s" fill="%s" stroke="%s" stroke-width="%s" stroke-linejoin="round" %s/>' % (
        pts(p), fill, stroke, w, extra)


def line(a, b, col=INK, w=2.5, extra=""):
    return '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%s" stroke-linecap="round" %s/>' % (
        a[0], a[1], b[0], b[1], col, w, extra)


def path(d, fill="none", col=INK, w=2.5, extra=""):
    return '<path d="%s" fill="%s" stroke="%s" stroke-width="%s" stroke-linecap="round" stroke-linejoin="round" %s/>' % (
        d, fill, col, w, extra)


def circle(c, r, fill="none", col=INK, w=2.5, extra=""):
    return '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" stroke="%s" stroke-width="%s" %s/>' % (
        c[0], c[1], r, fill, col, w, extra)


def ellipse(c, rx, ry, fill="none", col=INK, w=2, extra=""):
    return '<ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="%s" stroke="%s" stroke-width="%s" %s/>' % (
        c[0], c[1], rx, ry, fill, col, w, extra)


def dot(c, r=3.2, col=BLU):
    return circle(c, r, col, "#fff", 1)


def text(x, y, s, size=14, col=INK, weight="bold", anchor="middle"):
    return ('<text x="%.1f" y="%.1f" font-family="DejaVu Sans,Arial,sans-serif" font-size="%s" font-weight="%s" '
            'fill="%s" text-anchor="%s">%s</text>') % (x, y, size, weight, col, anchor, s)


def arrow(a, b, col=BLU, w=3.5, head=7):
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    l = (b[0] - head * math.cos(ang), b[1] - head * math.sin(ang))
    p1 = (b[0] - head * math.cos(ang - 0.45) * 1.15, b[1] - head * math.sin(ang - 0.45) * 1.15)
    p2 = (b[0] - head * math.cos(ang + 0.45) * 1.15, b[1] - head * math.sin(ang + 0.45) * 1.15)
    return line(a, l, col, w) + poly([b, p1, p2], col, col, 1)


# ---------------------------------------------------------------- isometric helpers
OX, OY, K = 32.0, 36.0, 1.0


def iso(x, y, z, ox=OX, oy=OY, k=K):
    c = math.cos(math.radians(30))
    return (ox + (x - y) * c * k, oy + ((x + y) * 0.5 - z) * k)


def block(x, y, z, dx, dy, dz, pal=GRY, **kw):
    P = lambda a, b, c: iso(a, b, c, **kw)
    top = [P(x, y, z + dz), P(x + dx, y, z + dz), P(x + dx, y + dy, z + dz), P(x, y + dy, z + dz)]
    left = [P(x, y + dy, z), P(x + dx, y + dy, z), P(x + dx, y + dy, z + dz), P(x, y + dy, z + dz)]
    right = [P(x + dx, y, z), P(x + dx, y + dy, z), P(x + dx, y + dy, z + dz), P(x + dx, y, z + dz)]
    return poly(left, pal[1]) + poly(right, pal[2]) + poly(top, pal[0])


def flat(x, y, z, dx, dy, fill, stroke=INK, w=SW, extra="", **kw):
    P = lambda a, b, c: iso(a, b, c, **kw)
    return poly([P(x, y, z), P(x + dx, y, z), P(x + dx, y + dy, z), P(x, y + dy, z)], fill, stroke, w, extra)


def cube_view(face):
    """Standard-view icon: a grey cube with one blue face."""
    kw = dict(ox=32, oy=34, k=1.0)
    s = 24
    P = lambda a, b, c: iso(a, b, c, **kw)
    x = y = -s / 2
    z = -s / 2
    faces = {
        "top": [P(x, y, z + s), P(x + s, y, z + s), P(x + s, y + s, z + s), P(x, y + s, z + s)],
        "front": [P(x, y + s, z), P(x + s, y + s, z), P(x + s, y + s, z + s), P(x, y + s, z + s)],
        "right": [P(x + s, y, z), P(x + s, y + s, z), P(x + s, y + s, z + s), P(x + s, y, z + s)],
    }
    out = ""
    for name in ("front", "right", "top"):
        col = {"top": GRY[0], "front": GRY[1], "right": GRY[2]}[name]
        if name == face or face == "iso":
            col = LBL if face != "iso" else col
        out += poly(faces[name], col)
    if face in ("back", "left", "bottom"):
        # hidden face: show it dashed
        hid = {"back": [P(x, y, z), P(x + s, y, z), P(x + s, y, z + s), P(x, y, z + s)],
               "left": [P(x, y, z), P(x, y + s, z), P(x, y + s, z + s), P(x, y, z + s)],
               "bottom": [P(x, y, z), P(x + s, y, z), P(x + s, y + s, z), P(x, y + s, z)]}[face]
        out += poly(hid, LBL, BLU, 2, 'fill-opacity="0.75" stroke-dasharray="3,2"')
    if face == "iso":
        out += path("M%.1f %.1f L%.1f %.1f" % (*P(x + s, y + s, z + s), *P(x + s, y + s, z)), col=BLU, w=2.5)
    return out


# ---------------------------------------------------------------- feature icons

def extrude_boss():
    return (flat(-14, -14, -8, 28, 28, LBL, BLU, 2, 'fill-opacity="0.5" stroke-dasharray="4,2"')
            + block(-9, -9, -8, 18, 18, 20, YEL) + arrow((52, 44), (52, 10)))


def extrude_cut():
    kw = {}
    return (block(-14, -14, -12, 28, 28, 14, GRY)
            + flat(-6, -6, 2, 12, 12, "#6b5200", INK, 1.2)
            + poly([iso(-6, 6, 2), iso(6, 6, 2), iso(6, 6, -4), iso(-6, 6, -4)], YEL[1], INK, 1)
            + poly([iso(6, -6, 2), iso(6, 6, 2), iso(6, 6, -4), iso(6, -6, -4)], YEL[0], INK, 1)
            + flat(-6, -6, 2, 12, 12, "none", INK, 1.6)
            + arrow((52, 6), (52, 34)))


def revolve_boss():
    return (line((32, 4), (32, 60), BLU, 2, 'stroke-dasharray="6,3"')
            + path("M18 18 C18 10 46 10 46 18 L46 44 C46 52 18 52 18 44 Z", YEL[1], INK, SW)
            + ellipse((32, 18), 14, 5, YEL[0], INK, SW)
            + path("M8 30 A24 9 0 0 0 56 30", col=BLU, w=3) + poly([(56, 30), (50, 25), (52, 33)], BLU, BLU, 1))


def revolve_cut():
    return (line((32, 4), (32, 60), BLU, 2, 'stroke-dasharray="6,3"')
            + path("M16 16 C16 8 48 8 48 16 L48 46 C48 54 16 54 16 46 Z", GRY[1], INK, SW)
            + ellipse((32, 16), 16, 6, GRY[0], INK, SW)
            + path("M16 28 C16 34 48 34 48 28 L44 36 C44 40 20 40 20 36 Z", YEL[1], INK, 1.2))


def swept(cut=False):
    base = block(-14, -14, -14, 28, 28, 10, GRY) if cut else ""
    col = YEL[1]
    return (base + path("M10 52 C10 30 30 40 34 24 S50 8 56 10", col=INK, w=12)
            + path("M10 52 C10 30 30 40 34 24 S50 8 56 10", col=col, w=9)
            + ellipse((10, 52), 7, 4, YEL[0], INK, 1.5)
            + path("M10 52 C10 30 30 40 34 24 S50 8 56 10", col=BLU, w=1.5, extra='stroke-dasharray="3,3"'))


def lofted(cut=False):
    base = block(-16, -16, -16, 32, 32, 8, GRY) if cut else ""
    b = [iso(-13, -13, -10), iso(13, -13, -10), iso(13, 13, -10), iso(-13, 13, -10)]
    t = [iso(-5, -5, 12), iso(5, -5, 12), iso(5, 5, 12), iso(-5, 5, 12)]
    return (base + poly([b[3], b[2], t[2], t[3]], YEL[1]) + poly([b[1], b[2], t[2], t[1]], YEL[2])
            + poly(t, YEL[0]) + poly(b, "none", BLU, 2, 'stroke-dasharray="3,2"'))


def helix(cut=False):
    base = block(-14, -14, -16, 28, 28, 8, GRY) if cut else ""
    d = "M18 50 " + " ".join("C46 %d 46 %d 18 %d" % (y + 2, y - 8, y - 10) for y in (50, 40, 30, 20))
    return base + path(d, col=INK, w=8) + path(d, col=YEL[1], w=5) + line((32, 4), (32, 60), BLU, 1.5, 'stroke-dasharray="4,3"')


def hole():
    return (block(-15, -15, -12, 30, 30, 14, GRY)
            + ellipse(iso(0, 0, 2), 11, 6.3, "#5a4600", INK, 1.6)
            + ellipse(iso(0, 0, 2), 6, 3.5, "#2a2000", INK, 1.2)
            + path("M%.1f %.1f L%.1f %.1f" % (iso(0, 0, 2)[0] - 6, iso(0, 0, 2)[1], iso(0, 0, 2)[0] - 6, iso(0, 0, 2)[1] + 10), col=YEL[1], w=2)
            + arrow((50, 6), (50, 26), BLU, 3))


def _edge_block(kind):
    """Grey block whose top/right edge is filleted or chamfered (yellow)."""
    P = iso
    if kind == "fillet":
        prof = lambda y: "L%.1f %.1f Q%.1f %.1f %.1f %.1f" % (*P(6, y, 10), *P(14, y, 10), *P(14, y, 2))
    else:
        prof = lambda y: "L%.1f %.1f L%.1f %.1f" % (*P(6, y, 10), *P(14, y, 2))
    front = "M%.1f %.1f L%.1f %.1f %s L%.1f %.1f Z" % (*P(-14, 14, -14), *P(-14, 14, 10), prof(14), *P(14, 14, -14))
    right = poly([P(14, -14, -14), P(14, 14, -14), P(14, 14, 2), P(14, -14, 2)], GRY[2])
    top = poly([P(-14, -14, 10), P(6, -14, 10), P(6, 14, 10), P(-14, 14, 10)], GRY[0])
    # the blend surface: between the profile at y=-14 and at y=14
    if kind == "fillet":
        band = "M%.1f %.1f Q%.1f %.1f %.1f %.1f L%.1f %.1f Q%.1f %.1f %.1f %.1f Z" % (
            *P(6, -14, 10), *P(14, -14, 10), *P(14, -14, 2), *P(14, 14, 2), *P(14, 14, 10), *P(6, 14, 10))
    else:
        band = "M%.1f %.1f L%.1f %.1f L%.1f %.1f L%.1f %.1f Z" % (
            *P(6, -14, 10), *P(14, -14, 2), *P(14, 14, 2), *P(6, 14, 10))
    return right + top + path(band, YEL[1], INK, SW) + path(front, GRY[1], INK, SW)


def fillet():
    return _edge_block("fillet")


def chamfer():
    return _edge_block("chamfer")


def shell():
    return (block(-15, -15, -14, 30, 30, 22, GRY)
            + flat(-11, -11, 8, 22, 22, YEL[2], INK, 1.2)
            + poly([iso(-11, -11, 8), iso(-11, 11, 8), iso(-11, 11, -10), iso(-11, -11, -10)], YEL[1], INK, 1)
            + poly([iso(-11, -11, 8), iso(11, -11, 8), iso(11, -11, -10), iso(-11, -11, -10)], YEL[0], INK, 1)
            + flat(-11, -11, 8, 22, 22, "none", INK, 1.6))


def draft():
    P = iso
    return (poly([P(-14, 14, -14), P(14, 14, -14), P(8, 8, 10), P(-8, 8, 10)], YEL[1])
            + poly([P(14, -14, -14), P(14, 14, -14), P(8, 8, 10), P(8, -8, 10)], GRY[2])
            + poly([P(-8, -8, 10), P(8, -8, 10), P(8, 8, 10), P(-8, 8, 10)], GRY[0])
            + line((50, 50), (58, 18), BLU, 2, 'stroke-dasharray="4,3"'))


def linear_pattern():
    out = block(-18, -18, -18, 36, 36, 4, GRY)
    for i in range(3):
        out += block(-14 + i * 11, -6, -14, 7, 7, 9, YEL if i == 0 else ("#fff2b3", "#f3d36b", "#d9b04a"))
    return out + arrow((10, 52), (54, 30), BLU, 2.5, 6)


def circular_pattern():
    out = ellipse((32, 36), 22, 13, "none", BLU, 2, 'stroke-dasharray="4,3"')
    for i in range(6):
        a = math.radians(i * 60 + 15)
        c = (32 + 22 * math.cos(a), 36 + 13 * math.sin(a))
        out += circle(c, 5.5, YEL[1] if i == 0 else "#f3d36b", INK, 1.5)
    return out + circle((32, 36), 2.5, BLU, BLU, 1)


def mirror():
    return (poly([(30, 6), (36, 2), (36, 56), (30, 62)], LBL, BLU, 1.5, 'fill-opacity="0.8"')
            + poly([(6, 22), (24, 16), (24, 42), (6, 48)], YEL[1])
            + poly([(58, 22), (42, 16), (42, 42), (58, 48)], "#f3d36b", INK, SW, 'stroke-dasharray="3,2"'))


def multi_pattern():
    out = ""
    for i in range(2):
        for j in range(2):
            out += block(-14 + i * 14, -14 + j * 14, -8, 9, 9, 9, YEL if i == j == 0 else ("#fff2b3", "#f3d36b", "#d9b04a"))
    return out


def scale_icon():
    return block(-14, -14, -14, 12, 12, 12, ("#fff2b3", "#f3d36b", "#d9b04a")) + block(-2, -2, -6, 18, 18, 18, YEL) + arrow((14, 50), (4, 58), BLU, 2.5, 5)


def plane():
    return (poly([(6, 40), (26, 14), (58, 22), (38, 50)], "#bcd6f7", BLU, 2.2, 'fill-opacity="0.85"')
            + poly([(10, 39), (27, 17)], "none", "#fff", 1))


def axis():
    return line((10, 54), (54, 10), BLU, 3, 'stroke-dasharray="9,4,2,4"') + circle((32, 32), 3, BLU, BLU, 1)


def point():
    return (line((32, 14), (32, 50), BLU, 2) + line((14, 32), (50, 32), BLU, 2)
            + circle((32, 32), 6, YEL[1], INK, 2))


def coord_sys():
    o = (24, 40)
    return (arrow(o, (56, 40), RED, 3.5) + arrow(o, (24, 6), GRN, 3.5) + arrow(o, (6, 58), BLU, 3.5)
            + circle(o, 3, INK, INK, 1))


def rollback():
    return (line((6, 34), (58, 34), BLU, 5) + line((6, 34), (58, 34), YEL[1], 2)
            + arrow((40, 20), (22, 20), INK, 2.5, 5) + text(32, 56, "", 10))


def new_body():
    return block(-12, -12, -12, 24, 24, 24, GRY) + circle((50, 14), 10, GRN, "#fff", 2) + text(50, 19, "+", 16, "#fff")


def combine():
    return block(-16, -10, -12, 18, 18, 18, GRY) + block(-4, -2, -12, 18, 18, 18, YEL)


def rebuild():
    return (path("M50 32 A18 18 0 1 1 40 16", col=GRN, w=6) + poly([(32, 6), (50, 12), (38, 24)], GRN, GRN, 1)
            + poly([(26, 26), (38, 26), (38, 38), (26, 38)], YEL[1]))


# ---------------------------------------------------------------- sketch icons
def sk_sketch():
    out = poly([(4, 46), (22, 18), (60, 24), (42, 54)], "#f4f7fb", INK, 1.6)
    for t in (0.25, 0.5, 0.75):
        a = (4 + 18 * t, 46 - 28 * t); b = (42 + 18 * t, 54 - 30 * t)
        out += line(a, b, "#a9bcd6", 1)
    out += path("M18 40 L36 28 L46 40 Z", col=BLU, w=2.2)
    out += poly([(40, 4), (48, 10), (34, 30), (28, 32), (30, 26)], YEL[1], INK, 1.4)
    return out


def sk_exit():
    return sk_sketch() + circle((50, 48), 12, "#fff", GRN, 2) + path("M44 48 L49 53 L57 42", col=GRN, w=3.5)


def dimension(label="", angled=False):
    out = line((10, 20), (10, 52), INK, 1.6) + line((54, 20), (54, 52), INK, 1.6)
    out += arrow((32, 30), (11, 30), INK, 2, 6) + arrow((32, 30), (53, 30), INK, 2, 6)
    out += poly([(32, 40), (38, 46), (32, 52), (26, 46)], YEL[1], INK, 1.5)
    if label:
        out += text(32, 22, label, 12, BLU)
    return out


def smart_dim():
    return (line((10, 54), (46, 18), INK, 2.5) + dot((10, 54)) + dot((46, 18))
            + arrow((32, 50), (54, 28), BLU, 2, 5) + arrow((44, 38), (22, 60), BLU, 2, 0.1)
            + poly([(50, 44), (56, 50), (50, 56), (44, 50)], YEL[1], INK, 1.4)
            + text(20, 18, "D", 14, BLU))


def sk_line():
    return line((10, 52), (54, 12)) + dot((10, 52)) + dot((54, 12))


def sk_polyline():
    p = [(8, 50), (22, 18), (40, 42), (56, 12)]
    return path("M" + " L".join("%d %d" % q for q in p)) + "".join(dot(q) for q in p)


def sk_centerline():
    return line((8, 52), (56, 12), INK, 2.2, 'stroke-dasharray="10,4,2,4"') + dot((8, 52)) + dot((56, 12))


def sk_rect(center=False, three=False):
    p = [(10, 16), (54, 16), (54, 48), (10, 48)]
    if three:
        p = [(8, 40), (34, 52), (56, 26), (30, 14)]
    out = poly(p, "none", INK, 2.5)
    out += "".join(dot(q) for q in (p if not center else []))
    if center:
        out += line((10, 16), (54, 48), INK, 1.2, 'stroke-dasharray="3,3"') + dot((32, 32)) + dot((54, 48))
    return out


def sk_rounded_rect():
    return '<rect x="8" y="14" width="48" height="36" rx="10" fill="none" stroke="%s" stroke-width="2.5"/>' % INK + dot((8, 14), 2.5) + dot((56, 50), 2.5)


def sk_slot(arc=False):
    if arc:
        return (path("M12 46 A24 24 0 0 1 52 46", col=INK, w=14) + path("M12 46 A24 24 0 0 1 52 46", col="#fff", w=9)
                + path("M12 46 A24 24 0 0 1 52 46", col=INK, w=1, extra='stroke-dasharray="3,3"') + dot((12, 46)) + dot((52, 46)))
    return (path("M18 20 L46 20 A12 12 0 0 1 46 44 L18 44 A12 12 0 0 1 18 20 Z")
            + line((18, 32), (46, 32), INK, 1, 'stroke-dasharray="3,3"') + dot((18, 32)) + dot((46, 32)))


def sk_circle(three=False):
    out = circle((32, 32), 22)
    if three:
        return out + dot((32, 10)) + dot((12, 42)) + dot((52, 42))
    return out + line((32, 32), (48, 17), INK, 1.4, 'stroke-dasharray="3,2"') + dot((32, 32)) + dot((48, 17))


def sk_arc(three=False):
    out = path("M10 46 A24 24 0 0 1 54 46")
    if three:
        return out + dot((10, 46)) + dot((54, 46)) + dot((32, 23))
    return (out + line((32, 52), (10, 46), INK, 1.2, 'stroke-dasharray="3,2"') + line((32, 52), (54, 46), INK, 1.2, 'stroke-dasharray="3,2"')
            + dot((32, 52)) + dot((10, 46)) + dot((54, 46)))


def sk_polygon():
    p = [(32 + 22 * math.cos(math.radians(a)), 32 + 22 * math.sin(math.radians(a))) for a in range(30, 390, 60)]
    return poly(p, "none", INK, 2.5) + circle((32, 32), 22, "none", INK, 1, 'stroke-dasharray="3,3"') + dot((32, 32)) + dot(p[0])


def sk_spline():
    return (path("M8 50 L20 10 L44 54 L56 14", col=BLU, w=1, extra='stroke-dasharray="3,3"')
            + path("M8 50 C20 10 44 54 56 14") + dot((8, 50)) + dot((56, 14)) + dot((32, 32), 2.5))


def sk_point():
    return line((20, 32), (44, 32), INK, 1.2) + line((32, 20), (32, 44), INK, 1.2) + dot((32, 32), 6)


def sk_ellipse(partial=False):
    if partial:
        return path("M8 32 A24 14 0 0 1 56 32") + dot((32, 32)) + dot((8, 32)) + dot((56, 32))
    return ellipse((32, 32), 24, 14, "none", INK, 2.5) + dot((32, 32)) + dot((56, 32)) + dot((32, 18))


def sk_parabola():
    return path("M10 10 Q32 80 54 10") + dot((10, 10)) + dot((54, 10)) + dot((32, 45))


def sk_fillet(chamf=False):
    corner = "L14 26 L26 14" if chamf else "Q14 14 26 14"
    return (line((14, 58), (14, 36), INK, 2.5) + line((36, 14), (58, 14), INK, 2.5)
            + path("M14 36 L14 14 L36 14", col=INK, w=1, extra='stroke-dasharray="3,3"')
            + path("M14 36 %s L36 14" % corner if chamf else "M14 36 Q14 14 36 14", col=YEL[2], w=3.5))


def sk_trim():
    return (line((8, 32), (56, 32), INK, 2.5) + line((22, 8), (22, 56), INK, 2.5)
            + line((42, 8), (42, 30), INK, 2.5) + line((42, 34), (42, 56), RED, 2.5, 'stroke-dasharray="4,3"')
            + path("M48 44 L58 54 M58 44 L48 54", col=RED, w=3))


def sk_extend():
    return (line((52, 8), (52, 56), INK, 2.5) + line((8, 40), (28, 24), INK, 2.5)
            + line((28, 24), (52, 5), BLU, 2, 'stroke-dasharray="4,3"') + arrow((30, 23), (46, 10), BLU, 2.5, 6))


def sk_split():
    return line((6, 50), (28, 30), INK, 2.5) + line((36, 24), (58, 6), INK, 2.5) + dot((28, 30)) + dot((36, 24)) + path("M24 14 L40 40", col=RED, w=2)


def sk_convert():
    return (block(-12, -12, -16, 24, 24, 20, GRY)
            + flat(-12, -12, 4, 24, 24, "none", BLU, 3)
            + arrow((52, 6), (42, 18), BLU, 2.5, 6))


def sk_offset():
    return (path("M8 52 L8 30 Q8 12 26 12 L56 12")
            + path("M18 52 L18 32 Q18 22 28 22 L56 22", col=BLU, w=2.5, extra='stroke-dasharray="5,3"')
            + arrow((40, 13), (40, 21), BLU, 1.5, 4))


def sk_mirror():
    return (line((32, 4), (32, 60), INK, 1.6, 'stroke-dasharray="10,4,2,4"')
            + path("M26 14 L8 24 L20 48") + path("M38 14 L56 24 L44 48", col=BLU, w=2.5)
            + dot((8, 24)) + dot((56, 24)))


def sk_lin_pattern():
    return "".join(circle((14 + i * 18, 32), 7) for i in range(3)) + arrow((14, 50), (52, 50), BLU, 2, 5)


def sk_move():
    return (arrow((32, 32), (32, 6), BLU, 3, 7) + arrow((32, 32), (32, 58), BLU, 3, 7)
            + arrow((32, 32), (6, 32), BLU, 3, 7) + arrow((32, 32), (58, 32), BLU, 3, 7)
            + poly([(24, 24), (40, 24), (40, 40), (24, 40)], "#fff", INK, 2))


def sk_rotate():
    return path("M50 32 A18 18 0 1 1 40 16", col=BLU, w=3.5) + poly([(34, 8), (48, 14), (36, 22)], BLU, BLU, 1) + sk_line_small()


def sk_line_small():
    return line((24, 40), (40, 24), INK, 2.2) + dot((24, 40), 2.5) + dot((40, 24), 2.5)


def sk_scale():
    return (poly([(6, 34), (26, 34), (26, 54), (6, 54)], "none", INK, 2, 'stroke-dasharray="3,3"')
            + poly([(18, 8), (56, 8), (56, 46), (18, 46)], "none", INK, 2.5) + arrow((22, 40), (44, 18), BLU, 2.5, 6))


def sk_carbon():
    return (poly([(4, 30), (22, 14), (40, 30), (22, 46)], "#eef3fa", INK, 1.6)
            + poly([(24, 34), (42, 18), (60, 34), (42, 50)], "#fff8d9", INK, 1.6) + path("M34 34 L42 26 L50 34 L42 42 Z", col=BLU, w=2))


def badge(glyph):
    return ('<rect x="4" y="4" width="56" height="56" rx="10" fill="%s" stroke="#1f6b35" stroke-width="2"/>' % GRN) + glyph


def rel(kind):
    W = "#fff"
    g = {
        "coincident": circle((24, 32), 9, "none", W, 3.5) + circle((40, 32), 9, "none", W, 3.5) + circle((32, 32), 3.5, W, W, 1),
        "horizontal": line((12, 32), (52, 32), W, 5),
        "vertical": line((32, 12), (32, 52), W, 5),
        "parallel": line((14, 48), (34, 14), W, 4.5) + line((30, 50), (50, 16), W, 4.5),
        "perpendicular": line((14, 50), (50, 50), W, 4.5) + line((32, 50), (32, 14), W, 4.5),
        "tangent": circle((26, 36), 13, "none", W, 3.5) + line((12, 23), (54, 23), W, 4),
        "equal": line((14, 26), (50, 26), W, 5) + line((14, 40), (50, 40), W, 5),
        "symmetric": line((32, 10), (32, 54), W, 2, 'stroke-dasharray="5,3"') + line((10, 32), (24, 32), W, 4.5) + line((40, 32), (54, 32), W, 4.5),
        "fix": path("M32 10 L32 40 M20 24 L44 24 M18 44 L46 44 L32 56 Z", col=W, w=4),
        "pointon": path("M10 46 Q32 6 54 46", col=W, w=3.5) + circle((32, 26), 5, W, W, 1),
        "lock": text(32, 44, "XY", 22, W),
        "add": line((14, 50), (50, 50), W, 4) + line((14, 50), (14, 14), W, 4) + text(38, 36, "+", 26, W),
    }[kind]
    return badge(g)


def construction():
    return line((8, 54), (56, 10), "#3a6fd0", 3, 'stroke-dasharray="8,5"') + dot((8, 54)) + dot((56, 10))


def driven():
    return dimension() .replace(INK, "#888")


def repair():
    return sk_sketch() + path("M40 58 L54 44", col="#555", w=5) + circle((56, 42), 5, "none", "#555", 3)


def normal_to():
    return (poly([(6, 42), (32, 28), (58, 42), (32, 56)], LBL, BLU, 2)
            + arrow((32, 42), (32, 6), BLU, 3.5, 8))


def section_view():
    return (block(-14, -14, -14, 28, 28, 24, GRY)
            + poly([iso(0, -20, -18), iso(0, 20, -18), iso(0, 20, 16), iso(0, -20, 16)], "#9cc3f5", BLU, 2, 'fill-opacity="0.65"'))


def clip_plane():
    return section_view() + path("M8 8 L20 20 M20 8 L8 20", col=RED, w=2.5)


# ---------------------------------------------------------------- evaluate / misc
def measure():
    return (poly([(6, 40), (40, 6), (58, 24), (24, 58)], "#ffe9a3", INK, 2)
            + "".join(line((14 + i * 6, 32 - i * 6), (18 + i * 6, 36 - i * 6) if i % 2 else (22 + i * 6, 40 - i * 6), INK, 1.6) for i in range(5)))


def check():
    return circle((26, 26), 16, "#e8f2ff", INK, 3) + line((38, 38), (56, 56), INK, 6) + path("M18 26 L24 32 L34 20", col=GRN, w=3.5)


def stats():
    return "".join('<rect x="%d" y="%d" width="10" height="%d" fill="%s" stroke="%s" stroke-width="1.5"/>' % (
        8 + i * 14, 56 - h, h, c, INK) for i, (h, c) in enumerate([(20, LBL), (40, YEL[1]), (30, LBL), (48, GRN)]))


# ---------------------------------------------------------------- assembly
def insert_component():
    return block(-12, -12, -14, 24, 24, 20, YEL) + circle((50, 14), 10, GRN, "#fff", 2) + text(50, 19, "+", 16, "#fff")


def mate():
    # paperclip-like
    d = "M22 54 L22 18 A8 8 0 0 1 38 18 L38 46 A5 5 0 0 1 28 46 L28 22"
    return path(d, col="#556", w=4.5) + path(d, col="#c7ced8", w=2)


def gears():
    out = ""
    for (cx, cy, r, n, col) in ((24, 36, 14, 10, GRY[1]), (46, 20, 10, 8, YEL[1])):
        p = []
        for i in range(n * 2):
            a = math.pi * i / n
            rr = r + (3 if i % 2 == 0 else 0)
            p.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        out += poly(p, col) + circle((cx, cy), r / 3, "#fff", INK, 1.5)
    return out


def fix_float():
    return block(-12, -12, -14, 24, 24, 18, GRY) + path("M44 4 L56 16 L50 22 L46 30 L34 18 L42 14 Z", RED, INK, 1.5) + line((38, 24), (28, 34), INK, 2.5)


def explode():
    return (block(-16, -16, -18, 20, 20, 10, GRY) + block(4, 4, 8, 14, 14, 10, YEL)
            + line(iso(4, 4, 8), iso(-2, -2, -8), BLU, 1.5, 'stroke-dasharray="3,3"'))


def bom():
    out = '<rect x="6" y="8" width="52" height="48" fill="#fff" stroke="%s" stroke-width="2"/>' % INK
    out += '<rect x="6" y="8" width="52" height="10" fill="%s"/>' % LBL
    for y in (18, 28, 38, 48):
        out += line((6, y), (58, y), INK, 1)
    return out + line((20, 8), (20, 56), INK, 1)


# ---------------------------------------------------------------- drawing
def sheet(inner=""):
    return ('<rect x="6" y="6" width="52" height="52" fill="#fff" stroke="%s" stroke-width="2.5"/>' % INK
            + '<rect x="38" y="48" width="20" height="10" fill="#dde3ea" stroke="%s" stroke-width="1.2"/>' % INK + inner)


def drw_model():
    return sheet(block(-8, -8, -8, 16, 16, 16, GRY, ox=30, oy=30, k=1.0))


def drw_3view():
    return sheet('<rect x="12" y="12" width="14" height="14" fill="none" stroke="%s" stroke-width="2"/>' % BLU
                 + '<rect x="32" y="12" width="10" height="14" fill="none" stroke="%s" stroke-width="2"/>' % BLU
                 + '<rect x="12" y="32" width="14" height="10" fill="none" stroke="%s" stroke-width="2"/>' % BLU)


def drw_section():
    return sheet(line((10, 28), (54, 28), RED, 2, 'stroke-dasharray="8,3,2,3"') + arrow((12, 28), (12, 14), RED, 2, 5)
                 + arrow((52, 28), (52, 14), RED, 2, 5) + text(20, 46, "A-A", 10, INK))


def drw_detail():
    return sheet(circle((24, 26), 11, "none", BLU, 2) + line((32, 34), (44, 46), BLU, 2) + text(48, 22, "A", 11, BLU))


def balloon():
    return circle((38, 24), 14, "#fff", INK, 2.5) + text(38, 30, "1", 16) + line((28, 34), (10, 54), INK, 2) + circle((10, 54), 2.5, INK, INK, 1)


def note():
    return text(32, 44, "A", 36, INK) + line((10, 54), (54, 54), BLU, 2)


def centerline():
    return line((6, 32), (58, 32), INK, 2.2, 'stroke-dasharray="12,4,3,4"') + line((32, 6), (32, 58), INK, 2.2, 'stroke-dasharray="12,4,3,4"')


def center_mark():
    return circle((32, 32), 18, "none", INK, 2) + line((32, 8), (32, 56), INK, 1.6, 'stroke-dasharray="8,3,2,3"') + line((8, 32), (56, 32), INK, 1.6, 'stroke-dasharray="8,3,2,3"')


def export():
    return sheet(arrow((18, 32), (50, 32), GRN, 4, 9))


def radius_dim():
    return path("M10 54 A40 40 0 0 1 50 14") + arrow((50, 54), (24, 28), INK, 2, 6) + text(46, 44, "R", 14, BLU)


def dia_dim():
    return circle((32, 32), 20) + arrow((32, 32), (46, 18), INK, 2, 6) + arrow((32, 32), (18, 46), INK, 2, 6) + text(50, 58, "Ø", 14, BLU)


def angle_dim():
    return line((8, 54), (58, 54)) + line((8, 54), (44, 12)) + path("M38 54 A30 30 0 0 0 28 31", col=BLU, w=2) + text(48, 42, "°", 18, BLU)


def h_dim():
    return dimension("H")


def v_dim():
    return '<g transform="rotate(90 32 32)">' + dimension() + "</g>" + text(52, 36, "V", 12, BLU)


# ---------------------------------------------------------------- heads-up / view
def zoom(kind="fit"):
    out = circle((26, 26), 15, "#eef5ff", INK, 3) + line((37, 37), (56, 56), INK, 6)
    if kind == "fit":
        out += poly([(4, 4), (14, 4)], "none", BLU, 2) + path("M4 14 L4 4 L14 4 M48 4 L58 4 L58 14", col=BLU, w=2.5)
    elif kind == "area":
        out += '<rect x="17" y="17" width="18" height="18" fill="none" stroke="%s" stroke-width="2" stroke-dasharray="3,2"/>' % BLU
    else:
        out += block(-5, -5, -5, 10, 10, 10, YEL, ox=26, oy=27, k=1.0)
    return out


def style(kind):
    kw = dict(ox=32, oy=36, k=1.0)
    s = 22
    P = lambda a, b, c: iso(a, b, c, **kw)
    x = y = z = -s / 2
    faces = [[P(x, y + s, z), P(x + s, y + s, z), P(x + s, y + s, z + s), P(x, y + s, z + s)],
             [P(x + s, y, z), P(x + s, y + s, z), P(x + s, y + s, z + s), P(x + s, y, z + s)],
             [P(x, y, z + s), P(x + s, y, z + s), P(x + s, y + s, z + s), P(x, y + s, z + s)]]
    cols = GRY[1], GRY[2], GRY[0]
    out = ""
    if kind in ("shaded_edges", "shaded"):
        for f, c in zip(faces, cols):
            out += poly(f, c, INK if kind == "shaded_edges" else c, SW)
    elif kind == "hlr":
        for f in faces:
            out += poly(f, "#fff", INK, SW)
    else:
        hid = [P(x, y, z), P(x + s, y, z), P(x, y + s, z), P(x, y, z + s)]
        dash = 'stroke-dasharray="3,2"'
        for e in ((hid[0], hid[1]), (hid[0], hid[2]), (hid[0], hid[3])):
            out += line(e[0], e[1], "#888" if kind == "hlv" else INK, 1.6, dash if kind == "hlv" else "")
        for f in faces:
            out += poly(f, "none", INK, SW)
    return out


def eye():
    return path("M4 32 Q32 6 60 32 Q32 58 4 32 Z", "#fff", INK, 2.5) + circle((32, 32), 10, BLU, INK, 2) + circle((32, 32), 4, INK, INK, 1)


def appearance():
    return (circle((32, 32), 24, "url(#g)", INK, 2)
            + '<defs><radialGradient id="g" cx="0.35" cy="0.35"><stop offset="0" stop-color="#fff"/>'
              '<stop offset="0.5" stop-color="#e94f4f"/><stop offset="1" stop-color="#7a1010"/></radialGradient></defs>')


ICONS = {
    # features
    "PartDesign_Pad": extrude_boss, "SS_ExtrudeBoss": extrude_boss,
    "PartDesign_Pocket": extrude_cut, "SS_ExtrudeCut": extrude_cut,
    "PartDesign_Revolution": revolve_boss, "SS_RevolveBoss": revolve_boss,
    "PartDesign_Groove": revolve_cut, "SS_RevolveCut": revolve_cut,
    "PartDesign_AdditivePipe": swept, "PartDesign_SubtractivePipe": lambda: swept(True),
    "PartDesign_AdditiveLoft": lofted, "PartDesign_SubtractiveLoft": lambda: lofted(True),
    "PartDesign_AdditiveHelix": helix, "PartDesign_SubtractiveHelix": lambda: helix(True),
    "PartDesign_Hole": hole, "SS_HoleWizard": hole,
    "PartDesign_Fillet": fillet, "SS_Fillet": fillet,
    "PartDesign_Chamfer": chamfer, "SS_Chamfer": chamfer,
    "PartDesign_Thickness": shell, "SS_Shell": shell,
    "PartDesign_Draft": draft,
    "PartDesign_LinearPattern": linear_pattern, "PartDesign_PolarPattern": circular_pattern,
    "PartDesign_Mirrored": mirror, "PartDesign_MultiTransform": multi_pattern, "PartDesign_Scaled": scale_icon,
    "PartDesign_Plane": plane, "PartDesign_Line": axis, "PartDesign_Point": point,
    "PartDesign_CoordinateSystem": coord_sys, "PartDesign_MoveTip": rollback,
    "PartDesign_Body": new_body, "PartDesign_Boolean": combine, "SS_Rebuild": rebuild,
    # sketch
    "PartDesign_NewSketch": sk_sketch, "Sketcher_LeaveSketch": sk_exit, "Sketcher_Dimension": smart_dim,
    "Sketcher_CreateLine": sk_line, "Sketcher_CreatePolyline": sk_polyline,
    "Sketcher_CreateRectangle": sk_rect, "Sketcher_CreateRectangle_Center": lambda: sk_rect(center=True),
    "Sketcher_CreateRectangle3Points": lambda: sk_rect(three=True), "Sketcher_CreateOblong": sk_rounded_rect,
    "Sketcher_CreateSlot": sk_slot, "Sketcher_CreateArcSlot": lambda: sk_slot(True),
    "Sketcher_CreateCircle": sk_circle, "Sketcher_Create3PointCircle": lambda: sk_circle(True),
    "Sketcher_CreateArc": sk_arc, "Sketcher_Create3PointArc": lambda: sk_arc(True),
    "Sketcher_CreateRegularPolygon": sk_polygon, "Sketcher_CreateBSpline": sk_spline, "Sketcher_CreatePoint": sk_point,
    "Sketcher_CreateEllipseByCenter": sk_ellipse, "Sketcher_CreateArcOfEllipse": lambda: sk_ellipse(True),
    "Sketcher_CreateArcOfParabola": sk_parabola,
    "Sketcher_CreateFillet": sk_fillet, "Sketcher_CreateChamfer": lambda: sk_fillet(True),
    "Sketcher_Trimming": sk_trim, "Sketcher_Extend": sk_extend, "Sketcher_Split": sk_split,
    "Sketcher_External": sk_convert, "Sketcher_Offset": sk_offset, "Sketcher_Symmetry": sk_mirror,
    "Sketcher_RectangularArray": sk_lin_pattern, "Sketcher_Translate": sk_move, "Sketcher_Rotate": sk_rotate,
    "Sketcher_Scale": sk_scale, "Sketcher_CarbonCopy": sk_carbon,
    "Sketcher_ConstrainCoincidentUnified": lambda: rel("coincident"), "Sketcher_ConstrainHorizontal": lambda: rel("horizontal"),
    "Sketcher_ConstrainVertical": lambda: rel("vertical"), "Sketcher_ConstrainParallel": lambda: rel("parallel"),
    "Sketcher_ConstrainPerpendicular": lambda: rel("perpendicular"), "Sketcher_ConstrainTangent": lambda: rel("tangent"),
    "Sketcher_ConstrainEqual": lambda: rel("equal"), "Sketcher_ConstrainSymmetric": lambda: rel("symmetric"),
    "Sketcher_ConstrainPointOnObject": lambda: rel("pointon"), "Sketcher_ConstrainBlock": lambda: rel("fix"),
    "Sketcher_ConstrainLock": lambda: rel("lock"), "SS_AddRelation": lambda: rel("add"),
    "Sketcher_ToggleConstruction": construction, "Sketcher_ToggleDrivingConstraint": driven,
    "Sketcher_ValidateSketch": repair, "Sketcher_ViewSketch": normal_to, "SS_NormalTo": normal_to,
    "Sketcher_ViewSection": section_view, "Sketcher_ConstrainDistanceX": h_dim,
    # evaluate
    "Std_Measure": measure, "Part_SectionCut": section_view, "Std_ToggleClipPlane": clip_plane,
    "Part_CheckGeometry": check, "Std_DependencyGraph": stats,
    # assembly
    "Assembly_InsertLink": insert_component, "Assembly_CreateJointFixed": mate,
    "Assembly_CreateJointRevolute": mate, "Assembly_CreateJointCylindrical": mate, "Assembly_CreateJointSlider": mate,
    "Assembly_CreateJointBall": mate, "Assembly_CreateJointDistance": mate, "Assembly_CreateJointParallel": mate,
    "Assembly_CreateJointPerpendicular": mate, "Assembly_CreateJointAngle": mate,
    "Assembly_CreateJointGears": gears, "Assembly_CreateJointRackPinion": gears, "Assembly_CreateJointScrew": gears,
    "Assembly_CreateJointBelt": gears, "Assembly_ToggleGrounded": fix_float, "Assembly_SolveAssembly": rebuild,
    "Assembly_CreateView": explode, "Assembly_CreateBom": bom,
    # drawing
    "TechDraw_View": drw_model, "TechDraw_ProjectionGroup": drw_3view, "TechDraw_SectionView": drw_section,
    "TechDraw_DetailView": drw_detail, "TechDraw_Dimension": smart_dim,
    "TechDraw_HorizontalDimension": h_dim, "TechDraw_VerticalDimension": v_dim, "TechDraw_AngleDimension": angle_dim,
    "TechDraw_RadiusDimension": radius_dim, "TechDraw_DiameterDimension": dia_dim, "TechDraw_Balloon": balloon,
    "TechDraw_Annotation": note, "TechDraw_FaceCenterLine": centerline, "TechDraw_CosmeticVertex": center_mark,
    "TechDraw_ExportPageSVG": export, "TechDraw_ExportPageDXF": export, "TechDraw_PrintAll": export,
    # view / heads-up
    "SS_ZoomFit": zoom, "Std_ViewFitAll": zoom, "Std_ViewBoxZoom": lambda: zoom("area"),
    "Std_ViewFitSelection": lambda: zoom("sel"),
    "SS_ViewFront": lambda: cube_view("front"), "SS_ViewBack": lambda: cube_view("back"),
    "SS_ViewLeft": lambda: cube_view("left"), "SS_ViewRight": lambda: cube_view("right"),
    "SS_ViewTop": lambda: cube_view("top"), "SS_ViewBottom": lambda: cube_view("bottom"),
    "SS_ViewIso": lambda: cube_view("iso"),
    "Std_DrawStyleAsIs": lambda: style("shaded_edges"), "Std_DrawStyleShaded": lambda: style("shaded"),
    "Std_DrawStyleHiddenLine": lambda: style("hlr"), "Std_DrawStyleNoShading": lambda: style("hlv"),
    "Std_DrawStyleWireframe": lambda: style("wire"),
    "Std_ToggleVisibility": eye, "Std_ShowSelection": eye, "Std_HideSelection": eye, "Std_ShowObjects": eye,
    "Std_SetAppearance": appearance,
}


# ---------------------------------------------------------------- FeatureManager tree icons
# Drawn bolder than the ribbon icons: they are shown at 16-24 px.

def t_part():
    return block(-15, -15, -13, 30, 30, 24, ("#ffe680", "#c3c8cf", "#9aa1ab"))


def t_assembly():
    return block(-17, -5, -16, 22, 22, 14, GRY) + block(-3, -15, -2, 18, 18, 16, ("#ffe680", "#c3c8cf", "#9aa1ab"))


def t_drawing():
    return (sheet() + '<rect x="12" y="14" width="14" height="12" fill="#c3c8cf" stroke="%s" stroke-width="2"/>' % INK
            + '<rect x="12" y="32" width="14" height="12" fill="#c3c8cf" stroke="%s" stroke-width="2"/>' % INK
            + '<rect x="32" y="14" width="18" height="12" fill="#c3c8cf" stroke="%s" stroke-width="2"/>' % INK)


def t_history():
    return (circle((34, 34), 22, "#fff", INK, 3.5) + line((34, 34), (34, 20), INK, 3.5) + line((34, 34), (45, 40), INK, 3.5)
            + path("M6 18 A28 28 0 0 1 22 8", col=BLU, w=4) + poly([(2, 12), (12, 22), (14, 10)], BLU, BLU, 1))


def t_sensors():
    return (circle((20, 44), 7, YEL[1], INK, 2.5)
            + path("M20 24 A20 20 0 0 1 40 44", col=BLU, w=4) + path("M20 10 A34 34 0 0 1 54 44", col=BLU, w=4))


def t_annotations():
    return (path("M10 56 L28 8 L36 8 L54 56", col=BLU, w=6) + line((18, 40), (46, 40), BLU, 5))


def t_folder(inner=""):
    return (path("M4 16 L4 54 L60 54 L60 20 L30 20 L24 12 L8 12 Z", "#f5c542", INK, 2.5)
            + path("M4 26 L60 26", col="#cc9b1a", w=2) + inner)


def t_solid_bodies():
    return t_folder(block(-8, -8, -10, 16, 16, 14, GRY, ox=34, oy=42, k=1.1))


def t_solid_body():
    return block(-15, -15, -13, 30, 30, 24, GRY)


def t_material():
    out = block(-17, -9, -10, 34, 18, 14, ("#d9dee5", "#aeb6c1", "#8a93a0"))
    for i in range(4):
        x = -13 + i * 8
        out += line(iso(x, -9, 4), iso(x + 8, 9, 4), "#fff", 2.2)
    return out


def t_plane():
    return poly([(4, 42), (24, 14), (60, 22), (40, 50)], "#c9ddf7", BLU, 3.2, 'fill-opacity="0.9"')


def t_origin():
    o = (14, 50)
    return (arrow(o, (58, 50), BLU, 4.5, 11) + arrow(o, (14, 6), BLU, 4.5, 11) + circle(o, 5.5, RED, INK, 1.5))


def t_sketch():
    return (poly([(2, 46), (22, 16), (62, 22), (42, 54)], "#f4f7fb", INK, 2.6)
            + path("M16 42 L32 26 L46 40 Z", col=BLU, w=3.5)
            + circle((16, 42), 3.4, BLU, BLU, 1) + circle((32, 26), 3.4, BLU, BLU, 1) + circle((46, 40), 3.4, BLU, BLU, 1))


def t_mates():
    return t_folder(path("M26 50 L26 32 A5 5 0 0 1 36 32 L36 46 A3 3 0 0 1 30 46 L30 34", col="#445", w=3.2))


def t_mate():
    d = "M20 56 L20 18 A10 10 0 0 1 40 18 L40 46 A6 6 0 0 1 28 46 L28 22"
    return path(d, col="#445", w=6.5) + path(d, col="#c7ced8", w=3)


def t_sheet():
    return sheet()


def t_sheet_format():
    return ('<rect x="6" y="6" width="52" height="52" fill="#fff" stroke="%s" stroke-width="3"/>' % INK
            + '<rect x="26" y="40" width="32" height="18" fill="#dde3ea" stroke="%s" stroke-width="2"/>' % INK
            + line((26, 49), (58, 49), INK, 1.5) + line((42, 40), (42, 58), INK, 1.5))


def t_view():
    return ('<rect x="6" y="10" width="52" height="44" fill="#fff" stroke="%s" stroke-width="2.5" stroke-dasharray="5,3"/>' % BLU
            + block(-10, -10, -9, 20, 20, 16, GRY, ox=32, oy=34))


def t_body_fc():
    return block(-15, -15, -13, 30, 30, 24, ("#d6e4f7", "#a9bcd6", "#7f95b4"))


def _pencil(x=34, y=4):
    return poly([(x + 14, y), (x + 22, y + 8), (x + 4, y + 30), (x - 4, y + 34), (x - 2, y + 26)], YEL[1], INK, 2)


def t_edit_feature():
    return block(-16, -16, -16, 26, 26, 18, ("#ffe680", "#c3c8cf", "#9aa1ab"), ox=28, oy=40) + _pencil()


def t_edit_sketch():
    return t_sketch() + _pencil(36, 0)


def t_suppress():
    return (block(-14, -14, -12, 28, 28, 20, ("#e4e6ea", "#c8ccd2", "#aab0b8"))
            + circle((44, 44), 15, "#fff", RED, 4.5) + line((34, 54), (54, 34), RED, 4.5))


def t_filter():
    return poly([(6, 8), (58, 8), (38, 32), (38, 54), (26, 60), (26, 32)], "#fff", INK, 3.5)


def t_fc_tree():
    out = line((14, 12), (14, 50), INK, 3) + line((14, 30), (26, 30), INK, 3) + line((14, 50), (26, 50), INK, 3)
    for y in (12, 30, 50):
        out += '<rect x="%d" y="%d" width="30" height="10" fill="#c9ddf7" stroke="%s" stroke-width="2.5"/>' % (
            26 if y > 12 else 8, y - 5, BLU)
    return out


TREE = {
    "edit_feature": t_edit_feature, "edit_sketch": t_edit_sketch, "suppress": t_suppress,
    "filter": t_filter, "fc_tree": t_fc_tree,
    "part": t_part, "assembly": t_assembly, "drawing": t_drawing, "history": t_history, "sensors": t_sensors,
    "annotations": t_annotations, "folder": t_folder, "solid_bodies": t_solid_bodies, "solid_body": t_solid_body,
    "material": t_material, "plane": t_plane, "origin": t_origin, "sketch": t_sketch, "mates": t_mates,
    "mate": t_mate, "sheet": t_sheet, "sheet_format": t_sheet_format, "view": t_view, "component": t_part,
    "axis": axis, "point": point, "coord_sys": coord_sys,
}


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, fn in ICONS.items():
        with open(os.path.join(OUT, name + ".svg"), "w") as f:
            f.write(svg(fn()))
    print("wrote %d icons to %s" % (len(ICONS), os.path.abspath(OUT)))
    tree = os.path.join(OUT, "..", "tree")
    os.makedirs(tree, exist_ok=True)
    for name, fn in TREE.items():
        with open(os.path.join(tree, name + ".svg"), "w") as f:
            f.write(svg(fn()))
    print("wrote %d tree icons to %s" % (len(TREE), os.path.abspath(tree)))


if __name__ == "__main__":
    main()
