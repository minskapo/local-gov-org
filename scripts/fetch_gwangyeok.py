"""광역 지자체 행정기구설치조례·시행규칙·정원조례 수집"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
API_KEY = "minskapo-korean-law"
FETCHED_AT = "2026-05-09"

# (지역코드, 지자체명, 조례검색어, 시행규칙검색어, 정원조례검색어)
GWANGYEOK = [
    ("21", "부산광역시",   "부산광역시 행정기구 설치 조례",      "부산광역시 행정기구 설치 조례 시행규칙",   "부산광역시 지방공무원 정원 조례"),
    ("22", "대구광역시",   "대구광역시 행정기구 설치 조례",      "대구광역시 행정기구 설치 조례 시행규칙",   "대구광역시 지방공무원 정원 조례"),
    ("23", "인천광역시",   "인천광역시 행정기구 설치 조례",      "인천광역시 행정기구 설치 조례 시행규칙",   "인천광역시 지방공무원 정원 조례"),
    ("24", "광주광역시",   "광주광역시 행정기구 설치 조례",      "광주광역시 행정기구 설치 조례 시행규칙",   "광주광역시 지방공무원 정원 조례"),
    ("25", "대전광역시",   "대전광역시 행정기구 설치 조례",      "대전광역시 행정기구 설치 조례 시행규칙",   "대전광역시 지방공무원 정원 조례"),
    ("26", "울산광역시",   "울산광역시 행정기구 설치 조례",      "울산광역시 행정기구 설치 조례 시행규칙",   "울산광역시 지방공무원 정원 조례"),
    ("29", "세종특별자치시", "세종특별자치시 행정기구 설치 조례",   "세종특별자치시 행정기구 설치 조례 시행규칙", "세종특별자치시 지방공무원 정원 조례"),
    ("31", "경기도",      "경기도 행정기구 설치 조례",          "경기도 행정기구 설치 조례 시행규칙",       "경기도 지방공무원 정원 조례"),
    ("32", "강원특별자치도", "강원특별자치도 행정기구 설치 조례",   "강원특별자치도 행정기구 설치 조례 시행규칙", "강원특별자치도 지방공무원 정원 조례"),
    ("33", "충청북도",     "충청북도 행정기구 설치 조례",        "충청북도 행정기구 설치 조례 시행규칙",     "충청북도 지방공무원 정원 조례"),
    ("34", "충청남도",     "충청남도 행정기구 설치 조례",        "충청남도 행정기구 설치 조례 시행규칙",     "충청남도 지방공무원 정원 조례"),
    ("35", "전북특별자치도", "전북특별자치도 행정기구 설치 조례",   "전북특별자치도 행정기구 설치 조례 시행규칙", "전북특별자치도 지방공무원 정원 조례"),
    ("36", "전라남도",     "전라남도 행정기구 설치 조례",        "전라남도 행정기구 설치 조례 시행규칙",     "전라남도 지방공무원 정원 조례"),
    ("37", "경상북도",     "경상북도 행정기구 설치 조례",        "경상북도 행정기구 설치 조례 시행규칙",     "경상북도 지방공무원 정원 조례"),
    ("38", "경상남도",     "경상남도 행정기구 설치 조례",        "경상남도 행정기구 설치 조례 시행규칙",     "경상남도 지방공무원 정원 조례"),
    ("39", "제주특별자치도", "제주특별자치도 행정기구 설치 조례",   "제주특별자치도 행정기구 설치 조례 시행규칙", "제주특별자치도 지방공무원 정원 조례"),
]


def search_ordin(query: str, display: int = 10) -> list[dict]:
    url = (
        f"https://www.law.go.kr/DRF/lawSearch.do"
        f"?OC={API_KEY}&target=ordin&query={urllib.parse.quote(query)}"
        f"&display={display}&page=1&type=JSON"
    )
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    items = data.get("OrdinSearch", {}).get("law", [])
    if isinstance(items, dict):
        items = [items]
    return items if isinstance(items, list) else []


def pick_best(items: list[dict], query: str, org_name: str):
    """검색 결과 중 가장 일치하는 항목 선택"""
    if not items:
        return None
    # 자치법규일련번호 = MST
    q_clean = query.replace(" ", "")
    # 1순위: 지자체기관명이 정확히 일치 + 자치법규명에 키워드 포함
    for item in items:
        org = item.get("지자체기관명", "")
        name = item.get("자치법규명", "").replace(" ", "")
        if org == org_name and q_clean in name:
            return item
    # 2순위: 지자체기관명 정확 일치
    for item in items:
        if item.get("지자체기관명", "") == org_name:
            return item
    # 3순위: 자치법규명에 org_name 포함
    for item in items:
        name = item.get("자치법규명", "")
        if org_name in name:
            return item
    return None


def fetch_ordin(mst: str) -> dict:
    url = (
        f"https://www.law.go.kr/DRF/lawService.do"
        f"?OC={API_KEY}&target=ordin&MST={mst}&type=JSON&mobileYn="
    )
    with urllib.request.urlopen(url, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8"))
    law = d["LawService"]
    info = law["자치법규기본정보"]
    articles = law["조문"]["조"]
    if isinstance(articles, dict):
        articles = [articles]
    annexes = law.get("별표단위", [])
    if isinstance(annexes, dict):
        annexes = [annexes]
    return {
        "law_name": info.get("자치법규명", ""),
        "mst": mst,
        "last_amended": info.get("시행일자", ""),
        "org": info.get("지자체기관명", ""),
        "source": "law.go.kr",
        "fetched_at": FETCHED_AT,
        "articles": articles,
        "annexes": annexes,
    }


def save(data: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def process_one(code: str, name: str, q_ord: str, q_rule: str, q_staff: str):
    print(f"\n{'='*55}")
    print(f"[{code}] {name}")

    results = {}
    for label, query in [("조례", q_ord), ("시행규칙", q_rule), ("정원조례", q_staff)]:
        try:
            items = search_ordin(query)
            best = pick_best(items, query, name)
            if not best:
                print(f"  {label}: 검색 결과 없음 — '{query}'")
                results[label] = None
                continue
            mst = best.get("자치법규일련번호", "")
            law_name = best.get("자치법규명", "")
            print(f"  {label}: {law_name} (MST={mst})")
            results[label] = (mst, law_name)
            time.sleep(0.5)
        except Exception as e:
            print(f"  {label}: 검색 오류 — {e}")
            results[label] = None

    # 조례 fetch + save
    for label, subdir, filename in [
        ("조례", "ordinances/광역", f"{name}_행정기구설치조례"),
        ("시행규칙", "시행규칙", f"{name}_행정기구설치조례_시행규칙"),
        ("정원조례", "ordinances/광역", f"{name}_지방공무원정원조례"),
    ]:
        if not results.get(label):
            continue
        mst, law_name_found = results[label]
        out_path = RAW_DIR / subdir / f"{filename}.json"
        if out_path.exists():
            print(f"  {label}: 이미 존재, 스킵 ({out_path.name})")
            continue
        try:
            data = fetch_ordin(mst)
            save(data, out_path)
            print(f"  {label}: 저장 완료 — 조문 {len(data['articles'])}개 → {out_path.name}")
            time.sleep(0.8)
        except Exception as e:
            print(f"  {label}: fetch 오류 (MST={mst}) — {e}")


def main():
    for code, name, q_ord, q_rule, q_staff in GWANGYEOK:
        # 서울은 이미 완료
        if code == "11":
            continue
        process_one(code, name, q_ord, q_rule, q_staff)
    print("\n\n완료.")


if __name__ == "__main__":
    main()
