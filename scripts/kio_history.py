# キオクシア決算相場(時のへや)用の出来事の履歴。data/earnings_us.json と earnings_jp.json は古い日付が消えるので、
# キオクシア(285A)自身の決算日と、メモリー連鎖(アプリの W2_CHAINS の mem.trig と同じ MU/WDC/STX/SNDK)の米国決算を、
# 消さずに data/kio_events.json へ足していく。同じ(銘柄,日付)は新しい値で上書き(予想→実績に変わるため)。
import json, os
MEM = ['MU', 'WDC', 'STX', 'SNDK']
OUT = os.path.join('data', 'kio_events.json')
def load(p):
    try:
        with open(p, encoding='utf-8') as f: return json.load(f)
    except Exception: return None
def main():
    old = load(OUT) or {'items': []}
    cur = {(x['kind'], x['key'], x['date']): x for x in old.get('items', [])}
    us = load(os.path.join('data', 'earnings_us.json')) or {}
    for x in us.get('items', []):
        if x.get('symbol') in MEM and x.get('date'):
            cur[('us', x['symbol'], x['date'])] = {'kind': 'us', 'key': x['symbol'], 'date': x['date'], 'name': x.get('name', ''),
                'time': x.get('time', ''), 'eps_fc': x.get('eps_fc'), 'eps_cons': x.get('eps_cons'), 'eps_act': x.get('eps_act'), 'surprise': x.get('surprise')}
    jp = load(os.path.join('data', 'earnings_jp.json')) or {}
    for x in jp.get('items', []):
        if x.get('code') == '285A' and x.get('date'):
            cur[('jp', '285A', x['date'])] = {'kind': 'jp', 'key': '285A', 'date': x['date'], 'name': x.get('name', ''), 'fq': x.get('kind', '')}
    items = sorted(cur.values(), key=lambda r: (r['date'], r['key']))
    if items == old.get('items'): print('変更なし'); return
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({'note': '追記専用の履歴。出典は earnings_us.json(Nasdaq・確認レベルB) と earnings_jp.json(JPX公式・A)', 'items': items}, f, ensure_ascii=False, separators=(',', ':'))
    print('更新', len(items), '件')
main()
