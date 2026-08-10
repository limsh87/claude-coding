import v0_boot
m,g,_ = v0_boot.load()
tc = g["to_code6"]
print("_TICKER_RE =", g["_TICKER_RE"].pattern)
cases = ["005930", 5930, 5930.0, "005930.KS", "A005930", "Q500011", "00104K", "09701L",
         "900140", "008465W", "00846W", "00088R", "J00123", "005930R", "KR7005930003",
         "0059301", "", None, float("nan"), "1", "12"]
for v in cases:
    print(f"  {str(v):16s} -> {tc(v)}")
