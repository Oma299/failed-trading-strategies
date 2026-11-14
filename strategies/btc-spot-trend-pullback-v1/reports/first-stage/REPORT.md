# BTC_SPOT_TREND_PULLBACK_V1 first-stage results

The source specification is [`BTC_SPOT_TREND_PULLBACK_V1.md`](../../BTC_SPOT_TREND_PULLBACK_V1.md). Each continuous segment is a separate account; returns are not compounded across segments. July–December 2025 is excluded.

## Scenario summary

| Scenario | Closed trades | W/L | Trade-weighted mean R |
|---|---:|---:|---:|
| ZERO | 847 | 617/230 | 0.05461920564663491247721415475307930722198 |
| FEE_ONLY | 847 | 471/376 | -0.08823728818771966630805893804014586052687 |
| BASE | 847 | 427/420 | -0.1173809429055353429429819884895337698460 |
| ADVERSE | 847 | 365/482 | -0.1548644171731262943385104529747305206059 |
| STRESS | 847 | 202/645 | -0.2559949987222451109131193007630925126640 |

The BASE result is negative on the allowed history after costs. ZERO is diagnostic only. The requested frequency and sensitivity files are saved separately; their descriptive aggregations do not form a single portfolio.

The 48-hour path is implemented and covered by a synthetic exact-deadline test. No historical BASE trade reached TIME_EXIT; the observed maximum holding time is below the deadline. RIGHT_CENSORED positions remain terminal estimates and are excluded from ordinary PF and win rate.

Deferred stages: tail stop slippage, delayed signals, six neighboring configurations, bootstrap, the closed Jul–Dec 2025 period, and live/partial-fill replay.
