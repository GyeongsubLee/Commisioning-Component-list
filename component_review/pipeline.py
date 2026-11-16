"""전체 실행: Subsystem별로 PID 읽기 -> ISO 색칠/추출 -> CSV -> 비교 리포트."""
import csv
import re
import time
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
ISO_KEY_RE = re.compile(r"ISO-\d+", re.I)


def say(*a):
    print(*a, flush=True)


def index_iso_files(iso_dir: Path):
    """파일명 안의 'ISO-00416' 부분으로 찾을 수 있게 미리 정리한다."""
    files = [p for p in iso_dir.rglob("*.pdf") if "_markedup" not in p.stem.lower()]
    by_key = {}
    for p in files:
        for k in ISO_KEY_RE.findall(p.stem.upper()):
            by_key.setdefault(k, []).append(p)
    return files, by_key


def find_iso_files(index, iso_no: str):
    files, by_key = index
    iso_no = iso_no.upper()
    keys = ISO_KEY_RE.findall(iso_no)
    pool = by_key.get(keys[-1], []) if keys else files
    return sorted(p for p in pool if iso_no in p.stem.upper())


def run(iso_dir, pid_root, system_list, component_list, subsystems=None, report_dir=None,
        cfg: Config = None, log=say):
    t_start = time.time()
    cfg = cfg or Config()
    iso_dir, pid_root = Path(iso_dir), Path(pid_root)
    report_dir = Path(report_dir) if report_dir else pid_root
    syslist = read_system_list(system_list)
    complist = read_component_list(component_list)
    log(f"ISO 폴더 파일 목록 읽는 중: {iso_dir}")
    iso_index = index_iso_files(iso_dir)
    iso_owner = syslist.groupby("iso")["subsystem"].nunique().to_dict()
    # Line No.(305-HI-0007)가 Tag로 잘못 읽히지 않도록 Line service code를 제외 목록에 추가
    for ln in syslist["line"]:
        parts = str(ln).split("-")
        if len(parts) >= 2 and re.fullmatch(r"[A-Z]{2,4}", parts[1]):
            cfg.excluded_prefixes.add(parts[1])

    wanted = [s.strip() for s in subsystems if s.strip()] if subsystems else list(dict.fromkeys(syslist["subsystem"]))
    if not subsystems:
        skipped = [s for s in wanted if not (pid_root / s).is_dir()]
        wanted = [s for s in wanted if (pid_root / s).is_dir()]
    else:
        skipped = []
    log(f"ISO PDF {len(iso_index[0])}개, 처리할 Subsystem {len(wanted)}개"
        + (f" (PID 폴더가 없어 건너뛰는 Subsystem {len(skipped)}개)" if skipped else ""))

    extracted, iso_rows, pid_rows, line_rows = [], [], [], []
    processed, pid_tags_by_sub, cache = [], {}, {}
    for s in skipped:
        pid_rows.append([s, "", "", "", 0, 0, "Marked up PID 폴더 없음 - 건너뜀"])
    out = report_dir / "component_review_report.xlsx"

    def save_report():
        cmp_rows = report.compare_tags(processed, complist, extracted, iso_rows, pid_tags_by_sub)
        return cmp_rows, report.write(out, cmp_rows, iso_rows, line_rows, pid_rows)

    def do_subsystem(n_sub, sub):
        t_sub = time.time()
        log(f"\n=== [{n_sub}/{len(wanted)}] {sub} ===")
        rows = syslist[syslist["subsystem"] == sub]
        folder = pid_root / sub
        if rows.empty:
            pid_rows.append([sub, "", "", "", 0, 0, "Subsystem-ISO List에 없음 - 건너뜀"])
            log("  Subsystem-ISO List에 없음 - 건너뜀")
            return
        if not folder.is_dir():
            pid_rows.append([sub, "", "", "", 0, 0, "Marked up PID 폴더 없음 - 건너뜀"])
            log(f"  PID 폴더 없음 - 건너뜀: {folder}")
            return
        try:
            rgb = hex_to_rgb(rows.iloc[0]["color"])
        except ValueError as e:
            pid_rows.append([sub, "", "", "", 0, 0, f"{e} - 건너뜀"])
            log(f"  {e} - 건너뜀")
            return
        color = rows.iloc[0]["color"]
        pid = read_pid_folder(folder, rgb, cfg, log)
        pid_tags_by_sub[sub] = pid.tags
        processed.append(sub)
        for f, mode, nt, nl, note in pid.per_file:
            pid_rows.append([sub, color, f, mode, nt, nl, note])
        for note in pid.notes:
            pid_rows.append([sub, color, "", "", 0, 0, note])
        log(f"  PID {len(pid.files)}개 판독 완료: Tag {len(pid.tags)}, Line {len(pid.lines)}")

        # 처리할 ISO 파일 목록을 먼저 만든다 (진행률 표시용)
        tasks, done = [], set()
        for _, row in rows.iterrows():
            iso_no, line_key = row["iso"], row["line"]
            if (iso_no, line_key) in done:
                continue
            done.add((iso_no, line_key))
            files = find_iso_files(iso_index, iso_no)
            if not files:
                iso_rows.append([sub, line_key, iso_no, "", "", REVIEW, "ISO PDF 파일을 찾지 못함", "", "", "", ""])
                log(f"  ISO 파일 없음: {iso_no}")
            tasks.extend((iso_no, line_key, f) for f in files)

        sub_ext, seen_tags, n_review = [], set(), 0
        for n, (iso_no, line_key, f) in enumerate(tasks, 1):
            t0 = time.time()
            head = f"  ISO [{n}/{len(tasks)}] {f.name}"
            print(head + " … 읽는 중", end="\r", flush=True) if log is say else None
            if f not in cache:
                try:
                    cache[f] = read_iso(f, cfg)
                except Exception as e:  # 손상된 PDF 등
                    cache[f] = e
            if isinstance(cache[f], Exception):
                iso_rows.append([sub, line_key, iso_no, f.name, "", REVIEW, f"PDF 읽기 실패: {cache[f]}", "", "", "", ""])
                log(f"{head} … 읽기 실패: {cache[f]}")
                n_review += 1
                continue
            sels, states, n_in = {}, [], 0
            for page in cache[f]:
                sel = select(page, pid.tags, line_key, pid.lines, cfg)
                if iso_owner.get(iso_no, 1) > 1 and sel.status != NA:
                    sel.status = REVIEW
                    sel.reason = (sel.reason + " / " if sel.reason else "") + "이 ISO는 여러 Subsystem의 List에 있음"
                if page.line and page.line != line_key and sel.status != NA:
                    sel.status = REVIEW
                    sel.reason = (sel.reason + " / " if sel.reason else "") + \
                        f"도면의 Line No.({page.line})가 List({line_key})와 다름"
                saved = ""
                if sel.status != NA and (sel.strokes or sel.in_tags):
                    sels[page.index] = sel
                    saved = f.stem + "_markedup.pdf"
                states.append(sel.status)
                n_in += len({t.tag for t in sel.in_tags})
                n_review += sel.status == REVIEW
                iso_rows.append([sub, line_key, iso_no, f.name, page.index + 1, sel.status, sel.reason,
                                 ", ".join(sorted({t.tag for t in sel.in_tags})),
                                 ", ".join(sorted({t.tag for t in sel.out_tags})), saved, page.line])
                for t in sel.in_tags:
                    if t.tag in seen_tags:
                        continue
                    seen_tags.add(t.tag)
                    sub_ext.append({"unit": sub.split("-")[0], "subsystem": sub, "tag": t.tag,
                                    "ctype": cfg.classify(t.prefix), "ref": pid.tags.get(t.tag, ""),
                                    "line": line_key, "iso": iso_no})
            if sels:
                try:
                    save_marked(f, folder / (f.stem + "_markedup.pdf"), sels, rgb, cfg)
                except Exception as e:
                    iso_rows.append([sub, line_key, iso_no, f.name, "", REVIEW, f"저장 실패: {e}", "", "", "", ""])
                    states.append(f"저장 실패({e})")
            log(f"{head} … {'/'.join(dict.fromkeys(states))}, Tag {n_in}개, {time.time() - t0:.1f}초")

        with open(folder / f"{sub}_extracted.csv", "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(CSV_HEADER)
            for i, e in enumerate(sub_ext, 1):
                w.writerow([i, e["unit"], e["subsystem"], e["tag"], e["ctype"], "", e["ref"], e["line"], e["iso"]])
        extracted.extend(sub_ext)
        line_rows.extend(report.compare_lines(sub, complist, pid))
        log(f"  완료: 추출 Tag {len(sub_ext)}개, 수동 검토 {n_review}건, {time.time() - t_sub:.0f}초")

    interrupted = False
    try:
        for n_sub, sub in enumerate(wanted, 1):
            do_subsystem(n_sub, sub)
            save_report()   # 중간에 꺼도 여기까지의 결과는 남는다
    except KeyboardInterrupt:
        interrupted = True
        log("\n중단됨 (Ctrl+C) - 지금까지의 결과로 리포트를 저장합니다.")
    cmp_rows, out = save_report()
    log(f"\n리포트: {out}  (총 {time.time() - t_start:.0f}초)")
    return {"report": out, "compare": cmp_rows, "iso": iso_rows, "extracted": extracted, "lines": line_rows,
            "interrupted": interrupted}
