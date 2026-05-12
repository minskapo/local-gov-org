"""기후환경 부서 현황 CSV → docs/data/climate_depts.json"""
import csv
import json
from pathlib import Path

BASE = Path(__file__).parent.parent
CSV_PATH = BASE / "기후시민_전국 지자체 탄소중립 주무부서 현황_김민석_260512 - 시트1.csv"
OUT = BASE / "docs" / "data" / "climate_depts.json"


def main():
    result = []
    with open(CSV_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gi = (row.get("기초명") or "").strip()
            result.append({
                "code":          (row.get("지자체코드") or "").strip(),
                "gw":            (row.get("광역명") or "").strip(),
                "gi":            gi,
                "level":         "기초" if gi else "광역",
                "parent_org":    (row.get("상위기구") or "").strip(),
                "parent_type":   (row.get("상위부서유형") or "").strip(),
                "climate_dept":  (row.get("기후환경 하위부서") or "").strip(),
                "dept_keywords": (row.get("하위부서유형") or "").strip(),
            })

    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"완료: {len(result)}개, {OUT.stat().st_size / 1024:.0f}KB → {OUT}")


if __name__ == "__main__":
    main()
