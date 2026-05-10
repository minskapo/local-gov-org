"""16개 광역 지자체 행정기구 JSON 생성 (서울 제외, 이미 완료)"""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
OUT_DIR = BASE_DIR / "data" / "processed" / "by_region"
META_DIR = BASE_DIR / "meta"
OUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent))
from parse_ordinance import parse_gwangyeok_generic

FETCHED_AT = "2026-05-09"

# (지역코드, 표준명, 유형, 상위코드, 조례파일명, 시행규칙파일명, 정원조례파일명)
# 시행규칙파일명이 None이면 조례와 동일한 파일 (통합 조례)
GWANGYEOK_LIST = [
    # 광역시
    ("21", "부산광역시",    "광역시",     None,
     "부산광역시_행정기구설치조례",
     "부산광역시_행정기구설치조례_시행규칙",
     "부산광역시_지방공무원정원조례"),
    ("22", "대구광역시",    "광역시",     None,
     "대구광역시_행정기구설치조례",
     "대구광역시_행정기구설치조례_시행규칙",
     "대구광역시_지방공무원정원조례"),
    ("23", "인천광역시",    "광역시",     None,
     "인천광역시_행정기구설치조례",
     "인천광역시_행정기구설치조례_시행규칙",
     "인천광역시_지방공무원정원조례"),
    ("24", "광주광역시",    "광역시",     None,
     "광주광역시_행정기구설치조례",
     "광주광역시_행정기구설치조례_시행규칙",
     "광주광역시_지방공무원정원조례"),
    ("25", "대전광역시",    "광역시",     None,
     "대전광역시_행정기구설치조례",
     "대전광역시_행정기구설치조례_시행규칙",
     "대전광역시_지방공무원정원조례"),
    ("26", "울산광역시",    "광역시",     None,
     "울산광역시_행정기구설치조례",
     "울산광역시_행정기구설치조례_시행규칙",
     "울산광역시_지방공무원정원조례"),
    # 특별자치시
    ("29", "세종특별자치시", "특별자치시",  None,
     "세종특별자치시_행정기구설치조례",
     "세종특별자치시_행정기구설치조례_시행규칙",
     "세종특별자치시_지방공무원정원조례"),
    # 도
    ("31", "경기도",       "도",         None,
     "경기도_행정기구설치조례",
     "경기도_행정기구설치조례_시행규칙",
     "경기도_지방공무원정원조례"),
    ("32", "강원특별자치도", "특별자치도",  None,
     "강원특별자치도_행정기구설치조례",
     "강원특별자치도_행정기구설치조례_시행규칙",
     "강원특별자치도_지방공무원정원조례"),
    ("33", "충청북도",     "도",         None,
     "충청북도_행정기구설치조례",
     "충청북도_행정기구설치조례_시행규칙",
     "충청북도_지방공무원정원조례"),
    ("34", "충청남도",     "도",         None,
     "충청남도_행정기구설치조례",         # 통합조례
     "충청남도_행정기구설치조례_시행규칙",
     "충청남도_지방공무원정원조례"),
    ("35", "전북특별자치도", "특별자치도",  None,
     "전북특별자치도_행정기구설치조례",
     "전북특별자치도_행정기구설치조례_시행규칙",
     "전북특별자치도_지방공무원정원조례"),
    ("36", "전라남도",     "도",         None,
     "전라남도_행정기구설치조례",
     "전라남도_행정기구설치조례_시행규칙",
     "전라남도_지방공무원정원조례"),
    ("37", "경상북도",     "도",         None,
     "경상북도_행정기구설치조례",
     "경상북도_행정기구설치조례_시행규칙",
     "경상북도_지방공무원정원조례"),
    ("38", "경상남도",     "도",         None,
     "경상남도_행정기구설치조례",
     "경상남도_행정기구설치조례_시행규칙",
     "경상남도_지방공무원정원조례"),
    # 특별자치도
    ("39", "제주특별자치도", "특별자치도",  None,
     "제주특별자치도_행정기구설치조례",
     "제주특별자치도_행정기구설치조례_시행규칙",
     "제주특별자치도_지방공무원정원조례"),
]

ORD_DIR = RAW_DIR / "ordinances" / "광역"
RULE_DIR = RAW_DIR / "시행규칙"


def ord_path(fname):
    return ORD_DIR / f"{fname}.json"

def rule_path(fname):
    # 시행규칙이 시행규칙 디렉터리에 없으면 조례 디렉터리에서 찾음
    p = RULE_DIR / f"{fname}.json"
    if not p.exists():
        p = ORD_DIR / f"{fname}.json"
    return p

def staff_path(fname):
    return ORD_DIR / f"{fname}.json"


def process_all(target_codes=None):
    results = []
    for code, name, rtype, parent, ord_f, rule_f, staff_f in GWANGYEOK_LIST:
        if target_codes and code not in target_codes:
            continue
        print(f"\n[{code}] {name} 파싱 중...")
        op = ord_path(ord_f)
        rp = rule_path(rule_f)
        sp = staff_path(staff_f)
        if not op.exists():
            print(f"  조례 파일 없음: {op}")
            results.append((code, name, 0, 0, "파일없음"))
            continue
        try:
            data = parse_gwangyeok_generic(
                code=code, name=name,
                region_type=rtype, parent=parent,
                ord_path=op, rule_path=rp, staff_path=sp,
                fetched_at=FETCHED_AT,
            )
            out_path = OUT_DIR / f"{code}_{name.replace('특별자치', '').replace('광역시', '').replace('특별', '')}{rtype[:1] if rtype != '광역시' else '광역시'}.json"
            # 더 간단한 파일명
            safe_name = name
            out_path = OUT_DIR / f"{code}_{safe_name}.json"
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
            results.append((code, name, len(s), total, "완료"))
        except Exception as e:
            import traceback
            print(f"  오류: {e}")
            traceback.print_exc()
            results.append((code, name, 0, 0, f"오류:{e}"))

    # 커버리지 업데이트
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
    cov["광역"]["done"] = len(done) + 1  # +1 for Seoul
    cov["광역"]["failed"] = len(failed)
    cov["광역"]["list"] = [{"code": r[0], "name": r[1], "status": r[4],
                             "기구수": r[2], "정원": r[3]} for r in results]
    cov["phase"] = "2_in_progress"
    cov["updated_at"] = FETCHED_AT
    with open(cov_path, "w", encoding="utf-8") as f:
        json.dump(cov, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    target_codes = sys.argv[1:] if len(sys.argv) > 1 else None
    process_all(target_codes)
