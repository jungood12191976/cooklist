#!/usr/bin/env python3
"""日経225の各銘柄について、直近30日の「日別ニュース記事数」を Googleニュース(RSS検索)から数え、
data/news_volume.json に書く。GitHub Actions から毎日実行される(.github/workflows/news-volume.yml)。

仕組み(2026-10-07に実機プローブで確認済み):
  ・news.google.com/rss/search?q=...+when:30d は1回に最大100件まで返す。pubDateが付いている。
  ・100件に達した銘柄は、日付で小分け(after:/before:)にして取り直し、取りこぼしを減らす。
  ・日別の件数は日本時間(JST)の日付で数える。当日分は途中経過。
銘柄コード→社名は index.html の STOCK_NAMES_JA / NIKKEI225 から読む(アプリと同じ辞書。二重管理しない)。
"""
import collections, datetime, email.utils, json, os, re, sys, time, urllib.parse
import requests

JST = datetime.timezone(datetime.timedelta(hours=9))
UA = {'User-Agent': 'Mozilla/5.0 (compatible; king-the-quest-news/1.0)'}
OUT = os.path.join('data', 'news_volume.json')
DIAG = os.path.join('data', 'news_volume_check.txt')
DAYS = 30
CAP = 100          # RSSが返す最大件数
SLICE_DAYS = 5     # 100件に達したときの小分けの日数
SLEEP = 1.0


def load_universe():
    s = open('index.html', encoding='utf-8').read()
    a = s.index('const NIKKEI225 = [')
    codes = re.findall(r"'([0-9A-Z]{4})'", s[a:s.index('];', a)])
    b = s.index('const STOCK_NAMES_JA = {')
    names = dict(re.findall(r"'([0-9A-Z]{4})'\s*:\s*'([^']*)'", s[b:s.index('};', b)]))
    return [(c, names.get(c, '')) for c in codes]


def search_word(name):
    """検索に使う社名。HD/グループ本社などの付け足しを外して、報道で使われる短い名前に寄せる。"""
    n = name.replace('　', ' ').strip()
    n = re.sub(r'\s*(ホールディングス|ＨＤ|HD)$', '', n)
    n = re.sub(r'(グループ本社|本社)$', '', n)
    return n.strip() or name


def get(url):
    for k in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 200:
                return r.text
            if r.status_code in (429, 503):
                time.sleep(5 * (k + 1))
                continue
            return None
        except requests.RequestException:
            time.sleep(3 * (k + 1))
    return None


def fetch_items(word, extra):
    q = '"%s" 株 %s' % (word, extra)
    url = 'https://news.google.com/rss/search?q=%s&hl=ja&gl=JP&ceid=JP:ja' % urllib.parse.quote(q)
    txt = get(url)
    time.sleep(SLEEP)
    if txt is None:
        return None
    out = []
    for it in re.findall(r'<item>(.*?)</item>', txt, flags=re.S):
        m = re.search(r'<pubDate>(.*?)</pubDate>', it)
        l = re.search(r'<link>(.*?)</link>', it)
        if not m:
            continue
        d = email.utils.parsedate_to_datetime(m.group(1)).astimezone(JST).date()
        out.append((l.group(1) if l else '', d))
    return out


def main():
    today = datetime.datetime.now(JST).date()
    dates = [today - datetime.timedelta(days=DAYS - 1 - i) for i in range(DAYS)]
    first = dates[0]
    uni = load_universe()
    old = {}
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT, encoding='utf-8')).get('items', {})
        except Exception:
            old = {}
    items, diag, n_fail, n_trunc = {}, [], 0, 0
    for code, name in uni:
        word = search_word(name) if name else code
        got = fetch_items(word, 'when:%dd' % DAYS)
        truncated = False
        if got is None:
            n_fail += 1
            if code in old:
                items[code] = old[code]   # 取得失敗時は前回の値を残す
            diag.append('FAIL %s %s' % (code, name))
            continue
        links = {}
        for l, d in got:
            links[(l, d)] = d
        if len(got) >= CAP:
            truncated = True
            n_trunc += 1
            links = {}
            ok_all = True
            start = first
            while start <= today:
                end = min(start + datetime.timedelta(days=SLICE_DAYS), today + datetime.timedelta(days=1))
                part = fetch_items(word, 'after:%s before:%s' % (start.isoformat(), end.isoformat()))
                if part is None:
                    ok_all = False
                else:
                    for l, d in part:
                        links[(l, d)] = d
                start = end
            diag.append('SLICED %s %s first=%d sliced=%d ok=%s' % (code, name, len(got), len(links), ok_all))
        cnt = collections.Counter(d for d in links.values() if first <= d <= today)
        items[code] = {
            'name': name,
            'q': word,
            'counts': [cnt.get(d, 0) for d in dates],
            'capped': truncated and any(v >= CAP for v in cnt.values()),
        }
    if len(items) < 150 or n_fail > 60:
        sys.exit('取得できた銘柄が少なすぎるため書き込みません: items=%d fail=%d' % (len(items), n_fail))
    doc = {
        'source': 'Googleニュース(RSS検索) 記事の公開日時を日本時間の日付で件数化',
        'grade': 'B',
        'fetched_at': datetime.datetime.now(JST).isoformat(timespec='minutes'),
        'window_days': DAYS,
        'dates': [d.isoformat() for d in dates],
        'note': '記事数は注目度の代用(期待値そのものではない)。当日分は途中経過。転載記事も数える。',
        'items': items,
    }
    os.makedirs('data', exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, separators=(',', ':'))
    diag.insert(0, 'items=%d fail=%d sliced=%d fetched_at=%s' % (len(items), n_fail, n_trunc, doc['fetched_at']))
    open(DIAG, 'w', encoding='utf-8').write('\n'.join(diag) + '\n')
    print(diag[0])


if __name__ == '__main__':
    main()
