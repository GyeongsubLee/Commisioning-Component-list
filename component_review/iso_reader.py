"""ISO PDF에서 도면 영역, 배관선, Tag와 그 위치를 읽는다."""
import math
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


def drawing_area(page):
    """오른쪽 BOM 표와 아래 Legend/Title block을 뺀 도면 영역."""
    r = pymupdf.Rect(page.rect)
    x1, y1 = r.x1, r.y1
    for key in ("FABRICATION MATERIALS", "ERECTION MATERIALS"):
        for hit in page.search_for(key):
            if hit.x0 > r.width * 0.4:
                x1 = min(x1, hit.x0 - 4)
    for key in ("LEGEND", "PIPELINE DATA"):
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
    for d in page.get_drawings():
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
            a, b = (a.x, a.y), (b.x, b.y)
            L = dist(a, b)
            if L < 0.5 or not (_inside(a, area) and _inside(b, area)):
                continue
            # 도면 테두리 같은 긴 수평/수직선은 제외
            if (abs(a[1] - b[1]) < 0.5 and L > 0.6 * aw) or (abs(a[0] - b[0]) < 0.5 and L > 0.6 * ah):
                continue
            segs.append((a, b, w))
    return segs


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


def _trace_leader(rect, thin, pipes, cfg: Config):
    """Tag 글자에서 지시선을 따라가 배관 위의 위치를 찾는다."""
    t = cfg.leader_touch
    box = (rect[0] - t, rect[1] - t, rect[2] + t, rect[3] + t)
    center = ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)
    points = [center]
    frontier = []
    used = set()
    for i, (a, b) in enumerate(thin):
        if _inside(a, box) or _inside(b, box):
            used.add(i)
            for p in (a, b):
                points.append(p)
                if not _inside(p, box):
                    frontier.append(p)
    for _ in range(cfg.leader_depth - 1):
        nxt = []
        for p in frontier:
            for i, (a, b) in enumerate(thin):
                if i in used:
                    continue
                if dist(p, a) <= 1.5 or dist(p, b) <= 1.5:
                    used.add(i)
                    far = b if dist(p, a) <= 1.5 else a
                    points.append(far)
                    nxt.append(far)
        frontier = nxt
    best = None
    for p in points:
        for a, b in pipes:
            q = project(p, a, b)
            d = dist(p, q)
            if best is None or d < best[0]:
                best = (d, q)
    return best[1] if best else None


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
        if thr is None:
            ip.note = "배관선 굵기를 구분하지 못함"
            thin = [(a, b) for a, b, w in segs]
        else:
            ip.pipes = [(a, b) for a, b, w in segs if w >= thr]
            thin = [(a, b) for a, b, w in segs if w < thr]
            ip.pipe_width = thr
            if not ip.pipes:
                ip.note = "배관선을 찾지 못함"
        seen = set()
        for text, rect, _ in text_lines(page):
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
                    it.anchor = _trace_leader(r, thin, ip.pipes, cfg)
                ip.tags.append(it)
        pages.append(ip)
    doc.close()
    return pages
