"""가짜 도면으로 전체 과정을 돌려 확인한다. 실행: python tests/test_pipeline.py (pytest도 가능)"""
import csv
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pymupdf  # noqa: E402
from make_synthetic import build, SUB, ISO  # noqa: E402
from component_review.pipeline import run  # noqa: E402

EXPECTED = {"343-GV-0091", "343-GV-0064", "343-SPV-0002", "343-STR-0002", "343-SPV-0003",
            "343-GV-0025", "343-GV-0019", "343-GV-0249", "343-GV-0300", "343-GV-0301"}


def blue_at(pdf, x, y):
    """렌더링한 그림의 (x, y) 픽셀이 파란색 계열인지."""
    doc = pymupdf.open(pdf)
    pix = doc[0].get_pixmap()
    r, g, b = pix.pixel(int(x), int(y))[:3]
    return b > r + 20


def test_pipeline():
    work = Path(__file__).parent / "_work"
    shutil.rmtree(work, ignore_errors=True)
    build(work)
    res = run(work / "iso", work / "pid", work / "system_list.xlsx", work / "component_list.xlsx", log=lambda *_: None)
    folder = work / "pid" / SUB

    tags = {e["tag"] for e in res["extracted"]}
    assert tags == EXPECTED, tags ^ EXPECTED
    types = {e["tag"]: e["ctype"] for e in res["extracted"]}
    assert types["343-SPV-0002"] == "Special item" and types["343-GV-0091"] == "Valve"

    with open(folder / f"{SUB}_extracted.csv", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    assert len(rows) == 11 and rows[1][3] == "343-GV-0091" and rows[1][8] == ISO % 416

    result = {r[1]: r[3] for r in res["compare"] if r[0] == SUB}
    for t in EXPECTED - {"343-GV-0300", "343-GV-0301"}:
        assert result[t] == "MATCH", t
    for t in ("305-GV-0071", "305-GV-0134", "343-GV-0101", "305-SPV-7151A", "343-GV-0043"):
        assert result[t] == "LIST ONLY", t
    assert result["343-GV-0300"] == "ISO ONLY"
    assert result["343-GV-0301"] == "OTHER SUBSYSTEM"
    why = {r[1]: r[4] for r in res["compare"]}
    assert "범위 밖" in why["343-GV-0043"] and "PID에는 색칠" in why["343-GV-0101"]
    assert "343-PG-3001" not in result and "302-P-007A" not in result

    status = {(r[2], r[3]): r[5] for r in res["iso"]}
    assert status[(ISO % 416, ISO % 416 + "-Sht01.pdf")] == "OK"
    assert status[(ISO % 69, ISO % 69 + ".pdf")] == "확인 권장"
    assert status[(ISO % 500, ISO % 500 + ".pdf")] == "수동 검토"
    assert status[(ISO % 501, ISO % 501 + ".pdf")] == "무관"
    assert status[(ISO % 999, "")] == "수동 검토"

    saved = {p.name for p in folder.glob("*_markedup.pdf")}
    assert saved == {ISO % 69 + "_markedup.pdf", ISO % 1 + "_markedup.pdf", ISO % 416 + "-Sht01_markedup.pdf",
                     ISO % 416 + "-Sht02_markedup.pdf", ISO % 500 + "_markedup.pdf"}, saved

    # 섞인 ISO: GV-0043(x=526) 앞까지만 색칠
    mixed = folder / (ISO % 500 + "_markedup.pdf")
    assert blue_at(mixed, 180, 400) and blue_at(mixed, 320, 400) and blue_at(mixed, 236, 400)
    assert not blue_at(mixed, 600, 400) and not blue_at(mixed, 650, 300)
    # 전체 색칠 ISO: 가지 배관과 밸브 위치까지 색칠
    full = folder / (ISO % 416 + "-Sht01_markedup.pdf")
    assert blue_at(full, 480, 300) and blue_at(full, 375, 305)
    assert len(list(pymupdf.open(full)[0].annots())) == 3

    reason = {r[2]: r[6] for r in res["iso"]}
    assert "305-HI-0010" in reason[ISO % 500] and "다름" in reason[ISO % 500]
    assert {r[2]: r[10] for r in res["iso"]}[ISO % 416] == "305-HI-0007"
    lrow = {r[1]: r for r in res["lines"]}
    assert "PID-30504" in lrow["305-HI-0008-100-ACB2B05SN53-NN"][5]
    assert "PID-34301" in lrow["305-HI-0007-100-ACB2B05SN53-NN"][5] and "List에 없는 PID" in lrow["305-HI-0007-100-ACB2B05SN53-NN"][7]
    lines = {r[1]: r[2] for r in res["lines"]}
    assert lines["305-HI-0007-100-ACB2B05SN53-NN"] == "MATCH"
    assert (work / "pid" / "component_review_report.xlsx").exists()


if __name__ == "__main__":
    test_pipeline()
    print("OK")


def _heavy_iso(path, n_lines, pipe_width):
    """선이 아주 많은 ISO (실제 CAD 도면 흉내). pipe_width가 0.35면 굵기로 배관을 구분할 수 없다."""
    import random
    rnd = random.Random(1)
    doc = pymupdf.open()
    page = doc.new_page(width=1191, height=842)
    shape = page.new_shape()
    for _ in range(n_lines):
        x, y = rnd.uniform(30, 780), rnd.uniform(30, 600)
        shape.draw_line((x, y), (x + rnd.uniform(-6, 6), y + rnd.uniform(-6, 6)))
    shape.finish(color=(0, 0, 0), width=0.35)
    shape.commit()
    for a, b in (((100, 300), (392, 300)), ((408, 300), (700, 300))):
        page.draw_line(a, b, color=(0, 0, 0), width=pipe_width)
    page.insert_text((420, 250), "343-GV-0091", fontsize=7)
    page.draw_line((400, 300), (420, 252), color=(0, 0, 0), width=0.35)
    page.insert_text((830, 40), "FABRICATION MATERIALS", fontsize=7)
    page.insert_text((30, 650), "LEGEND", fontsize=7)
    doc.save(path)


def test_heavy_drawings():
    import time
    from component_review.config import Config
    from component_review.iso_reader import read_iso
    from component_review.matcher import select
    work = Path(__file__).parent / "_work"
    work.mkdir(exist_ok=True)
    cfg = Config()

    _heavy_iso(work / "heavy.pdf", 30000, 2.0)
    t0 = time.time()
    page = read_iso(work / "heavy.pdf", cfg)[0]
    sel = select(page, {"343-GV-0091": ""}, "305-HI-0007", {}, cfg)
    took = time.time() - t0
    assert took < 20, took
    assert len(page.pipes) == 2 and sel.status == "OK" and len(sel.strokes) == 3
    assert abs(page.tags[0].anchor[1] - 300) < 1 and 390 < page.tags[0].anchor[0] < 410

    _heavy_iso(work / "flat.pdf", 30000, 0.35)   # 굵기 구분 불가 -> 색칠 없이 수동 검토로 넘어가야 함
    t0 = time.time()
    page = read_iso(work / "flat.pdf", cfg)[0]
    sel = select(page, {"343-GV-0091": ""}, "305-HI-0007", {}, cfg)
    assert time.time() - t0 < 20
    assert not page.pipes and sel.status == "수동 검토" and sel.in_tags and not sel.strokes
    # Tag가 없고 배관도 못 찾으면 "색칠되지 않음"으로 표시되어야 한다
    tags = page.tags
    page.tags = []
    sel = select(page, {}, "305-HI-0007", {"305-HI-0007": "x"}, Config())
    assert sel.status == "수동 검토" and "색칠되지 않음" in sel.reason, sel.reason
    assert "PCV" in cfg.excluded_prefixes

    # 실제 도면 형태: 선 굵기는 모두 같고 배관은 채워진 사각형으로 그려짐
    doc = pymupdf.open(work / "flat.pdf")
    pg = doc[0]
    for (x0, y0), (x1, y1) in (((100, 300), (392, 300)), ((408, 300), (700, 300)), ((500, 300), (600, 200))):
        ux, uy = x1 - x0, y1 - y0
        L = (ux * ux + uy * uy) ** 0.5
        nx, ny = -uy / L * 1.2, ux / L * 1.2
        pg.draw_quad(pymupdf.Quad((x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x0 - nx, y0 - ny), (x1 - nx, y1 - ny)),
                     color=None, fill=(0, 0, 0))
    pg.draw_polyline([(300, 500), (306, 497), (306, 503), (300, 500)], color=None, fill=(0, 0, 0))  # 화살촉
    doc.save(work / "quads.pdf")
    page = read_iso(work / "quads.pdf", cfg)[0]
    assert page.method == "채워진 도형" and len(page.pipes) == 3, (page.method, len(page.pipes))
    sel = select(page, {"343-GV-0091": ""}, "305-HI-0007", {}, cfg)
    assert sel.status == "OK" and len(sel.strokes) >= 4
    assert abs(page.tags[0].anchor[1] - 300) < 1.5 and 390 < page.tags[0].anchor[0] < 410
    from component_review.marker import save_marked
    save_marked(work / "quads.pdf", work / "quads_markedup.pdf", {0: sel}, (0x5C, 0x8A, 0xB8), cfg)
    assert blue_at(work / "quads_markedup.pdf", 250, 303) and blue_at(work / "quads_markedup.pdf", 550, 253)
    return took


if __name__ == "__main__":
    print("heavy ISO: %.1f초" % test_heavy_drawings())
