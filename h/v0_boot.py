import types, sys, os, tempfile
FILE = "/home/user/claude-coding/strategies/tcd_v2_00_integrated_all_packs.py"
def load():
    os.environ["TCD_NO_PIP"]="1"
    src = open(FILE, encoding="utf-8").read()
    src = src[:src.index("def offer_download")]
    src = src.replace("def _pip_install(pkgs: List[str], quiet: bool = True) -> Tuple[bool, str]:",
                      "def _pip_install(pkgs: List[str], quiet: bool = True) -> Tuple[bool, str]:\n    return True,'skip'")
    m = types.ModuleType("tcd"); sys.modules["tcd"] = m
    exec(compile(src, "tcd", "exec"), m.__dict__)
    g = m.__dict__; g["VERBOSE"]=False
    d = tempfile.mkdtemp()
    g["VAULT"] = g["Vault"](d, "TEST")
    return m, g, d
