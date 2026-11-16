"""진단: python -m component_review.inspect_pdf <PDF> [--page N] [--color #5C8AB8]
PDF 안의 선이 어떻게 그려져 있는지 숫자로 요약한다 (도면의 글자 내용은 출력하지 않음).
배관선을 무엇으로 구분할 수 있는지(굵기, 레이어, 색, 채워진 도형) 알아내는 데 쓴다."""
import argparse
import math
from collections import Counter, defaultdict
import pymupdf

from .config import Config, float_to_rgb, hex_to_rgb, color_dist
from .iso_reader import drawing_area, read_segments, pipe_threshold
from .pid_reader import text_lines


def hx(rgb):
    return "#%02X%02X%02X" % tuple(rgb) if rgb else "-"


def _len(it):
    if it[0] == "l":
        return math.hypot(it[2].x - it[1].x, it[2].y - it[1].y)
    if it[0] == "c":
        return math.hypot(it[4].x - it[1].x, it[4].y - it[1].y)
    return 0.0


def _bucket(L):
    for lim in (2, 5, 10, 20, 50, 100, 200):
        if L < lim:
            return f"<{lim}"
    return ">=200"


def _top(counter, n=12):
    return ", ".join(f"{k}:{v}" for k, v in counter.most_common(n)) or "없음"


def inspect_page(page, cfg, target):
    print(f"\n=== page {page.number + 1}  크기 {page.rect.width:.0f}x{page.rect.height:.0f}pt  회전 {page.rotation}")
    page.remove_rotation()
    lines = text_lines(page)
    tcol = Counter()
    for text, _, marks in lines:
        for i, (start, c) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
            tcol[hx(c)] += end - start
    n_tag = sum(1 for t, _, _ in lines for _ in cfg.tag_re.finditer(t))
    print(f"[글자] {len(lines)}줄, Tag 모양 {n_tag}개, 그림(이미지) {len(page.get_images())}개")
    print(f"  글자색별 글자 수: {_top(tcol, 8)}")

    area = drawing_area(page)
    inside = lambda r: r.x0 >= area[0] and r.y0 >= area[1] and r.x1 <= area[2] and r.y1 <= area[3]
    by_w = defaultdict(lambda: [0, 0.0, Counter()])      # 굵기 -> [선 개수, 총 길이, 길이 분포]
    kinds, stroke_col, fill_col, types, layers, dashes = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    layer_w = defaultdict(Counter)
    fills = []   # 채워진 도형의 (긴 변, 짧은 변)
    n_in = n_out = 0
    drawings = page.get_drawings()
    for d in drawings:
        typ = d.get("type", "?")
        types[typ] += 1
        rect = pymupdf.Rect(d["rect"])
        if inside(rect):
            n_in += 1
        else:
            n_out += 1
            continue
        layer = d.get("layer") or "(레이어 없음)"
        w = round(float(d.get("width") or 0.0), 3)
        for it in d["items"]:
            kinds[it[0]] += 1
        if "s" in typ:
            stroke_col[hx(float_to_rgb(d.get("color")))] += 1
            if d.get("dashes") and d["dashes"] not in ("[] 0", ""):
                dashes[d["dashes"]] += 1
            for it in d["items"]:
                L = _len(it)
                by_w[w][0] += 1
                by_w[w][1] += L
                by_w[w][2][_bucket(L)] += 1
                layers[layer] += 1
                layer_w[layer][w] += 1
        if "f" in typ:
            fill_col[hx(float_to_rgb(d.get("fill")))] += 1
            fills.append((max(rect.width, rect.height), min(rect.width, rect.height)))

    print(f"[도면 영역] {tuple(round(v) for v in area)}  영역 안 도형 {n_in}개 / 밖 {n_out}개")
    print(f"[도형 종류] 그리기 방식 {dict(types)} (s=선, f=채움, fs=둘 다),  요소 {dict(kinds)} (l=직선, c=곡선, re=사각형, qu=사변형)")
    print("[선 굵기별] 굵기(pt): 개수, 총 길이, 길이 분포")
    for w in sorted(by_w):
        n, total, dist_ = by_w[w]
        order = ["<2", "<5", "<10", "<20", "<50", "<100", "<200", ">=200"]
        print(f"  {w}: {n}개, {total:.0f}pt, " + " ".join(f"{k}:{dist_[k]}" for k in order if dist_[k]))
    print(f"[선 색별 개수] {_top(stroke_col)}")
    print(f"[점선] {_top(dashes, 6)}")
    print(f"[채워진 도형] {len(fills)}개, 색: {_top(fill_col, 8)}")
    if fills:
        slim = [f for f in fills if f[0] >= 15 and f[1] <= 6]
        big = sorted(fills, reverse=True)[:8]
        print(f"  가늘고 긴 것(길이 15pt 이상, 폭 6pt 이하): {len(slim)}개")
        print("  큰 것 (긴 변 x 짧은 변): " + ", ".join(f"{a:.0f}x{b:.1f}" for a, b in big))
    print(f"[레이어] {len(layers)}종")
    for name, n in layers.most_common(25):
        print(f"  {name}: 선 {n}개, 굵기 {dict(layer_w[name].most_common(4))}")
    ocgs = page.parent.get_ocgs() if hasattr(page.parent, "get_ocgs") else {}
    if ocgs:
        print("  PDF 레이어 목록: " + ", ".join(v.get("name", "?") for v in ocgs.values()))
    segs = read_segments(page, area)
    thr = pipe_threshold(segs, cfg)
    n_pipe = sum(1 for _, _, w in segs if thr is not None and w >= thr)
    print(f"[현재 프로그램의 판단] 선 {len(segs)}개 중 배관 굵기 기준 {thr} → 배관 {n_pipe}개")
    annots = Counter(a.type[1] for a in page.annots() or [])
    print(f"[주석] {dict(annots) or '없음'}")
    if target:
        n_text = sum(1 for _, _, marks in lines for _, c in marks if color_dist(c, target) <= cfg.color_tol)
        n_line = sum(1 for d in drawings
                     if any(float_to_rgb(d.get(k)) and color_dist(float_to_rgb(d.get(k)), target) <= cfg.color_tol
                            for k in ("color", "fill")))
        print(f"[지정 색] 글자 {n_text}곳, 선/면 {n_line}개")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="component_review.inspect_pdf", description=__doc__)
    ap.add_argument("pdf")
    ap.add_argument("color", nargs="?", help="(선택) Color Code, 예: #5C8AB8")
    ap.add_argument("--page", type=int, help="이 페이지만 (1부터)")
    ap.add_argument("--color", dest="color_opt")
    a = ap.parse_args(argv)
    code = a.color_opt or a.color
    target = hex_to_rgb(code) if code else None
    doc = pymupdf.open(a.pdf)
    print(f"페이지 {len(doc)}장, 만든 프로그램: {doc.metadata.get('creator')!r} / {doc.metadata.get('producer')!r}")
    for page in doc:
        if a.page and page.number + 1 != a.page:
            continue
        inspect_page(page, Config(), target)


if __name__ == "__main__":
    main()
