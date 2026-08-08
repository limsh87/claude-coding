#!/usr/bin/env python3
"""ARC-BDF B-1 전진 수집기 — 거래원 상위 5창구 일별 스냅샷.

거래원 과거 이력은 어떤 무료 소스에도 없다. 그래서 오늘부터 쌓는다.
매 영업일 장마감 후 1회 실행하도록 스케줄러에 등록하라.

  · Linux/Mac cron :   30 16 * * 1-5  /usr/bin/python3 /home/user/claude-coding/arc_bdf_work/outputs/forward_collect_member_flow.py
  · Windows        :   작업 스케줄러 → 매일 16:30 → python /home/user/claude-coding/arc_bdf_work/outputs/forward_collect_member_flow.py
  · GitHub Actions :   schedule: - cron: "30 7 * * 1-5"   (UTC 기준)

하루라도 빠지면 그날은 영구 결손이다. Colab 세션에 의존하지 말고 상시 실행 환경에 올릴 것.
저장 위치는 ARC_BDF_CACHE 환경변수(없으면 ./arc_bdf_cache) 아래 공용 인덱스다.
"""
import os, re, json, time, random, hashlib, datetime as dt
import pandas as pd, requests

ROOT = os.environ.get("ARC_BDF_CACHE", "./arc_bdf_cache")
OUT = os.path.join(ROOT, "_shared", "table", "naver_member_flow_snapshot")
os.makedirs(OUT, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"


def codes_today():
    """상장 종목 코드 목록. FDR 이 있으면 그걸, 없으면 캐시된 목록을 쓴다."""
    try:
        import FinanceDataReader as fdr
        d = fdr.StockListing("KRX")
        c = [str(x).zfill(6) for x in d[[c for c in d.columns if c.lower() in ("code", "symbol")][0]]]
        return [x for x in c if re.fullmatch(r"\d{6}", x)]
    except Exception:
        p = os.path.join(ROOT, "_shared", "table", "code_list.json")
        if os.path.isfile(p):
            return json.load(open(p))
        raise SystemExit("종목 목록을 얻지 못했습니다. finance-datareader 를 설치하세요.")


def fetch_one(code):
    url = f"https://finance.naver.com/item/frame_trade.naver?code={code}"
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Referer": "https://finance.naver.com/"},
                         timeout=20)
        if r.status_code != 200:
            return None
        html = r.content.decode("euc-kr", "replace")
    except Exception:
        return None
    tds = re.findall(r"<td[^>]*>(.*?)</td>", html, re.S)
    tds = [re.sub(r"<[^>]+>", "", t).replace("&nbsp;", " ").strip() for t in tds]
    rows, side_i = [], 0
    pairs = [(tds[i], tds[i + 1]) for i in range(len(tds) - 1)
             if re.fullmatch(r"[\d,]+", tds[i + 1] or "") and tds[i]
             and not re.fullmatch(r"[\d,\.%]+", tds[i])]
    for i, (nm, v) in enumerate(pairs[:10]):
        rows.append(dict(member_raw=nm, volume=float(v.replace(",", "")),
                         side="SELL" if i % 2 == 0 else "BUY", rank=i // 2 + 1, code=code))
    return rows or None


def main():
    now = dt.datetime.now()
    td = now.date() if now.hour >= 16 else (now.date() - dt.timedelta(days=1))
    while td.weekday() >= 5:
        td -= dt.timedelta(days=1)
    codes = codes_today()
    out, fail = [], 0
    for i, c in enumerate(codes):
        time.sleep(random.uniform(0.3, 1.2))          # 차단 방지 (SPEC 2.3)
        r = fetch_one(c)
        if not r:
            fail += 1
            if fail >= 30:
                print("[중단] 연속 실패 30회 — 차단 가능성. 여기까지 저장합니다.")
                break
            continue
        fail = 0
        out.extend(r)
        if i % 200 == 0:
            print(f"  {i}/{len(codes)} ...")
    if not out:
        print("수집 0건 — 휴장이거나 차단입니다."); return
    df = pd.DataFrame(out)
    df["trade_date"] = pd.Timestamp(td)
    df["captured_at"] = pd.Timestamp(now)
    df["parser_ver"] = 1
    p = os.path.join(OUT, f"snapshot_{td:%Y%m%d}.parquet")
    df.to_parquet(p, index=False)                     # 기존 파일을 덮지 않는 날짜별 파일
    print(f"저장 {len(df):,}행 → {p}")


if __name__ == "__main__":
    main()
