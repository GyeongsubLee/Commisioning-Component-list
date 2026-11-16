"""Subsystem-ISO List, 기존 Component List 읽기."""
from pathlib import Path
import pandas as pd


def _read_raw(path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in (".csv", ".txt"):
        for enc in ("utf-8-sig", "cp949", "cp1251"):
            try:
                return pd.read_csv(path, header=None, dtype=str, encoding=enc, sep=None, engine="python")
            except UnicodeDecodeError:
                continue
        raise ValueError(f"인코딩을 알 수 없는 파일: {path}")
    return pd.read_excel(path, header=None, dtype=str)


def _table(path, required: dict) -> pd.DataFrame:
    """required: {표준이름: 헤더에 들어 있는 글자}. 헤더 행을 찾아 표준이름 열만 돌려준다."""
    raw = _read_raw(path)
    for r in range(min(30, len(raw))):
        cells = [str(v).lower() if pd.notna(v) else "" for v in raw.iloc[r]]
        cols = {}
        for name, key in required.items():
            hit = [i for i, c in enumerate(cells) if key in c]
            if hit:
                cols[name] = hit[0]
        if len(cols) == len(required):
            df = raw.iloc[r + 1:, list(cols.values())].copy()
            df.columns = list(cols.keys())
            df = df.apply(lambda s: s.astype("string").str.strip())
            return df.fillna("").reset_index(drop=True)
    raise ValueError(f"{Path(path).name}: 헤더({', '.join(required.values())})를 찾지 못했습니다.")


def read_system_list(path) -> pd.DataFrame:
    df = _table(path, {"subsystem": "subsystem", "line": "line no", "iso": "iso", "color": "color"})
    df = df[(df.subsystem != "") & (df.iso != "")]
    return df.reset_index(drop=True)


def read_component_list(path) -> pd.DataFrame:
    df = _table(path, {"unit": "unit", "subsystem": "subsystem number", "tag": "tag number",
                       "ctype": "component type", "desc": "component description",
                       "ref": "reference document"})
    df = df[(df.subsystem != "") & (df.tag != "")]
    return df.reset_index(drop=True)
