"""
자치법규 파서 — 조례 + 시행규칙 + 정원조례 → processed JSON 변환
현재: 서울특별시 (광역) 대상
"""
import html
import json
import re
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed" / "by_region"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

KEYWORD_PATH = BASE_DIR / "schema" / "keywords.json"
with open(KEYWORD_PATH, encoding="utf-8") as f:
    KEYWORDS = json.load(f)


# ─── 유틸 ──────────────────────────────────────────────
def get_content(article: dict) -> str:
    """조문 내용을 단일 문자열로 (HTML 엔티티 디코드 포함)"""
    c = article.get("조내용", "") or article.get("조문내용", "")
    if isinstance(c, list):
        parts = []
        for item in c:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, list):
                for sub in item:
                    if isinstance(sub, str):
                        parts.append(sub)
        return html.unescape("\n".join(parts))
    return html.unescape(str(c)) if c else ""


def _strip_art_header(text: str) -> str:
    """조문 헤더 '제X조(제목)' 제거 — 본문만 반환"""
    return re.sub(r"^제\d+조(?:의\d+)?\([^)]{0,120}\)", "", text.strip())


def parse_duties(text: str) -> list[str]:
    """분장사무 번호 항목 분리 — '1.', '가.', '①' 등 (인라인 포함)"""
    if not text:
        return []
    # 조문 헤더 제거: "제X조(제목) ... 다음 사항을 분장한다." 앞 제거
    text = re.sub(r"^.{0,200}(?:분장한다|관장한다|수행한다)\.", "", text, flags=re.DOTALL).strip()
    # 개정 주석 제거: <개정 2022...>
    text = re.sub(r"<[^>]{1,100}>", "", text)
    # 번호 앞에 구분자 삽입 (인라인 번호 처리)
    text = re.sub(r"(?<!\n)(\d+\. )", r"\n\1", text)
    text = re.sub(r"(?<!\n)([가-힣]\. )", r"\n\1", text)
    text = re.sub(r"([①②③④⑤⑥⑦⑧⑨⑩])", r"\n\1 ", text)
    parts = re.split(r"\n\s*", text)
    items = []
    for p in parts:
        p = p.strip()
        if p and len(p) > 3 and re.match(r"^(\d+\.|[가-힣]\.|[①-⑩])", p):
            # 번호 접두사 제거
            p = re.sub(r"^(?:\d+\.|[가-힣]\.|[①-⑩])\s*", "", p).strip()
            if p and len(p) > 3:
                items.append(p)
    return items


def apply_keywords(text: str) -> list[str]:
    """키워드 사전으로 태그 부여"""
    tags = []
    for tag, words in KEYWORDS.items():
        if any(w in text for w in words):
            tags.append(tag)
    return tags


def article_num_to_str(num_raw) -> str:
    """['000500', '000502'] → '제5조의2' 형식"""
    if isinstance(num_raw, list) and num_raw:
        raw = num_raw[-1] if len(num_raw) > 1 else num_raw[0]
    else:
        raw = str(num_raw)
    # 000502 → 5조의2, 001204 → 12조의4
    raw = raw.strip()
    base = int(raw[:4]) if len(raw) >= 4 else 0
    sub = int(raw[4:]) if len(raw) > 4 else 0
    if sub:
        return f"제{base}조의{sub}"
    return f"제{base}조"


def build_id(region_code: str, *parts: str) -> str:
    return f"{region_code}." + ".".join(p.strip() for p in parts if p.strip())


# ─── 서울특별시 파서 ──────────────────────────────────
def parse_seoul() -> dict:
    region_code = "11"
    region_name = "서울특별시"

    # 1. 원문 로드
    with open(RAW_DIR / "ordinances/광역/서울특별시_행정기구설치조례.json", encoding="utf-8") as f:
        ord_data = json.load(f)
    with open(RAW_DIR / "시행규칙/서울특별시_행정기구설치조례_시행규칙.json", encoding="utf-8") as f:
        rule_data = json.load(f)
    with open(RAW_DIR / "ordinances/광역/서울특별시_공무원정원조례.json", encoding="utf-8") as f:
        staff_data = json.load(f)

    ord_articles = {article_num_to_str(a["조문번호"]): a for a in ord_data["articles"] if a.get("조문여부") == "Y"}
    rule_articles = {article_num_to_str(a["조문번호"]): a for a in rule_data["articles"] if a.get("조문여부") == "Y"}

    # 2. 실/본부/국 목록 추출 (조례 제4조)
    # 제4조: "실ㆍ본부ㆍ국의 설치" — 실/본부/국 명칭 열거
    art4 = get_content(ord_articles.get("제4조", {}))
    # 키: (조례 조문번호, 기구명, type)
    top_units = []

    # 조례에서 기구명 추출: 제5조 기획조정실, 제5조의2 소방재난본부, ...
    ORD_TYPE_MAP = {
        "실": "실", "본부": "본부", "국": "국", "관": "관",
        "단": "직속기관",  # 추진단 등
    }

    def guess_type(name: str) -> str:
        for suffix, t in ORD_TYPE_MAP.items():
            if name.endswith(suffix):
                return t
        return "국"

    # 조례 제5조~ 순서로 기구 수집 (본청 부분, 제22조 이전)
    CHAPTER2_ARTICLES = [
        ("제4조", None),  # 설치 조문
        ("제5조", "기획조정실"), ("제5조의2", "소방재난본부"),
        ("제6조", "경제실"), ("제7조", "복지실"), ("제8조", "교통실"),
        ("제9조", "기후환경본부"), ("제10조", "문화본부"),
        ("제11조", "관광체육국"), ("제12조", "평생교육국"),
        ("제12조의2", "시민건강국"), ("제12조의3", "민생노동국"),
        ("제12조의4", "디지털도시국"), ("제13조", "행정국"),
        ("제14조", "재무국"), ("제14조의2", "민생사법경찰국"),
        ("제15조", "재난안전실"), ("제16조", "주택실"),
        ("제17조", "도시공간본부"), ("제18조", "균형발전본부"),
        ("제19조", "정원도시국"), ("제20조", "물순환안전국"),
        ("제21조", "한시기구"),
    ]

    # 시행규칙에서 직속기관 장 직급 추출하는 헬퍼
    def extract_grade_from_text(text: str) -> str:
        m = re.search(r"(지방관리관|지방이사관|지방부이사관|지방서기관|지방사무관|[1-9]급)", text)
        return m.group(1) if m else ""

    # 직급 → 표준 변환
    GRADE_MAP = {
        "지방관리관": "2급",
        "지방이사관": "3급",
        "지방부이사관": "4급",
        "지방서기관": "5급",
        "지방사무관": "6급",
        "고위공무원단": "고위공무원단",
    }

    def normalize_grade(raw: str) -> str:
        return GRADE_MAP.get(raw, raw)

    # 시행규칙에서 과/담당관 수집
    # 시행규칙 제10조(기획조정실): "기획조정실장 밑에 정책기획관·재정기획관·..."
    def get_sub_units(rule_art_key: str, parent_name: str) -> list[dict]:
        """시행규칙 조문에서 과/담당관 목록과 직급 추출"""
        a = rule_articles.get(rule_art_key, {})
        text = get_content(a)
        if not text:
            return []

        # 행 단위 파싱: "과장ㆍ담당관은 ○○로 보한다."
        sub_units = []

        # 과/담당관 목록 추출 (첫 문장 또는 항1)
        # 패턴: "X에 A과·B담당관·C기획관을 둔다"
        place_match = re.search(r"밑에\s+(.+?)을\s+두", text)
        if not place_match:
            place_match = re.search(r"에\s+(.+?)을?\s+둔다", text)

        names_raw = place_match.group(1) if place_match else ""
        # 구분자: ·ㆍ,、 등
        names = re.split(r"[·ㆍ,、\s]+", names_raw) if names_raw else []
        # 조사 제거: "생활환경과를" → "생활환경과"
        names = [re.sub(r"[을를이가은는]$", "", n).strip() for n in names]
        names = [n for n in names if n and len(n) > 1]

        # 직급 추출: "○○과장은 지방이사관 또는 지방부이사관으로"
        grade_map_local = {}
        for m in re.finditer(r"([\w]+(?:과장|담당관|기획관|부장|단장|팀장))\s*(?:은|는)\s*(지방관리관|지방이사관|지방부이사관|지방서기관|지방사무관|[1-9]급)", text):
            role = m.group(1)
            grade = m.group(2)
            grade_map_local[role] = normalize_grade(grade)

        for name in names:
            unit_type = "담당관" if "담당관" in name or "기획관" in name else "과"
            head_pos = name + "장" if not name.endswith("관") else name
            grade_raw = grade_map_local.get(head_pos, "")
            if not grade_raw:
                # fallback: "과장은 지방X"
                m2 = re.search(r"과장[은는]\s*(지방\w+|[1-9]급)", text)
                grade_raw = normalize_grade(m2.group(1)) if m2 else ""

            sub_units.append({
                "name": name,
                "type": unit_type,
                "head_grade": grade_raw,
                "근거조문": f"시행규칙 {rule_art_key}",
            })
        return sub_units

    # 시행규칙 과 → 조례 국 매핑
    # 시행규칙 제10조 → 조례 기획조정실 (제5조)
    RULE_TO_ORD = {
        "제10조": "제5조",        # 기획조정실
        "제10조의2": "제5조의2",  # 소방재난본부
        "제11조": "제6조",        # 경제실
        "제12조": "제7조",        # 복지실
        "제13조": "제8조",        # 교통실
        "제14조": "제9조",        # 기후환경본부
        "제15조": "제10조",       # 문화본부
        "제16조": "제11조",       # 관광체육국
        "제17조": "제12조",       # 평생교육국
        "제17조의2": "제12조의2", # 시민건강국
        "제17조의3": "제12조의3", # 민생노동국
        "제17조의4": "제12조의4", # 디지털도시국
        "제17조의5": "제13조",    # 행정국
        "제17조의6": "제14조",    # 재무국
        "제17조의7": "제14조의2", # 민생사법경찰국
        "제20조": "제15조",       # 재난안전실
        "제20조의2": "제16조",    # 주택실
        "제21조": "제17조",       # 도시공간본부
        "제22조": "제18조",       # 균형발전본부
        "제23조": "제19조",       # 정원도시국
        "제24조": "제20조",       # 물순환안전국
    }

    # 직속기관 파악 (조례 제3장부터)
    # 조례 제22조 이후 = 직속기관
    AGENCY_ARTICLES = {}
    for key, art in ord_articles.items():
        num = int(re.search(r"\d+", key).group()) if re.search(r"\d+", key) else 0
        if num >= 22:
            title = art.get("조제목", "")
            if title and "설치" not in title and "직제" not in title:
                AGENCY_ARTICLES[key] = art

    # 3. structure 구성
    structure = []
    validation_notes = []

    for ord_key, unit_name in CHAPTER2_ARTICLES:
        if ord_key == "제4조" or not unit_name or unit_name == "한시기구":
            continue
        ord_art = ord_articles.get(ord_key, {})
        if not ord_art:
            validation_notes.append(f"조문 없음: {ord_key} ({unit_name})")
            continue

        content = get_content(ord_art)
        unit_type = guess_type(unit_name)
        uid = build_id(region_code, unit_name)

        # 시행규칙에서 하위 과/담당관
        rule_key = next((rk for rk, ok in RULE_TO_ORD.items() if ok == ord_key), None)
        children = []
        if rule_key:
            subs = get_sub_units(rule_key, unit_name)
            for s in subs:
                child_id = build_id(region_code, unit_name, s["name"])
                duty_text = ""  # 과별 분장사무는 시행규칙에 별도 조문으로 있음
                children.append({
                    "id": child_id,
                    "type": s["type"],
                    "name": s["name"],
                    "level": 2,
                    "head_position": s["name"] + ("장" if not s["name"].endswith("관") else ""),
                    "head_grade": s["head_grade"],
                    "정원": None,
                    "근거조문": s["근거조문"],
                    "분장사무_원문": duty_text,
                    "분장사무_항목": [],
                    "키워드_태그": apply_keywords(s["name"] + " " + duty_text),
                    "children": [],
                })

        # 실/본부/국 직급 (시행규칙에서)
        rule_art = rule_articles.get(rule_key, {}) if rule_key else {}
        rule_text = get_content(rule_art)
        head_grade_raw = ""
        if rule_text:
            # 실장/국장/본부장 직급 추출 — 직후 또는 문장 내 어디서나
            m = re.search(
                r"(?:실장|본부장|국장)[은는].*?(고위공무원단|지방관리관|지방이사관|지방부이사관|[1-9]급)",
                rule_text, re.DOTALL
            )
            if m:
                head_grade_raw = normalize_grade(m.group(1))

        duties_items = parse_duties(content)

        node = {
            "id": uid,
            "type": unit_type,
            "name": unit_name,
            "level": 1,
            "head_position": unit_name + ("장" if not unit_name.endswith("국") else "장"),
            "head_grade": head_grade_raw,
            "정원": None,
            "근거조문": f"조례 {ord_key}",
            "상위법령_매칭": None,
            "분장사무_원문": content,
            "분장사무_항목": duties_items,
            "키워드_태그": apply_keywords(unit_name + " " + content),
            "children": children,
        }
        structure.append(node)

    # 직속기관 파싱 — 제X절 헤더에서 기관명 추출
    # 패턴: is_art=N인 조문 중 내용이 "제X절 기관명" 형식
    all_articles_raw = [a for a in ord_data["articles"]]

    def parse_direct_agencies() -> list[dict]:
        agencies = []
        current_name = None
        install_content = ""
        duty_content = ""
        install_ref = ""
        duty_ref = ""
        head_pos = ""

        for a in all_articles_raw:
            num_raw = a["조문번호"]
            raw = num_raw[-1] if isinstance(num_raw, list) and num_raw else str(num_raw)
            base_num = int(raw[:4]) if len(raw) >= 4 else 0
            is_art = a.get("조문여부", "")
            title = a.get("조제목", "")
            content = get_content(a)

            if base_num < 22:
                continue

            # 절 헤더에서 기관명 추출
            if is_art == "N" and content:
                m = re.search(r"제\d+절\s+(.+)", content.strip())
                if m:
                    # 기관명 클린업: <개정...>, <신설...> 제거
                    raw_name = m.group(1).strip()
                    clean_name = re.sub(r"\s*[<〈][^>〉]+[>〉]", "", raw_name).strip()
                    # 이전 기관 저장
                    if current_name:
                        agencies.append(_make_agency(
                            region_code, current_name, install_content,
                            duty_content, install_ref, duty_ref, head_pos
                        ))
                    current_name = clean_name
                    install_content = ""
                    duty_content = ""
                    install_ref = ""
                    duty_ref = ""
                    head_pos = ""

            elif is_art == "Y" and current_name:
                art_ref = article_num_to_str(num_raw)
                if title == "설치" or title == "소관사무":
                    if title == "설치":
                        install_content = content
                        install_ref = f"조례 {art_ref}"
                    elif title == "소관사무":
                        duty_content = content
                        duty_ref = f"조례 {art_ref}"
                elif title in ("소장", "원장", "관장", "총장", "단장", "본부장", "대장", "서장", "교장", "위원장"):
                    head_pos = title

        if current_name:
            agencies.append(_make_agency(
                region_code, current_name, install_content,
                duty_content, install_ref, duty_ref, head_pos
            ))
        return agencies

    def _make_agency(rc, name, install_txt, duty_txt, install_ref, duty_ref, head_pos):
        combined = install_txt + " " + duty_txt
        return {
            "id": build_id(rc, "직속기관", name),
            "type": "직속기관",
            "name": name,
            "level": 1,
            "head_position": head_pos or (name + "장"),
            "head_grade": "",
            "정원": None,
            "근거조문": install_ref or duty_ref,
            "분장사무_원문": duty_txt,
            "분장사무_항목": parse_duties(duty_txt),
            "키워드_태그": apply_keywords(name + " " + combined),
            "children": [],
        }

    for agency in parse_direct_agencies():
        # 삭제된 기관 필터링
        if "삭제" in agency["name"]:
            continue
        structure.append(agency)

    # 4. 정원 검증
    total_from_ordinance = staff_data.get("total_staff", 19171)
    # 부서별 합산은 별표4에 있지만 현재 파싱 미완 → 합산 스킵
    validation = {
        "정원_합산_일치": None,  # 별표4 상세 파싱 후 검증 예정
        "정원_총_조례기준": total_from_ordinance,
        "분장사무_누락_부서": [
            n["name"] for n in structure if not n["분장사무_원문"] and n["type"] not in ("직속기관",)
        ],
        "비고": validation_notes,
    }

    # 5. 출력 JSON
    output = {
        "region": {
            "code": region_code,
            "name": region_name,
            "level": "광역",
            "type": "특별시",
            "parent": None,
        },
        "source": {
            "ordinance": {
                "name": ord_data["law_name"],
                "mst": ord_data["mst"],
                "last_amended": ord_data["last_amended"],
                "url": f"https://www.law.go.kr/DRF/lawService.do?OC=open&target=ordin&MST={ord_data['mst']}&type=HTML",
                "fetched_at": "2026-05-09",
            },
            "enforcement_rule": {
                "name": rule_data["law_name"],
                "mst": rule_data["mst"],
                "last_amended": rule_data["last_amended"],
                "url": f"https://www.law.go.kr/DRF/lawService.do?OC=open&target=ordin&MST={rule_data['mst']}&type=HTML",
                "fetched_at": "2026-05-09",
            },
            "staff_ordinance": {
                "name": staff_data["law_name"],
                "mst": staff_data["mst"],
                "last_amended": staff_data["last_amended"],
                "fetched_at": "2026-05-09",
            },
        },
        "totals": {
            "정원_총": total_from_ordinance,
            "정원_근거조문": "서울특별시 공무원 정원 조례 제2조",
            "정원_비고": "소방·경찰 제외 11,730명 포함 총 19,171명",
        },
        "structure": structure,
        "validation": validation,
    }

    return output


# ─── 마포구 파서 ──────────────────────────────────────
def parse_mapo() -> dict:
    region_code = "11440"
    region_name = "서울특별시 마포구"
    BASE_DIR_RAW = Path(__file__).parent.parent / "data" / "raw"

    with open(BASE_DIR_RAW / "ordinances/기초/마포구_행정기구설치조례.json", encoding="utf-8") as f:
        ord_data = json.load(f)
    with open(BASE_DIR_RAW / "시행규칙/마포구_행정기구설치조례_시행규칙.json", encoding="utf-8") as f:
        rule_data = json.load(f)

    ord_articles = {article_num_to_str(a["조문번호"]): a
                    for a in ord_data["articles"] if a.get("조문여부") == "Y"}
    rule_articles = {article_num_to_str(a["조문번호"]): a
                     for a in rule_data["articles"] if a.get("조문여부") == "Y"}

    # 국 목록 (조례 제3조에서 추출)
    art3 = get_content(ord_articles.get("제3조", {}))
    # "행정지원국, 복지동행국, ..." 추출
    m = re.search(r"두[어]?\s*[,、]\s*(.+?)\s*을\s*둔다", art3, re.DOTALL)
    if not m:
        m = re.search(r"(?:를 두고[,、]\s*)(.+?)\s*을\s*둔다", art3, re.DOTALL)

    # 직접 추출 (조례 제4조~11조: 각 국)
    DEPT_ARTICLES = {
        "제4조": "행정지원국",
        "제5조": "복지동행국",
        "제6조": "교육체육국",
        "제7조": "관광경제국",
        "제8조": "재정관리국",
        "제9조": "환경녹지국",
        "제10조": "도시관리국",
        "제11조": "교통건설국",
    }

    # 시행규칙 국별 조문 번호 매핑 (국장 직급 + 과 목록)
    # 시행규칙 제5조 = 행정지원국, 제11조 = 복지동행국 등
    RULE_DEPT_MAP = {
        "행정지원국": "제5조",
        "복지동행국": "제11조",
        "교육체육국": "제18조",
        "관광경제국": "제23조",
        "재정관리국": "제28조",
        "환경녹지국": "제35조",
        "도시관리국": "제40조",
        "교통건설국": "제45조",
    }

    # 시행규칙에서 과 목록과 직급 추출
    def extract_sub_units_mapo(dept_name: str) -> list[dict]:
        rule_key = RULE_DEPT_MAP.get(dept_name)
        if not rule_key:
            return []
        dept_art = rule_articles.get(rule_key, {})
        dept_text = get_content(dept_art)

        # 국장 직급
        m_grade = re.search(r"국장[은는]\s*(지방서기관|지방이사관|지방부이사관|지방관리관|[1-9]급)", dept_text)
        dept_grade = normalize_grade(m_grade.group(1)) if m_grade else ""

        # 과장 직급
        m_sub_grade = re.search(r"과장[은는]\s*(지방행정사무관|지방서기관|[1-9]급)", dept_text)
        default_sub_grade = ""
        if m_sub_grade:
            raw = m_sub_grade.group(1)
            default_sub_grade = "6급" if "사무관" in raw else normalize_grade(raw)

        # 다음 조문들이 이 국의 과별 분장사무
        # 조문 번호를 순서대로 순회하여 연속된 과 조문 수집
        rule_base_num = int(re.search(r"\d+", rule_key).group())
        children = []
        num = rule_base_num + 1

        while True:
            sub_key = f"제{num}조"
            sub_art = rule_articles.get(sub_key)
            if not sub_art:
                break
            sub_title = sub_art.get("조제목", "")
            sub_content = get_content(sub_art)
            # 새 국 시작 또는 다른 섹션이면 중단
            if sub_title in RULE_DEPT_MAP or not sub_title or "보건소" in sub_title:
                break
            # 과 이름 확인
            if "과" in sub_title or "담당관" in sub_title:
                duties = parse_duties(sub_content)
                children.append({
                    "id": build_id(region_code, dept_name, sub_title),
                    "type": "담당관" if "담당관" in sub_title else "과",
                    "name": sub_title,
                    "level": 2,
                    "head_position": sub_title + "장",
                    "head_grade": default_sub_grade,
                    "정원": None,
                    "근거조문": f"시행규칙 {sub_key}",
                    "분장사무_원문": sub_content,
                    "분장사무_항목": duties,
                    "키워드_태그": apply_keywords(sub_title + " " + sub_content),
                    "children": [],
                })
            num += 1

        return dept_grade, children

    # 구조 생성
    structure = []
    validation_notes = []

    GRADE_MAP_MAPO = {
        "지방관리관": "2급", "지방이사관": "3급", "지방부이사관": "4급",
        "지방서기관": "5급", "지방행정사무관": "6급", "지방사무관": "6급",
    }

    def normalize_grade(raw):
        return GRADE_MAP_MAPO.get(raw, raw)

    for ord_key, dept_name in DEPT_ARTICLES.items():
        ord_art = ord_articles.get(ord_key, {})
        content = get_content(ord_art)

        dept_grade, children = extract_sub_units_mapo(dept_name)

        structure.append({
            "id": build_id(region_code, dept_name),
            "type": "국",
            "name": dept_name,
            "level": 1,
            "head_position": dept_name + "장",
            "head_grade": dept_grade,
            "정원": None,
            "근거조문": f"조례 {ord_key}",
            "분장사무_원문": content,
            "분장사무_항목": parse_duties(content),
            "키워드_태그": apply_keywords(dept_name + " " + content),
            "children": children,
        })

    # 보좌기관 (조례 제3조② — "부구청장 소속으로 X담당관과 Y담당관을 두고")
    # 타 지자체와 동일 패턴: type="관", name="보좌기관" 부모 아래 개별 보좌기관을 자식으로 구성
    DANGGWAN_RULE_MAP = {
        "새마포담당관": "제3조",
        "감사담당관": "제4조",
    }
    art3_para2 = ""
    m_para2 = re.search(r"②(.+?)(?=③|$)", art3, re.DOTALL)
    if m_para2:
        art3_para2 = m_para2.group(1)
    dg_names = re.findall(r"([가-힣]+담당관)", art3_para2)
    dg_children = []
    seen_dg = set()
    for dg_name in dg_names:
        if dg_name in seen_dg:
            continue
        seen_dg.add(dg_name)
        rule_key = DANGGWAN_RULE_MAP.get(dg_name, "")
        rule_art = rule_articles.get(rule_key, {}) if rule_key else {}
        rule_text = get_content(rule_art)
        m_grade = re.search(r"담당관[은는]\s*(지방행정사무관|지방서기관|지방부이사관|지방이사관|[1-9]급)", rule_text)
        dg_grade = normalize_grade(m_grade.group(1)) if m_grade else ""
        duties = parse_duties(rule_text)
        dg_children.append({
            "id": build_id(region_code, "보좌기관", dg_name),
            "type": "담당관",
            "name": dg_name,
            "level": 2,
            "head_position": dg_name,
            "head_grade": dg_grade,
            "정원": None,
            "근거조문": "조례 제3조②",
            "분장사무_원문": rule_text,
            "분장사무_항목": duties,
            "키워드_태그": apply_keywords(dg_name + " " + rule_text),
            "children": [],
        })
    if dg_children:
        combined_text = " ".join(c["분장사무_원문"] for c in dg_children)
        structure.append({
            "id": build_id(region_code, "보좌기관"),
            "type": "관",
            "name": "보좌기관",
            "level": 1,
            "head_position": "보좌기관",
            "head_grade": "",
            "정원": None,
            "근거조문": "조례 제3조②",
            "분장사무_원문": art3_para2,
            "분장사무_항목": [],
            "키워드_태그": apply_keywords("보좌기관 " + combined_text),
            "children": dg_children,
        })

    # 보건소 직속기관
    art12 = get_content(ord_articles.get("제12조", {}))
    art14 = get_content(ord_articles.get("제14조", {}))
    # 보건소 하위 과 (시행규칙 후반부)
    보건소_children = []
    for key, art in rule_articles.items():
        num = int(re.search(r"\d+", key).group()) if re.search(r"\d+", key) else 0
        if num < 50:
            continue
        title = art.get("조제목", "")
        if not title or "보건소" in title and "과" not in title:
            continue
        c = get_content(art)
        if "과" in title:
            보건소_children.append({
                "id": build_id(region_code, "보건소", title),
                "type": "과",
                "name": title,
                "level": 2,
                "head_position": title + "장",
                "head_grade": "6급",
                "정원": None,
                "근거조문": f"시행규칙 {key}",
                "분장사무_원문": c,
                "분장사무_항목": parse_duties(c),
                "키워드_태그": apply_keywords(title + " " + c),
                "children": [],
            })

    structure.append({
        "id": build_id(region_code, "직속기관", "보건소"),
        "type": "직속기관",
        "name": "마포구보건소",
        "level": 1,
        "head_position": "소장",
        "head_grade": "",
        "정원": None,
        "근거조문": "조례 제12조",
        "분장사무_원문": art12,
        "분장사무_항목": parse_duties(art12),
        "키워드_태그": apply_keywords("보건소 " + art12 + " " + art14),
        "children": 보건소_children,
    })

    output = {
        "region": {
            "code": region_code,
            "name": region_name,
            "level": "기초",
            "type": "자치구",
            "parent": "11",
        },
        "source": {
            "ordinance": {
                "name": ord_data["law_name"],
                "mst": ord_data["mst"],
                "last_amended": ord_data["last_amended"],
                "url": f"https://www.law.go.kr/DRF/lawService.do?OC=open&target=ordin&MST={ord_data['mst']}&type=HTML",
                "fetched_at": "2026-05-09",
            },
            "enforcement_rule": {
                "name": rule_data["law_name"],
                "mst": rule_data["mst"],
                "last_amended": rule_data["last_amended"],
                "url": f"https://www.law.go.kr/DRF/lawService.do?OC=open&target=ordin&MST={rule_data['mst']}&type=HTML",
                "fetched_at": "2026-05-09",
            },
        },
        "totals": {
            "정원_총": 1479,
            "정원_근거조문": "서울특별시 마포구 지방공무원 정원 조례(예정) 제2조 / MST=2126521",
            "정원_비고": "2026.07.01 시행 예정 정원 조례 기준",
        },
        "structure": structure,
        "validation": {
            "정원_합산_일치": None,
            "정원_총_조례기준": 1479,
            "분장사무_누락_부서": [n["name"] for n in structure if not n["분장사무_원문"]],
            "비고": validation_notes,
        },
    }
    return output


# ─── 단양군 파서 ──────────────────────────────────────
def parse_danyang() -> dict:
    region_code = "33780"
    region_name = "충청북도 단양군"

    with open(RAW_DIR / "ordinances/기초/단양군_행정기구설치조례.json", encoding="utf-8") as f:
        ord_data = json.load(f)
    with open(RAW_DIR / "시행규칙/단양군_행정기구설치조례_시행규칙.json", encoding="utf-8") as f:
        rule_data = json.load(f)
    with open(RAW_DIR / "ordinances/기초/단양군_지방공무원정원조례.json", encoding="utf-8") as f:
        staff_data = json.load(f)

    ord_articles = {article_num_to_str(a["조문번호"]): a
                    for a in ord_data["articles"] if a.get("조문여부") == "Y"}
    rule_articles = {article_num_to_str(a["조문번호"]): a
                     for a in rule_data["articles"] if a.get("조문여부") == "Y"}

    def extract_sub_names(content: str) -> list[str]:
        """'X국에 A과, B과, C과를 둔다' 형태에서 과 이름 추출"""
        m = re.search(r"에는?\s*(.+?)\s*[을를]\s*둔다", content, re.DOTALL)
        if not m:
            return []
        raw = m.group(1)
        names = re.split(r"[,、ㆍ\s]+", raw)
        return [n.strip() for n in names if n.strip() and ("과" in n or "담당관" in n)]

    structure = []

    # 1. 보좌기관 — 기획예산담당관 (조례 제3조의2)
    # 타 지자체와 동일 패턴: type="관", name="보좌기관" 부모 아래 개별 보좌기관을 자식으로 구성
    art3_2_content = get_content(ord_articles.get("제3조의2", {}))
    boja_child = {
        "id": build_id(region_code, "보좌기관", "기획예산담당관"),
        "type": "담당관",
        "name": "기획예산담당관",
        "level": 2,
        "head_position": "기획예산담당관",
        "head_grade": "",  # 시행규칙 별표 1 제1호
        "정원": None,
        "근거조문": "조례 제3조의2",
        "분장사무_원문": art3_2_content,
        "분장사무_항목": [],  # 시행규칙 별표 2
        "키워드_태그": apply_keywords("기획예산담당관 " + art3_2_content),
        "children": [],
    }
    structure.append({
        "id": build_id(region_code, "보좌기관"),
        "type": "관",
        "name": "보좌기관",
        "level": 1,
        "head_position": "보좌기관",
        "head_grade": "",
        "정원": None,
        "근거조문": "조례 제3조의2",
        "분장사무_원문": "",
        "분장사무_항목": [],
        "키워드_태그": apply_keywords("보좌기관 " + art3_2_content),
        "children": [boja_child],
    })

    # 2. 3개 국 (행정복지국·관광건설국·농림환경국)
    DEPT_ORD_KEYS = ["제3조의3", "제3조의4", "제3조의5"]
    for art_key in DEPT_ORD_KEYS:
        art = ord_articles.get(art_key, {})
        dept_name = art.get("조제목", "")
        content = get_content(art)
        sub_names = extract_sub_names(content)

        children = []
        for sub_name in sub_names:
            children.append({
                "id": build_id(region_code, dept_name, sub_name),
                "type": "담당관" if "담당관" in sub_name else "과",
                "name": sub_name,
                "level": 2,
                "head_position": sub_name + "장",
                "head_grade": "",  # 시행규칙 별표 1 제2호
                "정원": None,
                "근거조문": f"조례 {art_key}",
                "분장사무_원문": "",  # 시행규칙 별표 2의X
                "분장사무_항목": [],
                "키워드_태그": apply_keywords(sub_name),
                "children": [],
            })

        structure.append({
            "id": build_id(region_code, dept_name),
            "type": "국",
            "name": dept_name,
            "level": 1,
            "head_position": dept_name + "장",
            "head_grade": "",  # 시행규칙 별표 1 제2호
            "정원": None,
            "근거조문": f"조례 {art_key}",
            "분장사무_원문": content,
            "분장사무_항목": parse_duties(content),
            "키워드_태그": apply_keywords(dept_name + " " + content),
            "children": children,
        })

    # 3. 보건의료원 (직속기관)
    art4_content = get_content(ord_articles.get("제4조", {}))
    art5_content = get_content(ord_articles.get("제5조", {}))
    rule_art5_content = get_content(rule_articles.get("제5조", {}))
    rule_art6_content = get_content(rule_articles.get("제6조", {}))

    m_원장 = re.search(r"원장[은는]?\s*(지방[가-힣]+?|개방형직위)(?=으로|은|는|\s)", rule_art5_content)
    원장_grade = m_원장.group(1) if m_원장 else ""

    보건의료원_children = []
    for sub_name in ["보건의료과", "보건사업과"]:
        m_grade = re.search(rf"{sub_name[:-1]}장[은는]\s*(지방[가-힣]+?)(?=으로|은|는|,|\s)", rule_art6_content)
        sub_grade = m_grade.group(1) if m_grade else ""
        보건의료원_children.append({
            "id": build_id(region_code, "보건의료원", sub_name),
            "type": "과",
            "name": sub_name,
            "level": 2,
            "head_position": sub_name + "장",
            "head_grade": sub_grade,
            "정원": None,
            "근거조문": "조례 제5조",
            "분장사무_원문": "",
            "분장사무_항목": [],
            "키워드_태그": apply_keywords(sub_name),
            "children": [],
        })

    structure.append({
        "id": build_id(region_code, "직속기관", "보건의료원"),
        "type": "직속기관",
        "name": "보건의료원",
        "level": 1,
        "head_position": "원장",
        "head_grade": 원장_grade,
        "정원": None,
        "근거조문": "조례 제4조",
        "분장사무_원문": art4_content + " " + art5_content,
        "분장사무_항목": [],  # 시행규칙 별표 3
        "키워드_태그": apply_keywords("보건의료원 " + art4_content + " " + art5_content),
        "children": 보건의료원_children,
    })

    # 4. 농업기술센터 (직속기관)
    art7_content = get_content(ord_articles.get("제7조", {}))
    art8_content = get_content(ord_articles.get("제8조", {}))
    rule_art8_content = get_content(rule_articles.get("제8조", {}))
    rule_art9_content = get_content(rule_articles.get("제9조", {}))

    m_소장 = re.search(r"소장[은는]?\s*(지방[가-힣]+?)(?=으로|은|는|\s)", rule_art8_content)
    소장_grade = m_소장.group(1) if m_소장 else ""

    structure.append({
        "id": build_id(region_code, "직속기관", "농업기술센터"),
        "type": "직속기관",
        "name": "농업기술센터",
        "level": 1,
        "head_position": "소장",
        "head_grade": 소장_grade,
        "정원": None,
        "근거조문": "조례 제7조",
        "분장사무_원문": art7_content + " " + art8_content,
        "분장사무_항목": [],  # 시행규칙 별표 4
        "키워드_태그": apply_keywords("농업기술센터 " + art7_content + " " + art8_content),
        "children": [{
            "id": build_id(region_code, "농업기술센터", "기술담당관"),
            "type": "담당관",
            "name": "기술담당관",
            "level": 2,
            "head_position": "기술담당관",
            "head_grade": "",
            "정원": None,
            "근거조문": "시행규칙 제9조",
            "분장사무_원문": rule_art9_content,
            "분장사무_항목": parse_duties(rule_art9_content),
            "키워드_태그": apply_keywords("기술담당관 " + rule_art9_content),
            "children": [],
        }],
    })

    output = {
        "region": {
            "code": region_code,
            "name": region_name,
            "level": "기초",
            "type": "군",
            "parent": "33",
        },
        "source": {
            "ordinance": {
                "name": ord_data["law_name"],
                "mst": ord_data["mst"],
                "last_amended": ord_data["last_amended"],
                "url": f"https://www.law.go.kr/DRF/lawService.do?OC=open&target=ordin&MST={ord_data['mst']}&type=HTML",
                "fetched_at": "2026-05-09",
            },
            "enforcement_rule": {
                "name": rule_data["law_name"],
                "mst": rule_data["mst"],
                "last_amended": rule_data["last_amended"],
                "url": f"https://www.law.go.kr/DRF/lawService.do?OC=open&target=ordin&MST={rule_data['mst']}&type=HTML",
                "fetched_at": "2026-05-09",
            },
            "staff_ordinance": {
                "name": staff_data["law_name"],
                "mst": staff_data["mst"],
                "last_amended": staff_data["last_amended"],
                "fetched_at": "2026-05-09",
            },
        },
        "totals": {
            "정원_총": 675,
            "정원_근거조문": "단양군 지방공무원 정원 조례 제2조",
            "정원_비고": "집행기관 656명 + 의회사무과 19명",
        },
        "structure": structure,
        "validation": {
            "정원_합산_일치": None,
            "정원_총_조례기준": 675,
            "분장사무_누락_부서": [n["name"] for n in structure if not n["분장사무_원문"]],
            "비고": ["분장사무 별표 미파싱 — 시행규칙 별표 2~6이 이미지/HWP 첨부로 제공됨"],
        },
    }
    return output


# ─── 광역 일반화 파서 ────────────────────────────────────
# 실/국/본부/관 등 레벨1 단위 판별용 접미사
_LEVEL1_SUFFIXES = ("실", "국", "본부", "관", "단", "처")
# 직속기관 판별 접미사
_AGENCY_SUFFIXES = ("원", "소", "센터", "청", "단", "사무처", "기관")

# 파싱에서 제외할 조제목 패턴 (행정적/절차적 조문)
_SKIP_TITLES = re.compile(
    r"^(목적|부지사|부시장|설치|직무|직급|보조|보좌|보좌기관|총칙|"
    r"한시기구|종전|이동|삭제|분장사무|하부조직|소장|원장|소관사무|관장|"
    r"과장|담당관의\s*직급|정원|임용권|의회|비서|예산|"
    r"소속기관|소속행정기관|합의제행정기관|부구청장|부군수|하부행정기관|"
    r"구청장\s*직속|시장\s*직속|군수\s*직속).*"
    r"|실[·ㆍ·]국|실·국|실ㆍ국"  # 실·국·본부 listing articles
)

# Agency section name patterns to exclude from 직속기관 list
_SKIP_AGENCY_NAMES = re.compile(
    r"실[·ㆍ·]국|실·국|실ㆍ국|하부행정|읍.면.동|지방자치단체가\s*아닌"
)

def _is_level1_unit(조제목: str, content: str) -> bool:
    """조제목이 실/국/본부/관/단으로 끝나고 분장사무를 담은 조문인지 판별"""
    if not 조제목 or len(조제목) < 2:
        return False
    if _SKIP_TITLES.match(조제목):
        return False
    if not 조제목.endswith(_LEVEL1_SUFFIXES):
        return False
    # 실제 분장사무 or 설치 조문인지 (둔다: 계양구·달서구형 — 국명이 조제목이고 내용에 과 목록)
    return ("분장" in content or "관장" in content or "처리" in content
            or "수행" in content or "총괄" in content
            or "둔다" in content)


def _extract_flat_org_list(content: str, code: str) -> list[dict]:
    """'실·과의 설치' 조문에서 실·과·단 평면 목록 추출 (국 계층 없음)"""
    m = re.search(r"(?:하여|위하여)[,\s]+(.+?)\s*[을를]\s*둔다", content, re.DOTALL)
    if not m:
        return []
    raw = re.sub(r"<[^>]+>|\([^)]*\)", "", m.group(1))
    parts = re.split(r"[,、ㆍ·\s]+", raw)
    result = []
    for p in parts:
        p = p.strip()
        if not p or len(p) < 2:
            continue
        if not p.endswith(("과", "실", "단", "관", "국", "처", "담당관")):
            continue
        unit_type = _guess_level1_type(p) if not p.endswith("담당관") else "담당관"
        result.append({
            "id": build_id(code, p),
            "type": unit_type, "name": p, "level": 1,
            "head_position": p + ("장" if not p.endswith("담당관") else ""),
            "head_grade": "", "정원": None, "근거조문": "조례",
            "분장사무_원문": "", "분장사무_항목": [],
            "키워드_태그": apply_keywords(p), "children": [],
        })
    return result


def _guess_level1_type(name: str) -> str:
    # "담당관"을 "관"보다 먼저 체크 ("감사담당관" → "담당관", "기획관" → "관")
    for suf in ("과", "실", "본부", "국", "담당관", "관", "단", "처"):
        if name.endswith(suf):
            return suf
    return "과"  # 기본: 평면 목록 단위는 과 수준


def _extract_sub_units_from_rule(rule_articles: dict, unit_name: str,
                                  region_code: str) -> tuple[str, list[dict]]:
    """시행규칙에서 unit_name에 해당하는 과/담당관 목록 및 국장 직급 추출"""
    # 시행규칙 조문 중 조제목이 unit_name과 일치하는 것 검색
    art = rule_articles.get(unit_name, {})
    if not art:
        # 부분 일치: 단위명이 조제목에 포함되는 경우 (개정 태그 등 포함)
        art = next(
            (a for t, a in rule_articles.items() if unit_name in t),
            {}
        )
    text = get_content(art)
    if not text:
        return "", []
    # 조문 헤더(제X조(...)) 제거 — 헤더에 "에" 포함 시 잘못된 매치 방지
    body = _strip_art_header(text)

    # 국장/실장/본부장 직급
    head_grade = ""
    m_hg = re.search(
        r"(?:실장|국장|본부장|관장|단장|처장)[은는].*?"
        r"(고위공무원단|지방관리관|지방이사관|지방부이사관|지방서기관|지방사무관|[1-9]급)",
        body, re.DOTALL
    )
    if m_hg:
        head_grade = _normalize_grade_generic(m_hg.group(1))

    # 과/담당관 이름 추출: "X에 A과·B담당관·C과를 둔다" (광역형)
    # U+2027(‧) = html.unescape('&#8231;') 포함
    _SEP = r"[·ㆍ‧,、\s]+"
    sub_names = []
    m_list = re.search(r"(?:에|밑에)\s*(.+?)\s*[을를]\s*둔다", body, re.DOTALL)
    if m_list:
        raw = m_list.group(1)
        parts = re.split(_SEP, raw)
        for p in parts:
            p = re.sub(r"[을를이가은는]$", "", p.strip())
            if p and len(p) >= 2 and ("과" in p or "담당관" in p or "기획관" in p or "관" in p):
                sub_names.append(p)

    # 직접 열거 패턴: "A과ㆍB과ㆍC과 및 D센터를 둔다" (접두 에/밑에 없이)
    if not sub_names:
        for m in re.finditer(
            r"([가-힣]+(?:과|담당관|실|단)(?:[·ㆍ‧,]\s*[가-힣]+(?:과|담당관|실|단))*"
            r"(?:\s*및\s*[가-힣]+(?:과|담당관|실|단|센터|소))*)\s*[을를]\s*둔다",
            body
        ):
            raw = m.group(1)
            parts = re.split(r"[·ㆍ‧,]\s*|\s*및\s*", raw)
            for p in parts:
                p = p.strip()
                if p and len(p) >= 2 and p not in sub_names:
                    sub_names.append(p)

    # 기초형 패턴: "A과장ㆍB과장ㆍC과장은 지방...으로 보한다"
    if not sub_names:
        for m in re.finditer(
            r"([가-힣]+(?:과장|담당관)(?:(?:[ㆍ·‧,]|\s*및\s*)\s*[가-힣]+(?:과장|담당관))*)[은는]",
            body
        ):
            chunk = m.group(1)
            for raw_part in re.split(r"[ㆍ·‧,]\s*|\s*및\s*", chunk):
                raw_part = raw_part.strip()
                name = re.sub(r"장$", "", raw_part)
                if name and len(name) >= 2 and name not in sub_names:
                    sub_names.append(name)

    children = []
    for sname in sub_names:
        unit_type = "담당관" if ("담당관" in sname or "기획관" in sname) else "과"
        children.append({
            "id": build_id(region_code, unit_name, sname),
            "type": unit_type,
            "name": sname,
            "level": 2,
            "head_position": sname + ("장" if not sname.endswith("관") else ""),
            "head_grade": "",
            "정원": None,
            "근거조문": f"시행규칙",
            "분장사무_원문": "",
            "분장사무_항목": [],
            "키워드_태그": apply_keywords(sname),
            "children": [],
        })
    return head_grade, children


def _extract_subs_inline(content: str, code: str, parent_name: str) -> list:
    """'X국에 A과, B과를 둔다' 조례 본문에서 직접 하위 과/담당관 추출"""
    # 조문 헤더 제거 후 처리 (헤더 내 "에"가 잘못 매치되어 ")①" 등이 끼어드는 현상 방지)
    body = _strip_art_header(content)
    subs = []
    # 우선: "X국에 A과, B과를 둔다" 인라인 열거 패턴
    # 분장사무 numbered list(1. 폐기물처리...)보다 먼저 시도해야 오염 방지
    m = re.search(r"에는?\s*(.+?)\s*[을를]\s*둔다", body, re.DOTALL)
    if m:
        raw = m.group(1)
        raw = re.sub(r"<[^>]+>|\([^)]*\)", "", raw)
        # U+2027(‧, html.unescape('&#8231;'))도 구분자로 처리
        parts = re.split(r"[,、ㆍ·‧\s]+|및", raw)
        for p in parts:
            p = p.strip()
            if p and len(p) >= 2 and (
                p.endswith("과") or "담당관" in p or p.endswith("실") or p.endswith("단")
            ):
                subs.append(p)
    if not subs:
        # 번호 목록 형식 fallback: "1. 기획예산과" 가 한 줄 전체인 경우
        # ② 또는 분장 서술 이전 부분만 검색해 분장사무 항목과 혼동 방지
        first_part = re.split(r"②|분장한다|분장하며", body)[0]
        numbered = re.findall(
            r"^\s*\d+\.\s*([가-힣]{2,10}(?:과|실|담당관|단))\s*$",
            first_part, re.MULTILINE,
        )
        subs = numbered
    result = []
    for s in subs:
        unit_type = "담당관" if "담당관" in s else ("실" if s.endswith("실") else "과")
        result.append({
            "id": build_id(code, parent_name, s),
            "type": unit_type,
            "name": s,
            "level": 2,
            "head_position": s + ("장" if not s.endswith("관") else ""),
            "head_grade": "",
            "정원": None,
            "근거조문": "조례",
            "분장사무_원문": "",
            "분장사무_항목": [],
            "키워드_태그": apply_keywords(s),
            "children": [],
        })
    return result


def _normalize_grade_generic(raw: str) -> str:
    MAP = {
        "지방관리관": "2급", "지방이사관": "3급", "지방부이사관": "4급",
        "지방서기관": "5급", "지방사무관": "6급",
        "고위공무원단": "고위공무원단",
    }
    return MAP.get(raw, raw)


def _extract_total_staff(staff_articles: list[dict]) -> int:
    """정원조례 제2조에서 총정원 추출"""
    for a in staff_articles:
        if a.get("조문여부") != "Y":
            continue
        title = a.get("조제목", "")
        content = get_content(a)
        # "총수" 또는 "정원의 총수" 조문 우선
        if "총수" in title or "정원" in title:
            m = re.search(r"총수[는은]?\s*([\d,]+)\s*명", content)
            if m:
                return int(m.group(1).replace(",", ""))
            m2 = re.search(r"총수는\s*([\d,]+)", content)
            if m2:
                return int(m2.group(1).replace(",", ""))
            # "(이하 "공무원"이라 한다)의 정원의 총수는 X명으로" 패턴
            m3 = re.search(r"정원(?:의\s*총수)?[는은]\s*([\d,]+)\s*명", content)
            if m3:
                return int(m3.group(1).replace(",", ""))
    # 모든 조문에서 대형 숫자 검색 (최후 수단)
    for a in staff_articles:
        if a.get("조문여부") != "Y":
            continue
        content = get_content(a)
        # 최소 3자리 이상 숫자 + "명"
        matches = re.findall(r"([\d,]{3,})\s*명", content)
        if matches:
            nums = [int(m.replace(",", "")) for m in matches]
            # 합리적인 정원 범위 (100~30000)
            valid = [n for n in nums if 100 <= n <= 30000]
            if valid:
                return max(valid)  # 가장 큰 숫자 = 총정원
    return 0


def parse_gwangyeok_generic(
    code: str,
    name: str,
    region_type: str,
    parent: str,
    ord_path: Path,
    rule_path: Path,
    staff_path: Path,
    fetched_at: str = "2026-05-09",
) -> dict:
    with open(ord_path, encoding="utf-8") as f:
        ord_data = json.load(f)
    # rule_path와 ord_path가 같은 파일일 수 있음 (통합 조례)
    same_file = ord_path.resolve() == rule_path.resolve()
    rule_data = ord_data if same_file else json.load(open(rule_path, encoding="utf-8"))
    staff_data = json.load(open(staff_path, encoding="utf-8"))

    all_ord_arts = ord_data["articles"]
    ord_articles_by_title = {}
    for a in all_ord_arts:
        if a.get("조문여부") == "Y":
            t = a.get("조제목", "").strip()
            if t:
                ord_articles_by_title[t] = a

    rule_articles_by_title = {}
    for a in rule_data["articles"]:
        if a.get("조문여부") == "Y":
            t = re.sub(r"\s*<[^>]+>.*", "", a.get("조제목", "") or "").strip()
            if t:
                rule_articles_by_title[t] = a

    structure = []
    validation_notes = []

    # 현재 챕터 추적 (1=총칙, 2=본청, 3+=직속기관)
    current_chapter = 1
    CHAPTER_PAT = re.compile(r"제\s*(\d+)\s*장")  # "제 2 장" 공백 포함 처리

    for a in all_ord_arts:
        is_art = a.get("조문여부", "")
        조제목 = (a.get("조제목", "") or "").strip()
        content = get_content(a)

        if is_art == "N":
            m_ch = CHAPTER_PAT.search(content)
            if m_ch:
                current_chapter = int(m_ch.group(1))
            continue

        # 삭제/이동된 조문 스킵
        if "삭제" in content[:30] or "이동" in content[:30]:
            continue

        # current_chapter <= 3: 안동시처럼 본청이 제3장에 오는 경우도 처리
        if current_chapter <= 3 and _is_level1_unit(조제목, content):
            unit_type = _guess_level1_type(조제목)
            uid = build_id(code, 조제목)
            duties = parse_duties(content)

            # 시행규칙에서 하위 과 추출
            head_grade, children = _extract_sub_units_from_rule(
                rule_articles_by_title, 조제목, code
            )
            # 조례 본문 인라인 추출로 보완 (규칙 추출보다 많으면 교체)
            inline_children = _extract_subs_inline(content, code, 조제목)
            if len(inline_children) > len(children):
                children = inline_children
            # head_grade가 없으면 조례 본문에서 추출 시도
            if not head_grade:
                m_hg = re.search(
                    r"(?:실장|국장|본부장|관장|단장)[은는].*?"
                    r"(고위공무원단|지방관리관|지방이사관|지방부이사관|지방서기관|[1-9]급)",
                    content, re.DOTALL
                )
                if m_hg:
                    head_grade = _normalize_grade_generic(m_hg.group(1))

            num_raw = a.get("조문번호", "")
            art_ref = article_num_to_str(num_raw)

            # 중복 방지: 이미 추가된 기구(평면 목록 선처리)는 업데이트만 수행
            existing = next((n for n in structure if n["name"] == 조제목), None)
            if existing:
                if children:
                    existing["children"] = children
                if head_grade:
                    existing["head_grade"] = head_grade
                if duties:
                    existing["분장사무_항목"] = duties
                existing["분장사무_원문"] = content
                existing["키워드_태그"] = apply_keywords(조제목 + " " + content)
            else:
                structure.append({
                    "id": uid,
                    "type": unit_type,
                    "name": 조제목,
                    "level": 1,
                    "head_position": 조제목 + "장",
                    "head_grade": head_grade,
                    "정원": None,
                    "근거조문": f"조례 {art_ref}",
                    "분장사무_원문": content,
                    "분장사무_항목": duties,
                    "키워드_태그": apply_keywords(조제목 + " " + content),
                    "children": children,
                })

        elif current_chapter <= 3:
            # "X국에 두는 과" / "X실에 두는 과" 패턴 처리
            # current_chapter <= 3: 챕터 마커 없는 경우(목포시형), 본청이 3장인 경우(안동시형) 포함
            m_in = re.match(r"^([가-힣]+(?:국|실|본부|관|단|처))에\s*두는", 조제목)
            if m_in:
                parent_name = m_in.group(1)
                parent_type = _guess_level1_type(parent_name)
                children = _extract_subs_inline(content, code, parent_name)
                num_raw = a.get("조문번호", "")
                art_ref = article_num_to_str(num_raw)
                existing = next((n for n in structure if n["name"] == parent_name), None)
                if existing:
                    existing["children"].extend(children)
                else:
                    structure.append({
                        "id": build_id(code, parent_name),
                        "type": parent_type,
                        "name": parent_name,
                        "level": 1,
                        "head_position": parent_name + "장",
                        "head_grade": "",
                        "정원": None,
                        "근거조문": f"조례 {art_ref}",
                        "분장사무_원문": content,
                        "분장사무_항목": parse_duties(content),
                        "키워드_태그": apply_keywords(parent_name + " " + content),
                        "children": children,
                    })
            # "실·과의 설치" / "실ㆍ담당관ㆍ과의 설치" 등 — 단일 조문에 평면 목록
            # (영광군·화순군·울릉군·완도군·청양군형)
            elif ("설치" in 조제목 and not _SKIP_TITLES.match(조제목)
                  and re.search(r"[·ㆍ,]", 조제목)
                  and ("를 둔다" in content or "을 둔다" in content)):
                flat = _extract_flat_org_list(content, code)
                for u in flat:
                    if not any(n["name"] == u["name"] for n in structure):
                        structure.append(u)
            # 보좌기관(감사실 등) 직접 정의 조문 — "감사실에 ...를 둔다" 또는 감사실 단독
            elif (조제목.endswith(_LEVEL1_SUFFIXES)
                  and not _SKIP_TITLES.match(조제목)
                  and "둔다" in content
                  and not any(n["name"] == 조제목 for n in structure)):
                children = _extract_subs_inline(content, code, 조제목)
                num_raw = a.get("조문번호", "")
                art_ref = article_num_to_str(num_raw)
                structure.append({
                    "id": build_id(code, 조제목),
                    "type": _guess_level1_type(조제목), "name": 조제목,
                    "level": 1, "head_position": 조제목 + "장",
                    "head_grade": "", "정원": None,
                    "근거조문": f"조례 {art_ref}",
                    "분장사무_원문": content,
                    "분장사무_항목": parse_duties(content),
                    "키워드_태그": apply_keywords(조제목 + " " + content),
                    "children": children,
                })

    # ── Post 1: 과/담당관 하위 기구 분장사무 채우기 (시행규칙 개별 조문) ──
    # 시행규칙에 과/담당관 이름과 일치하는 조문이 있으면 분장사무_원문 채움
    for unit in structure:
        for child in unit.get("children", []):
            if child.get("분장사무_원문"):
                continue
            cname = child["name"]
            rule_art = rule_articles_by_title.get(cname)
            if not rule_art:
                # 개정 태그 포함 조제목 부분 일치
                rule_art = next(
                    (a for t, a in rule_articles_by_title.items()
                     if cname == t.split("<")[0].strip()),
                    None
                )
            if rule_art:
                rt = get_content(rule_art)
                if rt:
                    child["분장사무_원문"] = rt
                    child["분장사무_항목"] = parse_duties(rt)
                    child["키워드_태그"] = apply_keywords(cname + " " + rt)

    # ── Post 2: 보좌기관 그룹 추출 (담당관·단·과·실·관 통합) ──
    # 조례의 "보좌기관" 유형 조문에서 단위 명단을 모두 추출하고,
    # 이미 다른 경로로 파싱된 동명의 level-1 단위가 있으면 그룹 자식으로 흡수한다.
    # (예: 동작구 — 감사담당관·홍보담당관·핵심정책추진단·운영지원과)
    _BOSWA_TITLE_RE = re.compile(
        r"보좌기관|독립.*담당관|국에\s*속하지|국에\s*설치하지"
    )
    # 단위명 자체로는 부적합한 일반어
    _BOSWA_GENERIC = {
        "보좌기관", "보조기관", "보조·보좌기관", "보좌·보조기관",
        "행정기관", "보좌관", "보조관", "정책관", "직속기관",
        "담당관", "단", "과", "실", "관", "보건소", "사업소",
    }
    # 우선순위 접미사 (긴 것 먼저: 담당관이 관보다 우선)
    _BOSWA_SUFFIXES = ("담당관", "단", "실", "과", "관")

    def _suffix_for(nm: str) -> str:
        for suf in _BOSWA_SUFFIXES:
            if nm.endswith(suf):
                return suf
        return "관"

    boja_names: list = []          # 등장 순서 보존
    boja_seen: set = set()
    boja_art_ref: str = ""

    for a in all_ord_arts:
        if a.get("조문여부") != "Y":
            continue
        t = (a.get("조제목", "") or "").strip()
        if not _BOSWA_TITLE_RE.search(t):
            continue
        c = get_content(a)
        # "부X장 밑에/소속으로 ... 을/를 둔다" 패턴에서 단위 목록 추출
        m_list = re.search(
            r"부\w*[장수]\s*(?:밑에|소속(?:으로)?)\s*(.+?)\s*[을를]\s*둔다",
            c, re.DOTALL,
        )
        chunk = m_list.group(1) if m_list else ""
        if not chunk:
            # fallback — 항 번호 직후 ~ "둔다" 사이
            m_alt = re.search(
                r"①\s*(.+?)\s*[을를]\s*둔다", c, re.DOTALL
            )
            chunk = m_alt.group(1) if m_alt else ""
        if not chunk:
            continue
        # 부속 마크업/괄호/개정 태그 제거
        chunk = re.sub(r"<[^>]+>|\([^)]*\)", "", chunk)
        # 한글 접속조사 "과/와"가 단위 사이에 끼어든 경우 분리 (예: "감사담당관과 홍보담당관")
        chunk = re.sub(
            r"(?<=[관실단])\s*[과와]\s+(?=[가-힣])", ", ", chunk
        )
        # 단위명 토큰화: 한글 묶음으로 끝나는 위 접미사 매칭
        for tok in re.split(r"\s*[,ㆍ·]\s*|\s+(?:및|또는)\s+|\s{2,}", chunk):
            tok = tok.strip()
            if not tok:
                continue
            m_unit = re.match(
                r"^([가-힣]{2,14}(?:담당관|단|실|과|관))$", tok
            )
            if not m_unit:
                continue
            nm = m_unit.group(1)
            if nm in _BOSWA_GENERIC:
                continue
            if nm not in boja_seen:
                boja_seen.add(nm)
                boja_names.append(nm)
        # 첫 매칭 보좌기관 조문번호 기억
        if not boja_art_ref:
            num_raw = a.get("조문번호", "")
            boja_art_ref = article_num_to_str(num_raw) if num_raw else ""

    # 시행규칙에 단독 담당관 조문이 있는 경우도 흡수 (조례에서 누락된 케이스)
    for t in rule_articles_by_title:
        if re.match(r"^[가-힣]{2,12}담당관$", t):
            if t not in boja_seen:
                boja_seen.add(t)
                boja_names.append(t)

    # 이미 그룹이 존재하면 (custom 파서 등) 건드리지 않음
    has_group = any(
        u.get("name") in ("보좌기관", "담당관")
        and u.get("type") == "관"
        and u.get("level") == 1
        for u in structure
    )

    if boja_names and not has_group:
        # 기존 level-1 standalone 단위 중 boja_names에 매칭되는 것을 그룹 자식으로 이동
        moved: dict = {}
        kept: list = []
        for u in structure:
            if (u.get("level") == 1
                    and u.get("name") in boja_seen
                    and not u.get("children")):
                # children이 없는 단순 leaf만 흡수 (국 본부 등 자식 보유 단위는 별개)
                moved[u["name"]] = u
            else:
                kept.append(u)
        structure = kept

        children = []
        for nm in boja_names:
            if nm in moved:
                child = moved[nm]
                child["level"] = 2
                child["type"] = _suffix_for(nm)
                child["id"] = build_id(code, "보좌기관", nm)
                children.append(child)
                continue
            # 새로 생성 — 시행규칙 우선, 없으면 조례 본문 활용
            rule_art = rule_articles_by_title.get(nm)
            ord_art = ord_articles_by_title.get(nm)
            detail_art = rule_art or ord_art
            rule_text = get_content(detail_art) if detail_art else ""
            m_grade = re.search(
                r"(?:장|관)[은는]\s*(지방관리관|지방이사관|지방부이사관|"
                r"지방서기관|지방기술서기관|지방행정사무관|지방기술사무관|"
                r"지방시설사무관|지방사무관|[1-9]급)",
                rule_text,
            )
            grade = _normalize_grade_generic(m_grade.group(1)) if m_grade else ""
            num_raw = detail_art.get("조문번호", "") if detail_art else ""
            art_ref = article_num_to_str(num_raw) if num_raw else ""
            src = "시행규칙" if rule_art else "조례"
            head_pos = nm if nm.endswith("담당관") else nm + "장"
            children.append({
                "id": build_id(code, "보좌기관", nm),
                "type": _suffix_for(nm),
                "name": nm,
                "level": 2,
                "head_position": head_pos,
                "head_grade": grade,
                "정원": None,
                "근거조문": f"{src} {art_ref}".strip(),
                "분장사무_원문": rule_text,
                "분장사무_항목": parse_duties(rule_text),
                "키워드_태그": apply_keywords(nm + " " + rule_text),
                "children": [],
            })

        if children:
            combined_text = " ".join(
                c["분장사무_원문"] for c in children if c["분장사무_원문"]
            )
            structure.append({
                "id": build_id(code, "보좌기관"),
                "type": "관",
                "name": "보좌기관",
                "level": 1,
                "head_position": "보좌기관",
                "head_grade": "",
                "정원": None,
                "근거조문": f"조례 {boja_art_ref}".strip(),
                "분장사무_원문": "",
                "분장사무_항목": [],
                "키워드_태그": apply_keywords("보좌기관 " + combined_text),
                "children": children,
            })

    # 직속기관 처리 (절 헤더에서 기관명 추출)
    agencies = _extract_agencies_generic(all_ord_arts, code)
    for ag in agencies:
        if "삭제" not in ag["name"]:
            structure.append(ag)

    # 총정원 추출
    total_staff = _extract_total_staff(staff_data["articles"])

    output = {
        "region": {
            "code": code,
            "name": name,
            "level": "광역",
            "type": region_type,
            "parent": parent,
        },
        "source": {
            "ordinance": {
                "name": ord_data["law_name"],
                "mst": ord_data["mst"],
                "last_amended": ord_data["last_amended"],
                "url": f"https://www.law.go.kr/DRF/lawService.do?OC=open&target=ordin&MST={ord_data['mst']}&type=HTML",
                "fetched_at": fetched_at,
            },
            "enforcement_rule": {
                "name": rule_data["law_name"],
                "mst": rule_data["mst"],
                "last_amended": rule_data["last_amended"],
                "url": f"https://www.law.go.kr/DRF/lawService.do?OC=open&target=ordin&MST={rule_data['mst']}&type=HTML",
                "fetched_at": fetched_at,
            },
            "staff_ordinance": {
                "name": staff_data["law_name"],
                "mst": staff_data["mst"],
                "last_amended": staff_data["last_amended"],
                "fetched_at": fetched_at,
            },
        },
        "totals": {
            "정원_총": total_staff,
            "정원_근거조문": f"{staff_data['law_name']} 제2조",
            "정원_비고": "",
        },
        "structure": structure,
        "validation": {
            "정원_합산_일치": None,
            "정원_총_조례기준": total_staff,
            "분장사무_누락_부서": [
                n["name"] for n in structure
                if not n["분장사무_원문"] and n["type"] not in ("직속기관",)
            ],
            "비고": validation_notes,
        },
    }
    return output


def _extract_agencies_generic(all_arts: list[dict], code: str) -> list[dict]:
    """직속기관 섹션(제3장 이후)에서 절 헤더 기반으로 기관 추출"""
    agencies = []
    in_agency_chapter = False
    current_name = None
    install_content = ""
    duty_content = ""
    install_ref = ""
    CHAPTER_PAT = re.compile(r"제(\d+)장")
    SECTION_PAT = re.compile(r"제\d+절\s+(.+)")

    for a in all_arts:
        is_art = a.get("조문여부", "")
        조제목 = (a.get("조제목", "") or "").strip()
        content = get_content(a)

        if is_art == "N":
            m_ch = CHAPTER_PAT.search(content)
            if m_ch and int(m_ch.group(1)) >= 3:
                in_agency_chapter = True
            elif m_ch and int(m_ch.group(1)) < 3:
                in_agency_chapter = False
            if in_agency_chapter:
                m_sec = SECTION_PAT.search(content)
                if m_sec:
                    if current_name:
                        agencies.append(_make_agency_node(
                            code, current_name, install_content,
                            duty_content, install_ref
                        ))
                    raw_name = m_sec.group(1).strip()
                    clean_name = re.sub(r"\s*[<〈][^>〉]+[>〉]", "", raw_name).strip()
                    current_name = None if _SKIP_AGENCY_NAMES.search(clean_name) else clean_name
                    install_content = ""
                    duty_content = ""
                    install_ref = ""
            continue

        if not in_agency_chapter or not current_name:
            continue
        if "삭제" in content[:20]:
            continue

        num_raw = a.get("조문번호", "")
        art_ref = article_num_to_str(num_raw)
        if 조제목 in ("설치", "소관사무", "목적"):
            if 조제목 == "설치":
                install_content = content
                install_ref = f"조례 {art_ref}"
            else:
                duty_content = content

    if current_name:
        agencies.append(_make_agency_node(
            code, current_name, install_content, duty_content, install_ref
        ))
    return agencies


def _make_agency_node(code, name, install_txt, duty_txt, install_ref):
    combined = install_txt + " " + duty_txt
    return {
        "id": build_id(code, "직속기관", name),
        "type": "직속기관",
        "name": name,
        "level": 1,
        "head_position": name + "장",
        "head_grade": "",
        "정원": None,
        "근거조문": install_ref,
        "분장사무_원문": duty_txt,
        "분장사무_항목": parse_duties(duty_txt),
        "키워드_태그": apply_keywords(name + " " + combined),
        "children": [],
    }


def parse_gicheo_generic(
    code: str,
    name: str,
    region_type: str,
    parent: str,
    ord_path: Path,
    rule_path: Path,
    staff_path,
    fetched_at: str = "2026-05-09",
) -> dict:
    """기초 지자체 행정기구 파싱 — 광역 제너릭 파서를 기초용으로 래핑"""
    # 시행규칙 없으면 조례와 동일 파일로 처리
    if not rule_path.exists():
        rule_path = ord_path

    # 정원조례 없으면 빈 더미 데이터
    if staff_path is None or not staff_path.exists():
        staff_data_dummy = {
            "law_name": f"{name} 지방공무원 정원 조례",
            "mst": "", "last_amended": "", "org": name,
            "source": "law.go.kr", "fetched_at": fetched_at,
            "articles": [], "annexes": [],
        }
        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(staff_data_dummy, tmp)
        tmp.close()
        result = parse_gwangyeok_generic(
            code=code, name=name, region_type=region_type, parent=parent,
            ord_path=ord_path, rule_path=rule_path,
            staff_path=Path(tmp.name), fetched_at=fetched_at,
        )
        os.unlink(tmp.name)
    else:
        result = parse_gwangyeok_generic(
            code=code, name=name, region_type=region_type, parent=parent,
            ord_path=ord_path, rule_path=rule_path, staff_path=staff_path,
            fetched_at=fetched_at,
        )

    result["region"]["level"] = "기초"
    return result


if __name__ == "__main__":
    import sys

    targets = sys.argv[1:] if len(sys.argv) > 1 else ["seoul", "mapo", "danyang"]

    if "seoul" in targets or not targets:
        print("서울특별시 파싱 중...")
        result = parse_seoul()
        out_path = PROCESSED_DIR / "11_서울특별시.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        s = result["structure"]
        print(f"완료: {len(s)}개 최상위 기구, 총정원 {result['totals']['정원_총']:,}명")

    if "mapo" in targets or not targets:
        print("\n마포구 파싱 중...")
        result = parse_mapo()
        out_path = PROCESSED_DIR / "11440_마포구.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        s = result["structure"]
        print(f"완료: {len(s)}개 최상위 기구, 총정원 {result['totals']['정원_총']:,}명")
        for node in s:
            child_cnt = len(node.get("children", []))
            tags = node.get("키워드_태그", [])
            print(f"  {node['type']:6} | {node['name']:<15} | 직급:{node['head_grade']:<8} | 하위:{child_cnt}개 | {','.join(tags)}")

    if "danyang" in targets or not targets:
        print("\n단양군 파싱 중...")
        result = parse_danyang()
        out_path = PROCESSED_DIR / "33780_충청북도 단양군.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        s = result["structure"]
        print(f"완료: {len(s)}개 최상위 기구, 총정원 {result['totals']['정원_총']:,}명")
        for node in s:
            child_cnt = len(node.get("children", []))
            tags = node.get("키워드_태그", [])
            print(f"  {node['type']:6} | {node['name']:<15} | 직급:{node['head_grade']:<25} | 하위:{child_cnt}개 | {','.join(tags)}")
        print(f"\n저장: {out_path}")
