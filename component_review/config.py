"""설정값. 실제 도면에 맞지 않으면 여기 숫자만 바꾸면 된다."""
import re
from dataclasses import dataclass, field


@dataclass
class Config:
    # --- Tag 인식 ---
    # ISO의 Tag: 343-GV-0091, 305-SPV-7151A ...
    tag_re: re.Pattern = re.compile(r"(?<![\w/\-])(\d{3})-([A-Z]{2,4})-(\d{4}[A-Z]?)(?![\w\-])")
    # PID의 Tag: GV-0134 (Unit 접두어 없음) 또는 343-GV-0134
    pid_tag_re: re.Pattern = re.compile(r"(?<![\w/\-])(?:(\d{3})-)?([A-Z]{2,4})-(\d{4}[A-Z]?)(?![\w\-])")
    # Line No.: 305-HI-0007-100-ACB2B05SN53-NN
    line_re: re.Pattern = re.compile(r"(?<![\w/\-])(\d{3}-[A-Z]{1,4}\d{0,2}-\d{4})-\d{2,4}-[A-Z0-9]+-[A-Z]{1,3}(?![\w\-])")
    # Piping 범위가 아닌 접두어 (계장 item, PSV 등) -> 추출하지 않음
    excluded_prefixes: set = field(default_factory=lambda: {
        "PG", "PI", "PT", "PIC", "PDT", "PDI", "PSV", "PRV", "PVRV", "TSV", "RD",
        "TG", "TI", "TE", "TT", "TW", "TIC", "FT", "FI", "FE", "FIC", "FQ", "FO",
        "FV", "PV", "LV", "TV", "HV", "XV", "XZV", "UV", "MOV", "SDV", "BDV",
        "LT", "LG", "LIC", "LS", "AT", "AE", "AI", "HS", "ZS", "ZT", "XA", "SP",
    })
    # Special item으로 분류할 접두어. 그 외는 Valve.
    special_prefixes: set = field(default_factory=lambda: {
        "SPV", "STR", "SG", "FA", "EJ", "HO", "ST", "SPB", "SB", "TS", "SIL", "INJ", "MIX",
    })

    # --- 색 ---
    color_tol: float = 40.0      # Color Code와의 RGB 거리 허용치 (0~441)
    pid_near_dist: float = 20.0  # 글자가 검정일 때: 색칠된 선에서 이 거리(pt) 안의 Tag를 사용

    # --- ISO 배관선 ---
    pipe_min_width: float = 0.0  # 0이면 자동 (가장 굵은 선 군집). inspect_pdf 결과로 지정 가능
    pipe_width_ratio: float = 0.6  # 자동일 때: 최대 굵기의 이 비율 이상을 배관으로 봄
    gap_tol: float = 20.0        # 밸브 심볼 등으로 끊긴 배관을 이어주는 최대 간격(pt)
    anchor_radius: float = 26.0  # Tag 위치와 배관 끊김 지점을 같은 곳으로 보는 반경(pt)
    leader_touch: float = 6.0    # Tag 글자와 지시선 시작점 사이 허용 거리(pt)
    leader_depth: int = 4

    # --- 색칠 모양 ---
    mark_width: float = 7.0
    mark_opacity: float = 0.45
    tag_highlight: tuple = (1.0, 1.0, 0.0)

    def classify(self, prefix: str) -> str:
        return "Special item" if prefix in self.special_prefixes else "Valve"


def hex_to_rgb(code: str):
    s = str(code).strip().lstrip("#")
    if len(s) != 6:
        raise ValueError(f"Color Code 형식 오류: {code!r}")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def color_dist(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def int_to_rgb(v: int):
    return ((v >> 16) & 255, (v >> 8) & 255, v & 255)


def float_to_rgb(c):
    if c is None:
        return None
    if len(c) == 1:
        c = (c[0],) * 3
    if len(c) == 4:  # CMYK
        cc, m, y, k = c
        c = ((1 - cc) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    return tuple(int(round(x * 255)) for x in c[:3])
