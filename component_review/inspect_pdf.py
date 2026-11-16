"""진단: python -m component_review.inspect_pdf <PDF> [#색코드]
PDF 안의 글자 색, 선 굵기/색 분포, 주석, Tag 후보를 요약해서 보여준다.
결과가 프로그램의 가정과 다를 때 config.py 값을 맞추는 데 쓴다."""
import sys
from collections import Counter
import pymupdf

from .config import Config, int_to_rgb, float_to_rgb, hex_to_rgb, color_dist
from .iso_reader import drawing_area, read_segments, pipe_threshold, dist
from .pid_reader import text_lines


def hx(rgb):
    return "#%02X%02X%02X" % tuple(rgb)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cfg = Config()
    target = hex_to_rgb(sys.argv[2]) if len(sys.argv) > 2 else None
    doc = pymupdf.open(sys.argv[1])
    for page in doc:
        print(f"=== page {page.number + 1}/{len(doc)}  size={page.rect.width:.0f}x{page.rect.height:.0f}pt  rotation={page.rotation}")
        page.remove_rotation()
        lines = text_lines(page)
        tcol = Counter()
        for text, _, marks in lines:
            for i, (start, c) in enumerate(marks):
                end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
                tcol[hx(c)] += end - start
        print(f"글자: {len(lines)}줄, 이미지 {len(page.get_images())}개")
        print("  글자색(글자 수):", ", ".join(f"{k}:{v}" for k, v in tcol.most_common(8)) or "없음 (스캔 이미지일 수 있음)")
        tags = Counter(m.group(0) for t, _, _ in lines for m in cfg.pid_tag_re.finditer(t))
        print(f"  Tag 모양 글자 {len(tags)}종:", ", ".join(list(tags)[:15]))
        wlen, scol = Counter(), Counter()
        kinds = Counter()
        for d in page.get_drawings():
            c = float_to_rgb(d.get("color"))
            f = float_to_rgb(d.get("fill"))
            for it in d["items"]:
                kinds[it[0]] += 1
            if c:
                scol[hx(c)] += len(d["items"])
            if f:
                scol["fill " + hx(f)] += len(d["items"])
        area = drawing_area(page)
        segs = read_segments(page, area)
        for a, b, w in segs:
            wlen[w] += dist(a, b)
        print(f"선: 종류 {dict(kinds)}")
        print("  선 색(개수):", ", ".join(f"{k}:{v}" for k, v in scol.most_common(8)))
        print("  선 굵기(pt):총 길이 →", ", ".join(f"{w}:{l:.0f}" for w, l in sorted(wlen.items())))
        print(f"  도면 영역 {tuple(round(v) for v in area)}, 배관 굵기 기준(자동) = {pipe_threshold(segs, cfg)}")
        annots = Counter(a.type[1] for a in page.annots() or [])
        print("주석:", dict(annots) or "없음")
        if target:
            n_text = sum(1 for _, _, marks in lines for _, c in marks if color_dist(c, target) <= cfg.color_tol)
            n_line = sum(1 for d in page.get_drawings()
                         if any(float_to_rgb(d.get(k)) and color_dist(float_to_rgb(d.get(k)), target) <= cfg.color_tol
                                for k in ("color", "fill")))
            print(f"{sys.argv[2]} 색: 글자 {n_text}곳, 선/면 {n_line}개")


if __name__ == "__main__":
    main()
