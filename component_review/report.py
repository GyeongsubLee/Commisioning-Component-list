"""기존 Component List와 비교하고 xlsx 리포트를 쓴다."""
import pandas as pd
from openpyxl.styles import PatternFill, Font
from openpyxl.utils import get_column_letter

PIPING_TYPES = {"valve", "special item"}
FILLS = {"MATCH": "C6EFCE", "LIST ONLY": "FFC7CE", "ISO ONLY": "FFEB9C", "OTHER SUBSYSTEM": "F4B084",
         "PID ONLY": "FFEB9C", "OK": "C6EFCE", "수동 검토": "FFC7CE", "확인 권장": "FFEB9C", "무관": "D9D9D9"}

CMP_COLS = ["Subsystem Number", "Tag Number", "Component Type", "결과", "설명",
            "기존 List", "ISO 추출", "PID 색칠", "LINE NO", "ISO", "Reference Document"]
ISO_COLS = ["Subsystem Number", "LINE NO", "ISO", "파일", "Page", "상태", "사유",
            "추출 Tag (영역 안)", "제외 Tag (영역 밖)", "저장 파일", "도면 Line No."]
LINE_COLS = ["Subsystem Number", "Line Number", "결과", "기존 List", "PID 색칠",
             "PID No. (판독된 PID)", "Reference Document (기존 List)", "비고"]
PID_COLS = ["Subsystem Number", "Color Code", "PID 파일", "판독 방식", "새로 읽은 Tag 수", "새로 읽은 Line 수", "비고"]


def compare_tags(subsystems, complist, extracted, iso_rows, pid_tags_by_sub):
    rows = []
    piping = complist[complist["ctype"].str.lower().isin(PIPING_TYPES)]
    owner = {}
    for _, r in piping.iterrows():
        owner.setdefault(r["tag"], set()).add(r["subsystem"])
    for sub in subsystems:
        lst = piping[piping["subsystem"] == sub].drop_duplicates("tag")
        ext = {e["tag"]: e for e in extracted if e["subsystem"] == sub}
        pid_tags = pid_tags_by_sub.get(sub) or {}
        outside = {}   # 이 Subsystem의 ISO에 있지만 영역 밖으로 판단된 Tag -> ISO
        for r in iso_rows:
            if r[0] == sub and r[8]:
                for t in r[8].split(", "):
                    outside.setdefault(t, r[2])
        for _, r in lst.iterrows():
            tag = r["tag"]
            yn_pid = "Y" if tag in pid_tags else "N"
            if tag in ext:
                e = ext[tag]
                rows.append([sub, tag, r["ctype"], "MATCH", "", "Y", "Y", yn_pid, e["line"], e["iso"], r["ref"]])
            else:
                if tag in outside:
                    why, iso = "ISO에는 있으나 PID 색칠 범위 밖으로 판단됨", outside[tag]
                elif yn_pid == "Y":
                    why, iso = "PID에는 색칠되어 있으나 List의 ISO에서 찾지 못함 (ISO 누락/미발행 가능)", ""
                else:
                    why, iso = "PID 색칠 범위에도, List의 ISO에도 없음", ""
                rows.append([sub, tag, r["ctype"], "LIST ONLY", why, "Y", "N", yn_pid, "", iso, r["ref"]])
        listed = set(lst["tag"])
        for tag, e in ext.items():
            if tag in listed:
                continue
            others = sorted(owner.get(tag, set()) - {sub})
            if others:
                rows.append([sub, tag, e["ctype"], "OTHER SUBSYSTEM", "기존 List에는 다른 Subsystem으로 등록: " + ", ".join(others),
                             "N", "Y", "Y", e["line"], e["iso"], e["ref"]])
            else:
                rows.append([sub, tag, e["ctype"], "ISO ONLY", "기존 List에 없음 → 추가 검토", "N", "Y", "Y",
                             e["line"], e["iso"], e["ref"]])
    return rows


def compare_lines(sub, complist, pid):
    lst = complist[(complist["subsystem"] == sub) & (complist["ctype"].str.lower() == "line number")]
    refs = {}
    for _, r in lst.iterrows():
        if r["ref"] and r["ref"] not in refs.setdefault(r["tag"], []):
            refs[r["tag"]].append(r["ref"])
    listed = set(lst["tag"])
    marked = set(pid.line_files)
    stem = lambda s: s[:-4] if s.lower().endswith(".pdf") else s
    rows = []
    for ln in sorted(listed | marked):
        res = "MATCH" if ln in listed and ln in marked else ("LIST ONLY" if ln in listed else "PID ONLY")
        found, ref = pid.line_files.get(ln, []), refs.get(ln, [])
        note = ""
        if found and ref:
            miss = [x for x in ref if stem(x) not in {stem(f) for f in found}]
            extra = [f for f in found if stem(f) not in {stem(x) for x in ref}]
            if miss:
                note = "List의 Reference Document에서는 색칠된 Line을 읽지 못함: " + ", ".join(miss)
            elif extra:
                note = "List에 없는 PID에도 색칠되어 있음: " + ", ".join(extra)
        rows.append([sub, ln, res, "Y" if ln in listed else "N", "Y" if ln in marked else "N",
                     ", ".join(found), ", ".join(ref), note])
    return rows


def _sheet(writer, name, cols, rows, status_col):
    df = pd.DataFrame(rows, columns=cols)
    df.to_excel(writer, sheet_name=name, index=False)
    ws = writer.sheets[name]
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    si = cols.index(status_col) + 1
    for row in ws.iter_rows(min_row=2):
        color = FILLS.get(str(row[si - 1].value))
        if color:
            row[si - 1].fill = PatternFill("solid", start_color=color)
    for i, col in enumerate(cols, 1):
        width = max([len(str(col))] + [len(str(r[i - 1])) for r in rows] or [8])
        ws.column_dimensions[get_column_letter(i)].width = min(max(10, width * 1.3 + 2), 70)


def write(path, cmp_rows, iso_rows, line_rows, pid_rows):
    review = [r for r in iso_rows if r[5] in ("수동 검토", "확인 권장")]
    summary = {}
    for r in cmp_rows:
        summary.setdefault(r[0], {}).setdefault(r[3], 0)
        summary[r[0]][r[3]] += 1
    keys = ["MATCH", "LIST ONLY", "ISO ONLY", "OTHER SUBSYSTEM"]
    sum_rows = [[s] + [v.get(k, 0) for k in keys] for s, v in summary.items()]
    try:
        open(path, "ab").close()
    except PermissionError:   # Excel에서 열려 있는 경우
        from datetime import datetime
        path = path.with_name(f"{path.stem}_{datetime.now():%H%M%S}{path.suffix}")
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        _sheet(w, "요약", ["Subsystem Number"] + keys, sum_rows, "Subsystem Number")
        _sheet(w, "비교 결과", CMP_COLS, cmp_rows, "결과")
        _sheet(w, "Line 비교", LINE_COLS, line_rows, "결과")
        _sheet(w, "ISO 처리 현황", ISO_COLS, iso_rows, "상태")
        _sheet(w, "수동 검토", ISO_COLS, review, "상태")
        _sheet(w, "PID 판독", PID_COLS, pid_rows, "Subsystem Number")
    return path
