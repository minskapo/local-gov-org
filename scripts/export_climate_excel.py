"""기후·환경 관련 행정기구 현황 → 엑셀"""
import json
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

BASE_DIR = Path(__file__).parent.parent
OUT_DIR = BASE_DIR / "data" / "processed" / "by_region"
EXCEL_PATH = BASE_DIR / "data" / "processed" / "기후환경_행정기구_현황.xlsx"

CLIMATE_KW = frozenset([
    "기후", "환경", "생태", "녹지", "폐기물", "깨끗", "맑은", "탄소",
    "대기", "수질", "오염", "자원순환", "재활용", "산림", "공원",
])


def is_climate(name: str) -> bool:
    return any(kw in name for kw in CLIMATE_KW)


def load_all():
    records = []
    for f in sorted(OUT_DIR.glob("*.json")):
        with open(f, encoding="utf-8") as fh:
            records.append(json.load(fh))
    return records


def get_climate_rows(d):
    """기후환경 관련 상위기구 행 목록 반환.
    각 행: {parent, children, climate_parent(bool)}
    - climate_parent=True: 상위기구명 자체가 기후환경 관련
    - climate_parent=False: 상위기구는 비기후이지만 하위기구 중 기후환경 기구 존재
    """
    rows = []
    for unit in d.get("structure", []):
        name = unit.get("name", "")
        children = [c.get("name", "") for c in unit.get("children", [])]
        if is_climate(name):
            rows.append({"parent": name, "children": children, "climate_parent": True})
        elif any(is_climate(c) for c in children):
            rows.append({"parent": name, "children": children, "climate_parent": False})
    return rows


def fill(hex_color):
    return PatternFill("solid", fgColor=hex_color)


def thin_border():
    s = Side(style="thin", color="CBD5E1")
    return Border(left=s, right=s, top=s, bottom=s)


def apply_cell(ws, row, col, value, bg, bold=False, align="center", wrap=False):
    cell = ws.cell(row=row, column=col, value=value)
    cell.fill = fill(bg)
    cell.border = thin_border()
    cell.font = Font(bold=bold, size=10)
    cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
    return cell


def main():
    print("데이터 로딩 중...")
    records = load_all()
    print(f"  {len(records)}개 지자체 로드 완료")

    # 코드 → 광역명 매핑
    code_to_name = {d["region"]["code"]: d["region"]["name"] for d in records}

    # 최대 하위기구 수 파악
    max_children = max(
        (len(row["children"]) for d in records for row in get_climate_rows(d)),
        default=0,
    )
    print(f"  최대 하위기구 수: {max_children}")

    wb = Workbook()
    ws = wb.active
    ws.title = "기후환경 행정기구 현황"

    # ── 헤더 ─────────────────────────────────────────────
    FIXED = [
        ("지자체코드",        9),
        ("광역명",           14),
        ("기초명",           14),
        ("기후환경\n관련여부", 9),
        ("상위기구",         22),
    ]
    HDR_BG = "1E3A5F"
    for col, (title, width) in enumerate(FIXED, 1):
        apply_cell(ws, 1, col, title, HDR_BG, bold=True, wrap=True)
        ws.column_dimensions[get_column_letter(col)].width = width
        ws.cell(row=1, column=col).font = Font(bold=True, color="FFFFFF", size=10)

    START = len(FIXED) + 1
    for i in range(1, max_children + 1):
        col = START + i - 1
        apply_cell(ws, 1, col, f"하위기구{i}", HDR_BG, bold=True)
        ws.column_dimensions[get_column_letter(col)].width = 18
        ws.cell(row=1, column=col).font = Font(bold=True, color="FFFFFF", size=10)
    ws.row_dimensions[1].height = 32

    # ── 데이터 ───────────────────────────────────────────
    # 색상
    BG_PARENT_CLIMATE  = "DCFCE7"  # 연초록: 상위기구 자체가 기후환경
    BG_PARENT_INDIRECT = "FEF9C3"  # 연노랑: 하위기구에만 기후환경 있음
    BG_CHILD_CLIMATE   = "BFDBFE"  # 연파랑: 기후환경 관련 하위기구
    BG_CHILD_OTHER     = "F8FAFC"  # 연회색: 비기후 하위기구

    data_row = 2
    total_rows = 0
    skipped = 0

    for d in records:
        reg = d["region"]
        code = reg.get("code", "")
        name = reg.get("name", "")
        level = reg.get("level", "")
        parent_code = reg.get("parent") or ""

        if level == "광역":
            gwangyeok = name
            gicheo = ""
        else:
            gwangyeok = code_to_name.get(parent_code, "")
            if not gwangyeok:
                # parent 코드 체계가 다를 때 (행정표준코드 vs 2자리 코드)
                # 지자체명에서 광역명 추출 ("충청북도 단양군" → "충청북도")
                parts = name.split()
                gwangyeok = parts[0] if len(parts) > 1 else name
            gicheo = name

        climate_rows = get_climate_rows(d)
        if not climate_rows:
            skipped += 1
            continue

        for cr in climate_rows:
            row_bg = BG_PARENT_CLIMATE if cr["climate_parent"] else BG_PARENT_INDIRECT
            label  = "○"     if cr["climate_parent"] else "△"

            fixed_vals = [code, gwangyeok, gicheo, label, cr["parent"]]
            aligns     = ["center", "left", "left", "center", "left"]
            for col, (val, al) in enumerate(zip(fixed_vals, aligns), 1):
                apply_cell(ws, data_row, col, val, row_bg, align=al)

            for i, child in enumerate(cr["children"]):
                col = START + i
                child_bg = BG_CHILD_CLIMATE if is_climate(child) else BG_CHILD_OTHER
                apply_cell(ws, data_row, col, child, child_bg, align="left")

            data_row += 1
            total_rows += 1

    ws.freeze_panes = "A2"
    total_cols = START + max_children - 1
    ws.auto_filter.ref = f"A1:{get_column_letter(total_cols)}1"

    print(f"저장 중: {EXCEL_PATH}")
    wb.save(EXCEL_PATH)
    size_kb = EXCEL_PATH.stat().st_size / 1024
    print(f"완료! {total_rows}행 작성 ({skipped}개 지자체 기후환경 기구 없음)")
    print(f"파일 크기: {size_kb:.0f} KB")
    print(f"\n[참고] 사용 키워드: {', '.join(sorted(CLIMATE_KW))}")


if __name__ == "__main__":
    main()
