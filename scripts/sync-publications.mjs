/**
 * Забирает актуальную Google-таблицу публикаций и обновляет встроенную копию каталога.
 *
 *   npm run sync:publications
 *
 * Ссылка берётся из src/config.ts (PUBLICATIONS_SHEET_CSV) либо из аргумента:
 *   node scripts/sync-publications.mjs "https://docs.google.com/.../pub?output=csv"
 *
 * Обновляются public/publications.csv, src/data/publicationsArchive.ts и
 * src/data/publicationsMeta.ts — то, что сайт показывает, когда таблица недоступна.
 */
import { readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function parseCsv(text) {
  const rows = []
  let row = [], field = '', quoted = false
  const src = text.replace(/^﻿/, '').replace(/\r\n?/g, '\n')
  for (let i = 0; i < src.length; i++) {
    const ch = src[i]
    if (quoted) {
      if (ch === '"') { if (src[i + 1] === '"') { field += '"'; i++ } else quoted = false }
      else field += ch
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

const COLUMNS = {
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

async function sheetUrl() {
  if (process.argv[2]) return process.argv[2]
  if (process.env.PUBLICATIONS_SHEET_CSV) return process.env.PUBLICATIONS_SHEET_CSV
  const config = await readFile(resolve(root, 'src/config.ts'), 'utf8')
  const match = config.match(/PUBLICATIONS_SHEET_CSV\s*=\s*'([^']*)'/)
  return match?.[1] ?? ''
}

const url = await sheetUrl()
if (!url) {
  console.error('Ссылка на таблицу не задана. Укажите её в src/config.ts или передайте аргументом.')
  process.exit(1)
}

const response = await fetch(url, { redirect: 'follow' })
if (!response.ok) {
  console.error(`Не удалось скачать таблицу: HTTP ${response.status}`)
  process.exit(1)
}
const csv = await response.text()
const rows = parseCsv(csv)
if (rows.length < 2) {
  console.error('Таблица пустая — ничего не меняем.')
  process.exit(1)
}

const header = rows[0].map(cell => cell.trim().toLowerCase().replace(/\s+/g, ' '))
const index = {}
for (const [key, names] of Object.entries(COLUMNS)) index[key] = header.findIndex(cell => names.includes(cell))
if (index.title < 0) {
  console.error('В таблице нет колонки «Название».')
  process.exit(1)
}

const cell = (row, key) => (index[key] >= 0 ? (row[index[key]] ?? '').trim() : '')
const records = rows.slice(1).map(row => {
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
}).filter(record => record.title)

records.sort((a, b) => (b.year ?? 0) - (a.year ?? 0) || a.title.localeCompare(b.title, 'ru'))

const line = record => {
  const parts = [
    `year: ${record.year ?? 'null'}`,
    `type: ${JSON.stringify(record.type)}`,
    `title: ${JSON.stringify(record.title)}`,
    `coauthors: ${JSON.stringify(record.coauthors)}`,
    `publisher: ${JSON.stringify(record.publisher)}`,
    `topics: ${JSON.stringify(record.topics)}`,
  ]
  for (const key of ['pages', 'doi', 'edn', 'url']) {
    if (record[key]) parts.push(`${key}: ${JSON.stringify(record[key])}`)
  }
  parts.push(`citation: ${JSON.stringify(record.citation)}`)
  return `  { ${parts.join(', ')} },`
}

await writeFile(resolve(root, 'src/data/publicationsArchive.ts'),
  '// Сгенерировано npm run sync:publications из Google-таблицы — резервная копия каталога.\n' +
  '// Живые данные берутся из таблицы (см. src/config.ts); этот файл используется,\n' +
  '// если таблица не настроена или недоступна.\n' +
  "import type { ArchivePublication } from './publicationTypes'\n\n" +
  'export const publicationsArchive: ArchivePublication[] = [\n' + records.map(line).join('\n') + '\n]\n')

const years = records.map(record => record.year).filter(Boolean)
await writeFile(resolve(root, 'src/data/publicationsMeta.ts'),
  '// Сгенерировано вместе с publicationsArchive.ts — краткая сводка для главной страницы,\n' +
  '// чтобы не тянуть в неё весь каталог.\n' +
  `export const archiveMeta = { count: ${records.length}, from: ${Math.min(...years)}, to: ${Math.max(...years)} }\n`)

await writeFile(resolve(root, 'public/publications.csv'), csv.startsWith('﻿') ? csv : '﻿' + csv)

console.log(`Готово: ${records.length} записей из таблицы.`)
console.log('Обновлены src/data/publicationsArchive.ts, src/data/publicationsMeta.ts, public/publications.csv')
