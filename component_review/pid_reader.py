"""Marked up PID에서 Color Code 색으로 표시된 Tag / Line No.를 읽는다."""
import re
from dataclasses import dataclass, field
from pathlib import Path
import pymupdf

from .config import Config, color_dist, int_to_rgb, float_to_rgb

PID_NO_RE = re.compile(r"PID-(\d{5})")
BARE_NUM_RE = re.compile(r"^\d{4}[A-Z]?$")


@dataclass
class PidResult:
    tags: dict = field(default_factory=dict)    # tag -> PID 파일명
    lines: dict = field(default_factory=dict)   # '305-HI-0007' -> 전체 Line No.
    line_files: dict = field(default_factory=dict)  # 전체 Line No. -> [PID 파일명]
    files: list = field(default_factory=list)
    mode: str = ""                              # 'text-color' / 'near-colored-line' / 'none'
    notes: list = field(default_factory=list)
    per_file: list = field(default_factory=list)  # [파일, 방식, Tag 수, Line 수, 비고]


def text_lines(page):
    """[(text, rect, [(start_idx, rgb)])] - 한 줄 단위 글자와 글자색."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text, marks = "", []
            for span in line["spans"]:
                marks.append((len(text), int_to_rgb(span["color"])))
                text += span["text"]
            if text.strip():
                out.append((text, pymupdf.Rect(line["bbox"]), marks))
    return out


def _color_at(marks, idx):
    col = marks[0][1]
    for start, c in marks:
        if start <= idx:
            col = c
    return col


def _colored_geometry(page, rgb, tol):
    """색칠된 선/주석의 사각형 목록."""
    rects = []
    for d in page.get_drawings():
        for key in ("color", "fill"):
            c = float_to_rgb(d.get(key))
            if c and color_dist(c, rgb) <= tol:
                rects.append(pymupdf.Rect(d["rect"]))
                break
    for a in page.annots() or []:
        cols = a.colors or {}
        for key in ("stroke", "fill"):
            c = float_to_rgb(cols.get(key)) if cols.get(key) else None
            if c and color_dist(c, rgb) <= tol:
                rects.append(pymupdf.Rect(a.rect))
                break
    return rects


def _near(rect, rects, dist):
    big = rect + (-dist, -dist, dist, dist)
    return any(big.intersects(r) for r in rects)


def _unit_of(page_text, filename):
    hits = re.findall(r"TH-PID-(\d{5})", page_text) or PID_NO_RE.findall(filename)
    if not hits:
        return None
    return max(set(hits), key=hits.count)[:3]


def read_pid_folder(folder, rgb, cfg: Config, log=None) -> PidResult:
    res = PidResult()
    pdfs = sorted(p for p in Path(folder).glob("*.pdf")
                  if "_markedup" not in p.stem.lower() and "-ISO-" not in p.stem.upper())
    modes = set()
    for n_file, pdf in enumerate(pdfs, 1):
        res.files.append(pdf.name)
        n_tag0, n_line0, fmodes = len(res.tags), len(res.lines), set()
        doc = pymupdf.open(pdf)
        for page in doc:
            page.remove_rotation()
            lines = text_lines(page)
            unit = _unit_of(page.get_text(), pdf.name)
            if unit is None:
                res.notes.append(f"{pdf.name} p{page.number + 1}: PID 번호를 읽지 못함 (Unit 접두어 없는 Tag는 제외됨)")

            def scan(is_marked):
                found = False
                nums = []  # 색칠된 번호만 있는 글자 (SPV / 7151B 처럼 두 줄로 나뉜 경우)
                codes = []
                for text, rect, marks in lines:
                    t = text.strip()
                    if not is_marked(rect, marks, 0):
                        marked_any = any(is_marked(rect, marks, m.start())
                                         for m in list(cfg.pid_tag_re.finditer(text)) + list(cfg.line_re.finditer(text)))
                        if not marked_any:
                            continue
                    if BARE_NUM_RE.match(t):
                        nums.append((t, rect))
                    elif t in cfg.special_prefixes:
                        codes.append((t, rect))
                    for m in cfg.line_re.finditer(text):
                        if is_marked(rect, marks, m.start()):
                            res.lines.setdefault(m.group(1), m.group(0))
                            lf = res.line_files.setdefault(m.group(0), [])
                            if pdf.name not in lf:
                                lf.append(pdf.name)
                            found = True
                    for m in cfg.pid_tag_re.finditer(text):
                        u, pre, num = m.groups()
                        if pre in cfg.excluded_prefixes or not is_marked(rect, marks, m.start()):
                            continue
                        u = u or unit
                        if u:
                            res.tags.setdefault(f"{u}-{pre}-{num}", pdf.name)
                            found = True
                for code, crect in codes:
                    cc = (crect.tl + crect.br) / 2
                    best = None
                    for num, nrect in nums:
                        d = abs((nrect.tl + nrect.br) / 2 - cc)
                        if d <= 3.0 * max(crect.height, 4) and (best is None or d < best[0]):
                            best = (d, num)
                    if best and unit:
                        res.tags.setdefault(f"{unit}-{code}-{best[1]}", pdf.name)
                        found = True
                return found

            by_text = scan(lambda rect, marks, idx: color_dist(_color_at(marks, idx), rgb) <= cfg.color_tol)
            if by_text:
                fmodes.add("text-color")
            else:
                geo = _colored_geometry(page, rgb, cfg.color_tol)
                if geo and scan(lambda rect, marks, idx: _near(rect, geo, cfg.pid_near_dist)):
                    fmodes.add("near-colored-line")
        doc.close()
        modes |= fmodes
        fmode = "+".join(sorted(fmodes)) or "못 읽음"
        note = ""
        if "near-colored-line" in fmodes:
            note = "글자 색 없음 → 색칠된 선 근처 기준, Tag가 과하게 잡힐 수 있음 (확인 필요)"
        elif not fmodes:
            note = "Color Code 색의 글자/선 없음"
        row = [pdf.name, fmode, len(res.tags) - n_tag0, len(res.lines) - n_line0, note]
        res.per_file.append(row)
        if log:
            log(f"  PID [{n_file}/{len(pdfs)}] {pdf.name} … 새 Tag {row[2]}, 새 Line {row[3]} ({fmode})")
    res.mode = "+".join(sorted(modes)) or "none"
    if not pdfs:
        res.notes.append("Marked up PID PDF가 폴더에 없음")
    elif res.mode == "none":
        res.notes.append("Color Code 색의 글자/선을 PID에서 찾지 못함")
    return res
