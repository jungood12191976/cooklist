#!/usr/bin/env python3
"""米国の決算発表予定日を Nasdaq の決算カレンダーAPI(日付ごと)から取り、連鎖の起爆剤になる銘柄だけを
data/earnings_us.json に書く。GitHub Actions から毎日実行(.github/workflows/earnings-us.yml)。

2026-10-07にActions上で実物を確認: https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD は
data.rows に [lastYearRptDt,lastYearEPS,time,symbol,name,marketCap,fiscalQuarterEnding,epsForecast,noOfEsts] を返す。
time は time-pre-market / time-after-hours / time-not-supplied。日付は米国の日付。
※「会社が確定発表した日」か「推定」かはAPIから区別できないため、画面では出典=Nasdaq(推定を含む)と表示する。
"""
import datetime, json, os, sys, time
import requests

H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
     'Accept': 'application/json, text/plain, */*', 'Origin': 'https://www.nasdaq.com', 'Referer': 'https://www.nasdaq.com/'}
OUT = os.path.join('data', 'earnings_us.json')
BACK, AHEAD = 3, 75
# 起爆剤候補(日本株へ波及しうる米国側)。絞らず広めに持つ(キング方針)。使いながら画面側で減らす。
SYMS = ['MU', 'NVDA', 'TSM', 'AVGO', 'AMAT', 'LRCX', 'KLAC', 'AMD', 'ASML', 'QCOM', 'INTC', 'TXN', 'ADI', 'ON', 'NXPI',
        'MCHP', 'WDC', 'STX', 'SNDK', 'ARM', 'SMCI', 'DELL', 'CSCO', 'ANET', 'VRT', 'MSFT', 'GOOGL', 'AMZN', 'META',
        'ORCL', 'AAPL', 'TSLA', 'MRVL', 'COHR', 'GLW', 'TER']


def get(url):
    for k in range(4):
        try:
            r = requests.get(url, headers=H, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 503):
                time.sleep(4 * (k + 1))
                continue
            return None
        except (requests.RequestException, ValueError):
            time.sleep(3 * (k + 1))
    return None


def main():
    today = datetime.datetime.now(datetime.timezone.utc).date()
    items, n_days, n_fail = [], 0, 0
    for off in range(-BACK, AHEAD + 1):
        d = today + datetime.timedelta(days=off)
        if d.weekday() >= 5:
            continue
        j = get('https://api.nasdaq.com/api/calendar/earnings?date=' + d.isoformat())
        time.sleep(0.5)
        if j is None:
            n_fail += 1
            continue
        n_days += 1
        for row in ((j.get('data') or {}).get('rows')) or []:
            if row.get('symbol') in SYMS:
                items.append({'symbol': row['symbol'], 'name': row.get('name', ''), 'date': d.isoformat(),
                              'time': row.get('time', ''), 'fq': row.get('fiscalQuarterEnding', ''),
                              'eps_fc': row.get('epsForecast', '')})
    if n_days < 40 or n_fail > 15:
        sys.exit('取得できた日が少なすぎるため書き込みません: days=%d fail=%d' % (n_days, n_fail))
    doc = {'source': 'Nasdaq 決算カレンダーAPI', 'grade': 'B', 'note': '日付は米国の日付。確定/推定の区別はAPIにない。',
           'fetched_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='minutes'),
           'days_ok': n_days, 'items': sorted(items, key=lambda x: (x['date'], x['symbol']))}
    old = None
    if os.path.exists(OUT):
        old = json.load(open(OUT, encoding='utf-8'))
        if {k: v for k, v in old.items() if k != 'fetched_at'} == {k: v for k, v in doc.items() if k != 'fetched_at'}:
            print('変更なし'); return
    os.makedirs('data', exist_ok=True)
    json.dump(doc, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('書き込み', len(items), '件 days_ok', n_days, 'fail', n_fail)


if __name__ == '__main__':
    main()
