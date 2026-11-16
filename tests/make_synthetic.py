"""실제 도면을 본뜬 가짜 PID / ISO / List를 만든다 (실제 도면은 공유할 수 없으므로 테스트용).
사용: python tests/make_synthetic.py [출력 폴더]"""
import sys
from pathlib import Path
import pandas as pd
import pymupdf

SUB = "12200-01-02-HI-03"
BLUE = (0x5C / 255, 0x8A / 255, 0xB8 / 255)
BLACK = (0, 0, 0)
ISO = "GCC-DLM-DDD-12200-50-4310-TKM-ISO-%05d"
PIDF = "GCC-DLM-DDD-12200-00-0000-TH-PID-%s"


def text(page, p, s, color=BLACK, size=7):
    page.insert_text(p, s, fontsize=size, color=color)


def make_pid(path, no, items, lines):
    """items: [(tag 또는 (code, num), 색)]"""
    doc = pymupdf.open()
    page = doc.new_page(width=1191, height=842)
    page.draw_rect(pymupdf.Rect(20, 20, 1171, 822), color=BLACK, width=1)
    y = 80
    for i, (item, col) in enumerate(items):
        x = 80 + (i % 6) * 170
        y = 120 + (i // 6) * 110
        page.draw_line((x - 40, y + 20), (x + 100, y + 20), color=col, width=1.5)
        if isinstance(item, tuple):  # SPV / 7151B 처럼 두 줄로 나뉜 상자
            page.draw_rect(pymupdf.Rect(x, y - 22, x + 34, y + 2), color=col, width=0.5)
            text(page, (x + 2, y - 13), item[0], col)
            text(page, (x + 10, y - 2), item[1], col)
        else:
            text(page, (x, y + 14), item, col)
    for i, (ln, col) in enumerate(lines):
        page.draw_line((80, 560 + i * 30), (700, 560 + i * 30), color=col, width=1.5)
        text(page, (300, 556 + i * 30), ln, col)
    page.draw_rect(pymupdf.Rect(500, 40, 800, 58), color=BLUE, fill=BLUE)
    text(page, (505, 53), f"{SUB} HP nitrogen supply to polymerization reactor 343-R-301", (1, 1, 1), 8)
    text(page, (900, 800), f"GCC-DLM-DDD-12200-00-0000-TH-PID-{no}", BLACK, 8)
    text(page, (60, 300), "12200-PID-34326", BLACK)   # 다른 PID로 가는 화살표 표기
    doc.save(path)


def make_iso(path, iso_no, line, runs, cont=()):
    """runs: [(점 목록, [(구간 번호, 위치 0~1, Tag, (라벨 dx, dy))])]"""
    doc = pymupdf.open()
    page = doc.new_page(width=1191, height=842)
    page.draw_rect(pymupdf.Rect(20, 20, 1171, 822), color=BLACK, width=1.0)
    text(page, (830, 40), "FABRICATION MATERIALS / МАТЕРИАЛЫ ДЛЯ ИЗГОТОВЛЕНИЯ")
    text(page, (830, 60), "1  PIPE, BE, SMLS, A333-6, STD   150")
    text(page, (30, 650), "LEGEND/УСЛОВНЫЕ ОБОЗНАЧЕНИЯ")
    text(page, (30, 700), f"Line number/Номер линии   {line}")
    text(page, (900, 700), iso_no, size=10)
    text(page, (900, 760), f"Isometric drawing   {line}")
    for pts, valves in runs:
        for i in range(len(pts) - 1):
            a, b = pymupdf.Point(pts[i]), pymupdf.Point(pts[i + 1])
            cuts = sorted(v for v in valves if v[0] == i)
            u = (b - a) / abs(b - a)
            prev = a
            for _, t, tag, off in cuts:
                c = a + (b - a) * t
                page.draw_line(prev, c - u * 8, color=BLACK, width=2.0)
                n = pymupdf.Point(-u.y, u.x) * 5
                for s in (-1, 1):  # 밸브 심볼 (나비 모양, 가는 선)
                    e = c + u * 8 * s
                    page.draw_line(e + n, e - n, color=BLACK, width=0.35)
                    page.draw_line(e + n, c, color=BLACK, width=0.35)
                    page.draw_line(e - n, c, color=BLACK, width=0.35)
                lab = c + pymupdf.Point(off)
                w = 7 * len(tag) * 0.55 + 6
                page.draw_rect(pymupdf.Rect(lab.x, lab.y - 9, lab.x + w, lab.y + 3), color=BLACK, width=0.35)
                text(page, (lab.x + 3, lab.y), tag)
                page.draw_line(c, (lab.x, lab.y - 3), color=BLACK, width=0.35)   # 지시선
                prev = c + u * 8
            page.draw_line(prev, b, color=BLACK, width=2.0)
            # 치수선 (가는 선)
            page.draw_line(a + (0, 18), b + (0, 18), color=BLACK, width=0.35)
    for p, s in cont:
        text(page, p, "CONT. ON(ПРОДОЛЖЕНИЕ НА)")
        text(page, (p[0], p[1] + 9), s)
    doc.save(path)


def build(out):
    out = Path(out)
    iso_dir, pid_dir = out / "iso", out / "pid" / SUB
    iso_dir.mkdir(parents=True, exist_ok=True)
    pid_dir.mkdir(parents=True, exist_ok=True)
    (out / "pid" / "12200-01-99-XX-01").mkdir(exist_ok=True)

    make_pid(pid_dir / (PIDF % "30504.pdf"), "30504",
             [("GV-0071", BLUE), ("GV-0038", BLUE), ("GV-0083", BLUE), ("GV-0134", BLUE),
              (("SPV", "7151A"), BLUE), (("SPV", "7151B"), BLUE), (("PSV", "7151A"), BLUE),
              ("GV-0140", BLACK), (("PIC", "7151"), BLUE)],
             [("305-HI-0008-100-ACB2B05SN53-NN", BLUE), ("305-HI-0007-100-ACB2B05SN53-NN", BLUE),
              ("305-ATM-0116-150-ACB2B02SN53-NN", BLUE), ("305-ATM-0117-150-ACB2B02SN53-NN", BLACK)])
    make_pid(pid_dir / (PIDF % "34301.pdf"), "34301",
             [("GV-0019", BLUE), ("GV-0025", BLUE), ("GV-0064", BLUE), ("GV-0091", BLUE), ("GV-0249", BLUE),
              ("GV-0101", BLUE), (("SPV", "0003"), BLUE), (("STR", "0002"), BLUE), (("SPV", "0002"), BLUE),
              (("PG", "3001"), BLUE), ("GV-0300", BLUE), ("GV-0301", BLUE),
              ("GV-0043", BLACK), ("GV-0162", BLACK), ("BV-0730", BLACK), (("SPV", "0001"), BLACK)],
             [("305-HI-0007-100-ACB2B05SN53-NN", BLUE), ("343-P20-0002-250-ACB2B05SN53-HE", BLACK)])

    make_iso(iso_dir / (ISO % 69 + ".pdf"), ISO % 69, "305-HI-0008",
             [([(150, 300), (300, 380), (300, 200), (600, 100)], [])])
    make_iso(iso_dir / (ISO % 1 + ".pdf"), ISO % 1, "305-ATM-0116",
             [([(150, 500), (250, 430), (400, 500), (400, 250), (700, 400), (700, 100)], [])])
    make_iso(iso_dir / (ISO % 416 + "-Sht01.pdf"), ISO % 416, "305-HI-0007",
             [([(150, 300), (270, 370), (480, 240), (680, 120)],
               [(1, 0.5, "343-GV-0091", (60, 110)), (2, 0.9, "343-SPV-0002", (40, -10))]),
              ([(480, 240), (480, 420)], [(0, 0.8, "343-GV-0064", (60, 20))])],
             cont=[((560, 60), "12200-50-4310/305-HI-0007-ACB2B05SN53-Sht02")])
    make_iso(iso_dir / (ISO % 416 + "-Sht02.pdf"), ISO % 416, "305-HI-0007",
             [([(120, 450), (420, 330), (700, 160)],
               [(0, 0.1, "343-SPV-0003", (40, 40)), (0, 0.3, "343-STR-0002", (-60, -50))]),
              ([(330, 366), (330, 220)], [(0, 0.6, "343-GV-0025", (-110, -30)), (0, 0.95, "343-PG-3001", (20, -10))]),
              ([(420, 330), (420, 180)], [(0, 0.8, "343-GV-0019", (-110, -20))]),
              ([(560, 245), (560, 330)], [(0, 0.7, "343-GV-0249", (50, 30))])],
             cont=[((100, 520), "12200-50-4310/305-HI-0007-ACB2B05SN53-Sht01")])
    # 두 System이 섞인 ISO: GV-0300, GV-0301은 색칠 범위, GV-0043부터는 다른 System
    make_iso(iso_dir / (ISO % 500 + ".pdf"), ISO % 500, "305-HI-0010",
             [([(120, 400), (700, 400)],
               [(0, 0.2, "343-GV-0300", (20, -40)), (0, 0.45, "343-GV-0301", (20, -40)),
                (0, 0.7, "343-GV-0043", (20, -40))]),
              ([(650, 400), (650, 200)], [])])
    # 상관없는 ISO: Tag가 모두 다른 System
    make_iso(iso_dir / (ISO % 501 + ".pdf"), ISO % 501, "343-P20-0002",
             [([(150, 300), (600, 300)], [(0, 0.5, "343-GV-0162", (20, -40))])])

    rows = [(SUB, "305-HI-0008", ISO % 69), (SUB, "305-HI-0007", ISO % 416), (SUB, "305-ATM-0116", ISO % 1),
            (SUB, "305-HI-0007", ISO % 500), (SUB, "343-P20-0002", ISO % 501), (SUB, "305-HI-0007", ISO % 999),
            ("12200-01-01-H-01", "301-H-0003", "GCC-DLM-DDD-12200-08-4304-TKM-ISO-00001")]
    df = pd.DataFrame(rows, columns=["Subsystem Number", "Line No.", "ISO"])
    df["Color Code"] = ["#5C8AB8"] * 6 + ["#954A00"]
    df.to_excel(out / "system_list.xlsx", index=False)

    ref1, ref2 = PIDF % "30504.pdf", PIDF % "34301.pdf"
    comp = [("12200-01-06-P97-03", "302-P-007A", "Equipment", "LP STEAM CONDENSATE PUMP", PIDF % "30204"),
            ("12200-01-23-P40-01", "343-GV-0301", "Valve", "", ref2)]
    comp += [(SUB, f"305-GV-{n}", "Valve", "", ref1) for n in ("0071", "0038", "0083", "0134")]
    comp += [(SUB, f"343-GV-{n}", "Valve", "", ref2) for n in ("0019", "0101", "0064", "0025", "0091", "0249")]
    comp += [(SUB, "305-SPV-7151A", "Special item", "", ref1), (SUB, "305-SPV-7151B", "Special item", "", ref1),
             (SUB, "343-SPV-0003", "Special item", "", ref2), (SUB, "343-STR-0002", "Special item", "", ref2),
             (SUB, "343-SPV-0002", "Special item", "", ref2), (SUB, "343-GV-0043", "Valve", "", ref2),
             (SUB, "305-HI-0008-100-ACB2B05SN53-NN", "Line Number", "", ref1),
             (SUB, "305-HI-0007-100-ACB2B05SN53-NN", "Line Number", "", ref1),
             (SUB, "305-ATM-0116-150-ACB2B02SN53-NN", "Line Number", "", ref1)]
    head = ["№№\n", "Unit\nТитул", "Subsystem Number\nНомер Подсистемы", "Tag Number \nТэговый номер",
            "Component Type\nТип компонента", "Component Description\nОписание компонента",
            "Reference Document\nНомер ссылочного документа"]
    body = [[i, "12200", *c] for i, c in enumerate(comp, 1)]
    pre = [[None] * 7, [None] * 5 + ["Component list", None], [None] * 7,
           [None] * 4 + ["Component type 예시 : Equipment/Piping/Valve/Instrument/Electrical Equipment/Cable", None, None]]
    pd.DataFrame(pre + [head] + body).to_excel(out / "component_list.xlsx", index=False, header=False)
    return out


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "_work"))
