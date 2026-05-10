# local-gov-org

전국 243개 지방자치단체(광역 17 + 기초 226) 행정기구 조직 데이터 수집·파싱·시각화 프로젝트.

---

## 프로젝트 구조

```
data/
  raw/ordinances/기초/     조례 JSON (기초 지자체)
  raw/시행규칙/            시행규칙 JSON
  processed/by_region/     완성된 per-region JSON 243개 (핵심 데이터)
  processed/*.xlsx         엑셀 출력물
meta/
  gicheo_list.json         기초 지자체 목록 (code, name, type, parent)
  coverage.json            파싱 진행 현황
schema/
  keywords.json            12개 정책분야 키워드 정의
scripts/
  parse_ordinance.py       핵심 파싱 엔진 (~1700줄)
  parse_gicheo.py          기초 지자체 일괄 파싱
  export_excel.py          전체 행정기구 엑셀 (3시트)
  export_units_excel.py    상하위 목록 엑셀 (행당 1기구)
  export_climate_excel.py  기후환경 부서 현황 엑셀
  build_web_data.py        GitHub Pages 웹 데이터 빌드
docs/                      GitHub Pages 정적 사이트
```

---

## 데이터 스키마 (by_region/*.json)

```json
{
  "region": { "code": "11440", "name": "서울특별시 마포구",
              "level": "기초|광역", "type": "자치구|...", "parent": "11" },
  "source": { "ordinance": {...}, "enforcement_rule": {...} },
  "totals": { "정원_총": 1479 },
  "structure": [
    {
      "id": "11440.행정지원국",
      "type": "국|실|본부|단|관|처|담당관|직속기관|과",
      "name": "행정지원국",
      "level": 1,
      "head_position": "...", "head_grade": "5급",
      "정원": null,
      "근거조문": "조례 제4조",
      "분장사무_원문": "...",
      "분장사무_항목": ["항목1", "항목2", ...],
      "키워드_태그": ["복지", "재난_안전", ...],
      "children": [ /* level-2 동일 구조, children 없음 */ ]
    }
  ]
}
```

- level 1: 국/실/본부/단/관/처/담당관/직속기관
- level 2 (children): 과/담당관
- `키워드_태그`: schema/keywords.json 12개 정책분야 기반

---

## 정책분야 키워드 (schema/keywords.json)

기후, 환경, 에너지, 녹지_생태, 교통, 복지, 재난_안전, 도시_건축, 경제_산업, 행정_기획, 문화_교육, 보건_위생

---

## 실행 명령

```bash
# 기초 지자체 파싱
uv run python scripts/parse_gicheo.py
uv run python scripts/parse_gicheo.py 11440  # 특정 코드만

# 엑셀 생성
uv run python scripts/export_excel.py          # 전체 3시트
uv run python scripts/export_units_excel.py    # 상하위 목록 (소관사무 메모 포함)
uv run python scripts/export_climate_excel.py  # 기후환경 현황 (소관사무 메모 포함)

# 웹 데이터 빌드 + 로컬 미리보기
uv run python scripts/build_web_data.py
cd docs && python3 -m http.server 8000
```

---

## 주요 작업 이력

### 파싱 엔진 (parse_ordinance.py)

- `parse_gwangyeok_generic` / `parse_gicheo_generic`: 광역·기초 조례 파싱 공통 함수
- `_guess_level1_type`: 기구유형 추론. **"담당관"을 "관"보다 먼저 체크** (순서 중요)
- 보좌기관 articles에서 standalone 담당관 추출 후 type="관", name="담당관" 부모 아래 자식으로 그룹화 (성동구·성북구 패턴과 동일)
- 시행규칙 individual 담당관 articles도 추출 (서울 중구 등 조례에 없는 경우)
- Post-processing: 시행규칙 개별 과 articles에서 분장사무 fill

### 담당관 그룹화 규칙

타 지자체와 일관성 유지: 개별 담당관(새마포담당관, 감사담당관 등)은 최상위 기구로 두지 말고, type="관", name="담당관" 부모 아래 children으로 배치.

### 엑셀 메모 (openpyxl.comments.Comment)

`make_comment(unit)`: 분장사무_항목 → 번호 목록; 없으면 분장사무_원문에서 조문 헤더 제거 후 사용. 3000자 제한. export_units_excel.py와 export_climate_excel.py 양쪽에 동일 로직.

### 기후환경 엑셀 필터 규칙

- **포함**: 사업소, 본청 기구
- **제외**: 연구원, 연구소, 연구실 (EXCLUDE_KW)
- **키워드**: 기후, 환경, 생태, 녹색, 깨끗, 맑은, 탄소, 대기, 수질, 오염, 재활용, 산림
- 기초명 형식: "서울특별시 마포구" → "마포구" (마지막 단어)

### 코드 수정 이력

- 단양군: 코드 `43730` → `33780`, parent `43` → `33` (충청북도)
  - 파일명: `43730_단양군.json` → `33780_충청북도 단양군.json`

### GitHub Pages 웹사이트 (docs/)

- 기술: Vanilla JS + Alpine.js 3 (ESM, CDN) + MiniSearch (검색)
- 빌드: `build_web_data.py` → `docs/data/` 번들 생성
- 5개 뷰: 전국 개요 / 지자체별 트리 / 정책분야별 / 광역 비교 / 기구유형별
- 해시 라우팅: `#/`, `#/region/11440`, `#/keyword/기후`, `#/compare`, `#/types`
- 성능: 초기 로드 94KB(index.json), region 클릭 시 lazy-fetch, 검색 인덱스 첫 입력 시 lazy-load
- **배포**: Settings → Pages → Source: `main` branch `/docs` folder

---

## 알려진 한계

- 분장사무 71%가 별표(appendix) 형식 → JSON 파싱 불가, 메모 미첨부
- 웹 search_index.json 3.6MB (첫 검색 시 lazy-load로 해결)
- SVG 지도 뷰 미구현 (step 4로 계획됨)
