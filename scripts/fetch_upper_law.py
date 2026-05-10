"""Phase 0.5: 상위법령(지방자치법, 행정기구정원기준규정) 수집 스크립트"""
import json
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_URL = "https://www.law.go.kr/DRF/lawService.do"
SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "data" / "raw" / "upper_law"
RAW_DIR.mkdir(parents=True, exist_ok=True)

FETCHED_AT = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def fetch_json(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_law(mst, law_name):
    url = f"{BASE_URL}?OC=open&target=law&MST={mst}&type=JSON&mobileYn="
    data = fetch_json(url)
    law = data["법령"]
    info = law["기본정보"]
    articles = law["조문"]["조문단위"]
    annexes = law.get("별표", {}).get("별표단위", [])
    return {
        "law_name": info.get("법령명한글", law_name),
        "law_id": info.get("법령ID", ""),
        "mst": mst,
        "last_amended": info.get("시행일자", ""),
        "source": "law.go.kr",
        "fetched_at": FETCHED_AT,
        "articles": articles,
        "annexes": annexes,
    }


def main():
    laws = [
        ("276357", "지방자치법", "지방자치법_전체.json"),
        ("283183", "지방자치단체의 행정기구와 정원기준 등에 관한 규정", "행정기구정원기준규정_전체.json"),
    ]

    for mst, name, filename in laws:
        print(f"Fetching {name}...")
        data = fetch_law(mst, name)
        out_path = RAW_DIR / filename
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  Saved: {out_path}")
        print(f"  시행일자: {data['last_amended']}, 조문: {len(data['articles'])}, 별표: {len(data['annexes'])}")

    print("\nDone.")


if __name__ == "__main__":
    main()
