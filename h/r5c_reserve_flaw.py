# Simulate the PROPOSED DartBudget.take() reservation, on a steady-state day where
# empSttus.json and list.json are already fully cached (zero jobs) -- the normal case
# from day ~3 onward -- and only fnlttSinglAcntAll.json still has work.
DART_DAILY_LIMIT = 19_000
DART_RESERVE = {"empSttus.json": 5_000, "list.json": 3_000}

class B:
    def __init__(self): self.n = 0
    def take(self, k=1, endpoint=""):
        reserved = sum(v for ep, v in DART_RESERVE.items() if ep != endpoint)
        cap = DART_DAILY_LIMIT - (reserved if endpoint not in DART_RESERVE else 0)
        if self.n + k > cap: return False
        self.n += k; return True

b = B()
n = 0
while b.take(2, "fnlttSinglAcntAll.json"):
    b.n -= 1            # dart_api refunds tries-1 on a 1-attempt success
    n += 1
print(f"fnlttSinglAcntAll calls granted on a day with no emp/disc work: {n:,}")
print(f"budget consumed: {b.n:,} / {DART_DAILY_LIMIT:,}   WASTED: {DART_DAILY_LIMIT-b.n:,} calls/day")
print(f"days to finish a 130,000-call sweep: {-(-130_000//max(n,1))} (vs {-(-130_000//19_000)} today)")
