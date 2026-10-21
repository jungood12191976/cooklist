#!/usr/bin/env python3
"""調査用(1回きり)：Polymarketの価格履歴APIの実レスポンスを data/polymarket_study_raw.txt に保存する。
画面・本体のデータには影響しない。時間帯ごとの動きを測る前に、実物の形を確認するためのもの。"""
import json
import time
import requests

UA = {"User-Agent": "king-the-quest/1.0 (personal app; contact: github.com/jungood12191976/cooklist)"}
out = []

r = requests.get("https://gamma-api.polymarket.com/events",
                 params={"limit": 100, "active": "true", "closed": "false", "order": "volume24hr", "ascending": "false"},
                 headers=UA, timeout=40)
out.append(f"gamma status={r.status_code}")
evs = r.json()
fed = [e for e in evs if "fed" in str(e.get("title", "")).lower()]
out.append(f"events={len(evs)} fed_events={len(fed)}")
ev = fed[0] if fed else evs[0]
out.append("event title=" + str(ev.get("title")))
m = (ev.get("markets") or [])[0]
out.append("market keys=" + ",".join(sorted(m.keys())))
out.append("clobTokenIds raw=" + repr(m.get("clobTokenIds")))
out.append("outcomes raw=" + repr(m.get("outcomes")))
toks = m.get("clobTokenIds")
if isinstance(toks, str):
    toks = json.loads(toks)
tok = toks[0]

end = int(time.time())
start = end - 14 * 86400
for label, url, params in [
    ("data-api v2", "https://data-api.polymarket.com/v2/prices-history",
     {"token_id": tok, "start": start, "end": end, "bucket_seconds": 3600}),
    ("clob legacy", "https://clob.polymarket.com/prices-history",
     {"market": tok, "startTs": start, "endTs": end, "fidelity": 60}),
]:
    try:
        rr = requests.get(url, params=params, headers=UA, timeout=40)
        out.append(f"--- {label}: HTTP {rr.status_code}")
        out.append(rr.text[:1500])
    except Exception as e:
        out.append(f"--- {label}: {type(e).__name__}: {e}")

with open("data/polymarket_study_raw.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print("\n".join(out)[:3000])
