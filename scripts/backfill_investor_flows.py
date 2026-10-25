#!/usr/bin/env python3
"""JPX 投資部門別売買状況(週次)の過去分(2016年〜)を取り込み、data/investor_flows_history.json に保存する。

読み方(2026-10-25に2016/2022/2025/2026のxlsの実物で確認):
  旧形式(〜2026/9第2週): 金額ファイル stock_val_1_YYMMNN.xls。市場ごとにシート。
     シート名 = 旧「TSE 1st/2nd/Mothers/JASDAQ」または新「TSE Prime/Standard/Growth」。
     1ファイルに前週(列D〜G)と当週(列H〜K)が並ぶ。使うのは当週(0始まりの列7〜10)だけ。
     行は「個 人」「海外投資家」「信託銀行」の売り行＋次の買い行。差引=買い−売り(千円)。
  新形式(2026/9第3週〜): stock_1_w_YYYYMMDD_YYYYMMDD.xlsx → fetch_investor_flows.parse をそのまま使う。
単位は千円→億円(÷100,000)。市場シート全部を足してから四捨五入。
安全策: 見出し位置・シート構成が想定と違う週、ファイル内の「差引き」欄と計算が合わない週は保存せず、確認ログに書く。
既に保存した週は消さない(再実行しても増えるだけ)。
"""
import datetime, json, os, re, sys, time
import requests, xlrd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_investor_flows as cur  # 新形式xlsxの読み取り(parse)と定数を再利用

BASE, IDX, UA = cur.BASE, cur.IDX, cur.UA
ARCHIVE = BASE + "/markets/statistics-equities/investor-type/00-00-archives-%02d.html"
OUT = "data/investor_flows_history.json"
CHECK = "data/investor_flows_history_check.txt"
CUR_JSON = "data/investor_flows.json"
NEW_MK = {"TSE Prime", "TSE Standard", "TSE Growth"}
OLD_MK = {"TSE 1st", "TSE 2nd", "TSE Mothers", "TSE JASDAQ"}
LABELS = {"individual": "個人", "foreign": "海外投資家", "trustbank": "信託銀行"}
KEYS = ("foreign", "individual", "trustbank")


def get(s, url, tries=3):
    last = None
    for i in range(tries):
        try:
            r = s.get(url, timeout=60)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            time.sleep(0.15)
            return r
        except Exception as ex:  # noqa
            last = ex
            time.sleep(2 * (i + 1))
    raise last


def num(v):
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).replace(",", "").strip()
    if t == "":
        raise ValueError("数値が空欄です")
    return float(t)


def header(sh):
    if sh.ncols < 11 or sh.nrows < 70:
        raise ValueError(f"シートの大きさが想定と違います: {sh.nrows}x{sh.ncols}")
    if "金額" not in str(sh.cell_value(11, 7)) or "差引" not in str(sh.cell_value(11, 10)):
        raise ValueError("見出しの位置が想定と違います")
    m = re.search(r"(\d{4})年(\d{1,2})月第(\d)週", str(sh.cell_value(3, 0)))
    d = re.search(r"(\d{1,2})/(\d{1,2})\s*[～~〜∼-]\s*(\d{1,2})/(\d{1,2})", str(sh.cell_value(10, 7)))
    if not m or not d:
        raise ValueError(f"週の表記を読めません: {sh.cell_value(3, 0)!r} / {sh.cell_value(10, 7)!r}")
    ty, tm = int(m.group(1)), int(m.group(2))
    m1, d1, m2, d2 = (int(x) for x in d.groups())
    s = datetime.date(ty, m1, d1)
    t = datetime.date(ty, tm, 15)
    if (s - t).days > 200:
        s = datetime.date(ty - 1, m1, d1)
    elif (t - s).days > 200:
        s = datetime.date(ty + 1, m1, d1)
    e = datetime.date(s.year, m2, d2)
    if e < s:
        e = datetime.date(s.year + 1, m2, d2)
    if abs((s - t).days) > 45:
        raise ValueError(f"当週の日付がタイトルと離れています: {s} / {sh.cell_value(3, 0)!r}")
    return s, e


def pick(sh):
    res = {}
    for k, lab in LABELS.items():
        hits = [r for r in range(12, sh.nrows - 1)
                if re.sub(r"\s", "", str(sh.cell_value(r, 0))) == lab
                and "売り" in str(sh.cell_value(r, 1)) and "買い" in str(sh.cell_value(r + 1, 1))]
        if len(hits) != 1:
            raise ValueError(f"「{lab}」の行が{len(hits)}件あります")
        r = hits[0]
        diff = num(sh.cell_value(r + 1, 8)) - num(sh.cell_value(r, 8))
        pub = None
        for rr in (r, r + 1):
            if str(sh.cell_value(rr, 10)).strip() != "":
                pub = num(sh.cell_value(rr, 10))
        if pub is not None and abs(pub - diff) > 1:
            raise ValueError(f"「{lab}」の差引きがファイル内の差引き欄と合いません: 計算{diff:.0f} / 欄{pub:.0f}")
        res[k] = diff
    return res


def parse_xls(content):
    wb = xlrd.open_workbook(file_contents=content)
    names = [n for n in wb.sheet_names() if n.startswith("TSE")]
    if set(names) == NEW_MK:
        era = "new"
    elif set(names) == OLD_MK:
        era = "old"
    else:
        raise ValueError(f"市場シートが想定と違います: {wb.sheet_names()}")
    tot = {k: 0.0 for k in KEYS}
    dates = None
    for n in names:
        sh = wb.sheet_by_name(n)
        dt = header(sh)
        if dates is None:
            dates = dt
        elif dates != dt:
            raise ValueError("シートごとの日付が一致しません")
        p = pick(sh)
        for k in KEYS:
            tot[k] += p[k]
    tn = None  # 「東証+名証」シートとの差(参考。市場区分の継ぎ目の目安)
    for n in wb.sheet_names():
        if n.startswith("Tokyo"):
            try:
                q = pick(wb.sheet_by_name(n))
                tn = {k: int(round((q[k] - tot[k]) / 1e5)) for k in KEYS}
            except Exception:
                tn = None
    return {k: int(round(tot[k] / 1e5)) for k in KEYS}, era, dates, tn


def monday(d):
    return d - datetime.timedelta(days=d.weekday())


def main():
    s = requests.Session()
    s.headers.update(UA)
    pages = [IDX]
    empty = 0
    for n in range(0, 30):
        pages.append(ARCHIVE % n)
    files, seen = [], set()
    pages_log = []
    for p in pages:
        r = get(s, p)
        if r is None:
            pages_log.append(f"{p.split('/')[-1]}: なし")
            if p != IDX:
                empty += 1
                if empty >= 2:
                    break
            continue
        h = r.text
        n_before = len(files)
        for href in re.findall(r'href="([^"]*stock_val_1_\d+\.xls)"', h):
            url = href if href.startswith("http") else BASE + href
            if url not in seen:
                seen.add(url); files.append(("xls", url, None))
        for href, sd, ed in re.findall(r'href="([^"]*stock_1_w_(\d{8})_(\d{8})\.xlsx)"', h):
            url = href if href.startswith("http") else BASE + href
            if url not in seen:
                seen.add(url); files.append(("xlsx", url, (sd, ed)))
        pages_log.append(f"{p.split('/')[-1]}: +{len(files) - n_before}件")
        if p != IDX and len(files) == n_before:
            empty += 1
            if empty >= 2:
                break

    hist = {}
    if os.path.exists(OUT):
        old = json.load(open(OUT, encoding="utf-8"))
        hist = {w["from"]: w for w in old["weeks"]}
    n_start = len(hist)

    fails, tn_big = [], []
    for kind, url, ds in files:
        name = url.split("/")[-1]
        try:
            content = get(s, url).content
            if kind == "xlsx":
                vals, _ = cur.parse(content)
                sd = datetime.datetime.strptime(ds[0], "%Y%m%d").date()
                ed = datetime.datetime.strptime(ds[1], "%Y%m%d").date()
                era, tn = "new", None
            else:
                vals, era, (sd, ed), tn = parse_xls(content)
            hist[monday(sd).isoformat()] = {"from": monday(sd).isoformat(), "to": ed.isoformat(), **vals, "era": era}
            if tn and max(abs(v) for v in tn.values()) > 50:
                tn_big.append(f"{monday(sd).isoformat()} {tn}")
        except Exception as ex:  # noqa
            fails.append(f"{name}: {ex!r}")

    weeks = sorted(hist.values(), key=lambda w: w["from"])
    doc = {
        "unit": "億円",
        "market": "東証の現物・差引=買い−売り。era=old は旧市場(一部+二部+マザーズ+JASDAQ)、era=new はプライム+スタンダード+グロース",
        "source": "JPX 投資部門別売買状況(週次) " + IDX,
        "note": "scripts/backfill_investor_flows.py が過去の全週を取り込んだもの。市場区分が旧→新に変わる継ぎ目は era で見分ける。",
        "updated": datetime.date.today().isoformat(),
        "weeks": weeks,
    }
    json.dump(doc, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    by_year = {}
    for w in weeks:
        by_year[w["from"][:4]] = by_year.get(w["from"][:4], 0) + 1
    eras = {}
    for w in weeks:
        eras[w["era"]] = eras.get(w["era"], 0) + 1
    last_old = max((w["from"] for w in weeks if w["era"] == "old" and w["from"] < "2022-12-31"), default=None)
    first_new = min((w["from"] for w in weeks if w["era"] == "new"), default=None)

    check = [f"実行 {datetime.datetime.utcnow().isoformat()}Z / ページ {len(pages_log)} / ファイル {len(files)}件 / 保存 {len(weeks)}週(今回の追加 {len(weeks) - n_start}) / 失敗 {len(fails)}件"]
    check.append("ページ別: " + ", ".join(pages_log))
    check.append(f"年別の週数: {by_year}")
    check.append(f"era別: {eras} / 旧市場で最後の週(2022年内) {last_old} / 新市場で最初の週 {first_new}")
    # 既存の毎週データ(株探転記+JPX xlsx)との比較
    if os.path.exists(CUR_JSON):
        cj = json.load(open(CUR_JSON, encoding="utf-8"))
        diffs, mx = [], {k: 0 for k in KEYS}
        for w in cj["weeks"]:
            h = hist.get(w["from"])
            if not h:
                diffs.append(f"{w['from']}: 履歴に無い")
                continue
            d = {k: h[k] - w[k] for k in KEYS}
            for k in KEYS:
                mx[k] = max(mx[k], abs(d[k]))
            if any(d.values()):
                diffs.append(f"{w['from']}: " + ", ".join(f"{k}={d[k]:+d}" for k in KEYS) + " (履歴−既存)")
        check.append(f"既存{len(cj['weeks'])}週との差の最大(億円): {mx}")
        check += diffs
    check.append(f"東証+名証シートとの差が50億円超の週: {len(tn_big)}件")
    check += tn_big[:30]
    check.append("失敗した週:")
    check += fails[:80]
    open(CHECK, "w", encoding="utf-8").write("\n".join(check) + "\n")
    print("\n".join(check))


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:  # noqa
        open(CHECK, "w", encoding="utf-8").write(f"失敗 {datetime.datetime.utcnow().isoformat()}Z: {ex!r}\n")
        print("失敗", repr(ex))
        sys.exit(1)
