import type { ArchivePublication } from '../data/publicationTypes'

/** Разбор CSV с поддержкой кавычек, переносов строк и запятых внутри ячеек. */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let quoted = false
  const src = text.replace(/^﻿/, '').replace(/\r\n?/g, '\n')
  for (let i = 0; i < src.length; i++) {
    const ch = src[i]
    if (quoted) {
      if (ch === '"') {
        if (src[i + 1] === '"') { field += '"'; i++ } else quoted = false
      } else field += ch
      continue
    }
    if (ch === '"') { quoted = true; continue }
    if (ch === ',') { row.push(field); field = ''; continue }
    if (ch === '\n') { row.push(field); rows.push(row); row = []; field = ''; continue }
    field += ch
  }
  if (field !== '' || row.length) { row.push(field); rows.push(row) }
  return rows.filter(r => r.some(cell => cell.trim() !== ''))
}

const COLUMNS: Record<keyof ArchivePublication, string[]> = {
  year: ['год', 'year'],
  type: ['тип', 'вид', 'type'],
  title: ['название', 'заголовок', 'title'],
  coauthors: ['соавторы', 'соавтор', 'авторы', 'authors'],
  publisher: ['издательство', 'издатель', 'publisher'],
  topics: ['темы', 'тема', 'topics'],
  pages: ['страницы', 'pages'],
  doi: ['doi'],
  edn: ['edn'],
  url: ['ссылка', 'url', 'link'],
  citation: ['полное описание', 'описание', 'библиографическая запись', 'citation'],
}

const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, ' ')

/** Сопоставляет строки таблицы с полями каталога по названиям колонок. */
export function rowsToPublications(rows: string[][]): ArchivePublication[] {
  if (!rows.length) return []
  const header = rows[0].map(norm)
  const index = {} as Record<keyof ArchivePublication, number>
  for (const key of Object.keys(COLUMNS) as (keyof ArchivePublication)[]) {
    index[key] = header.findIndex(cell => COLUMNS[key].includes(cell))
  }
  if (index.title < 0) throw new Error('В таблице нет колонки «Название»')
  const cell = (row: string[], key: keyof ArchivePublication) =>
    index[key] >= 0 ? (row[index[key]] ?? '').trim() : ''
  return rows.slice(1).map(row => {
    const year = parseInt(cell(row, 'year'), 10)
    const title = cell(row, 'title')
    const citation = cell(row, 'citation')
    return {
      year: Number.isFinite(year) ? year : null,
      type: cell(row, 'type') || 'Публикация',
      title: title || citation,
      coauthors: cell(row, 'coauthors'),
      publisher: cell(row, 'publisher'),
      topics: cell(row, 'topics'),
      pages: cell(row, 'pages'),
      doi: cell(row, 'doi'),
      edn: cell(row, 'edn'),
      url: cell(row, 'url'),
      citation: citation || title,
    }
  }).filter(p => p.title)
}
