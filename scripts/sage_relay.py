"""賢者のイシ(クロ)の中継：アプリが ntfy に送った質問を拾い、クロのルーティンを API トリガーで起こす。
GitHub Actions から5分ごとに動く。ルーティンのURLとトークンは GitHub の Secrets(SAGEURL / SAGETOKEN。2026-10-14 キングの入力でアンダーバーが通らなかったため記号なしの名前に)。
公式: https://code.claude.com/docs/en/routines (API trigger / /fire / text フィールド / beta ヘッダー)
"""
import json, os, re, sys, pathlib, urllib.request

TOPIC_URL = 'https://ntfy.sh/ktq-sage-a9381535c5b4e768376e'
SEEN = pathlib.Path('.sage_seen/ids.txt')
MAX_FIRE = 5  # 1回の実行で起こす上限(ルーティンは1時間30回まで)

def main():
    SEEN.parent.mkdir(exist_ok=True)
    if not SEEN.exists(): SEEN.write_text('')  # キャッシュ保存が空振りで失敗しないように
    url, token = os.environ.get('SAGE_ROUTINE_URL', '').strip(), os.environ.get('SAGE_ROUTINE_TOKEN', '').strip()
    if not url or not token:
        print('Secrets(SAGE_ROUTINE_URL / SAGE_ROUTINE_TOKEN)が未設定のため何もしません'); return
    seen = set(SEEN.read_text().split()) if SEEN.exists() else set()
    with urllib.request.urlopen(TOPIC_URL + '/json?poll=1&since=40m', timeout=30) as r:
        lines = r.read().decode('utf-8', 'replace').splitlines()
    fired = 0
    for line in lines:
        try: ev = json.loads(line)
        except Exception: continue
        if ev.get('event') != 'message': continue
        mid = str(ev.get('id', ''))
        if not mid or mid in seen: continue
        try: body = json.loads(ev.get('message', ''))
        except Exception: seen.add(mid); continue
        qid, q = str(body.get('qid', '')), str(body.get('q', '')).strip()
        if not re.fullmatch(r'[0-9a-z]{6,24}', qid) or not q or len(q) > 1000:
            seen.add(mid); continue
        if fired >= MAX_FIRE: break
        text = json.dumps({'qid': qid, 'q': q, 'asked_at': body.get('t', '')}, ensure_ascii=False)
        req = urllib.request.Request(url, method='POST', data=json.dumps({'text': text}).encode('utf-8'), headers={
            'Authorization': 'Bearer ' + token,
            'anthropic-beta': 'experimental-cc-routine-2026-04-01',
            'anthropic-version': '2023-06-01',
            'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                print('起こしました', qid, r.status, json.loads(r.read()).get('claude_code_session_url', ''))
            seen.add(mid); fired += 1
        except urllib.error.HTTPError as e:
            print('起こせませんでした', qid, e.code, e.read()[:300])
            if e.code in (400, 401, 403, 404): seen.add(mid)  # やり直しても同じ
    SEEN.parent.mkdir(exist_ok=True)
    SEEN.write_text('\n'.join(sorted(seen)[-500:]))
    print('完了: 起こした数', fired)

if __name__ == '__main__':
    main()
