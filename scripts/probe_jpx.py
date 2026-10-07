#!/usr/bin/env python3
"""JPX 決算発表予定日Excelの中身を確認するだけの確認用スクリプト。
アプリの画面・保存データには一切触らない。結果は data/jpx_probe.txt に書く。
"""
import datetime
import io
import os
import re
import traceback

import openpyxl
import requests

BASE = 'https://www.jpx.co.jp'
PAGE = BASE + '/listing/event-schedules/financial-announcement/index.html'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; king-the-quest-earnings/1.0)'}
# 含まれているかを見るだけの例(監視銘柄の選定ではない)
TARGETS = ('6857', '8035', '285A', '5803', '6963')

out = []


def p(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    out.append(s)


def norm(c):
    if c is None:
        return ''
    if isinstance(c, float) and c.is_integer():
        return str(int(c))
    return str(c).strip()


def main():
    p('run_at_utc', datetime.datetime.now(datetime.timezone.utc).isoformat())
    r = requests.get(PAGE, headers=UA, timeout=60)
    p('PAGE status', r.status_code, 'bytes', len(r.content))
    r.encoding = 'utf-8'
    html = r.text
    for m in re.finditer(r'[^<>\n]{0,40}(更新|時点)[^<>\n]{0,60}', html):
        p('PAGE_HINT', m.group(0).strip())
        if len(out) > 40:
            break
    links = re.findall(r'<a[^>]+href="([^"]+\.xlsx?)"[^>]*>(.*?)</a>', html, flags=re.S | re.I)
    p('LINKS', len(links))
    for href, label in links:
        label = re.sub(r'<[^>]+>', '', label).strip()
        url = href if href.startswith('http') else BASE + href
        p('---- FILE', url, '|', label)
        resp = requests.get(url, headers=UA, timeout=120)
        p('download status', resp.status_code, 'bytes', len(resp.content))
        try:
            wb = openpyxl.load_workbook(io.BytesIO(resp.content), data_only=True)
        except Exception as e:  # noqa: BLE001
            p('openpyxl error', repr(e)[:300])
            continue
        for ws in wb.worksheets:
            p('SHEET', repr(ws.title), 'max_row', ws.max_row, 'max_col', ws.max_column)
            rows = list(ws.iter_rows(values_only=True))
            nonempty = [r_ for r_ in rows if any(norm(c) for c in r_)]
            p('nonempty_rows', len(nonempty))
            for i, row in enumerate(rows[:15]):
                p('ROW', i, [norm(c) for c in row][:12])
            hits = 0
            for i, row in enumerate(rows):
                cells = [norm(c) for c in row]
                if any(c in TARGETS for c in cells):
                    p('HIT row', i, cells[:12])
                    hits += 1
                    if hits >= 12:
                        break
            p('target_hits', hits)


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        p('ERROR', traceback.format_exc()[-1500:])
    os.makedirs('data', exist_ok=True)
    with open('data/jpx_probe.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n')
