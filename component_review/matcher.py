"""ISO 한 장에서 어느 배관 구간이 해당 Subsystem인지 판단한다."""
from dataclasses import dataclass, field

from .config import Config
from .iso_reader import IsoPage, SegmentGrid, dist, project, seg_gap

OK = "OK"
REVIEW = "수동 검토"
CHECK = "확인 권장"
NA = "무관"


@dataclass
class Selection:
    status: str = NA
    reason: str = ""
    strokes: list = field(default_factory=list)   # 색칠할 선분 [((x,y),(x,y))]
    in_tags: list = field(default_factory=list)   # IsoTag
    out_tags: list = field(default_factory=list)
    pipe_width: float = 0.0


def _split(pipes, anchors, r):
    """Tag 위치가 선분 중간에 있으면 그 점에서 선분을 나눈다."""
    out = []
    for a, b in pipes:
        cuts = []
        for p in anchors:
            q = project(p, a, b)
            if dist(p, q) <= 1.0 and dist(q, a) > r and dist(q, b) > r:
                cuts.append((dist(a, q), q))
        prev = a
        for _, q in sorted(cuts):
            out.append((prev, q))
            prev = q
        out.append((prev, b))
    return out


def _pairs(pipes, cfg: Config):
    """서로 가까이 있을 수 있는 배관선 쌍 (i < j)."""
    grid = SegmentGrid(pipes, cfg.grid_cell)
    g = cfg.gap_tol
    for i, (a, b) in enumerate(pipes):
        box = (min(a[0], b[0]) - g, min(a[1], b[1]) - g, max(a[0], b[0]) + g, max(a[1], b[1]) + g)
        for j in sorted(grid.query(*box)):
            if j > i:
                yield i, j


def _partial(page: IsoPage, in_tags, out_tags, cfg: Config):
    r = cfg.anchor_radius
    ins = [t.anchor for t in in_tags if t.anchor]
    outs = [t.anchor for t in out_tags if t.anchor]
    pipes = _split(page.pipes, ins + outs, r)
    n = len(pipes)
    adj = {i: [] for i in range(n)}
    for i, j in _pairs(pipes, cfg):
        if True:
            d, (p, q) = seg_gap(pipes[i], pipes[j])
            if d <= cfg.gap_tol:
                mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
                blocked = any(dist(mid, o) <= r for o in outs)
                near_in = any(dist(mid, a) <= r for a in ins)
                if blocked and not near_in:
                    continue
                adj[i].append((j, p, q))
                adj[j].append((i, q, p))
    seeds = set()
    for a in ins:
        ds = [dist(a, project(a, *s)) for s in pipes]
        near = [i for i, d in enumerate(ds) if d <= 1.0]
        seeds.update(near or [min(range(n), key=ds.__getitem__)])
    picked, stack, links = set(seeds), list(seeds), []
    while stack:
        i = stack.pop()
        for j, p, q in adj[i]:
            if dist(p, q) > 0.5:
                links.append((p, q))
            if j not in picked:
                picked.add(j)
                stack.append(j)
    return [pipes[i] for i in sorted(picked)] + links


def _all(page: IsoPage, cfg: Config):
    strokes = list(page.pipes)
    for i, j in _pairs(page.pipes, cfg):
        d, (p, q) = seg_gap(page.pipes[i], page.pipes[j])
        if 0.5 < d <= cfg.gap_tol:
            strokes.append((p, q))
    return strokes


def select(page: IsoPage, pid_tags, line_key, pid_lines, cfg: Config) -> Selection:
    sel = Selection()
    sel.pipe_width = page.pipe_width
    sel.in_tags = [t for t in page.tags if t.tag in pid_tags]
    sel.out_tags = [t for t in page.tags if t.tag not in pid_tags]
    line_marked = line_key in pid_lines

    if sel.in_tags and not sel.out_tags:
        sel.status, sel.strokes = OK, _all(page, cfg)
    elif sel.in_tags and sel.out_tags:
        sel.status = REVIEW
        sel.reason = "한 ISO에 다른 System Tag 혼재: " + ", ".join(sorted({t.tag for t in sel.out_tags}))
        if page.pipes:
            sel.strokes = _partial(page, sel.in_tags, sel.out_tags, cfg)
    elif sel.out_tags:
        if line_marked:
            sel.status = REVIEW
            sel.reason = "Line은 PID에 색칠되어 있으나 ISO의 Tag가 모두 PID 색칠 범위 밖 (색칠 안 함)"
        else:
            sel.status, sel.reason = NA, "ISO의 Tag가 모두 PID 색칠 범위 밖"
    else:
        if not pid_lines:
            sel.status, sel.reason = REVIEW, "Tag 없음, PID에서 Line No.도 읽지 못함 → 전체 색칠 대상으로 처리"
            sel.strokes = _all(page, cfg)
        elif line_marked:
            sel.status, sel.reason = CHECK, "Tag 없음 → Line No. 기준 전체 색칠 대상"
            sel.strokes = _all(page, cfg)
        else:
            sel.status, sel.reason = NA, "Tag 없음, Line No.가 PID에 색칠되어 있지 않음"

    wants_color = sel.status in (OK, CHECK) or bool(sel.in_tags) or "전체 색칠 대상" in sel.reason
    if wants_color and not sel.strokes:
        sel.status = REVIEW
        tail = "색칠되지 않음, Tag만 형광펜 표시" if sel.in_tags else "색칠되지 않음"
        sel.reason = (sel.reason + " / " if sel.reason else "") + f"{page.note or '배관선 인식 실패'} → {tail}"
    return sel
