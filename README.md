# Commissioning Component List 검토 프로그램

Marked up PID(Subsystem별로 색칠된 P&ID)를 기준으로 ISO를 같은 색으로 색칠하고,
색칠된 영역의 Valve / Special item Tag를 뽑아 기존 Component List와 비교합니다.

## 설치 (Windows, Python 3.10 이상)

```bash
pip install -r requirements.txt
```

## 실행

```bash
python -m component_review
```

창이 차례로 뜨면 다음을 지정합니다.

1. ISO PDF 폴더 (하위 폴더 포함 검색, 파일명에 ISO No.가 들어 있어야 함)
2. Marked up PID 폴더 — 그 안에 `12200-01-02-HI-03` 같은 Subsystem Number 이름의 폴더가 있고, 각 폴더에 그 Subsystem의 Marked up PID PDF가 있어야 함
3. Subsystem-ISO List (열: Subsystem Number, Line No., ISO, Color Code)
4. 기존 Component List
5. 처리할 Subsystem Number (비우면 PID 폴더가 있는 전체)

창 없이 실행하려면:

```bash
python -m component_review --iso-dir "D:\ISO" --pid-root "D:\PID" --system-list list.xlsx --component-list comp.xlsx --subsystem 12200-01-02-HI-03
```

실행 중에는 PID와 ISO 파일마다 한 줄씩 진행 상황(`ISO [17/120] 파일명 … OK, Tag 3개, 2.1초`)이 표시됩니다.
Subsystem 하나가 끝날 때마다 리포트를 저장하므로, Ctrl+C로 중단해도 그때까지의 결과가 남습니다.

## 결과

| 위치 | 파일 | 내용 |
|---|---|---|
| Subsystem PID 폴더 | `<ISO 파일명>_markedup.pdf` | Color Code 색으로 배관 색칠 + Tag 형광펜. 원본 ISO는 그대로 둠 |
| Subsystem PID 폴더 | `<Subsystem>_extracted.csv` | 추출된 Tag (Component List 양식 + LINE NO, ISO) |
| Marked up PID 폴더 | `component_review_report.xlsx` | 비교 리포트 |

리포트 시트

- **요약** — Subsystem별 건수
- **비교 결과** — Tag별 `MATCH` / `LIST ONLY`(기존 List에만 있음) / `ISO ONLY`(ISO에만 있음, 추가 검토) / `OTHER SUBSYSTEM`(다른 Subsystem으로 등록됨)와 그 이유
- **Line 비교** — 기존 List의 Line Number와 PID에 색칠된 Line No. 대조, 그 Line을 읽은 PID No.
- **ISO 처리 현황** — ISO 한 장마다 `OK` / `확인 권장` / `수동 검토` / `무관`
- **수동 검토** — 사람이 꼭 봐야 하는 ISO만 모음
- **PID 판독** — PID에서 읽은 Tag / Line 수

## 판단 기준

- PID에서 Color Code 색의 글자를 그 Subsystem의 Tag로 봅니다. `GV-0134`처럼 접두어가 없으면 PID 번호(`PID-30504` → `305`)를 붙입니다.
- Tag의 첫 부분(`301-GV-0048`의 `301`)은 PID 번호를 따르는 System code입니다. Line No.의 번호(`311-P16-0016`의 `311`)와 달라도 정상이며, 프로그램은 둘을 비교하지 않습니다.
- ISO 한 개는 Line No. 하나만 가집니다. 리포트의 "도면 Line No." 열은 List에 Line–ISO 짝이 잘못 적힌 경우를 찾기 위한 점검용입니다.
- ISO의 Tag가 모두 PID 색칠 범위면 ISO 전체를 색칠합니다 (`OK`).
- 범위 안/밖 Tag가 섞여 있으면 범위 안 Tag에서 배관을 따라가다 범위 밖 Tag에서 멈춥니다. 경계가 정확한지는 보장할 수 없어 `수동 검토`로 표시합니다.
- Tag가 모두 범위 밖이면 상관없는 ISO로 보고 저장하지 않습니다 (`무관`).
- Tag가 없는 ISO는 Line No.가 PID에 색칠되어 있으면 전체를 색칠하고 `확인 권장`으로 표시합니다.
- 계장 item, PSV 등은 추출하지 않습니다. 접두어 목록은 `component_review/config.py`의 `excluded_prefixes`, Special item 접두어는 `special_prefixes`에서 고칩니다.

## 실제 도면에서 결과가 이상할 때

이 프로그램은 실제 도면 없이 가짜 도면으로만 검증했습니다. 실제 PDF에서 색칠이나 추출이 맞지 않으면 진단을 돌려 보세요.

```bash
python -m component_review.inspect_pdf "ISO 또는 PID.pdf" --page 1
```

선 굵기별 개수·길이, 레이어, 채워진 도형, 색 등 숫자 요약이 나옵니다 (도면의 글자 내용은 출력하지 않음). 이 결과에 맞춰 `config.py`의 값을 조정합니다.

| 증상 | 조정할 값 |
|---|---|
| 배관이 색칠되지 않음 / 다른 선까지 색칠됨 | `pipe_min_width` (배관선 굵기 기준) |
| ISO가 `배관선으로 잡힌 선이 너무 많음`으로 수동 검토 처리됨 | `pipe_min_width`를 진단 결과의 배관 굵기로 지정 |
| 밸브에서 색칠이 끊김 | `gap_tol` 키우기 |
| PID Tag를 못 읽음 | `color_tol` 키우기 (글자가 검정이면 색칠된 선 근처 Tag를 자동으로 사용) |

## 테스트

```bash
python tests/test_pipeline.py
```
