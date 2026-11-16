"""ISO PDF에서 도면 영역, 배관선, Tag와 그 위치를 읽는다."""
import math
import re
from dataclasses import dataclass, field
import pymupdf

from .config import Config
from .pid_reader import text_lines


@dataclass
class IsoTag:
    tag: str
    prefix: str
    rect: tuple                 # 글자 위치 (x0, y0, x1, y1)
    anchor: tuple = None        # 배관 위의 위치 (x, y)


@dataclass
class IsoPage:
    index: int
    area: tuple
    pipes: list = field(default_factory=list)   # [((x1,y1),(x2,y2))]
    tags: list = field(default_factory=list)
    pipe_width: float = 0.0
    method: str = "선 굵기"
    line: str = ""             # Title block의 Line number (예: 305-HI-0007)
    note: str = ""


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def project(p, a, b):
    """점 p에서 선분 ab 위의 가장 가까운 점."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return a
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return (a[0] + t * dx, a[1] + t * dy)


def seg_gap(s, t):
    """두 선분 사이 최소 거리와 그 연결점 (s쪽 점, t쪽 점)."""
    best = None
    for p, other, flip in ((s[0], t, False), (s[1], t, False), (t[0], s, True), (t[1], s, True)):
        q = project(p, *other)
        d = dist(p, q)
        if best is None or d < best[0]:
            best = (d, (q, p) if flip else (p, q))
    return best


class SegmentGrid:
    """선분을 격자 칸에 등록해 두고, 어떤 범위 근처의 선분만 빠르게 찾는다."""

    def __init__(self, segs, cell=40.0):
        self.segs, self.cell, self.cells = segs, cell, {}
        for i, (a, b) in enumerate(segs):
            n = max(1, int(dist(a, b) / (cell / 2)) + 1)
            keys = {(int((a[0] + (b[0] - a[0]) * k / n) // cell), int((a[1] + (b[1] - a[1]) * k / n) // cell))
                    for k in range(n + 1)}
            for key in keys:
                self.cells.setdefault(key, []).append(i)

    def query(self, x0, y0, x1, y1):
        """범위에 걸친 칸(양옆 한 칸 여유)에 있는 선분 번호."""
        c, out = self.cell, set()
        for gx in range(int(x0 // c) - 1, int(x1 // c) + 2):
            for gy in range(int(y0 // c) - 1, int(y1 // c) + 2):
                out.update(self.cells.get((gx, gy), ()))
        return out

    def near(self, p, r):
        return self.query(p[0] - r, p[1] - r, p[0] + r, p[1] + r)

    def nearest(self, p):
        """(거리, 선분 위의 점, 선분 번호). 가까운 칸부터 넓혀 가며 찾는다."""
        if not self.segs:
            return None
        r = self.cell
        while True:
            best = None
            cand = self.near(p, r) if r < 1e5 else range(len(self.segs))
            for i in cand:
                q = project(p, *self.segs[i])
                d = dist(p, q)
                if best is None or d < best[0]:
                    best = (d, q, i)
            if best and (best[0] <= r or r >= 1e5):
                return best
            r = r * 4 if r < 5000 else 1e5


def drawing_area(page):
    """오른쪽 BOM 표와 아래 Legend/Title block을 뺀 도면 영역."""
    r = pymupdf.Rect(page.rect)
    x1, y1 = r.x1, r.y1
    for key in ("FABRICATION MATERIALS", "ERECTION MATERIALS"):
        for hit in page.search_for(key):
            if hit.x0 > r.width * 0.4:
                x1 = min(x1, hit.x0 - 4)
    for key in ("LEGEND", "PIPELINE DATA", "SHOP WELD", "FIELD WELD", "Line number", "P&ID Ref"):
        for hit in page.search_for(key):
            if hit.y0 > r.height * 0.5:
                y1 = min(y1, hit.y0 - 4)
    return (r.x0, r.y0, x1, y1)


def _inside(p, area, m=0.0):
    return area[0] + m <= p[0] <= area[2] - m and area[1] + m <= p[1] <= area[3] - m


def read_segments(page, area):
    """[(p1, p2, width)] - 도면 영역 안의 선 (곡선은 양 끝점을 잇는 선으로 근사)."""
    segs = []
    aw, ah = area[2] - area[0], area[3] - area[1]
    for d in page.get_cdrawings():
        if d.get("color") is None or "s" not in d.get("type", ""):
            continue
        w = round(float(d.get("width") or 0.0), 2)
        for it in d["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
            elif it[0] == "c":
                a, b = it[1], it[4]
            else:
                continue
            a, b = (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))
            L = dist(a, b)
            if L < 0.5 or not (_inside(a, area) and _inside(b, area)):
                continue
            # 도면 테두리 같은 긴 수평/수직선은 제외
            if (abs(a[1] - b[1]) < 0.5 and L > 0.6 * aw) or (abs(a[0] - b[0]) < 0.5 and L > 0.6 * ah):
                continue
            segs.append((a, b, w))
    return segs


def quad_centerline(pts):
    """사각형(꼭짓점 4개, 둘레 순서) -> (중심선 시작, 끝, 폭)."""
    s = [dist(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    mid = lambda p, q: ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    if s[0] + s[2] <= s[1] + s[3]:
        return mid(pts[0], pts[1]), mid(pts[2], pts[3]), (s[0] + s[2]) / 2
    return mid(pts[1], pts[2]), mid(pts[3], pts[0]), (s[1] + s[3]) / 2


def filled_quads(page, area):
    """채워진 사각형 도형들의 [(중심선 시작, 끝, 폭)]. CAD가 굵은 선을 채워진 면으로 출력한 경우."""
    out = []
    for d in page.get_cdrawings():
        if "f" not in d.get("type", "") or d.get("fill") is None:
            continue
        rings, chain = [], []
        for it in d["items"]:
            if it[0] == "qu":
                q = [(float(p[0]), float(p[1])) for p in it[1]]
                rings.append([q[0], q[1], q[3], q[2]])
            elif it[0] == "re":
                x0, y0, x1, y1 = (float(v) for v in it[1][:4])
                rings.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
            elif it[0] == "l":
                a, b = (float(it[1][0]), float(it[1][1])), (float(it[2][0]), float(it[2][1]))
                if not chain or dist(chain[-1], a) > 0.05:
                    if len(chain) >= 4:
                        rings.append(chain)
                    chain = [a]
                chain.append(b)
            else:
                chain = []
        if len(chain) >= 4:
            rings.append(chain)
        for ring in rings:
            if len(ring) >= 4 and dist(ring[0], ring[-1]) <= 0.05:
                ring = ring[:-1]
            if len(ring) != 4:
                continue
            a, b, w = quad_centerline(ring)
            if _inside(a, area) and _inside(b, area):
                out.append((a, b, w))
    return out


def fill_pipes(quads, cfg: Config):
    """채워진 사각형 중 배관(가늘고 긴 것, 대표 폭과 비슷한 것)만 고른다. -> (선분 목록, 대표 폭)"""
    slim = [(a, b, w) for a, b, w in quads if 0.2 <= w <= cfg.fill_pipe_max_width and dist(a, b) >= max(w, 2.0)]
    if not slim:
        return [], 0.0
    by_w = {}
    for a, b, w in slim:
        k = round(w * 2) / 2
        by_w[k] = by_w.get(k, 0.0) + dist(a, b)
    main = max(by_w, key=by_w.get) or 0.5
    picked = [(a, b) for a, b, w in slim if 0.5 * main <= w <= 1.6 * main + 0.5]
    if sum(dist(a, b) for a, b in picked) < 40:
        return [], 0.0
    return picked, main


def pipe_threshold(segs, cfg: Config):
    if cfg.pipe_min_width > 0:
        return cfg.pipe_min_width
    length = {}
    for a, b, w in segs:
        length[w] = length.get(w, 0.0) + dist(a, b)
    if len(length) < 2:
        return None
    wmax = max(length)
    common = max(length, key=length.get)
    if wmax < 1.5 * max(min(length), 0.01) or (common == wmax and len(length) < 2):
        return None
    return wmax * cfg.pipe_width_ratio


def _trace_leader(rect, thin: SegmentGrid, pipes: SegmentGrid, cfg: Config):
    """Tag 글자에서 지시선을 따라가 배관 위의 위치를 찾는다."""
    t = cfg.leader_touch
    box = (rect[0] - t, rect[1] - t, rect[2] + t, rect[3] + t)
    center = ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)
    points = [center]
    frontier = []
    used = set()
    for i in thin.query(*box):
        a, b = thin.segs[i]
        if _inside(a, box) or _inside(b, box):
            used.add(i)
            for p in (a, b):
                points.append(p)
                if not _inside(p, box):
                    frontier.append(p)
    for _ in range(cfg.leader_depth - 1):
        nxt = []
        for p in frontier[:50]:
            for i in thin.near(p, 1.5):
                if i in used:
                    continue
                a, b = thin.segs[i]
                if dist(p, a) <= 1.5 or dist(p, b) <= 1.5:
                    used.add(i)
                    far = b if dist(p, a) <= 1.5 else a
                    points.append(far)
                    nxt.append(far)
        frontier = nxt
    best = None
    for p in points[:400]:
        hit = pipes.nearest(p)
        if hit and (best is None or hit[0] < best[0]):
            best = hit
    return best[1] if best else None


LINE_KEY_RE = re.compile(r"(?<![\w/\-])(\d{3}-[A-Z]{1,4}\d{0,2}-\d{4})(?![\w])")


def title_line(page, lines):
    """Title block의 'Line number' 또는 'Isometric drawing' 옆에 적힌 Line No."""
    for key in ("Line number", "Isometric drawing"):
        for hit in page.search_for(key):
            for text, rect, _ in lines:
                if rect.y1 < hit.y0 - 3 or rect.y0 > hit.y1 + 3 or rect.x1 < hit.x0:
                    continue
                m = LINE_KEY_RE.search(text)
                if m:
                    return m.group(1)
    return ""


def read_iso(path, cfg: Config):
    """ISO PDF 한 개 -> [IsoPage]."""
    pages = []
    doc = pymupdf.open(path)
    for page in doc:
        page.remove_rotation()
        area = drawing_area(page)
        segs = read_segments(page, area)
        thr = pipe_threshold(segs, cfg)
        ip = IsoPage(index=page.number, area=area)
        fpipes, fwidth = fill_pipes(filled_quads(page, area), cfg)
        if fpipes:   # 굵은 선이 채워진 면으로 그려진 도면
            ip.pipes, ip.pipe_width, ip.method = fpipes, fwidth, "채워진 도형"
            thin = [(a, b) for a, b, w in segs]
        elif thr is None:
            ip.note = "배관선 굵기를 구분하지 못함"
            thin = [(a, b) for a, b, w in segs]
        else:
            ip.pipes = [(a, b) for a, b, w in segs if w >= thr]
            thin = [(a, b) for a, b, w in segs if w < thr]
            ip.pipe_width = thr
            if not ip.pipes:
                ip.note = "배관선을 찾지 못함"
            elif len(ip.pipes) > cfg.max_pipe_segments:
                ip.note = f"배관선으로 잡힌 선이 너무 많음({len(ip.pipes)}개) - 굵기 기준(pipe_min_width) 조정 필요"
                thin, ip.pipes = [(a, b) for a, b, w in segs], []
        thin_grid = SegmentGrid(thin, cfg.grid_cell)
        pipe_grid = SegmentGrid(ip.pipes, cfg.grid_cell)
        seen = set()
        tlines = text_lines(page)
        ip.line = title_line(page, tlines)
        for text, rect, _ in tlines:
            c = ((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
            if not _inside(c, area):
                continue
            for m in cfg.tag_re.finditer(text):
                unit, pre, num = m.groups()
                if pre in cfg.excluded_prefixes:
                    continue
                tag = f"{unit}-{pre}-{num}"
                hits = [h for h in page.search_for(m.group(0)) if h.intersects(rect)]
                r = tuple(hits[0]) if hits else tuple(rect)
                if (tag, round(r[0]), round(r[1])) in seen:
                    continue
                seen.add((tag, round(r[0]), round(r[1])))
                it = IsoTag(tag=tag, prefix=pre, rect=r)
                if ip.pipes:
                    it.anchor = _trace_leader(r, thin_grid, pipe_grid, cfg)
                ip.tags.append(it)
        pages.append(ip)
    doc.close()
    return pages
