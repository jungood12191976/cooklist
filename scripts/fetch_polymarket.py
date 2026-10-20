#!/usr/bin/env python3
"""Polymarket(公開API)から、株に関係するテーマの市場を集めて data/polymarket.json に保存する。

- 取得元: https://gamma-api.polymarket.com/events (認証不要の公開API)
- 24時間の取引量が多い順に最大500イベントを読み、テーマごとのキーワードで機械的に振り分ける。
- テーマとキーワードは「最初は絞らず広く」の方針で広めに置いてある(使いながら消す)。
- 確率は予測市場の値段であり、事実ではない。
"""
import json
import re
import sys
import time
import datetime

import requests

API = "https://gamma-api.polymarket.com/events"
UA = {"User-Agent": "king-the-quest/1.0 (personal app; contact: github.com/jungood12191976/cooklist)"}
PAGES = 5          # 100件 x 5ページ = 最大500イベント(取引量の多い順)
PER_THEME_EVENTS = 6
PER_EVENT_MARKETS = 3

# (key, 画面の見出し, 正規表現(タイトル＋タグ名に当てる))
THEMES = [
    ("rates",     "金利・FRB",        r"\b(fed|fomc|interest rates?|rate (cut|hike)s?|powell|warsh|treasury|yields?)\b"),
    ("oil_iran",  "イラン・原油",     r"\b(iran|oil|crude|wti|brent|hormuz|opec)\b"),
    ("trump",     "トランプ関連",     r"\b(trump)\b"),
    ("tariff",    "関税・貿易",       r"\b(tariffs?|trade deal|trade war)\b"),
    ("recession", "景気後退・景気",   r"\b(recession|gdp|unemployment|jobs report|payrolls?|layoffs?)\b"),
    ("inflation", "インフレ",         r"\b(inflation|cpi|pce)\b"),
    ("stocks",    "株価指数・相場",   r"\b(s&p|nasdaq|dow jones|stock market|vix|market crash)\b"),
    ("ai_chips",  "AI・半導体",       r"\b(nvidia|openai|anthropic|semiconductors?|chips?|tsmc|micron|ai bubble)\b"),
    ("fx",        "為替(ドル・円)",   r"\b(yen|usd/jpy|dollar index|dxy|boj|bank of japan)\b"),
]


def jparse(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return None
    return v


def num(v):
    try:
        return float(v)
    except Exception:
        return None


def fetch_events():
    out, notes = [], []
    for p in range(PAGES):
        params = {"limit": 100, "offset": p * 100, "active": "true", "closed": "false",
                  "order": "volume24hr", "ascending": "false"}
        r = None
        for attempt in range(3):
            try:
                r = requests.get(API, params=params, headers=UA, timeout=40)
                if r.status_code == 200:
                    break
                notes.append(f"page{p} attempt{attempt+1}: HTTP {r.status_code}")
            except Exception as e:
                notes.append(f"page{p} attempt{attempt+1}: {type(e).__name__}: {e}")
            time.sleep(3)
        if r is None or r.status_code != 200:
            break
        arr = r.json()
        if not isinstance(arr, list) or not arr:
            break
        out.extend(arr)
        time.sleep(0.6)
    return out, notes


def event_text(ev):
    tags = " ".join(str(t.get("label", "")) + " " + str(t.get("slug", "")) for t in (ev.get("tags") or []))
    return (str(ev.get("title", "")) + " " + tags).lower()


def pick_markets(ev):
    ms = []
    for m in ev.get("markets") or []:
        if m.get("closed"):
            continue
        outs, prices = jparse(m.get("outcomes")), jparse(m.get("outcomePrices"))
        if not outs or not prices or len(outs) != len(prices):
            continue
        yes = None
        for o, pr in zip(outs, prices):
            if str(o).lower() == "yes":
                yes = num(pr)
        if yes is None:
            continue
        ms.append({
            "q": m.get("question"),
            "label": m.get("groupItemTitle") or "",
            "yes": yes,
            "d1": num(m.get("oneDayPriceChange")),
            "vol24": num(m.get("volume24hr")) or 0.0,
            "end": m.get("endDate"),
        })
    ms.sort(key=lambda x: -x["vol24"])
    return ms[:PER_EVENT_MARKETS]


def main():
    events, notes = fetch_events()
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst).replace(microsecond=0).isoformat()
    themes_out, check = [], []
    check.append(f"fetched_at={now}")
    check.append(f"events_fetched={len(events)}")
    for n in notes:
        check.append("note: " + n)
    if events:
        check.append("event_keys=" + ",".join(sorted(events[0].keys())[:60]))
    for key, label, pat in THEMES:
        rx = re.compile(pat, re.I)
        evs = []
        for ev in events:
            if not rx.search(event_text(ev)):
                continue
            ms = pick_markets(ev)
            if not ms:
                continue
            evs.append({
                "title": ev.get("title"),
                "slug": ev.get("slug"),
                "url": "https://polymarket.com/event/" + str(ev.get("slug")),
                "end": ev.get("endDate"),
                "vol24": num(ev.get("volume24hr")) or 0.0,
                "markets": ms,
            })
            if len(evs) >= PER_THEME_EVENTS:
                break
        themes_out.append({"key": key, "label": label, "events": evs})
        check.append(f"theme {key}: {len(evs)} events" + ("".join("\n    - " + str(e["title"]) for e in evs)))
    doc = {
        "fetched_at": now,
        "source": "Polymarket 公開API (gamma-api.polymarket.com/events・取引量の多い順500件から振り分け)",
        "grade": "A",
        "note": "確率は予測市場の値段で、事実の確率ではありません。キーワードでの機械的な振り分けです。",
        "themes": themes_out,
    }
    if not events:
        # 取得に失敗したときは、前回のデータを壊さないために書き込まずに終わる(チェックだけ残す)
        check.append("取得0件のため data/polymarket.json は更新しません")
        open("data/polymarket_check.txt", "w", encoding="utf-8").write("\n".join(check) + "\n")
        print("\n".join(check))
        sys.exit(0)
    with open("data/polymarket.json", "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    open("data/polymarket_check.txt", "w", encoding="utf-8").write("\n".join(check) + "\n")
    print("\n".join(check))


if __name__ == "__main__":
    main()
