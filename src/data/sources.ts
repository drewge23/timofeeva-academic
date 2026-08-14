export type Source = { name: string; url: string; description: string; level: 'Первичный источник' | 'Библиографическая запись' | 'Профиль организации' }

export const sources: Source[] = [
  { name: 'РГБ — кандидатская диссертация', url: 'https://search.rsl.ru/ru/record/01000305911', description: 'Постоянная каталоговая запись и открытый доступ к диссертации 2000 года.', level: 'Первичный источник' },
  { name: 'Президентская библиотека — автореферат докторской диссертации', url: 'https://www.prlib.ru/item/2006176', description: 'Карточка автореферата 2022 года с местом защиты и объёмом.', level: 'Первичный источник' },
  { name: 'МПСУ — кафедра общей и специальной педагогики', url: 'https://www.mpsu.ru/life/department/kafedra-obshchey-i-spetsialnoy-pedagogiki/', description: 'Официальная страница кафедры с профилем преподавателя.', level: 'Профиль организации' },
  { name: 'МПСУ — публикация о модели культуры безопасности', url: 'https://mpsuinfo.ru/articles/154/ocenka-effektivnosti-modeli-formirovaniya-kultury-bezopasnosti-u-detei-doskolnogo-i-mladsego-skolnogo-vozrasta', description: 'Страница статьи, опубликованной МПСУ в 2022 году.', level: 'Первичный источник' },
  { name: 'РГБ — «Юные исследователи»', url: 'https://search.rsl.ru/ru/record/07000512661', description: 'Каталоговая запись с ISBN 978-5-09-099913-7.', level: 'Библиографическая запись' },
  { name: 'SciUp — статья 2025 года', url: 'https://sciup.org/148331606', description: 'Библиографическая страница с DOI и полным текстом статьи.', level: 'Библиографическая запись' },
  { name: 'ORCID', url: 'https://orcid.org/0000-0002-7944-9796', description: 'Научный идентификатор, указанный в публикации МПСУ.', level: 'Профиль организации' }
]
