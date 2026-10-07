#!/usr/bin/env python3
"""JPX公式「決算発表予定日」のExcelを取得し、data/earnings_jp.json に書く。

GitHub Actions から毎営業日に実行される(.github/workflows/earnings-jp.yml)。
中身が前回と同じなら何も書かない(=コミットされない)。
列の構成は2026-10-07にActions上で実物を確認した:
  行0-3=タイトル/「YYYY年M月D日 現在」、行4=見出し、行5以降=データ。
  A 決算発表予定日 / B コード / C 会社名 / D Issue Name / E 決算期末 /
  F 業種名 / G Industry / H 種別 / I Fiscal Year/Quarter / J 市場区分 / K Market Segment
"""
import datetime
import io
import json
import os
import re
import sys

import openpyxl
import requests

BASE = 'https://www.jpx.co.jp'
PAGE = BASE + '/listing/event-schedules/financial-announcement/index.html'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; king-the-quest-earnings/1.0)'}
OUT = os.path.join('data', 'earnings_jp.json')
MIN_ITEMS = 1000  # 実物は約3,250件。これより少なければ壊れたとみなして上書きしない。


def norm(c):
    if c is None:
        return ''
    if isinstance(c, float) and c.is_integer():
        return str(int(c))
    return str(c).strip()


def to_date(v):
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    m = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', norm(v))
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def find_columns(header):
    """見出し行(日本語+英語が改行でつながっている)から列位置を探す。"""
    want = {
        'date': '決算発表予定日',
        'code': 'コード',
        'name': '会社名',
        'name_en': 'Issue Name',
        'fy_end': '決算期末',
        'industry': '業種名',
        'kind': '種別',
        'market': '市場区分',
    }
    cols = {}
    for key, label in want.items():
        for i, c in enumerate(header):
            if label in norm(c):
                cols[key] = i
                break
    for req in ('date', 'code', 'name', 'kind'):
        if req not in cols:
            raise ValueError('見出しが見つかりません: %s / 見出し行=%r' % (want[req], [norm(c) for c in header]))
    return cols


def parse_workbook(content):
    """xlsxのバイト列 -> (items, as_of(date|None), rows_skipped)"""
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    header_idx = None
    as_of = None
    for i, row in enumerate(rows[:15]):
        cells = [norm(c) for c in row]
        for c in cells:
            m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日\s*現在', c)
            if m:
                as_of = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if any('決算発表予定日' in c for c in cells) and any('コード' in c for c in cells):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError('見出し行が見つかりません')
    cols = find_columns(rows[header_idx])

    def cell(row, key):
        i = cols.get(key)
        return norm(row[i]) if i is not None and i < len(row) else ''

    items, skipped, n_rows = [], [], 0
    for row in rows[header_idx + 1:]:
        if not any(norm(c) for c in row):
            continue
        n_rows += 1
        d = to_date(row[cols['date']])
        code = cell(row, 'code')
        raw_date = norm(row[cols['date']])
        # 実物では、発表日が決まっていない会社は日付欄が「未定_Undecided」になっている(2026-10-07確認)。
        undecided = d is None and ('未定' in raw_date or 'Undecided' in raw_date)
        if not code or (d is None and not undecided):
            skipped.append([norm(c) for c in row][:8])  # 末尾の注記行など
            continue
        fy = to_date(row[cols['fy_end']]) if 'fy_end' in cols else None
        item = {
            'code': code,
            'name': cell(row, 'name'),
            'name_en': cell(row, 'name_en'),
            'date': d.isoformat() if d else '',
            'kind': cell(row, 'kind'),
            'fy_end': fy.isoformat() if fy else '',
            'industry': cell(row, 'industry'),
            'market': cell(row, 'market'),
        }
        if undecided:
            item['undecided'] = True
        items.append(item)
    return items, as_of, skipped, n_rows


def main():
    r = requests.get(PAGE, headers=UA, timeout=60)
    r.raise_for_status()
    r.encoding = 'utf-8'
    html = r.text
    m = re.search(r'(\d{4}/\d{1,2}/\d{1,2})\s*更新', html)
    page_updated = m.group(1) if m else ''
    hrefs = re.findall(r'href="([^"]+\.xlsx?)"', html, flags=re.I)
    hrefs = [h for h in dict.fromkeys(hrefs) if 'kessan' in h.lower()]
    if not hrefs:
        raise SystemExit('決算発表予定日のExcelへのリンクが見つかりません')

    files, merged, diag = [], {}, []
    for href in hrefs:
        url = href if href.startswith('http') else BASE + href
        resp = requests.get(url, headers=UA, timeout=120)
        resp.raise_for_status()
        items, as_of, skipped, n_rows = parse_workbook(resp.content)
        dups, dup_samples = 0, []
        for it in items:
            key = (it['code'], it['date'], it['kind'])
            if key in merged:
                dups += 1
                if len(dup_samples) < 10:
                    dup_samples.append(key)
            merged[key] = it
        print('FILE', url, 'rows', len(items), 'skipped', len(skipped), 'as_of', as_of)
        files.append({'url': url, 'as_of': as_of.isoformat() if as_of else '', 'rows': len(items)})
        n_und = sum(1 for it in items if it.get('undecided'))
        diag.append('FILE %s as_of=%s data_rows=%d parsed=%d (うち日付未定=%d) skipped=%d dups=%d' % (
            url.split('/')[-1], as_of, n_rows, len(items), n_und, len(skipped), dups))
        for s in skipped[:25]:
            diag.append('  SKIPPED %r' % (s,))
        for s in dup_samples:
            diag.append('  DUP %r' % (s,))
    os.makedirs('data', exist_ok=True)
    with open(os.path.join('data', 'earnings_jp_check.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(diag) + '\n')

    items = sorted(merged.values(), key=lambda x: (x['date'] or '9999-99-99', x['code']))
    if len(items) < MIN_ITEMS:
        raise SystemExit('件数が少なすぎるため書き込みません: %d' % len(items))
    years = {int(i['date'][:4]) for i in items if i['date']}
    if not years or min(years) < 2020 or max(years) > 2035:
        raise SystemExit('日付が想定範囲外です: %s' % sorted(years))

    doc = {
        'source': '日本取引所グループ(JPX) 決算発表予定日一覧',
        'source_url': PAGE,
        'grade': 'A',
        'page_updated': page_updated,
        'files': files,
        'count': len(items),
        'items': items,
    }
    old = None
    if os.path.exists(OUT):
        with open(OUT, encoding='utf-8') as f:
            old = json.load(f)
    if old == doc:
        print('変更なし: 書き込みません')
        return
    os.makedirs('data', exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, separators=(',', ':'))
    print('書き込み', OUT, len(items), '件 / page_updated', page_updated)


if __name__ == '__main__':
    sys.exit(main())
