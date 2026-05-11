import Alpine from 'https://esm.sh/alpinejs@3.14.7'
import MiniSearch from 'https://esm.sh/minisearch@7.1.1'
import { loadIndex, loadAggregates, loadRegion, loadKeyword, loadSearchDocs } from './api.js'

const KW_ORDER = ['기후','환경','에너지','녹지_생태','교통','복지','재난_안전','도시_건축','경제_산업','행정_기획','문화_교육','보건_위생']
const TYPE_ORDER = [
  '국','실','본부','단','관','처',
  '보좌기관','담당관','한시기구',
  '직속기관','사업소','출장소',
  '과',
]

function parseHash(hash) {
  const h = (hash || location.hash).replace(/^#/, '') || '/'
  if (h === '/' || h === '') return { view: 'overview', code: '', keyword: '', type: '' }
  if (h.startsWith('/region/')) return { view: 'region', code: h.slice(8), keyword: '', type: '' }
  if (h.startsWith('/keyword/')) return { view: 'keyword', keyword: decodeURIComponent(h.slice(9)), code: '', type: '' }
  if (h === '/compare')          return { view: 'compare', code: '', keyword: '', type: '' }
  if (h.startsWith('/types'))    return { view: 'types', type: h.slice(7).replace(/^\//,''), code: '', keyword: '' }
  return { view: 'overview', code: '', keyword: '', type: '' }
}

Alpine.data('mainApp', () => ({
  // ── 라우터 상태 ──────────────────────────────────────────
  view: 'overview',
  currentCode: '',
  currentKeyword: '',
  currentType: '',
  loading: false,

  // ── 공통 데이터 ──────────────────────────────────────────
  index: [],
  aggregates: null,

  // ── 지자체별 트리 ─────────────────────────────────────────
  selectedRegion: null,
  selectedUnit: null,
  selectedParentUnit: null,

  // ── 정책분야별 ────────────────────────────────────────────
  kwUnits: [],
  kwFilter: '',

  // ── 기구유형별 ────────────────────────────────────────────
  selectedType: '',
  searchDocs: null,   // 검색 인덱스 배열 — 기구유형별 뷰와 공유

  // ── 광역 비교 ─────────────────────────────────────────────
  compareTypes: ['국','실','본부','단','보좌기관','직속기관','사업소'],

  // ── 검색 ─────────────────────────────────────────────────
  searchQuery: '',
  searchResults: [],
  searchOpen: false,
  miniSearch: null,

  // ── 전역 상수 ─────────────────────────────────────────────
  kwOrder: KW_ORDER,
  typeOrder: TYPE_ORDER,

  // ── 개요 뷰 상태 ──────────────────────────────────────────
  gicheoFilterParent: '',

  // ── computed ─────────────────────────────────────────────
  get gwangyeok() {
    return this.index.filter(r => r.level === '광역')
  },
  get filteredGicheo() {
    const list = this.index.filter(r => r.level === '기초')
    if (!this.gicheoFilterParent) return list
    return list.filter(r => r.parent === this.gicheoFilterParent)
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
  get maxKwCount() {
    const d = this.aggregates?.['전국_키워드별'] || {}
    return Math.max(1, ...Object.values(d))
  },
  get maxTypeCount() {
    const d = this.aggregates?.['전국_기구유형별'] || {}
    return Math.max(1, ...Object.values(d))
  },
  get typeCountFor() {
    return (t) => this.aggregates?.['전국_기구유형별']?.[t] || 0
  },
  get childRegions() {
    if (!this.selectedRegion) return []
    const code = this.selectedRegion.region.code
    return this.index.filter(r => r.parent === code)
  },
  get filteredKwUnits() {
    if (!this.kwFilter.trim()) return this.kwUnits
    const q = this.kwFilter.trim().toLowerCase()
    return this.kwUnits.filter(u =>
      u.unit_name.includes(q) || u.region_name.includes(q) || u.parent_name?.includes(q)
    )
  },
  get filteredByType() {
    if (!this.selectedType || !this.searchDocs) return []
    return this.searchDocs.filter(u => u.unit_type === this.selectedType)
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

    // 라우팅
    const apply = () => this._applyRoute(parseHash(location.hash))
    window.addEventListener('hashchange', apply)
    apply()
  },

  // ── 라우팅 ────────────────────────────────────────────────
  navigate(path) {
    location.hash = '#' + path
  },

  async _applyRoute({ view, code, keyword, type }) {
    this.view = view
    this.currentCode = code
    this.currentKeyword = keyword
    this.currentType = type

    if (view === 'region' && code) {
      this.loading = true
      this.selectedUnit = null
      this.selectedParentUnit = null
      try {
        const data = await loadRegion(code)
        // 트리 아이템에 _open 상태 주입
        for (const u of data.structure || []) {
          u._open = false
        }
        this.selectedRegion = data
      } catch (e) {
        console.error(e)
      } finally {
        this.loading = false
      }
    }

    if (view === 'keyword' && keyword) {
      this.kwFilter = ''
      this.loading = true
      try {
        this.kwUnits = await loadKeyword(keyword)
      } catch (e) {
        console.error(e)
      } finally {
        this.loading = false
      }
    }

    if (view === 'types' && type) {
      this.selectedType = type
      await this._ensureSearchDocs()
    }
  },

  // ── 트리 선택 ─────────────────────────────────────────────
  selectUnit(unit, parent = null) {
    this.selectedUnit = unit
    this.selectedParentUnit = parent
  },

  // ── 기구유형별 ────────────────────────────────────────────
  async selectType(type) {
    this.selectedType = type
    this.navigate('/types/' + type)
    await this._ensureSearchDocs()
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

  // ── 검색 ─────────────────────────────────────────────────
  async onSearch() {
    const q = this.searchQuery.trim()
    if (!q) { this.searchResults = []; return }

    // 검색 인덱스 lazy 초기화
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

  // ── 유틸 ─────────────────────────────────────────────────
  getGwangyeokName(regionCode) {
    const r = this.indexMap[regionCode]
    if (!r) return ''
    return r.level === '광역' ? r.name : r.parent_name
  },
}))

Alpine.start()
