#!/usr/bin/env python3
"""JPX 投資部門別売買状況(週次xlsx)から、海外投資家・個人・信託銀行『以外』の投資家区分の差引(買い−売り)を
東証3市場(プライム+スタンダード+グロース)・現物で合計し、data/investor_flows_others.json に保存する。

列(2026-10-29にxlsxの実物の見出し行で確認。data/investor_flows_headers.txt に実物の見出しを残してある):
  証券会社の自己売買 = F(自己・現金 差引) + J(自己・信用 差引)
  証券会社(委託)     = AD    投資信託 = AH    事業法人 = AL    その他法人等 = AP
  生保・損保 = AT    都銀・地銀等 = AX    その他金融機関 = BF
  (海外 = V+Z、個人 = N+R、信託銀行 = BB は fetch_investor_flows.py が扱う。ここでは照合のためだけに読む)
単位は千円 → 億円(÷100,000)に四捨五入。JPXの一覧にある週(直近5週ほど)を毎回上書きし、一覧から消えた古い週は残す。
照合: 14区分の差引の合計(ほぼ0になるはず)を data/investor_flows_others_check.txt に書く。
"""
import io, json, re, sys, datetime
import requests
from openpyxl import load_workbook

BASE = "https://www.jpx.co.jp"
IDX = BASE + "/markets/statistics-equities/investor-type/index.html"
UA = {"User-Agent": "Mozilla/5.0 (king-the-quest personal app)"}
JSON_PATH = "data/investor_flows_others.json"
CHECK_PATH = "data/investor_flows_others_check.txt"
MARKETS = ("プライム", "スタンダード", "グロース")
OTHERS = {  # キー: 差引の列
    "proprietary": ("F", "J"), "brokerage": ("AD",), "invtrust": ("AH",), "bizcorp": ("AL",), "othercorp": ("AP",),
    "lifenl": ("AT",), "citybank": ("AX",), "otherfin": ("BF",),
}
KNOWN = {"foreign": ("V", "Z"), "individual": ("N", "R"), "trustbank": ("BB",)}   # 照合用
BAL_COLS = ["F", "J", "N", "R", "V", "Z", "AD", "AH", "AL", "AP", "AT", "AX", "BB", "BF"]
HEADERS = {  # 列: (見出しの行, その行に含まれるはずの語)
    "D3": "自己", "AB6": "証券会社", "AF6": "投資信託", "AJ6": "事業法人", "AN6": "その他法人等", "AR6": "生保・損保", "AV6": "都銀・地銀等",
    "AZ6": "信託銀行", "BD6": "その他金融機関", "D5": "現金", "H5": "信用", "T4": "海外投資家", "L4": "個人",
}


def num(ws, letter, row):
    v = ws[f"{letter}{row}"].value
    if not isinstance(v, (int, float)):
        raise ValueError(f"{letter}{row} が数値ではありません: {v!r}")
    return v


def parse(content):
    ws = load_workbook(io.BytesIO(content), data_only=True).worksheets[0]
    for cell, word in HEADERS.items():
        if word not in str(ws[cell].value or ""):
            raise ValueError(f"{cell} の見出しが想定と違います: {ws[cell].value!r}")
    for L in BAL_COLS:
        if "差引" not in str(ws[f"{L}7"].value or ""):
            raise ValueError(f"列{L}の7行目が「差引」ではありません: {ws[f'{L}7'].value!r}")
    tot = {c: 0.0 for c in BAL_COLS}
    seen, market = [], None
    for r in range(8, ws.max_row + 1):
        b = ws[f"B{r}"].value
        if b:
            market = str(b)
        if "金額" in str(ws[f"C{r}"].value or "") and market and any(m in market for m in MARKETS):
            seen.append(market.split("\n")[0])
            for c in BAL_COLS:
                tot[c] += num(ws, c, r)
    if len(seen) != 3:
        raise ValueError(f"3市場の金額行が見つかりません: {seen}")
    oku = lambda letters: int(round(sum(tot[L] for L in letters) / 100000))
    vals = {k: oku(v) for k, v in OTHERS.items()}
    known = {k: oku(v) for k, v in KNOWN.items()}
    residual = int(round(sum(tot.values()) / 100000))
    return vals, known, residual, seen


def monday(d):
    return d - datetime.timedelta(days=d.weekday())


def main():
    try:
        doc = json.load(open(JSON_PATH, encoding="utf-8"))
    except FileNotFoundError:
        doc = {"unit": "億円", "market": "東証プライム+スタンダード+グロース(現物・差引=買い−売り)", "weeks": []}
    html = requests.get(IDX, headers=UA, timeout=60).text
    links = sorted(set(re.findall(r'href="([^"]*stock_1_w_(\d{8})_(\d{8})\.xlsx)"', html)), key=lambda x: x[1])
    check = [f"実行 {datetime.datetime.utcnow().isoformat()}Z / 一覧のxlsx {len(links)}件"]
    byfrom = {w["from"]: w for w in doc["weeks"]}
    flows = {w["from"]: w for w in json.load(open("data/investor_flows.json", encoding="utf-8"))["weeks"]}
    for href, s, e in links:
        sd = datetime.datetime.strptime(s, "%Y%m%d").date(); ed = datetime.datetime.strptime(e, "%Y%m%d").date()
        mon = monday(sd).isoformat()
        res = requests.get(BASE + href, headers=UA, timeout=60); res.raise_for_status()
        vals, known, residual, seen = parse(res.content)
        byfrom[mon] = {"from": mon, "to": max(ed, monday(sd)).isoformat(), **vals}
        cmp = ""
        if mon in flows:
            cmp = " / 既存3者との差: " + ", ".join(f"{k}={known[k] - flows[mon][k]:+d}" for k in KNOWN)
        check.append(f"{s}〜{e}: {vals} / 全14区分の合計={residual:+d}億円 / 市場={seen}{cmp}")
    doc["weeks"] = sorted(byfrom.values(), key=lambda w: w["from"])
    doc["source"] = "JPX 投資部門別売買状況(週次) " + IDX
    doc["note"] = "海外投資家・個人・信託銀行以外の区分。JPXの一覧にある直近の週(2026/9/14の週〜)から取り込み、それより前の週は未取得。scripts/fetch_investor_others.py が毎週更新。"
    doc["updated"] = datetime.date.today().isoformat()
    json.dump(doc, open(JSON_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(CHECK_PATH, "w", encoding="utf-8").write("\n".join(check) + "\n")
    print("\n".join(check))


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        open(CHECK_PATH, "w", encoding="utf-8").write(f"失敗 {datetime.datetime.utcnow().isoformat()}Z: {ex!r}\n")
        print("失敗", repr(ex)); sys.exit(1)
