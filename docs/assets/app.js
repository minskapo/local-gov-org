import Alpine from 'https://esm.sh/alpinejs@3.14.7'
import MiniSearch from 'https://esm.sh/minisearch@7.1.1'
import { loadIndex, loadAggregates, loadRegion, loadSearchDocs, loadClimateDepts } from './api.js'

const KW_ORDER = ['기후','환경','에너지','녹지_생태','교통','복지','재난_안전','도시_건축','경제_산업','행정_기획','문화_교육','보건_위생']
const TYPE_ORDER = ['국','실','본부','단','관','처','보좌기관','담당관','한시기구','직속기관','사업소','출장소','과']

function parseHash(hash) {
  const h = (hash || location.hash).replace(/^#/, '') || '/'
  if (h === '/' || h === '')     return { view: 'overview', code: '' }
  if (h.startsWith('/region/')) return { view: 'region',   code: h.slice(8) }
  if (h === '/compare')          return { view: 'compare',  code: '' }
  if (h.startsWith('/kwsearch')) return { view: 'kwsearch', code: '' }
  if (h.startsWith('/units'))    return { view: 'units',    code: '' }
  if (h.startsWith('/climate'))  return { view: 'climate',  code: '' }
  return { view: 'overview', code: '' }
}

Alpine.data('mainApp', () => ({
  // ── 라우터 ──────────────────────────────────────────────
  view: 'overview',
  currentCode: '',
  loading: false,

  // ── 공통 데이터 ──────────────────────────────────────────
  index: [],
  aggregates: null,

  // ── 지자체별 트리 ─────────────────────────────────────────
  selectedRegion: null,
  selectedUnit: null,
  selectedParentUnit: null,

  // ── 지자체 비교 ───────────────────────────────────────────
  compareTypes: ['국','실','본부','단','보좌기관','직속기관','사업소'],
  compareExpanded: {},

  // ── 키워드 검색 ───────────────────────────────────────────
  // 각 조건: { type: 'include'|'exclude'|'or', text: '' }
  kwConditions: [{ type: 'include', text: '' }],
  kwTypeVisible: [...TYPE_ORDER],  // 표시할 기구 유형 목록
  kwResultMap: {},   // { regionCode: [ group, ... ] }
  kwSearchDone: false,
  searchDocs: null,

  // ── 전체 기구 현황 ────────────────────────────────────────
  unitsRows: [],
  unitsFilter: { gw: '', gi: '', type: '', name: '' },
  unitsSortCol: '',
  unitsSortDir: 1,
  _unitsDetailItems: [],
  unitDetail: null,

  // ── 탄소중립 주무부서 현황 ────────────────────────────────────
  climateDepts: null,
  climateFilter: { gw: '', level: '', type: '' },

  // ── 헤더 검색 ────────────────────────────────────────────
  searchQuery: '',
  searchResults: [],
  searchOpen: false,
  miniSearch: null,

  kwOrder: KW_ORDER,
  typeOrder: TYPE_ORDER,

  // ── computed ─────────────────────────────────────────────
  get gwangyeok() {
    return this.index.filter(r => r.level === '광역')
  },
  get gicheoByParent() {
    const m = {}
    for (const r of this.index) {
      if (r.level === '기초') {
        if (!m[r.parent]) m[r.parent] = []
        m[r.parent].push(r)
      }
    }
    return m
  },
  get indexMap() {
    const m = {}
    for (const r of this.index) m[r.code] = r
    return m
  },
  get totalUnits() {
    return this.index.reduce((s, r) => s + (r.기구수||0) + (r.하위기구수||0), 0)
  },
  get totalStaff() {
    return this.index.filter(r => r.level==='광역').reduce((s,r) => s + (r.정원||0), 0)
  },
  get childRegions() {
    if (!this.selectedRegion) return []
    const code = this.selectedRegion.region.code
    return this.index.filter(r => r.parent === code)
  },

  // 비교 테이블용 평탄 행 목록 (x-if 중첩 없이 tbody에서 사용)
  get compareRows() {
    const rows = []
    for (const gw of (this.aggregates?.광역 || [])) {
      rows.push({ kind: 'gw', data: gw })
      if (this.compareExpanded[gw.code]) {
        for (const r of (this.gicheoByParent[gw.code] || [])) {
          rows.push({ kind: 'gi', data: r, gwCode: gw.code })
        }
      }
    }
    return rows
  },

  // 타입 필터 적용된 검색 결과
  get kwFilteredResultMap() {
    if (!this.kwSearchDone) return {}
    const visible = this.kwTypeVisible
    const out = {}
    for (const [code, groups] of Object.entries(this.kwResultMap)) {
      out[code] = groups.map(g => {
        const parentVisible = !g.parentType || visible.includes(g.parentType)
        // hit children are always shown; type filter only hides non-matching siblings
        const filteredChildren = g.children.filter(c => c.hit || !c.type || visible.includes(c.type))
        const anyChildHit = g.children.some(c => c.hit)
        if (!parentVisible && !anyChildHit) return null
        if (!g.parentHit && !anyChildHit) return null
        return { ...g, parentVisible, children: filteredChildren }
      }).filter(Boolean)
    }
    return out
  },

  // 키워드 검색 결과 통계
  get kwSearchStats() {
    if (!this.kwSearchDone) return null
    const rm = this.kwFilteredResultMap
    let total = 0
    const byLevel = { 광역: 0, 기초: 0 }
    const byType = {}
    for (const [code, groups] of Object.entries(rm)) {
      const level = (this.indexMap[code] || {}).level || ''
      for (const g of groups) {
        if (g.parentHit) {
          total++
          if (level in byLevel) byLevel[level]++
          byType[g.parentType] = (byType[g.parentType] || 0) + 1
        }
        for (const c of g.children) {
          if (c.hit) {
            total++
            if (level in byLevel) byLevel[level]++
            byType[c.type] = (byType[c.type] || 0) + 1
          }
        }
      }
    }
    const typeList = TYPE_ORDER.filter(t => byType[t]).map(t => ({ type: t, count: byType[t] }))
    return { total, byLevel, typeList }
  },

  // ── 전체 기구 현황 computed ───────────────────────────────
  get unitsGwOptions() {
    return this.gwangyeok.map(r => r.name)
  },
  get unitsGiOptions() {
    const gw = this.unitsFilter.gw
    return this.index.filter(r =>
      r.level === '기초' && (!gw || r.parent_name === gw)
    ).map(r => ({ code: r.code, label: r.short_name }))
  },
  get unitsFiltered() {
    const { gw, gi, type, name } = this.unitsFilter
    let rows = this.unitsRows
    if (gw)   rows = rows.filter(r => r.gwName === gw)
    if (gi)   rows = rows.filter(r => r.code === gi)
    if (type) rows = rows.filter(r => r.parentType === type)
    if (name) { const q = name.toLowerCase(); rows = rows.filter(r => r.parentName.toLowerCase().includes(q)) }
    if (!this.unitsSortCol) return rows
    const col = this.unitsSortCol, dir = this.unitsSortDir
    return [...rows].sort((a, b) => {
      const av = a[col] || '', bv = b[col] || ''
      return av < bv ? -dir : av > bv ? dir : 0
    })
  },
  get unitsMaxChildren() {
    return this.unitsRows.reduce((m, r) => Math.max(m, r.children.length), 0)
  },
  get unitsChildIndices() {
    return Array.from({ length: this.unitsMaxChildren }, (_, i) => i)
  },

  // ── 탄소중립 주무부서 현황 computed ───────────────────────────
  get climateGwOptions() {
    const seen = new Set()
    return (this.climateDepts || []).filter(r => !seen.has(r.gw) && seen.add(r.gw)).map(r => r.gw)
  },
  get climateFiltered() {
    let rows = this.climateDepts || []
    const { gw, level, type } = this.climateFilter
    if (gw)    rows = rows.filter(r => r.gw === gw)
    if (level) rows = rows.filter(r => r.level === level)
    if (type)  rows = rows.filter(r => r.parent_type === type)
    return rows
  },
  get climateDisplayRows() {
    let lastGw = null
    return this.climateFiltered.map(r => {
      const showGw = r.gw !== lastGw
      lastGw = r.gw
      return { ...r, showGw }
    })
  },
  get climateParentTypeList() {
    const ptCount = {}
    for (const r of this.climateFiltered) {
      if (r.parent_type) ptCount[r.parent_type] = (ptCount[r.parent_type] || 0) + 1
    }
    return ['기후환경 단독', '타 영역 혼합', '타 영역 단독']
      .filter(t => ptCount[t]).map(t => ({ label: t, count: ptCount[t] }))
  },
  get climateDeptKwList() {
    const kwCount = {}
    for (const r of this.climateFiltered) {
      if (r.dept_keywords) kwCount[r.dept_keywords] = (kwCount[r.dept_keywords] || 0) + 1
    }
    return Object.entries(kwCount).sort((a, b) => b[1] - a[1]).map(([kw, count]) => ({ kw, count }))
  },

  // kwsearch 뷰 표시용 평탄 행 목록
  get kwSearchRows() {
    if (!this.kwSearchDone) return []
    const rm = this.kwFilteredResultMap
    const rows = []
    for (const gw of this.gwangyeok) {
      rows.push({ kind: 'gw', region: gw, groups: rm[gw.code] || [] })
      for (const r of (this.gicheoByParent[gw.code] || [])) {
        rows.push({ kind: 'gi', region: r, groups: rm[r.code] || [] })
      }
    }
    return rows
  },

  // ── 초기화 ────────────────────────────────────────────────
  async init() {
    this.loading = true
    try {
      const [idx, agg] = await Promise.all([loadIndex(), loadAggregates()])
      this.index = idx
      this.aggregates = agg
    } finally {
      this.loading = false
    }
    const apply = () => this._applyRoute(parseHash(location.hash))
    window.addEventListener('hashchange', apply)
    apply()
  },

  navigate(path) { location.hash = '#' + path },

  async _applyRoute({ view, code }) {
    this.loading = false
    this.view = view
    this.currentCode = code

    if (view === 'units') {
      await this._ensureSearchDocs()
      this._buildUnitsRows()
    }

    if (view === 'climate') {
      await this._ensureClimateDepts()
    }

    if (view === 'region' && code) {
      this.loading = true
      this.selectedUnit = null
      this.selectedParentUnit = null
      try {
        const data = await loadRegion(code)
        for (const u of data.structure || []) u._open = false
        this.selectedRegion = data
      } catch (e) {
        console.error(e)
      } finally {
        this.loading = false
      }
    }
  },

  // ── 전체 기구 현황 ────────────────────────────────────────
  _buildUnitsRows() {
    if (!this.searchDocs) return
    if (this.unitsRows.length) return
    const childrenOf = {}
    for (const doc of this.searchDocs) {
      if (doc.parent_name) {
        const key = doc.region_code + '\x00' + doc.parent_name
        if (!childrenOf[key]) childrenOf[key] = []
        childrenOf[key].push({ name: doc.unit_name, type: doc.unit_type, summary: doc.분장사무_summary || '' })
      }
    }
    const rows = []
    for (const doc of this.searchDocs) {
      if (doc.parent_name) continue
      const ri = this.indexMap[doc.region_code] || {}
      const gwName = ri.level === '광역' ? ri.name : (ri.parent_name || '')
      const giName = ri.level === '기초' ? (ri.short_name || ri.name) : ''
      const key = doc.region_code + '\x00' + doc.unit_name
      rows.push({
        code: doc.region_code,
        gwName,
        giName,
        parentType: doc.unit_type,
        parentName: doc.unit_name,
        parentSummary: doc.분장사무_summary || '',
        children: childrenOf[key] || [],
      })
    }
    this.unitsRows = rows
    this._renderUnitsTable()
  },
  _renderUnitsTable() {
    const tbody = document.getElementById('units-tbody')
    if (!tbody) return
    const rows = this.unitsFiltered
    const maxCols = this.unitsMaxChildren
    const di = []
    const esc = s => (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const SPECIAL = new Set(['보좌기관', '직속기관', '사업소', '출장소'])
    let html = ''
    let lastCode = null
    for (const row of rows) {
      const showRegion = row.code !== lastCode
      lastCode = row.code
      const cls = [
        showRegion ? 'urow-region-start' : '',
        SPECIAL.has(row.parentType) ? `urow-${row.parentType}` : '',
      ].filter(Boolean).join(' ')
      let parentCell
      if (row.parentSummary) {
        const idx = di.length
        di.push({ name: row.parentName, type: row.parentType, summary: row.parentSummary })
        parentCell = `<span class="unit-link has-summary" data-di="${idx}">${esc(row.parentName)}</span>`
      } else {
        parentCell = `<span class="unit-link">${esc(row.parentName)}</span>`
      }
      let childCells = ''
      for (let i = 0; i < maxCols; i++) {
        const c = row.children[i]
        if (c) {
          let inner
          if (c.summary) {
            const idx = di.length
            di.push({ name: c.name, type: c.type, summary: c.summary })
            inner = `<span class="unit-link has-summary" data-di="${idx}">${esc(c.name)}</span>`
          } else {
            inner = `<span class="unit-link">${esc(c.name)}</span>`
          }
          childCells += `<td class="units-child-cell"><div class="units-name-cap">${inner}</div></td>`
        } else {
          childCells += `<td class="units-child-cell"></td>`
        }
      }
      html += `<tr class="${cls}">` +
        `<td class="units-gw-cell">${showRegion ? esc(row.gwName) : ''}</td>` +
        `<td class="units-gi-cell">${showRegion ? esc(row.giName) : ''}</td>` +
        `<td><span class="type-badge badge-${esc(row.parentType)}">${esc(row.parentType)}</span></td>` +
        `<td><div class="units-name-cap">${parentCell}</div></td>` +
        childCells +
        `</tr>`
    }
    this._unitsDetailItems = di
    tbody.innerHTML = html
  },
  onUnitTableClick(e) {
    const el = e.target.closest('[data-di]')
    if (!el) return
    const item = this._unitsDetailItems[+el.dataset.di]
    if (item) this.unitDetail = item
  },
  showUnitDetail(unit) { if (unit) this.unitDetail = unit },
  sortUnits(col) {
    if (this.unitsSortCol === col) this.unitsSortDir *= -1
    else { this.unitsSortCol = col; this.unitsSortDir = 1 }
    this._renderUnitsTable()
  },

  // ── 트리 선택 ─────────────────────────────────────────────
  selectUnit(unit, parent = null) {
    this.selectedUnit = unit
    this.selectedParentUnit = parent
  },

  // ── 지자체 비교 ───────────────────────────────────────────
  toggleCompare(gwCode) {
    this.compareExpanded = {
      ...this.compareExpanded,
      [gwCode]: !this.compareExpanded[gwCode],
    }
  },

  gwTypeTotal(typeMap) {
    return Object.values(typeMap || {}).reduce((a, b) => a + b, 0)
  },

  // ── 키워드 검색 조건 관리 ─────────────────────────────────
  addKwCondition() {
    this.kwConditions = [...this.kwConditions, { type: 'include', text: '' }]
  },
  removeKwCondition(i) {
    this.kwConditions = this.kwConditions.filter((_, idx) => idx !== i)
    if (!this.kwConditions.length) this.kwConditions = [{ type: 'include', text: '' }]
  },

  // ── 기구 유형 표시 토글 ───────────────────────────────────
  toggleKwType(t) {
    if (this.kwTypeVisible.includes(t)) {
      this.kwTypeVisible = this.kwTypeVisible.filter(x => x !== t)
    } else {
      this.kwTypeVisible = [...this.kwTypeVisible, t]
    }
  },

  // ── 키워드 검색 실행 ──────────────────────────────────────
  async runKwSearch() {
    const conditions = this.kwConditions.filter(c => c.text.trim())
    if (!conditions.length) return

    await this._ensureSearchDocs()

    // searchDocs를 region 기준으로 인덱싱
    const regionDocs = {}
    for (const doc of this.searchDocs) {
      const rc = doc.region_code
      if (!regionDocs[rc]) regionDocs[rc] = { parents: [], childrenByParent: {} }
      if (doc.parent_name) {
        if (!regionDocs[rc].childrenByParent[doc.parent_name])
          regionDocs[rc].childrenByParent[doc.parent_name] = []
        regionDocs[rc].childrenByParent[doc.parent_name].push(doc)
      } else {
        regionDocs[rc].parents.push(doc)
      }
    }

    const resultMap = {}
    for (const r of this.index) {
      const rd = regionDocs[r.code]
      if (!rd) { resultMap[r.code] = []; continue }

      const groups = []
      const seenParents = new Set()

      for (const doc of rd.parents) {
        const parentHit = this._matchesCond(doc.unit_name, conditions)
        const children = rd.childrenByParent[doc.unit_name] || []
        const hitSet = new Set(
          children
            .filter(c => this._matchesCond(c.unit_name, conditions))
            .map(c => c.unit_name)
        )
        if (parentHit || hitSet.size) {
          groups.push({
            parentName: doc.unit_name,
            parentType: doc.unit_type,
            parentHit,
            parentSummary: doc.분장사무_summary || '',
            children: children.map(c => ({
              name: c.unit_name,
              type: c.unit_type,
              hit: hitSet.has(c.unit_name),
              summary: c.분장사무_summary || '',
            })),
          })
          seenParents.add(doc.unit_name)
        }
      }

      // parent가 없는 child 히트
      for (const [pName, children] of Object.entries(rd.childrenByParent)) {
        if (seenParents.has(pName)) continue
        const hitSet = new Set(
          children
            .filter(c => this._matchesCond(c.unit_name, conditions))
            .map(c => c.unit_name)
        )
        if (hitSet.size) {
          groups.push({
            parentName: pName,
            parentType: '',
            parentHit: false,
            parentSummary: '',
            children: children.map(c => ({
              name: c.unit_name,
              type: c.unit_type,
              hit: hitSet.has(c.unit_name),
              summary: c.분장사무_summary || '',
            })),
          })
        }
      }

      resultMap[r.code] = groups
    }

    this.kwResultMap = resultMap
    this.kwSearchDone = true
  },

  // 조건 배열로 텍스트 매칭 — include/exclude/or 모델
  _matchesCond(text, conditions) {
    const t = text.toLowerCase()
    const include = conditions.filter(c => c.type === 'include' && c.text.trim())
    const exclude = conditions.filter(c => c.type === 'exclude' && c.text.trim())
    const or     = conditions.filter(c => c.type === 'or'      && c.text.trim())
    if (!include.length && !or.length) return false
    if (exclude.some(c => t.includes(c.text.trim().toLowerCase()))) return false
    if (!include.every(c => t.includes(c.text.trim().toLowerCase()))) return false
    if (or.length && !or.some(c => t.includes(c.text.trim().toLowerCase()))) return false
    return true
  },

  async _ensureClimateDepts() {
    if (this.climateDepts) return
    this.loading = true
    try {
      this.climateDepts = await loadClimateDepts()
    } finally {
      this.loading = false
    }
  },

  async _ensureSearchDocs() {
    if (this.searchDocs) return
    this.loading = true
    try {
      this.searchDocs = await loadSearchDocs()
    } finally {
      this.loading = false
    }
  },

  // ── 헤더 검색 ─────────────────────────────────────────────
  async onSearch() {
    const q = this.searchQuery.trim()
    if (!q) { this.searchResults = []; return }
    if (!this.miniSearch) {
      this.loading = true
      try {
        const docs = await loadSearchDocs()
        this.searchDocs = docs
        const ms = new MiniSearch({
          fields: ['region_name', 'unit_name', '키워드_태그', '분장사무_summary'],
          storeFields: ['region_code','region_name','unit_name','unit_type','parent_name','분장사무_summary'],
          searchOptions: { boost: { unit_name: 3, region_name: 2 }, fuzzy: 0.2 },
        })
        ms.addAll(docs)
        this.miniSearch = ms
      } finally {
        this.loading = false
      }
    }
    this.searchResults = this.miniSearch.search(q).slice(0, 20)
    this.searchOpen = true
  },

  gotoResult(r) {
    this.searchOpen = false
    this.searchQuery = ''
    this.searchResults = []
    this.navigate('/region/' + r.region_code)
  },
}))

Alpine.start()
