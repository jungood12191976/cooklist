#!/usr/bin/env python3
"""毎週の取り込み(data/investor_flows.json)に新しく入った週を、過去分(data/investor_flows_history.json)へ追記する。

追記するのは過去分にまだ無い週だけ。既にある週は書き換えない(過去分は backfill_investor_flows.py がJPX公式から作ったもの)。
追記する週は新形式(era=new)の値。毎週の取り込みもJPX公式xlsxの3市場の差引なので、同じ計算。
"""
import datetime, json, sys

WEEKLY = "data/investor_flows.json"
HIST = "data/investor_flows_history.json"
KEYS = ("foreign", "individual", "trustbank")


def main():
    cur = json.load(open(WEEKLY, encoding="utf-8"))
    hist = json.load(open(HIST, encoding="utf-8"))
    have = {w["from"] for w in hist["weeks"]}
    last = max(have)
    added = []
    for w in sorted(cur["weeks"], key=lambda x: x["from"]):
        if w["from"] in have or w["from"] < last:
            continue  # 既にある週、または過去分より古い週は触らない
        hist["weeks"].append({"from": w["from"], "to": w["to"], **{k: w[k] for k in KEYS}, "era": "new"})
        added.append(w["from"])
    if added:
        hist["weeks"].sort(key=lambda x: x["from"])
        hist["updated"] = datetime.date.today().isoformat()
        json.dump(hist, open(HIST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"過去分へ追記 {len(added)}週 {added}")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:  # noqa
        print("失敗", repr(ex))
        sys.exit(1)
