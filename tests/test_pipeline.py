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

    lines = {r[1]: r[2] for r in res["lines"]}
    assert lines["305-HI-0007-100-ACB2B05SN53-NN"] == "MATCH"
    assert (work / "pid" / "component_review_report.xlsx").exists()


if __name__ == "__main__":
    test_pipeline()
    print("OK")
