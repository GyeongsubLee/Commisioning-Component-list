"""전체 실행: Subsystem별로 PID 읽기 -> ISO 색칠/추출 -> CSV -> 비교 리포트."""
import csv
import re
from pathlib import Path

from .config import Config, hex_to_rgb
from .inputs import read_system_list, read_component_list
from .pid_reader import read_pid_folder
from .iso_reader import read_iso
from .matcher import select, NA, REVIEW
from .marker import save_marked
from . import report

CSV_HEADER = ["№№", "Unit\nТитул", "Subsystem Number\nНомер Подсистемы", "Tag Number\nТэговый номер",
              "Component Type\nТип компонента", "Component Description\nОписание компонента",
              "Reference Document\nНомер ссылочного документа", "LINE NO", "ISO"]


def find_iso_files(iso_dir: Path, index: dict, iso_no: str):
    return sorted(p for p in index.get("all", []) if iso_no.upper() in p.stem.upper())


def run(iso_dir, pid_root, system_list, component_list, subsystems=None, report_dir=None,
        cfg: Config = None, log=print):
    cfg = cfg or Config()
    iso_dir, pid_root = Path(iso_dir), Path(pid_root)
    report_dir = Path(report_dir) if report_dir else pid_root
    syslist = read_system_list(system_list)
    complist = read_component_list(component_list)
    iso_index = {"all": [p for p in iso_dir.rglob("*.pdf") if "_markedup" not in p.stem.lower()]}
    iso_owner = syslist.groupby("iso")["subsystem"].nunique().to_dict()
    # Line No.(305-HI-0007)가 Tag로 잘못 읽히지 않도록 Line service code를 제외 목록에 추가
    for ln in syslist["line"]:
        parts = str(ln).split("-")
        if len(parts) >= 2 and re.fullmatch(r"[A-Z]{2,4}", parts[1]):
            cfg.excluded_prefixes.add(parts[1])

    wanted = [s.strip() for s in subsystems if s.strip()] if subsystems else list(dict.fromkeys(syslist["subsystem"]))
    extracted, iso_rows, pid_rows, line_rows = [], [], [], []
    cache = {}
    pid_tags_by_sub = {}

    for sub in wanted:
        rows = syslist[syslist["subsystem"] == sub]
        folder = pid_root / sub
        if rows.empty:
            pid_rows.append([sub, "", "", 0, 0, "Subsystem-ISO List에 없음"])
            log(f"[{sub}] Subsystem-ISO List에 없음 - 건너뜀")
            continue
        if not folder.is_dir():
            pid_rows.append([sub, "", "", 0, 0, "Marked up PID 폴더 없음 - 건너뜀"])
            log(f"[{sub}] PID 폴더 없음 - 건너뜀")
            continue
        try:
            rgb = hex_to_rgb(rows.iloc[0]["color"])
        except ValueError as e:
            pid_rows.append([sub, "", "", 0, 0, str(e)])
            continue
        pid = read_pid_folder(folder, rgb, cfg)
        pid_tags_by_sub[sub] = pid.tags
        pid_rows.append([sub, rows.iloc[0]["color"], ", ".join(pid.files), len(pid.tags), len(pid.lines),
                         f"판독 방식: {pid.mode}" + ("; " + "; ".join(pid.notes) if pid.notes else "")])
        log(f"[{sub}] PID {len(pid.files)}개: Tag {len(pid.tags)}, Line {len(pid.lines)} ({pid.mode})")

        sub_ext, seen_tags = [], set()
        done = set()
        for _, row in rows.iterrows():
            iso_no, line_key = row["iso"], row["line"]
            if (iso_no, line_key) in done:
                continue
            done.add((iso_no, line_key))
            files = find_iso_files(iso_dir, iso_index, iso_no)
            if not files:
                iso_rows.append([sub, line_key, iso_no, "", "", REVIEW, "ISO PDF 파일을 찾지 못함", "", "", ""])
                continue
            for f in files:
                if f not in cache:
                    try:
                        cache[f] = read_iso(f, cfg)
                    except Exception as e:  # 손상된 PDF 등
                        cache[f] = e
                if isinstance(cache[f], Exception):
                    iso_rows.append([sub, line_key, iso_no, f.name, "", REVIEW, f"PDF 읽기 실패: {cache[f]}", "", "", ""])
                    continue
                sels = {}
                for page in cache[f]:
                    sel = select(page, pid.tags, line_key, pid.lines, cfg)
                    if iso_owner.get(iso_no, 1) > 1 and sel.status != NA:
                        sel.status = REVIEW
                        sel.reason = (sel.reason + " / " if sel.reason else "") + "이 ISO는 여러 Subsystem의 List에 있음"
                    saved = ""
                    if sel.status != NA and (sel.strokes or sel.in_tags):
                        sels[page.index] = sel
                        saved = f.stem + "_markedup.pdf"
                    iso_rows.append([sub, line_key, iso_no, f.name, page.index + 1, sel.status, sel.reason,
                                     ", ".join(sorted({t.tag for t in sel.in_tags})),
                                     ", ".join(sorted({t.tag for t in sel.out_tags})), saved])
                    for t in sel.in_tags:
                        if t.tag in seen_tags:
                            continue
                        seen_tags.add(t.tag)
                        sub_ext.append({"unit": sub.split("-")[0], "subsystem": sub, "tag": t.tag,
                                        "ctype": cfg.classify(t.prefix), "ref": pid.tags.get(t.tag, ""),
                                        "line": line_key, "iso": iso_no})
                if sels:
                    save_marked(f, folder / (f.stem + "_markedup.pdf"), sels, rgb, cfg)

        with open(folder / f"{sub}_extracted.csv", "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(CSV_HEADER)
            for i, e in enumerate(sub_ext, 1):
                w.writerow([i, e["unit"], e["subsystem"], e["tag"], e["ctype"], "", e["ref"], e["line"], e["iso"]])
        extracted.extend(sub_ext)
        line_rows.extend(report.compare_lines(sub, complist, pid))
        log(f"[{sub}] 추출 Tag {len(sub_ext)}개")

    processed = [r[0] for r in pid_rows if not r[5].endswith("건너뜀") and "List에 없음" not in r[5]]
    cmp_rows = report.compare_tags(processed, complist, extracted, iso_rows, pid_tags_by_sub)
    out = report_dir / "component_review_report.xlsx"
    report.write(out, cmp_rows, iso_rows, line_rows, pid_rows)
    log(f"리포트: {out}")
    return {"report": out, "compare": cmp_rows, "iso": iso_rows, "extracted": extracted, "lines": line_rows}
