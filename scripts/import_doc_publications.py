# -*- coding: utf-8 -*-
"""Разбирает Word-файл со списком печатных работ и собирает из него таблицу.

    python3 scripts/import_doc_publications.py [Pechatnye_raboty.doc]

На выходе:
    public/publications.csv         — таблица для загрузки в Google Таблицы / Excel
    public/publications.xlsx        — та же таблица в формате Excel
    src/data/publicationsArchive.ts — встроенная копия каталога для сайта
    src/data/publicationsMeta.ts    — количество работ и диапазон лет для главной страницы

Скрипт нужен только для первичного импорта из Word: после того как таблица
заведена в Google, источником данных становится она (см. scripts/sync-publications.mjs).
Конвертация .doc выполняется системной утилитой macOS `textutil`.
"""
import os, re, io, csv, sys, json, zipfile, subprocess, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + '/'

def source_text(path):
    if path.lower().endswith('.txt'):
        return io.open(path, encoding='utf-8').read()
    out = ROOT + '.publications-source.txt'
    subprocess.run(['textutil', '-convert', 'txt', '-output', out, path], check=True)
    text = io.open(out, encoding='utf-8').read()
    os.remove(out)
    return text


def split_records(raw):
    """Каждая непустая строка Word-файла — одна библиографическая запись.
    Строки-продолжения со ссылками присоединяются к предыдущей записи."""
    recs = []
    for line in [x.strip() for x in raw.split("\n")]:
        if not line:
            continue
        if recs and (line.startswith("HYPERLINK") or line.startswith("http")):
            recs[-1] += " " + line
            continue
        recs.append(line)
    return recs

URL_RE = re.compile(r'https?://[^\s"]+')
DOI_RE = re.compile(r'(?:DOI:?\s*|https?://doi\.org/)(10\.\d{4,}/[^\s,;]+)', re.I)
EDN_RE = re.compile(r'EDN:?\s*([A-Z]{6})', re.I)

def clean(s):
    s = re.sub(r'HYPERLINK\s+"[^"]*"(\s+\\t\s+"[^"]*")?', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def strip_ids(s):
    s = URL_RE.sub(' ', s)
    s = re.sub(r'DOI:?\s*10\.\d{4,}/\S+', ' ', s, flags=re.I)
    s = re.sub(r'10\.\d{4,}/\S+', ' ', s)
    s = re.sub(r'EDN:?\s*[A-Z]{6}', ' ', s, flags=re.I)
    return s

YEAR_RE = re.compile(r'\b(19[89]\d|20[0-4]\d)\b')
def get_year(s):
    t = strip_ids(s)
    t = re.sub(r'[Сс]\.\s*\d+\s*[–—\-]\s*\d+', ' ', t)
    t = re.sub(r'\d+\s*с\.', ' ', t)
    ys = [int(y) for y in YEAR_RE.findall(t)]
    return max(ys) if ys else None

# ---------------- people ----------------
NAME = r'[А-ЯЁ][а-яё]+(?:-[А-ЯЁа-яё]+)?'
AUTH_FWD = re.compile(r'\b(' + NAME + r')\s+([А-ЯЁ])\.\s?([А-ЯЁ])?\.?')
AUTH_REV = re.compile(r'\b([А-ЯЁ])\.\s?([А-ЯЁ])?\.?\s*(' + NAME + r')\b')
EDITOR_CTX = re.compile(r'(?:под\s+(?:общ\.?\s*)?(?:науч\.?\s*)?ред\.?|отв\.?\s*ред\.?|науч\.?\s*ред\.?|Ред\.|редакцией|составител[ьия]|Сост\.|Составители)', re.I)

GENITIVE = [('овой','ова'),('евой','ева'),('иной','ина'),('ской','ская'),('цкой','цкая'),
            ('ёвой','ёва'),('ева ','ева '),]
ALIAS = {}

def canon_surname(s):
    for a,b in GENITIVE:
        if s.lower().endswith(a):
            return s[:-len(a)] + b
    # masculine genitive: Умана -> Уман, Майера -> Майер, Гафнера -> Гафнер
    return s

def person(last, i1, i2):
    last = canon_surname(last)
    last = ALIAS.get(last, last)
    ini = i1 + '.' + ((i2 + '.') if i2 else '')
    return last + ' ' + ini

BAD_SURNAMES = set("""Изд Вып Том Часть Ч Сб Материалы Тираж Москва Орел Орёл Санкт Петербург Минск Тверь
Барнаул Челябинск Саратов Краснодар Мозырь Белгород Автор-составитель Автор Составитель Составители
Авторы-составители Редактор Ответственный Отв Науч Общ Ред""".split())

def people_in(text):
    out = []
    for m in AUTH_FWD.finditer(text):
        if m.group(1) in BAD_SURNAMES: continue
        out.append(person(m.group(1), m.group(2), m.group(3)))
    # reversed order only in editor/compiler context
    for m in AUTH_REV.finditer(text):
        start = max(0, m.start() - 30)
        if not EDITOR_CTX.search(text[start:m.start()]): continue
        if m.group(3) in BAD_SURNAMES: continue
        out.append(person(m.group(3), m.group(1), m.group(2)))
    seen, res = set(), []
    for p in out:
        if p not in seen: seen.add(p); res.append(p)
    return res

AUTH_TOKEN = r'' + NAME + r'\s+[А-ЯЁ]\.\s?[А-ЯЁ]?\.?'
AUTH_PREFIX = re.compile(r'^((?:' + AUTH_TOKEN + r')(?:\s*[,;]?\s*(?:' + AUTH_TOKEN + r'))*)[\s,;]*')

# ---------------- venue / publisher ----------------
PUB_ALIASES = [
 (r'Педагогическое общество России', 'Педагогическое общество России'),
 (r'Детство[-\s]?[ПпРр][рР]?[еЕ][сС][сС]|ДЕТСТВО-ПРЕСС', 'Детство-Пресс'),
 (r'Центр педагогического образования', 'Центр педагогического образования'),
 (r'Просвещение', 'Просвещение'),
 (r'Дрофа', 'Дрофа'),
 (r'ИНФРА-М', 'ИНФРА-М'),
 (r'РУСАЙНС', 'РУСАЙНС'),
 (r'Цветной мир', 'ИД «Цветной мир»'),
 (r'Белый Ветер', 'Белый Ветер'),
 (r'ACADEMIA|Академия', 'ACADEMIA'),
 (r'ТЦ\s*«?Сфера»?|Сфера', 'ТЦ «Сфера»'),
 (r'Юрайт', 'Юрайт'),
 (r'Знание-М', 'Знание-М'),
 (r'«?Наука»?', 'ИЦ «Наука»'),
 (r'\bМПСУ\b|Московский психолого-социальный', 'МПСУ'),
 (r'\bМПГУ\b', 'МПГУ'),
 (r'\bМГПУ\b', 'МГПУ'),
 (r'НШУОС', 'Изд-во НШУОС'),
 (r'(?:ОО\s*|О\s*)?ИУУ|Издательство ИУУ|институт усовершенствования учителей', 'Орловский институт усовершенствования учителей'),
 (r'\bОИРО\b|институт развития образования', 'Орловский институт развития образования'),
 (r'\bОГУ\b', 'Орловский государственный университет'),
 (r'\bАПО\b', 'Академия последипломного образования (Минск)'),
 (r'\bИРО\b', 'Институт развития образования (Краснодар)'),
]
def norm_publisher(s):
    if not s: return ''
    for pat, name in PUB_ALIASES:
        if re.search(pat, s):
            return name
    name = re.sub(r'^(Изд-во|Издательство|ООО|ЗАО|ГАОУ ВО|ФГБОУ ВО)\s+', '', s).strip(' .,;"«»')
    if name.count('«') > name.count('»'): name += '»'
    # мусор от неудачно сработавшего разбора выходных данных
    if '//' in name or not re.match(r'^[А-ЯЁA-Z«"]', name) or len(name) < 2: return ''
    return name

IMPRINT = re.compile(r'[–—-]\s*(?:г\.\s*)?[А-ЯЁ][А-Яа-яёЁ\-\s]{0,18}?\.?\s*:\s*([^,;]{2,70}?)\s*[,;]\s*(?:19|20)\d\d')
IMPRINT2 = re.compile(r'(?:^|[.\s])(?:г\.\s*)?[А-ЯЁ][А-Яа-яёЁ\-]{0,18}\.?\s*:\s*([^,;]{2,70}?)\s*[,;]?\s*(?:19|20)\d\d')
IMPRINT3 = re.compile(r'[–—-]\s*(?:г\.\s*)?[А-ЯЁ][А-Яа-яёЁ\-]{0,18}\.?\s*,\s*([А-ЯЁ][^,;]{2,60}?)\s*,\s*(?:19|20)\d\d')

def find_publisher(body):
    m = IMPRINT.search(body) or IMPRINT2.search(body) or IMPRINT3.search(body)
    return norm_publisher(clean(m.group(1))) if m else ''

VENUE_CUT = re.compile(r'\s*(?:[–—]\s*)?(?:\b(?:19|20)\d\d\b|№|Вып\.|Выпуск|Том\b|Т\.\s*\d|/|Сб\.|[Сс]борник|[Мм]атериалы|под\s+ред|Под\s+ред|отв\.\s*ред|\[Электронн|(?:М|СПб|Спб|Орел|Орёл|Минск|Москва)\.?\s*:)')
def venue_name(venue):
    v = clean(venue).lstrip(' .:')
    m = VENUE_CUT.search(v)
    if m: v = v[:m.start()]
    v = v.strip(' .,;:–—')
    v = re.sub(r'\s*\.\s*$', '', v)
    return v

# ---------------- title ----------------
TITLE_CUTS = [
 re.compile(r'(?<![\d ])\s[–—]\s(?!\d)'),
 re.compile(r'\s/\s'),
 re.compile(r'\.\s*(?:Методическое пособие|Учебное пособие|Учебно-методическое|Методические рекомендации|Практическое пособие|Рабочая тетрадь|Хрестоматия|Развивающая кн|Изд\.\s*\d|Издание\s+\d|Учебник|Монография|монография)'),
 re.compile(r'\.\s*(?:Авторы?-составител|Составител|Автор-составител|Под\s+ред|под\s+ред|Под\s+общ)'),
 re.compile(r'\.\s*(?:г\.\s*)?[А-ЯЁ][А-Яа-яёЁ\-]{0,18}\.?\s*:\s*[А-ЯЁ]'),
 re.compile(r'\s*[;,]\s*(?:под\.?\s*(?:общ\.?\s*)?ред|[Сс]ост\.|составител|автор[ыи]?-составител)'),
 re.compile(r'\s*/\s*(?:под|сост|отв|науч)'),
 re.compile(r'\s*:\s*(?:учебно-методическое|учебно-практическое|методическое|учебное|практическое)\s+пособие'),
 re.compile(r'\s*:\s*(?:[Мм]атериалы|[Сс]борник|монография|учебник)\b'),
]
def make_title(head):
    t = head.strip()
    cut = len(t)
    for i, rx in enumerate(TITLE_CUTS):
        low = 14 if i < 2 else 8
        for m in rx.finditer(t):
            if m.start() >= low:
                cut = min(cut, m.start()); break
    t = t[:cut].strip(' .,;:')
    return t

# ---------------- topics ----------------
TOPICS = [
 ('Информационная культура и безопасность', r'информацион|цифров'),
 ('Культура безопасности',                  r'безопасн|ОБЖ|чрезвычайн'),
 ('Естественно-научная грамотность',        r'естественно-?научн|природовед|естествознан|окружающ(ий|ему) мир'),
 ('Функциональная грамотность',             r'грамотност'),
 ('Экологическое образование',              r'эколог'),
 ('Духовно-нравственное воспитание',        r'духовно-нравствен|нравствен|ценност'),
 ('Проектная и исследовательская деятельность', r'проектн|проект|исследовательск|мультфильм|познавательн'),
 ('Планирование образовательной деятельности',  r'планирован|ФГТ|ФОП|ФГОС|программ|преемственност'),
 ('Профессиональное развитие педагогов',    r'компетентност|аттестац|тьютор|квалификаци|профессиональн|подготовк[аие]\s+педагог|педагог[ауов]\b|воспитател[ья]\b|учител'),
 ('Дошкольное образование',                 r'дошкольн|ДОУ|ДОО|детском саду|детского сада|предшкольн'),
 ('Начальное образование',                  r'начальн|\\bмладш|\\bшкольник|урок|первоклассник|\\bкласс'),
]
def detect_topics(text):
    hits = [n for n, p in TOPICS if re.search(p, text, re.I)]
    return hits[:2]

CONF_PAT = r'конференц|[Мм]атериалы|[Сс]борник|Сб\.|чтения|Чтения|съезд|семинар|НПК|трудов'
def classify(body, venue, has_slash):
    low = body.lower()
    if 'деп. в' in low: return 'Депонированная работа'
    if 'автореферат' in low or 'диссертац' in low: return 'Диссертация'
    if 'монографи' in low: return 'Монография'
    if has_slash:
        return 'Статья в сборнике' if re.search(CONF_PAT, venue) else 'Статья в журнале'
    if 'рабочая тетрадь' in low: return 'Рабочая тетрадь'
    if re.search(r'методическое пособие|учебное пособие|методические рекомендации|учебно-методическ|практическое пособие', low): return 'Методическое пособие'
    if re.search(r'планирование|программа|хрестоматия', low): return 'Программа / планирование'
    return 'Книга'

def role_of(body, lead):
    if any(p.startswith('Тимофеева Л') for p in lead): return 'Автор'
    if re.search(r'[Пп]од\s+(?:общ\.?\s*)?ред\.[^/]{0,40}Тимофеев', body): return 'Редактор'
    if re.search(r'[Сс]оставител|[Аа]втор[ыи]?-составител', body) : return 'Составитель'
    return 'Автор'

def parse(rec):
    rec = clean(rec)
    urls = URL_RE.findall(rec)
    doi = DOI_RE.search(rec); edn = EDN_RE.search(rec)
    body = clean(URL_RE.sub(' ', rec)).strip(' .')
    has_slash = '//' in body
    head, venue = body.split('//', 1) if has_slash else (body, '')
    m = AUTH_PREFIX.match(head)
    lead = people_in(m.group(1)) if m else []
    head_rest = head[m.end():] if (m and lead) else head
    title = make_title(head_rest)
    coauthors = [p for p in people_in(head) if not p.startswith('Тимофеева Л')]
    _ = lead
    publisher = find_publisher(body)
    return dict(
        raw=body, year=get_year(body), title=title,
        coauthors='; '.join(coauthors),
        publisher=publisher, venue=clean(venue).strip(' .'),
        type=classify(body, venue, has_slash),
        topics='; '.join(detect_topics(title) or detect_topics(body)),
        pages=('с. ' + re.sub(r'\s*[–—\-]\s*', '–', re.search(r'[Сс]\.\s*(\d+\s*[–—\-]\s*\d+)', body).group(1))) if re.search(r'[Сс]\.\s*(\d+\s*[–—\-]\s*\d+)', body) else '',
        doi=doi.group(1) if doi else '', edn=edn.group(1).upper() if edn else '',
        url=urls[0] if urls else '')


def normalize(d):

    # ---- канонические названия издательств (варианты написания сводим к одному) ----
    CANON = [
     ('Детство-Пресс', ['Детство-пресс', '«Детство-пресс»', 'Детство Пресс']),
     ('ИНФРА-М', ['Инфра-М', 'Инфра-м']),
     ('БИНОМ. Лаборатория знаний', ['Бином. Лаборатория знаний', 'БИНОМ. Лаборатория знаний: Редакция БИНОМ ДЕТСТВА']),
     ('Институт развития образования (Владимир)', ['ВИРО', 'ГАОУ ДПО ВО ВИРО']),
     ('Орловский институт развития образования', ['БУ ОО ДПО «Институт развития образования»', 'ОИРО']),
     ('Орловский государственный университет', ['Орловский государственный университет имени И.С. Тургенева']),
    ]
    def canon_source(s):
        if not s: return s
        t = s.strip(' .;"')
        bare = t.strip('«»')
        for good, alts in CANON:
            for cand in [good] + alts:
                for probe in (t, bare):
                    if probe == cand or re.fullmatch(re.escape(cand) + r'[.,:;? ].*', probe): return good
        return t

    for x in d:
        x['publisher'] = canon_source(x['publisher'])

    # ---- merge person variants ----
    cnt = collections.Counter()
    for x in d:
        for p in filter(None, x['coauthors'].split('; ')): cnt[p] += 1
    names = set(cnt)
    merge = {}
    for n in list(names):
        last, ini = n.rsplit(' ', 1)
        # masculine genitive: Майера А.А. -> Майер А.А.
        if last.endswith(('а','я')) and (last[:-1] + ' ' + ini) in names:
            merge[n] = last[:-1] + ' ' + ini
        # single initial -> unique two-initial match
        if len(ini) == 2:
            cands = [m for m in names if m.startswith(last + ' ' + ini) and len(m) > len(n)]
            if len(cands) == 1: merge[n] = cands[0]
    for x in d:
        ps = [merge.get(p, p) for p in filter(None, x['coauthors'].split('; '))]
        seen, out = set(), []
        for p in ps:
            if p not in seen: seen.add(p); out.append(p)
        x['coauthors'] = '; '.join(out)


    return d

def emit(d):
    d.sort(key=lambda x: (-(x["year"] or 0), x["title"]))

    HEAD = ['Год','Тип','Название','Соавторы','Издательство','Темы','Страницы','DOI','EDN','Ссылка','Полное описание']
    def row(x):
        return [str(x['year'] or ''), x['type'], x['title'], x['coauthors'], x['publisher'], x['topics'],
                x['pages'], x['doi'], x['edn'], x['url'], x['raw']]
    rows = [row(x) for x in d]

    # ---- CSV (UTF-8 BOM so Excel opens it correctly) ----
    os.makedirs(ROOT+'public', exist_ok=True)
    with io.open(ROOT+'public/publications.csv','w',encoding='utf-8-sig',newline='') as f:
        w = csv.writer(f); w.writerow(HEAD); w.writerows(rows)

    # ---- minimal XLSX ----
    def esc(s):
        return (s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
                 .replace('"','&quot;'))
    def cell(ci, ri, val, style=0):
        col = ''
        n = ci
        while True:
            col = chr(65 + n % 26) + col; n = n // 26 - 1
            if n < 0: break
        ref = '%s%d' % (col, ri)
        if val and re.fullmatch(r'\d{4}', val):
            return '<c r="%s" s="%d"><v>%s</v></c>' % (ref, style, val)
        if not val:
            return '<c r="%s" s="%d"/>' % (ref, style)
        return '<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, style, esc(val))

    sheet = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
     '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
     '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>',
     '<sheetFormatPr defaultRowHeight="15"/>',
     '<cols>' + ''.join('<col min="%d" max="%d" width="%d" customWidth="1"/>' % (i+1,i+1,w)
        for i,w in enumerate([7,22,60,26,34,34,12,26,12,32,90])) + '</cols>',
     '<sheetData>']
    sheet.append('<row r="1">' + ''.join(cell(i,1,h,1) for i,h in enumerate(HEAD)) + '</row>')
    for ri, r in enumerate(rows, start=2):
        sheet.append('<row r="%d">' % ri + ''.join(cell(i,ri,v) for i,v in enumerate(r)) + '</row>')
    sheet.append('</sheetData><autoFilter ref="A1:K%d"/></worksheet>' % (len(rows)+1))
    sheet = ''.join(sheet)

    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
    <fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
    <fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF0E7D8"/><bgColor indexed="64"/></patternFill></fill></fills>
    <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
    <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
    <cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center"/></xf></cellXfs>
    </styleSheet>'''

    wb = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Публикации" sheetId="1" r:id="rId1"/></sheets></workbook>'''
    wbrels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    ct = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'''

    with zipfile.ZipFile(ROOT+'public/publications.xlsx','w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ct)
        z.writestr('_rels/.rels', rels)
        z.writestr('xl/workbook.xml', wb)
        z.writestr('xl/_rels/workbook.xml.rels', wbrels)
        z.writestr('xl/styles.xml', styles)
        z.writestr('xl/worksheets/sheet1.xml', sheet)

    # ---- TypeScript bundled fallback ----
    def js(s): return json.dumps(s, ensure_ascii=False)
    lines = []
    for x in d:
        parts = ['year: ' + (str(x['year']) if x['year'] else 'null'),
                 'type: ' + js(x['type']),
                 'title: ' + js(x['title']),
                 'coauthors: ' + js(x['coauthors']),
                 'publisher: ' + js(x['publisher']),
                 'topics: ' + js(x['topics'])]
        for k in ('pages','doi','edn','url'):
            if x[k]: parts.append(k + ': ' + js(x[k]))
        parts.append('citation: ' + js(x['raw']))
        lines.append('  { ' + ', '.join(parts) + ' },')
    ts = ('// Сгенерировано из Pechatnye_raboty.doc — резервная копия каталога публикаций.\n'
          '// Живые данные берутся из Google-таблицы (см. src/config.ts); этот файл используется,\n'
          '// если таблица не настроена или недоступна.\n'
          'import type { ArchivePublication } from \'./publicationTypes\'\n\n'
          'export const publicationsArchive: ArchivePublication[] = [\n' + '\n'.join(lines) + '\n]\n')
    io.open(ROOT+'src/data/publicationsArchive.ts','w',encoding='utf-8').write(ts)
    ys = [x['year'] for x in d if x['year']]
    io.open(ROOT+'src/data/publicationsMeta.ts','w',encoding='utf-8').write(
     '// Сгенерировано вместе с publicationsArchive.ts — краткая сводка для главной страницы,\n'
     '// чтобы не тянуть в неё весь каталог.\n'
     'export const archiveMeta = { count: %d, from: %d, to: %d }\n' % (len(d), min(ys), max(ys)))


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else ROOT + 'Pechatnye_raboty.doc'
    records = [parse(r) for r in split_records(source_text(src))]
    records = normalize(records)
    emit(records)
    print('Разобрано записей: %d' % len(records))
    print('Обновлены: public/publications.csv, public/publications.xlsx,')
    print('           src/data/publicationsArchive.ts, src/data/publicationsMeta.ts')

if __name__ == '__main__':
    main()
