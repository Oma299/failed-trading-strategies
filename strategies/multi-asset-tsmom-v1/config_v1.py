from __future__ import annotations

VARIANT_ID = "V1"
STAGE = "V1"

SOURCE = "Yahoo Finance Chart API"
PERIOD1 = 0
PERIOD2 = 1751320799
CUTOFF_DATE = "2025-07-01"
DATA_DIR = "data/v1"

ASSETS = {
    "EURUSD": {
        "ticker": "EURUSD=X",
        "kind": "FX",
        "timezone": "Europe/London",
        "filename": "EURUSD.csv",
    },
    "USDJPY": {
        "ticker": "USDJPY=X",
        "kind": "FX",
        "timezone": "Europe/London",
        "filename": "USDJPY.csv",
    },
    "GBPUSD": {
        "ticker": "GBPUSD=X",
        "kind": "FX",
        "timezone": "Europe/London",
        "filename": "GBPUSD.csv",
    },
    "AUDUSD": {
        "ticker": "AUDUSD=X",
        "kind": "FX",
        "timezone": "Europe/London",
        "filename": "AUDUSD.csv",
    },
    "USDCAD": {
        "ticker": "USDCAD=X",
        "kind": "FX",
        "timezone": "Europe/London",
        "filename": "USDCAD.csv",
    },
    "USDCHF": {
        "ticker": "USDCHF=X",
        "kind": "FX",
        "timezone": "Europe/London",
        "filename": "USDCHF.csv",
    },
    "SPY": {
        "ticker": "SPY",
        "kind": "ETF",
        "timezone": "America/New_York",
        "filename": "SPY.csv",
    },
    "EFA": {
        "ticker": "EFA",
        "kind": "ETF",
        "timezone": "America/New_York",
        "filename": "EFA.csv",
    },
    "EEM": {
        "ticker": "EEM",
        "kind": "ETF",
        "timezone": "America/New_York",
        "filename": "EEM.csv",
    },
    "TLT": {
        "ticker": "TLT",
        "kind": "ETF",
        "timezone": "America/New_York",
        "filename": "TLT.csv",
    },
    "GLD": {
        "ticker": "GLD",
        "kind": "ETF",
        "timezone": "America/New_York",
        "filename": "GLD.csv",
    },
}

DATA_SHA256 = {
    "AUDUSD": "6CDD44D32A088D26F235E831DE3563DAE44BDCC7946570DF6E040F9AED419187",
    "EEM": "5640C8B8BE33947645C9C5F351ED61AFF4D048721805A8138AC6964EFC07C8E9",
    "EFA": "70336A43FEC27922652C7D2F55FCE3B1F1747EBF161C48144D0BE34E61165B18",
    "EURUSD": "D2180F1780C3313CC240A1A4EDD27CAC68377FA2CB5C74E3F4C4488402DE76F3",
    "GBPUSD": "A4FE7B87DE99ABB440A6F3795018D5927CE60104CE45C51691F7E29576F6228B",
    "GLD": "B303DA7BA425C0ED2CBD76F0ACD4250C51AA644A49A4780C1AEAC513FB29BACF",
    "SPY": "70B848AD0D869A2996BD3E50C99BC361A8D2163424206D222171C332073E4D6A",
    "TLT": "8573D3A94BBBD40EEC9014B9B7AA50BCB3E4D00997C12AF9F3DC5DA27BDECD5E",
    "USDCAD": "DE49C51E9D69AEFE33A385F12D12E55FD667D59500A466FFF2A4579ACB94DE62",
    "USDCHF": "DD618D298856EFBDB184BBDD71DA10E9D406385851FCB6E231AC9F7D984CD2B7",
    "USDJPY": "6C6B789CD4AA552EBDCCA5D7C56013D6046A08408F13427BFBD8234C67FA2206",
}

LOOKBACK_DAYS = 28
RANK_WINDOW = 365
RANK_THRESHOLD = 2 / 3
MIN_VALID_RANK_VALUES = 200
MAX_BASE_GAP_DAYS = 4
HOLD_DAYS = 7

FX_ROUND_TRIP_COST = 0.0003
ETF_ROUND_TRIP_COST = 0.0005

PLACEBO_DRAWS = 10_000
PLACEBO_MIN_SHIFT_DAYS = 60
BOOT_DRAWS = 10_000
BOOT_BLOCK_WEEKS = 8
SEED = 12345

MIN_ON_BLOCKS = 300
ABANDON_PLACEBO_P = 0.20
CONTINUE_PLACEBO_P = 0.10
ABANDON_MIN_POSITIVE_ASSETS = 5
CONTINUE_MIN_POSITIVE_ASSETS = 7
BOOTSTRAP_LOWER_PERCENTILE = 10
BEST_BLOCK_FRACTION = 0.05

OUTPUT_BLOCKS = "blocks_v1.csv"
OUTPUT_RESULTS = "results_v1.json"
OUTPUT_REPORT = "report_v1.md"
OUTPUT_MANIFEST = "run_manifest_v1.json"
OUTPUT_LEDGER = "ledger.csv"


def as_dict() -> dict[str, object]:
    return {
        "VARIANT_ID": VARIANT_ID,
        "STAGE": STAGE,
        "SOURCE": SOURCE,
        "PERIOD1": PERIOD1,
        "PERIOD2": PERIOD2,
        "CUTOFF_DATE": CUTOFF_DATE,
        "DATA_DIR": DATA_DIR,
        "ASSETS": ASSETS,
        "DATA_SHA256": DATA_SHA256,
        "LOOKBACK_DAYS": LOOKBACK_DAYS,
        "RANK_WINDOW": RANK_WINDOW,
        "RANK_THRESHOLD": RANK_THRESHOLD,
        "MIN_VALID_RANK_VALUES": MIN_VALID_RANK_VALUES,
        "MAX_BASE_GAP_DAYS": MAX_BASE_GAP_DAYS,
        "HOLD_DAYS": HOLD_DAYS,
        "FX_ROUND_TRIP_COST": FX_ROUND_TRIP_COST,
        "ETF_ROUND_TRIP_COST": ETF_ROUND_TRIP_COST,
        "PLACEBO_DRAWS": PLACEBO_DRAWS,
        "PLACEBO_MIN_SHIFT_DAYS": PLACEBO_MIN_SHIFT_DAYS,
        "BOOT_DRAWS": BOOT_DRAWS,
        "BOOT_BLOCK_WEEKS": BOOT_BLOCK_WEEKS,
        "SEED": SEED,
        "MIN_ON_BLOCKS": MIN_ON_BLOCKS,
        "ABANDON_PLACEBO_P": ABANDON_PLACEBO_P,
        "CONTINUE_PLACEBO_P": CONTINUE_PLACEBO_P,
        "ABANDON_MIN_POSITIVE_ASSETS": ABANDON_MIN_POSITIVE_ASSETS,
        "CONTINUE_MIN_POSITIVE_ASSETS": CONTINUE_MIN_POSITIVE_ASSETS,
        "BOOTSTRAP_LOWER_PERCENTILE": BOOTSTRAP_LOWER_PERCENTILE,
        "BEST_BLOCK_FRACTION": BEST_BLOCK_FRACTION,
        "OUTPUT_BLOCKS": OUTPUT_BLOCKS,
        "OUTPUT_RESULTS": OUTPUT_RESULTS,
        "OUTPUT_REPORT": OUTPUT_REPORT,
        "OUTPUT_MANIFEST": OUTPUT_MANIFEST,
        "OUTPUT_LEDGER": OUTPUT_LEDGER,
    }
