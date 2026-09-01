import { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { publicationsArchive } from './data/publicationsArchive'
import type { ArchivePublication } from './data/publicationTypes'
import { parseCsv, rowsToPublications } from './lib/csv'
import { PUBLICATIONS_SHEET_CSV } from './config'
import './styles.css'
import './publications.css'

const BASE = import.meta.env.BASE_URL
const PAGE_SIZE = 60
const ANY_YEAR = 'любой'
const ANY = { publisher: 'Все издательства', coauthor: 'Все соавторы', topic: 'Все темы', type: 'Все типы' }

type Facet = keyof typeof ANY
type Filters = { query: string; yearFrom: string; yearTo: string } & Record<Facet, string>
const EMPTY: Filters = { query: '', yearFrom: ANY_YEAR, yearTo: ANY_YEAR, ...ANY }

const split = (value: string) => value.split(';').map(part => part.trim()).filter(Boolean)

const matchers: Record<Facet, (p: ArchivePublication, value: string) => boolean> = {
  publisher: (p, v) => p.publisher === v,
  coauthor: (p, v) => split(p.coauthors).includes(v),
  topic: (p, v) => split(p.topics).includes(v),
  type: (p, v) => p.type === v,
}

const inYearRange = (p: ArchivePublication, filters: Filters) => {
  if (filters.yearFrom !== ANY_YEAR && (!p.year || p.year < Number(filters.yearFrom))) return false
  if (filters.yearTo !== ANY_YEAR && (!p.year || p.year > Number(filters.yearTo))) return false
  return true
}

const searchable = (p: ArchivePublication) =>
  `${p.title} ${p.citation} ${p.coauthors} ${p.publisher} ${p.topics} ${p.doi ?? ''} ${p.edn ?? ''}`.toLowerCase()

function apply(list: ArchivePublication[], filters: Filters, skip?: Facet | 'year' | 'query') {
  const query = filters.query.trim().toLowerCase()
  return list.filter(p => {
    if (skip !== 'query' && query && !searchable(p).includes(query)) return false
    if (skip !== 'year' && !inYearRange(p, filters)) return false
    for (const key of Object.keys(matchers) as Facet[]) {
      if (key === skip) continue
      if (filters[key] !== ANY[key] && !matchers[key](p, filters[key])) return false
    }
    return true
  })
}

/** Значения фасета считаются по выборке, отфильтрованной всеми остальными условиями. */
function facet(list: ArchivePublication[], filters: Filters, key: Facet, pick: (p: ArchivePublication) => string[]) {
  const counts = new Map<string, number>()
  for (const p of apply(list, filters, key)) {
    for (const value of pick(p)) counts.set(value, (counts.get(value) ?? 0) + 1)
  }
  const entries = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'ru'))
  if (filters[key] !== ANY[key] && !counts.has(filters[key])) entries.unshift([filters[key], 0])
  return entries
}

function Select({ label, value, onChange, options, all }: {
  label: string; value: string; onChange: (v: string) => void; options: [string, number][]; all: string
}) {
  return <label className="pf-field">
    <span>{label}</span>
    <select value={value} onChange={e => onChange(e.target.value)}>
      <option>{all}</option>
      {options.map(([name, count]) => <option key={name} value={name}>{name} ({count})</option>)}
    </select>
  </label>
}

function YearSelect({ label, value, onChange, years }: {
  label: string; value: string; onChange: (v: string) => void; years: number[]
}) {
  return <label className="pf-field">
    <span>{label}</span>
    <select value={value} onChange={e => onChange(e.target.value)}>
      <option>{ANY_YEAR}</option>
      {years.map(year => <option key={year} value={String(year)}>{year}</option>)}
    </select>
  </label>
}

function App() {
  const [data, setData] = useState<ArchivePublication[]>(publicationsArchive)
  const [live, setLive] = useState<'bundled' | 'loading' | 'sheet' | 'error'>(PUBLICATIONS_SHEET_CSV ? 'loading' : 'bundled')
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const [sort, setSort] = useState('new')
  const [limit, setLimit] = useState(PAGE_SIZE)

  useEffect(() => {
    if (!PUBLICATIONS_SHEET_CSV) return
    let cancelled = false
    fetch(PUBLICATIONS_SHEET_CSV, { cache: 'no-store' })
      .then(response => { if (!response.ok) throw new Error(String(response.status)); return response.text() })
      .then(text => {
        const rows = rowsToPublications(parseCsv(text))
        if (cancelled || !rows.length) return
        setData(rows)
        setLive('sheet')
      })
      .catch(() => { if (!cancelled) setLive('error') })
    return () => { cancelled = true }
  }, [])

  const set = (key: keyof Filters) => (value: string) => { setFilters(f => ({ ...f, [key]: value })); setLimit(PAGE_SIZE) }
  const setYearFrom = (value: string) => {
    setFilters(f => ({ ...f, yearFrom: value, yearTo: f.yearTo !== ANY_YEAR && value !== ANY_YEAR && Number(value) > Number(f.yearTo) ? value : f.yearTo }))
    setLimit(PAGE_SIZE)
  }
  const setYearTo = (value: string) => {
    setFilters(f => ({ ...f, yearTo: value, yearFrom: f.yearFrom !== ANY_YEAR && value !== ANY_YEAR && Number(value) < Number(f.yearFrom) ? value : f.yearFrom }))
    setLimit(PAGE_SIZE)
  }
  const clearYears = () => { setFilters(f => ({ ...f, yearFrom: ANY_YEAR, yearTo: ANY_YEAR })); setLimit(PAGE_SIZE) }

  const found = useMemo(() => {
    const list = apply(data, filters)
    const byYear = (a: ArchivePublication, b: ArchivePublication) => (b.year ?? 0) - (a.year ?? 0) || a.title.localeCompare(b.title, 'ru')
    if (sort === 'old') return [...list].sort((a, b) => -byYear(a, b))
    if (sort === 'title') return [...list].sort((a, b) => a.title.localeCompare(b.title, 'ru'))
    return [...list].sort(byYear)
  }, [data, filters, sort])

  const yearOptions = useMemo(() => {
    const years = new Set<number>()
    for (const p of apply(data, filters, 'year')) if (p.year) years.add(p.year)
    return [...years].sort((a, b) => b - a)
  }, [data, filters])
  const publishers = facet(data, filters, 'publisher', p => (p.publisher ? [p.publisher] : []))
  const coauthors = facet(data, filters, 'coauthor', p => split(p.coauthors))
  const topics = facet(data, filters, 'topic', p => split(p.topics))
  const types = facet(data, filters, 'type', p => (p.type ? [p.type] : []))

  const activeFacets = (Object.keys(ANY) as Facet[]).filter(key => filters[key] !== ANY[key])
  const yearLabel = filters.yearFrom !== ANY_YEAR && filters.yearTo !== ANY_YEAR
    ? (filters.yearFrom === filters.yearTo ? filters.yearFrom : `с ${filters.yearFrom} по ${filters.yearTo}`)
    : filters.yearFrom !== ANY_YEAR ? `с ${filters.yearFrom}`
    : filters.yearTo !== ANY_YEAR ? `по ${filters.yearTo}` : ''
  const dirty = activeFacets.length > 0 || !!yearLabel || filters.query.trim() !== ''
  const visible = found.slice(0, limit)
  const allYears = data.map(p => p.year).filter((y): y is number => !!y)

  let previousYear: number | null | undefined

  return <>
    <header className="header">
      <a className="brand" href={BASE} aria-label="На главную"><span>ЛЛТ</span><i>Академический архив</i></a>
      <nav><a href={BASE}>Главная</a><a href={`${BASE}#works`}>Книги</a><a href={`${BASE}#sources`}>Источники</a></nav>
    </header>
    <main className="pubpage">
      <section className="pf-hero">
        <p className="section-kicker">Библиография · полный список</p>
        <h1>Печатные<br /><em>работы</em></h1>
        <p className="pf-lead">
          {data.length} публикаций {allYears.length ? `с ${Math.min(...allYears)} по ${Math.max(...allYears)} год` : ''} — статьи,
          монографии, пособия, программы и рабочие тетради. Список можно фильтровать по годам, издательству, соавторам и темам.
        </p>
        <p className="pf-status">
          {live === 'sheet' && <>Данные загружены из рабочей таблицы.</>}
          {live === 'loading' && <>Загружаем актуальную таблицу…</>}
          {live === 'error' && <>Таблица сейчас недоступна — показана последняя сохранённая копия.</>}
          {live === 'bundled' && <>Показана сохранённая копия каталога.</>}
          {' '}
          <a href={`${BASE}publications.csv`} download>Скачать CSV</a> · <a href={`${BASE}publications.xlsx`} download>Скачать XLSX</a>
        </p>
      </section>

      <section className="pf-tools">
        <label className="pf-field pf-search">
          <span>Поиск</span>
          <input value={filters.query} onChange={e => set('query')(e.target.value)} placeholder="Название, издание, DOI…" />
        </label>
        <YearSelect label="Год: с" value={filters.yearFrom} onChange={setYearFrom} years={yearOptions} />
        <YearSelect label="Год: по" value={filters.yearTo} onChange={setYearTo} years={yearOptions} />
        <Select label="Издательство" all={ANY.publisher} value={filters.publisher} onChange={set('publisher')} options={publishers} />
        <Select label="Соавтор" all={ANY.coauthor} value={filters.coauthor} onChange={set('coauthor')} options={coauthors} />
        <Select label="Тема" all={ANY.topic} value={filters.topic} onChange={set('topic')} options={topics} />
        <Select label="Тип работы" all={ANY.type} value={filters.type} onChange={set('type')} options={types} />
        <label className="pf-field">
          <span>Сортировка</span>
          <select value={sort} onChange={e => setSort(e.target.value)}>
            <option value="new">Сначала новые</option>
            <option value="old">Сначала ранние</option>
            <option value="title">По названию</option>
          </select>
        </label>
      </section>

      <div className="pf-summary">
        <span>Найдено: <strong>{found.length}</strong> из {data.length}</span>
        <div className="pf-chips">
          {filters.query.trim() && <button onClick={() => set('query')('')}>«{filters.query.trim()}» ✕</button>}
          {yearLabel && <button onClick={clearYears}>{yearLabel} ✕</button>}
          {activeFacets.map(key => <button key={key} onClick={() => set(key)(ANY[key])}>{filters[key]} ✕</button>)}
          {dirty && <button className="pf-reset" onClick={() => { setFilters(EMPTY); setLimit(PAGE_SIZE) }}>Сбросить всё</button>}
        </div>
      </div>

      <ol className="pf-list" aria-live="polite">
        {visible.map((p, i) => {
          const head = sort !== 'title' && p.year !== previousYear
          previousYear = p.year
          return <li key={`${p.title}-${i}`}>
            {head && <div className="pf-year">{p.year ?? 'Год уточняется'}</div>}
            <article>
              <h2>{p.url ? <a href={p.url} target="_blank" rel="noreferrer">{p.title} ↗</a> : p.title}</h2>
              <p className="pf-citation">{p.citation}</p>
              <div className="pf-meta">
                <b>{p.type}</b>
                {p.publisher && <button onClick={() => set('publisher')(p.publisher)}>{p.publisher}</button>}
                {split(p.coauthors).map(name => <button key={name} className="pf-person" onClick={() => set('coauthor')(name)}>{name}</button>)}
                {split(p.topics).map(topic => <button key={topic} className="pf-topic" onClick={() => set('topic')(topic)}>{topic}</button>)}
                {p.pages && <span>{p.pages}</span>}
                {p.doi && <a href={`https://doi.org/${p.doi}`} target="_blank" rel="noreferrer">DOI {p.doi}</a>}
                {p.edn && <span>EDN {p.edn}</span>}
              </div>
            </article>
          </li>
        })}
        {!found.length && <li className="pf-empty">По этому запросу ничего не нашлось. Попробуйте снять часть фильтров.</li>}
      </ol>

      {limit < found.length && <div className="pf-more">
        <button onClick={() => setLimit(limit + PAGE_SIZE)}>Показать ещё {Math.min(PAGE_SIZE, found.length - limit)}</button>
        <span>Показано {visible.length} из {found.length}</span>
      </div>}
    </main>
    <footer><span>Л. Л. Тимофеева</span><span>Академический архив · 2026</span><a href={BASE}>На главную ↑</a></footer>
  </>
}

createRoot(document.getElementById('root')!).render(<App />)
