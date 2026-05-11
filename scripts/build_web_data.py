"""웹 데이터 번들 빌더 — docs/data/ 산출물 생성

실행: uv run python scripts/build_web_data.py
출력:
  docs/data/index.json           — 243개 지자체 요약 (초기 로드용)
  docs/data/regions/{code}.json  — per-region 전체 데이터 (lazy-load)
  docs/data/by_keyword/{kw}.json — 정책분야별 평탄 목록
  docs/data/aggregates.json      — 전국·광역 집계
  docs/data/search_index.json    — 검색 문서 배열 (브라우저에서 인덱싱)
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
IN_DIR   = BASE_DIR / "data" / "processed" / "by_region"
META_DIR = BASE_DIR / "meta"
SCHEMA_DIR = BASE_DIR / "schema"
OUT_DIR  = BASE_DIR / "docs" / "data"
REGIONS_DIR = OUT_DIR / "regions"
KW_DIR   = OUT_DIR / "by_keyword"

TYPE_ORDER = [
    "국", "실", "본부", "단", "관", "처",
    "보좌기관", "담당관", "한시기구",
    "직속기관", "사업소", "출장소",
    "과",
]


def load_all():
    return [json.loads(f.read_text(encoding="utf-8"))
            for f in sorted(IN_DIR.glob("*.json"))]


def short_name(full_name: str) -> str:
    parts = full_name.strip().split()
    return parts[-1] if len(parts) > 1 else full_name


def build_index(records, code_to_name):
    items = []
    for d in records:
        reg = d["region"]
        code = reg["code"]
        structure = d.get("structure", [])
        children_total = sum(len(u.get("children", [])) for u in structure)
        kw_dist: dict[str, int] = {}
        for u in structure:
            for kw in u.get("키워드_태그", []):
                kw_dist[kw] = kw_dist.get(kw, 0) + 1
            for c in u.get("children", []):
                for kw in c.get("키워드_태그", []):
                    kw_dist[kw] = kw_dist.get(kw, 0) + 1
        items.append({
            "code": code,
            "name": reg["name"],
            "short_name": short_name(reg["name"]),
            "level": reg.get("level", ""),
            "type": reg.get("type", ""),
            "parent": reg.get("parent", ""),
            "parent_name": code_to_name.get(reg.get("parent", ""), ""),
            "기구수": len(structure),
            "하위기구수": children_total,
            "정원": d.get("totals", {}).get("정원_총") or 0,
            "키워드_분포": kw_dist,
        })
    return items


def build_by_keyword(records, keywords):
    kw_data: dict[str, list] = {kw: [] for kw in keywords}
    for d in records:
        reg = d["region"]
        rc = reg["code"]
        rn = reg["name"]
        for u in d.get("structure", []):
            u_name = u.get("name", "")
            summary = " ".join((u.get("분장사무_항목") or [])[:5])
            for kw in u.get("키워드_태그", []):
                if kw in kw_data:
                    kw_data[kw].append({
                        "region_code": rc, "region_name": rn,
                        "unit_id": u.get("id", ""),
                        "unit_name": u_name, "unit_type": u.get("type", ""),
                        "parent_name": "",
                        "head_grade": u.get("head_grade", ""),
                        "분장사무_summary": summary,
                    })
            for c in u.get("children", []):
                c_summary = " ".join((c.get("분장사무_항목") or [])[:5])
                for kw in c.get("키워드_태그", []):
                    if kw in kw_data:
                        kw_data[kw].append({
                            "region_code": rc, "region_name": rn,
                            "unit_id": c.get("id", ""),
                            "unit_name": c.get("name", ""), "unit_type": c.get("type", ""),
                            "parent_name": u_name,
                            "head_grade": c.get("head_grade", ""),
                            "분장사무_summary": c_summary,
                        })
    return kw_data


def build_aggregates(records):
    gwangyeok = [d for d in records if d["region"].get("level") == "광역"]
    gw_list = []
    for d in gwangyeok:
        reg = d["region"]
        type_count = {t: 0 for t in TYPE_ORDER}
        for u in d.get("structure", []):
            ut = u.get("type", "")
            if ut in type_count:
                type_count[ut] += 1
            for c in u.get("children", []):
                ct = c.get("type", "")
                if ct in type_count:
                    type_count[ct] += 1
        gw_list.append({
            "code": reg["code"],
            "name": reg["name"],
            "정원": d.get("totals", {}).get("정원_총") or 0,
            "기구유형별": type_count,
        })

    all_type_count = {t: 0 for t in TYPE_ORDER}
    kw_total: dict[str, int] = {}
    for d in records:
        for u in d.get("structure", []):
            ut = u.get("type", "")
            if ut in all_type_count:
                all_type_count[ut] += 1
            for kw in u.get("키워드_태그", []):
                kw_total[kw] = kw_total.get(kw, 0) + 1
            for c in u.get("children", []):
                ct = c.get("type", "")
                if ct in all_type_count:
                    all_type_count[ct] += 1
                for kw in c.get("키워드_태그", []):
                    kw_total[kw] = kw_total.get(kw, 0) + 1

    return {
        "광역": gw_list,
        "전국_기구유형별": all_type_count,
        "전국_키워드별": kw_total,
    }


def build_search_docs(records):
    docs = []
    for d in records:
        reg = d["region"]
        rc = reg["code"]
        rn = reg["name"]
        rl = reg.get("level", "")
        for u in d.get("structure", []):
            summary = " ".join((u.get("분장사무_항목") or [])[:5])
            docs.append({
                "id": f"{rc}#{u.get('id', u.get('name', ''))}",
                "region_code": rc,
                "region_name": rn,
                "region_level": rl,
                "unit_name": u.get("name", ""),
                "unit_type": u.get("type", ""),
                "parent_name": "",
                "키워드_태그": " ".join(u.get("키워드_태그", [])),
                "분장사무_summary": summary,
            })
            for c in u.get("children", []):
                c_summary = " ".join((c.get("분장사무_항목") or [])[:5])
                docs.append({
                    "id": f"{rc}#{c.get('id', c.get('name', ''))}",
                    "region_code": rc,
                    "region_name": rn,
                    "region_level": rl,
                    "unit_name": c.get("name", ""),
                    "unit_type": c.get("type", ""),
                    "parent_name": u.get("name", ""),
                    "키워드_태그": " ".join(c.get("키워드_태그", [])),
                    "분장사무_summary": c_summary,
                })
    return docs


def write_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main():
    print("데이터 로딩 중...")
    records = load_all()
    print(f"  {len(records)}개 지자체 로드 완료")

    keywords = list(json.loads((SCHEMA_DIR / "keywords.json").read_text(encoding="utf-8")).keys())
    code_to_name = {d["region"]["code"]: d["region"]["name"] for d in records}

    REGIONS_DIR.mkdir(parents=True, exist_ok=True)
    KW_DIR.mkdir(parents=True, exist_ok=True)

    # 1. index.json
    print("1/5  index.json 생성 중...")
    index = build_index(records, code_to_name)
    write_json(OUT_DIR / "index.json", index)
    print(f"     완료: {len(index)}개, {(OUT_DIR/'index.json').stat().st_size/1024:.0f}KB")

    # 2. regions/{code}.json
    print("2/5  regions/ 생성 중...")
    for d in records:
        write_json(REGIONS_DIR / f"{d['region']['code']}.json", d)
    total_mb = sum(f.stat().st_size for f in REGIONS_DIR.glob("*.json")) / 1024 / 1024
    print(f"     완료: {len(records)}개, {total_mb:.1f}MB")

    # 3. by_keyword/
    print("3/5  by_keyword/ 생성 중...")
    kw_data = build_by_keyword(records, keywords)
    for kw, items in kw_data.items():
        write_json(KW_DIR / f"{kw}.json", items)
        print(f"     {kw}: {len(items)}개 단위")

    # 4. aggregates.json
    print("4/5  aggregates.json 생성 중...")
    write_json(OUT_DIR / "aggregates.json", build_aggregates(records))
    print(f"     완료")

    # 5. search_index.json
    print("5/5  search_index.json 생성 중...")
    docs = build_search_docs(records)
    write_json(OUT_DIR / "search_index.json", docs)
    size_mb = (OUT_DIR / "search_index.json").stat().st_size / 1024 / 1024
    print(f"     완료: {len(docs)}개 문서, {size_mb:.1f}MB")

    total = sum(f.stat().st_size for f in OUT_DIR.rglob("*.json")) / 1024 / 1024
    print(f"\n전체 docs/data/ 크기: {total:.1f}MB")


if __name__ == "__main__":
    main()
