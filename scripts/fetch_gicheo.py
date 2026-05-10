"""226개 기초 지자체 행정기구설치조례·시행규칙·정원조례 수집"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
META_DIR = BASE_DIR / "meta"
API_KEY = "minskapo-korean-law"
FETCHED_AT = "2026-05-09"

ORD_DIR = RAW_DIR / "ordinances" / "기초"
RULE_DIR = RAW_DIR / "시행규칙"

# 이미 완료된 기초 지자체 (Phase 1)
ALREADY_DONE = {"11440", "33780"}  # 마포구, 단양군


def load_gicheo_list() -> list[dict]:
    with open(META_DIR / "gicheo_list.json", encoding="utf-8") as f:
        return json.load(f)


def search_ordin(query: str, page: int = 1, display: int = 10) -> list[dict]:
    url = (
        f"https://www.law.go.kr/DRF/lawSearch.do"
        f"?OC={API_KEY}&target=ordin&query={urllib.parse.quote(query)}"
        f"&display={display}&page={page}&type=JSON"
    )
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    items = data.get("OrdinSearch", {}).get("law", [])
    if isinstance(items, dict):
        items = [items]
    return items if isinstance(items, list) else []


def pick_best(items: list[dict], org_name: str, keywords: list[str]):
    """가장 일치하는 항목 선택 (지자체기관명 exact match 우선)"""
    if not items:
        return None
    for item in items:
        org = item.get("지자체기관명", "")
        law = item.get("자치법규명", "").replace(" ", "")
        if org == org_name and all(k in law for k in keywords):
            return item
    for item in items:
        if item.get("지자체기관명", "") == org_name:
            return item
    return None


def find_best_paginated(query: str, org_name: str, keywords: list[str],
                        max_pages: int = 3, fallback_query: str = None):
    """여러 페이지에 걸쳐 검색; 결과 없으면 fallback_query 재시도"""
    for q in ([query, fallback_query] if fallback_query else [query]):
        if not q:
            continue
        for page in range(1, max_pages + 1):
            try:
                items = search_ordin(q, page=page)
            except Exception as e:
                print(f"    검색 오류 (page={page}): {e}")
                break
            best = pick_best(items, org_name, keywords)
            if best:
                return best
            if len(items) < 10:
                break
            time.sleep(0.3)
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
    조문_raw = law.get("조문", {})
    if isinstance(조문_raw, dict):
        articles = 조문_raw.get("조", [])
    else:
        articles = []
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


def process_one(entry: dict) -> dict:
    code = entry["code"]
    full_name = entry["name"]
    sname = short_name(full_name)

    print(f"\n[{code}] {full_name} ({sname})")

    # 파일 경로
    ord_path = ORD_DIR / f"{sname}_행정기구설치조례.json"
    rule_path = RULE_DIR / f"{sname}_행정기구설치조례_시행규칙.json"
    staff_path = ORD_DIR / f"{sname}_지방공무원정원조례.json"

    # (레이블, 쿼리, 폴백쿼리, 키워드, 저장경로)
    targets = [
        ("조례",    f"{sname} 행정기구 설치 조례",          f"{sname} 행정기구",   ["행정기구"], ord_path),
        ("시행규칙", f"{sname} 행정기구 설치 조례 시행규칙", f"{sname} 행정기구",   ["행정기구"], rule_path),
        ("정원조례", f"{sname} 지방공무원 정원 조례",         f"{sname} 공무원 정원", ["정원"],    staff_path),
    ]

    result = {"code": code, "name": full_name}
    for label, query, fallback, kw, out_path in targets:
        if out_path.exists():
            print(f"  {label}: 이미 존재, 스킵")
            result[label] = "skip"
            continue

        # 정원조례 미발견 시 통합형 조례 재사용
        if label == "정원조례" and not out_path.exists():
            if ord_path.exists():
                with open(ord_path, encoding="utf-8") as f:
                    ord_data = json.load(f)
                if "정원" in ord_data.get("law_name", ""):
                    import shutil
                    shutil.copy2(ord_path, out_path)
                    print(f"  {label}: 통합조례 재사용 — {out_path.name}")
                    result[label] = "ok"
                    continue

        best = find_best_paginated(query, full_name, kw, fallback_query=fallback)
        if not best:
            print(f"  {label}: 검색 결과 없음 — '{query}'")
            result[label] = "not_found"
            time.sleep(0.3)
            continue
        mst = best.get("자치법규일련번호", "")
        law_name = best.get("자치법규명", "")
        print(f"  {label}: {law_name} (MST={mst})")
        time.sleep(0.5)
        try:
            data = fetch_ordin(mst)
            save(data, out_path)
            print(f"  {label}: 저장 완료 — {out_path.name}")
            result[label] = "ok"
            time.sleep(0.8)
        except Exception as e:
            print(f"  {label}: fetch 오류 (MST={mst}) — {e}")
            result[label] = f"err:{e}"
            time.sleep(0.5)

    return result


def main():
    entries = load_gicheo_list()
    target_codes = set(sys.argv[1:]) if len(sys.argv) > 1 else None

    results = []
    for entry in entries:
        code = entry["code"]
        if code in ALREADY_DONE:
            print(f"[{code}] {entry['name']}: 이미 완료, 스킵")
            continue
        if target_codes and code not in target_codes:
            continue
        r = process_one(entry)
        results.append(r)

    print("\n\n=== 완료 요약 ===")
    ok = [r for r in results if all(v in ("ok","skip") for k,v in r.items() if k not in ("code","name"))]
    miss = [r for r in results if any(v == "not_found" for v in r.values())]
    err = [r for r in results if any(str(v).startswith("err:") for v in r.values())]
    print(f"  전체: {len(results)}개 처리")
    print(f"  성공(스킵포함): {len(ok)}개")
    print(f"  검색실패: {len(miss)}개  {[r['name'] for r in miss]}")
    print(f"  fetch오류: {len(err)}개  {[r['name'] for r in err]}")


if __name__ == "__main__":
    main()
