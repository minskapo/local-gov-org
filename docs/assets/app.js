import Alpine from 'https://esm.sh/alpinejs@3.14.7'
import MiniSearch from 'https://esm.sh/minisearch@7.1.1'
import { loadIndex, loadAggregates, loadRegion, loadSearchDocs } from './api.js'

const KW_ORDER = ['기후','환경','에너지','녹지_생태','교통','복지','재난_안전','도시_건축','경제_산업','행정_기획','문화_교육','보건_위생']
const TYPE_ORDER = [
  '국','실','본부','단','관','처',
  '보좌기관','담당관','한시기구',
  '직속기관','사업소','출장소',
  '과',
]

function parseHash(hash) {
  const h = (hash || location.hash).replace(/^#/, '') || '/'
  if (h === '/' || h === '')         return { view: 'overview', code: '' }
  if (h.startsWith('/region/'))      return { view: 'region',   code: h.slice(8) }
  if (h === '/compare')              return { view: 'compare',  code: '' }
  if (h.startsWith('/kwsearch'))     return { view: 'kwsearch', code: '' }
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
  kwSearch: '',
  kwResultMap: {},
  kwSearchDone: false,
  searchDocs: null,

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
  get kwSearchRows() {
    if (!this.kwSearchDone) return []
    const rows = []
    for (const gw of this.gwangyeok) {
      rows.push({ kind: 'gw', region: gw, groups: this.kwResultMap[gw.code] || [] })
      for (const r of (this.gicheoByParent[gw.code] || [])) {
        rows.push({ kind: 'gi', region: r, groups: this.kwResultMap[r.code] || [] })
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

  navigate(path) {
    location.hash = '#' + path
  },

  async _applyRoute({ view, code }) {
    this.loading = false
    this.view = view
    this.currentCode = code

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

  // ── 트리 선택 ─────────────────────────────────────────────
  selectUnit(unit, parent = null) {
    this.selectedUnit = unit
    this.selectedParentUnit = parent
  },

  // ── 지자체 비교 ───────────────────────────────────────────
  toggleCompare(gwCode) {
    this.compareExpanded = { ...this.compareExpanded, [gwCode]: !this.compareExpanded[gwCode] }
  },

  gwTypeTotal(typeMap) {
    return Object.values(typeMap || {}).reduce((a, b) => a + b, 0)
  },

  // ── 키워드 검색 ───────────────────────────────────────────
  async runKwSearch() {
    const q = this.kwSearch.trim()
    if (!q) { this.kwResultMap = {}; this.kwSearchDone = false; return }

    await this._ensureSearchDocs()
    const queryGroups = this._parseKwQuery(q)
    if (!queryGroups.length) return

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
        const text = doc.unit_name + ' ' + (doc.분장사무_summary || '')
        const parentHit = this._matchesKwQuery(text, queryGroups)
        const children = rd.childrenByParent[doc.unit_name] || []
        const hitSet = new Set(
          children.filter(c => this._matchesKwQuery(c.unit_name + ' ' + (c.분장사무_summary || ''), queryGroups))
            .map(c => c.unit_name)
        )
        if (parentHit || hitSet.size) {
          groups.push({
            parentName: doc.unit_name,
            parentType: doc.unit_type,
            parentHit,
            children: children.map(c => ({ name: c.unit_name, type: c.unit_type, hit: hitSet.has(c.unit_name) })),
          })
          seenParents.add(doc.unit_name)
        }
      }

      // 부모가 없는 고아 child hits
      for (const [pName, children] of Object.entries(rd.childrenByParent)) {
        if (seenParents.has(pName)) continue
        const hitSet = new Set(
          children.filter(c => this._matchesKwQuery(c.unit_name + ' ' + (c.분장사무_summary || ''), queryGroups))
            .map(c => c.unit_name)
        )
        if (hitSet.size) {
          groups.push({
            parentName: pName, parentType: '', parentHit: false,
            children: children.map(c => ({ name: c.unit_name, type: c.unit_type, hit: hitSet.has(c.unit_name) })),
          })
        }
      }

      resultMap[r.code] = groups
    }

    this.kwResultMap = resultMap
    this.kwSearchDone = true
  },

  _parseKwQuery(q) {
    return q.split(/\bOR\b/i).map(part => {
      const tokens = part.trim().split(/\s+/).filter(Boolean)
      const must = [], mustNot = []
      for (let i = 0; i < tokens.length; i++) {
        if (/^AND$/i.test(tokens[i])) continue
        if (/^NOT$/i.test(tokens[i])) {
          if (i + 1 < tokens.length) mustNot.push(tokens[++i].toLowerCase())
          continue
        }
        must.push(tokens[i].toLowerCase())
      }
      return { must, mustNot }
    }).filter(g => g.must.length)
  },

  _matchesKwQuery(text, groups) {
    const t = text.toLowerCase()
    return groups.some(g => {
      if (g.mustNot.some(term => t.includes(term))) return false
      return g.must.every(term => t.includes(term))
    })
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
