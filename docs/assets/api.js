// fetch 래퍼 + 응답 캐시
const cache = new Map()

async function fetchJSON(url) {
  if (cache.has(url)) return cache.get(url)
  const res = await fetch(url)
  if (!res.ok) throw new Error(`fetch 실패: ${url}`)
  const data = await res.json()
  cache.set(url, data)
  return data
}

const base = document.querySelector('meta[name=data-base]')?.content || 'data'

export const loadIndex       = () => fetchJSON(`${base}/index.json`)
export const loadAggregates  = () => fetchJSON(`${base}/aggregates.json`)
export const loadRegion      = (code) => fetchJSON(`${base}/regions/${code}.json`)
export const loadKeyword     = (kw)   => fetchJSON(`${base}/by_keyword/${encodeURIComponent(kw)}.json`)
export const loadSearchDocs  = () => fetchJSON(`${base}/search_index.json`)
export const loadClimateDepts = () => fetchJSON(`${base}/climate_depts.json`)
