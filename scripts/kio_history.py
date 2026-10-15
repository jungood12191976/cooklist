# 決算相場の折れ線(時のへや)用の出来事の履歴。data/earnings_us.json と earnings_jp.json は古い日付が消えるので、
# 消さずに data/kio_events.json へ足していく。同じ(種類,銘柄,日付)は新しい値で上書き(予想→実績に変わるため)。
# 2026-10-15 キング承認: キオクシアだけ → 連鎖(アプリの W2_CHAINS)に入っている日本株49銘柄と、全連鎖の米国の起爆剤に広げた。
# 銘柄の一覧は index.html の W2_CHAINS から読む(二重管理しない)。読めなかった時は従来のキオクシア＋メモリー連鎖だけ。
# 仮置き(去年の日付・est)は履歴に入れない。
import json, os, re

OUT = os.path.join('data', 'kio_events.json')


def load(p):
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def chain_lists():
    try:
        s = open('index.html', encoding='utf-8').read()
        i = s.index('const W2_CHAINS = [')
        blk = s[i:s.index('];', i)]
        jp, us = [], []
        for key, arr in re.findall(r"\b(w1|w2|trig):\[([^\]]*)\]", blk):
            for c in re.findall(r"'([0-9A-Z]+)'", arr):
                tgt = us if key == 'trig' else jp
                if c not in tgt:
                    tgt.append(c)
        if len(jp) >= 10 and len(us) >= 10:
            return jp, us
    except Exception:
        pass
    return ['285A'], ['MU', 'WDC', 'STX', 'SNDK']


def main():
    jp_codes, us_syms = chain_lists()
    old = load(OUT) or {'items': []}
    cur = {(x['kind'], x['key'], x['date']): x for x in old.get('items', [])}
    us = load(os.path.join('data', 'earnings_us.json')) or {}
    for x in us.get('items', []):
        if x.get('symbol') in us_syms and x.get('date') and not x.get('est'):
            cur[('us', x['symbol'], x['date'])] = {'kind': 'us', 'key': x['symbol'], 'date': x['date'], 'name': x.get('name', ''),
                'time': x.get('time', ''), 'eps_fc': x.get('eps_fc'), 'eps_cons': x.get('eps_cons'), 'eps_act': x.get('eps_act'), 'surprise': x.get('surprise')}
    jp = load(os.path.join('data', 'earnings_jp.json')) or {}
    for x in jp.get('items', []):
        if x.get('code') in jp_codes and x.get('date'):
            cur[('jp', x['code'], x['date'])] = {'kind': 'jp', 'key': x['code'], 'date': x['date'], 'name': x.get('name', ''), 'fq': x.get('kind', '')}
    items = sorted(cur.values(), key=lambda r: (r['date'], r['key']))
    if items == old.get('items'):
        print('変更なし'); return
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({'note': '追記専用の履歴。出典は earnings_us.json(Nasdaq・確認レベルB) と earnings_jp.json(JPX公式・A)', 'items': items}, f, ensure_ascii=False, separators=(',', ':'))
    print('更新', len(items), '件', 'jp', len(jp_codes), 'us', len(us_syms))


main()
