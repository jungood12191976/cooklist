#!/usr/bin/env python3
"""調査用(手動)：Polymarketの「株に関係するテーマ」の市場が、日本時間の何時台によく動くかを測る。

- 市場の選び方：scripts/fetch_polymarket.py と同じテーマ・キーワードで振り分けた各テーマの上位イベントの市場のうち、
  Yesの値段が 3%〜97% のもの(ほぼ動かない市場は除く)。最大 MAX_MARKETS 本。
- データ：data-api.polymarket.com/v2/prices-history (1時間ごと・過去14日)。実レスポンスは data/polymarket_study_raw.txt で確認済みの形。
- 指標：隣り合う1時間の値段の変化の絶対値(ポイント)を、日本時間の時間帯ごとに平均する。
- 書き出し：data/polymarket_hours_study.json と data/polymarket_hours_study.txt
"""
import json
import re
import sys
import time
import datetime
from collections import defaultdict

import requests

sys.path.insert(0, "scripts")
import fetch_polymarket as fp  # テーマ定義(THEMES)を共有する

UA = fp.UA
HIST = "https://data-api.polymarket.com/v2/prices-history"
DAYS = 14
MAX_MARKETS = 40
JST = datetime.timezone(datetime.timedelta(hours=9))


def get_events():
    out = []
    for p in range(5):
        r = requests.get(fp.API, params={"limit": 100, "offset": p * 100, "active": "true", "closed": "false",
                                         "order": "volume24hr", "ascending": "false"}, headers=UA, timeout=40)
        r.raise_for_status()
        arr = r.json()
        if not arr:
            break
        out.extend(arr)
        time.sleep(0.5)
    return out


def pick_targets(events):
    targets, seen = [], set()
    for key, label, pat in fp.THEMES:
        rx = re.compile(pat, re.I)
        n_ev = 0
        for ev in events:
            if not rx.search(fp.event_text(ev)):
                continue
            n_ev += 1
            if n_ev > 4:
                break
            for m in ev.get("markets") or []:
                if m.get("closed"):
                    continue
                outs, prices = fp.jparse(m.get("outcomes")), fp.jparse(m.get("outcomePrices"))
                toks = fp.jparse(m.get("clobTokenIds"))
                if not outs or not prices or not toks:
                    continue
                yes = None
                tok = None
                for o, pr, t in zip(outs, prices, toks):
                    if str(o).lower() == "yes":
                        yes, tok = fp.num(pr), t
                if yes is None or not (0.03 <= yes <= 0.97) or tok in seen:
                    continue
                seen.add(tok)
                targets.append({"theme": label, "event": ev.get("title"), "q": m.get("question"),
                                "yes_now": yes, "token": tok, "vol24": fp.num(m.get("volume24hr")) or 0.0})
    targets.sort(key=lambda x: -x["vol24"])
    return targets[:MAX_MARKETS]


def history(tok, start, end):
    for attempt in range(3):
        try:
            r = requests.get(HIST, params={"token_id": tok, "start": start, "end": end, "bucket_seconds": 3600},
                             headers=UA, timeout=40)
            if r.status_code == 200:
                return r.json().get("data") or []
        except Exception:
            pass
        time.sleep(2)
    return None


def main():
    events = get_events()
    targets = pick_targets(events)
    end = int(time.time())
    start = end - DAYS * 86400
    by_hour = defaultdict(list)      # JST時 -> [絶対変化(pt)]
    by_hour_signed = defaultdict(list)
    used, failed = [], []
    for t in targets:
        data = history(t["token"], start, end)
        time.sleep(0.4)
        if not data or len(data) < 24:
            failed.append(t["q"])
            continue
        pts = sorted(data, key=lambda d: d["timestamp"])
        n = 0
        for a, b in zip(pts, pts[1:]):
            gap = b["timestamp"] - a["timestamp"]
            if gap != 3600:        # 欠けた時間をまたぐ変化は使わない
                continue
            h = datetime.datetime.fromtimestamp(b["timestamp"], JST).hour   # その時間の終わり(b)の時刻の「時」
            chg = (b["price"] - a["price"]) * 100
            by_hour[h].append(abs(chg))
            by_hour_signed[h].append(chg)
            n += 1
        used.append({"theme": t["theme"], "q": t["q"], "event": t["event"], "yes_now": t["yes_now"], "points": n})
    rows = []
    total = sum(sum(v) for v in by_hour.values()) or 1.0
    for h in range(24):
        v = by_hour.get(h, [])
        rows.append({"hour_jst": h, "samples": len(v),
                     "mean_abs_move_pt": round(sum(v) / len(v), 4) if v else None,
                     "share_of_total_move": round(sum(v) / total, 4)})
    doc = {"generated_at": datetime.datetime.now(JST).replace(microsecond=0).isoformat(),
           "days": DAYS, "markets_used": len(used), "markets_failed": len(failed),
           "note": "hour_jst は『その1時間の終わりの時刻の時(日本時間)』。例: 9 = 8:00→9:00 の変化",
           "hours": rows, "markets": used, "failed": failed}
    with open("data/polymarket_hours_study.json", "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    lines = [f"generated_at={doc['generated_at']} days={DAYS} markets_used={len(used)} failed={len(failed)}",
             "hour_jst(終わりの時) samples mean_abs_move_pt share"]
    for r in rows:
        lines.append(f"{r['hour_jst']:02d} {r['samples']:5d} {r['mean_abs_move_pt']} {r['share_of_total_move']}")
    lines.append("--- markets")
    for u in used:
        lines.append(f"[{u['theme']}] {u['q']} (yes_now={u['yes_now']}, points={u['points']})")
    with open("data/polymarket_hours_study.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[:40]))


if __name__ == "__main__":
    main()
