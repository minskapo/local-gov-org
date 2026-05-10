"""단양군 자치법규 수집"""
import json
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
FETCHED_AT = "2026-05-09"
API_KEY = "minskapo-korean-law"

TARGETS = [
    ("1900293", "단양군_행정기구설치조례", "ordinances/기초"),
    ("1974917", "단양군_행정기구설치조례_시행규칙", "시행규칙"),
    ("2032375", "단양군_지방공무원정원조례", "ordinances/기초"),
]


def fetch_ordin(mst: str) -> dict:
    url = (
        f"https://www.law.go.kr/DRF/lawService.do"
        f"?OC={API_KEY}&target=ordin&MST={mst}&type=JSON&mobileYn="
    )
    with urllib.request.urlopen(url) as r:
        d = json.loads(r.read().decode("utf-8"))
    law = d["LawService"]
    info = law["자치법규기본정보"]
    articles = law["조문"]["조"]
    annexes = law.get("별표단위", [])
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


def main():
    for mst, filename, subdir in TARGETS:
        print(f"Fetching {filename}...")
        data = fetch_ordin(mst)
        out_path = RAW_DIR / subdir / f"{filename}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(
            f"  Saved: 조문={len(data['articles'])}, 별표={len(data['annexes'])}, "
            f"시행={data['last_amended']}"
        )


if __name__ == "__main__":
    main()
