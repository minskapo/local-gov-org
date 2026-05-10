"""226개 기초 지자체 행정기구 JSON 생성 (마포구·단양군 제외, 이미 완료)"""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
OUT_DIR = BASE_DIR / "data" / "processed" / "by_region"
META_DIR = BASE_DIR / "meta"
OUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent))
from parse_ordinance import parse_gicheo_generic

FETCHED_AT = "2026-05-09"

ORD_DIR = RAW_DIR / "ordinances" / "기초"
RULE_DIR = RAW_DIR / "시행규칙"

# 이미 완료된 기초 지자체
ALREADY_DONE = {"11440", "33780"}  # 마포구, 단양군


def load_gicheo_list() -> list[dict]:
    with open(META_DIR / "gicheo_list.json", encoding="utf-8") as f:
        return json.load(f)


_CITY_ABBR = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
    "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "강원특별자치도": "강원", "경상북도": "경북",
    "경상남도": "경남",
}
_COLLISION_NAMES = {"중구", "동구", "서구", "남구", "북구", "강서구", "군위군", "고성군"}


def short_name(full_name: str) -> str:
    """'서울특별시 종로구' → '종로구'; 중복명은 도시 접두어 추가 ('서울중구')"""
    parts = full_name.strip().split()
    base = parts[-1] if len(parts) > 1 else full_name
    if base in _COLLISION_NAMES and len(parts) >= 2:
        abbr = _CITY_ABBR.get(parts[0], parts[0][:2])
        return abbr + base
    return base


def ord_path(sname: str) -> Path:
    return ORD_DIR / f"{sname}_행정기구설치조례.json"


def rule_path(sname: str) -> Path:
    p = RULE_DIR / f"{sname}_행정기구설치조례_시행규칙.json"
    if not p.exists():
        p = ORD_DIR / f"{sname}_행정기구설치조례.json"  # 통합조례 fallback
    return p


def staff_path(sname: str):
    p = ORD_DIR / f"{sname}_지방공무원정원조례.json"
    return p if p.exists() else None


def process_all(target_codes=None):
    entries = load_gicheo_list()
    results = []

    for entry in entries:
        code = entry["code"]
        full_name = entry["name"]
        rtype = entry["type"]
        parent = entry["parent"]
        sname = short_name(full_name)

        if code in ALREADY_DONE:
            continue
        if target_codes and code not in target_codes:
            continue

        print(f"\n[{code}] {full_name} ({sname}) 파싱 중...")

        op = ord_path(sname)
        if not op.exists():
            print(f"  조례 파일 없음: {op.name}")
            results.append((code, full_name, 0, 0, "파일없음"))
            continue

        rp = rule_path(sname)
        sp = staff_path(sname)

        try:
            data = parse_gicheo_generic(
                code=code, name=full_name,
                region_type=rtype, parent=parent,
                ord_path=op, rule_path=rp, staff_path=sp,
                fetched_at=FETCHED_AT,
            )
            out_path = OUT_DIR / f"{code}_{full_name}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            s = data["structure"]
            total = data["totals"]["정원_총"]
            children_total = sum(len(n.get("children", [])) for n in s)
            print(f"  완료: {len(s)}개 최상위 기구 ({children_total}개 하위), 총정원 {total:,}명")
            for n in s:
                ct = len(n.get("children", []))
                tags = ",".join(n.get("키워드_태그", [])[:3])
                print(f"    {n['type']:5} | {n['name']:<20} | 하위:{ct}개 | {tags}")
            results.append((code, full_name, len(s), total, "완료"))
        except Exception as e:
            import traceback
            print(f"  오류: {e}")
            traceback.print_exc()
            results.append((code, full_name, 0, 0, f"오류:{e}"))

    update_coverage(results)
    print("\n\n=== 완료 요약 ===")
    for r in results:
        print(f"  [{r[0]}] {r[1]}: {r[4]}")


def update_coverage(results):
    cov_path = META_DIR / "coverage.json"
    with open(cov_path, encoding="utf-8") as f:
        cov = json.load(f)
    done = [r for r in results if r[4] == "완료"]
    failed = [r for r in results if "오류" in r[4]]
    no_file = [r for r in results if r[4] == "파일없음"]
    cov["기초"]["done"] = len(done) + len(ALREADY_DONE)
    cov["기초"]["failed"] = len(failed)
    cov["기초"]["no_file"] = len(no_file)
    cov["기초"]["list"] = [
        {"code": r[0], "name": r[1], "status": r[4], "기구수": r[2], "정원": r[3]}
        for r in results
    ]
    cov["phase"] = "3_in_progress"
    cov["updated_at"] = FETCHED_AT
    with open(cov_path, "w", encoding="utf-8") as f:
        json.dump(cov, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    target_codes = set(sys.argv[1:]) if len(sys.argv) > 1 else None
    process_all(target_codes)
