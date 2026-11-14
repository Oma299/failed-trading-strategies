# Volatility Compression Breakout Retest V1

> **Report provenance:** No Markdown report was saved in the canonical
> `reports/volatility_compression_breakout_retest_v1/` run directory. This
> Markdown report is a staging-only rendering of its saved `run_config.json`,
> `metrics.json`, `data_quality.json`, and the strategy specification. The
> numerical values below are copied from those saved aggregate artifacts; no
> experiment or backtest was rerun to prepare this report.

Separate BTCUSDT Spot research strategy on completed UTC H1 candles. At the
close of `t`, the last 12 H1 candles form a range; its width is compared with
the preceding 720 12-hour widths. The threshold is nearest-rank
`ceil(0.20 × 720)`. When `W <= threshold`, the upper and lower boundaries are
fixed and do not move.

During the next six completed H1 candles, a close breakout beyond a boundary
by at least `0.1 × ATR(14)` is sought. Wilder ATR is fixed at breakout. During
the following three H1 candles, the first retest is sought: LONG
`low <= U && close > U`, SHORT is mirrored. A close on the wrong side cancels
the episode. Entry is the next hour's open with 0.02% adverse slippage.

The stop is the retest candle extreme plus/minus `0.1 × ATR_breakout`. Entry
is skipped when stop distance is less than `0.5 ATR`; equality is allowed.
The target is exactly 2R from the actual entry fill. Commission in this run
was 0%. Minute OHLCV execution starts at the entry minute; when both stop and
target are touched in the same minute, stop is first. Maximum holding time is
12 hours; end-of-data is `DATA_INCOMPLETE`, not a planned exit.

Only one position and one attempt per range are allowed. New ranges do not
accumulate while a range or position is active. SHORT is a hypothetical price
model on Spot data. January–June 2025 with December history is a research
window, not an independent final test.

## Data and execution summary

- Symbol/market: BTCUSDT Spot; input granularity: one-minute OHLCV, aggregated
  into H1.
- Saved period: `2025-01-01T00:00:00` inclusive to `2025-07-01T00:00:00`
  exclusive, UTC.
- Saved source quality: 305,280 minute rows from `2024-12-01T00:00:00+00:00`
  through `2025-06-30T23:59:00+00:00`; zero duplicate timestamps, out-of-order
  pairs, missing minutes, numeric errors, or negative-volume rows.
- Commission: 0%; adverse slippage: 0.02% per fill.
- Position model: per-trade one-BTC price model, not account equity.
- `DATA_INCOMPLETE` trades: 0.

## Event counts and aggregate executed-trade results

Counts are not interchangeable: the run recorded 39 compressions, 342
breakouts, 62 retests, and 39 executed-trade records.

| Metric | Saved result |
|---|---:|
| Trades | 39 |
| Data incomplete | 0 |
| Win rate | 0.2051282051282051282051282051282051282051 |
| Mean winning R | 1.330543158236389849105234814915110054685 |
| Mean losing R | -0.94350869729639792973558808625936657364 |
| Mean R | -0.4770365218024927443323423629415252139833 |
| Sum R | -18.60442435029721702896135215471948334535 |
| Profit factor | 0.3639245481286770433562737647919012536556 |
| Maximum drawdown (R) | 19.97876062298498871770028662288738303320 |
| LONG / hypothetical SHORT | 18 / 21 |
| Sum gross PnL per 1 BTC (USDT) | -6764.88629579550362117442141681424992419 |
| Mean gross PnL per 1 BTC (USDT) | -173.4586229691154774660108055593397416459 |

## Monthly results

| Month | Trades | Incomplete | Win rate | Mean win R | Mean loss R | Mean R | Sum R | Profit factor | Max drawdown R | LONG | SHORT | Gross PnL / 1 BTC (USDT) | Mean gross PnL / 1 BTC (USDT) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025-01 | 6 | 0 | 0.1666666666666666666666666666666666666667 | 0.6065612002044044870064192433535286457671 | -0.9531074698237481620005660520015100391954 | -0.6931626914857227204994018361090035917017 | -4.158976148914336322996411016654021550210 | 0.1272807567685041485654200127493109936497 | 4.158976148914336322996411016654021550210 | 4 | 2 | -1240.22920219724435933155791741952624142 | -206.7048670328740598885929862365877069033 |
| 2025-02 | 12 | 0 | 0.1666666666666666666666666666666666666667 | 2.044826137641896158715930846423316747210 | -0.950485260283744212421711908177135747551 | -0.4512666939628041505654381157437269984242 | -5.415200327553649806785257388924723981090 | 0.4302699311784094673832439966929872734620 | 7.460002203933959220014589303355608729048 | 6 | 6 | -4118.27575138262928613346301095612350115 | -343.1896459485524405111219175796769584292 |
| 2025-03 | 5 | 0 | 0.2 | 0.2114660859694279666739773324660727566717 | -0.942040649069088898735619362303690282726 | -0.7113393020613855256537000233497376748464 | -3.556696510306927628268500116748688374232 | 0.05611915106274759203473738744460671237740 | 3.768162596276355594942477449214761130904 | 2 | 3 | -1108.12649578524708283252460529906893716 | -221.625299157049416566504921059813787432 |
| 2025-04 | 4 | 0 | 0.25 | 2.027755421565622985666415087772719831368 | -0.943250839061268004855709338078279397824 | -0.2004992739045452572251782316155295905260 | -0.8019970956181810289007129264621183621041 | 0.7165840154755526159135758543687965896987 | 2.829752517183804014567128014234838193472 | 1 | 3 | -105.57457147540427696426011141553711229 | -26.3936428688510692410650278538842780725 |
| 2025-05 | 5 | 0 | 0 | — | -0.936906784003555569282781682797737427393 | -0.936906784003555569282781682797737427393 | -4.684533920017777846413908413988687136965 | 0E+39 | 4.684533920017777846413908413988687136965 | 3 | 2 | -1721.63736142916364309542178868641503527 | -344.327472285832728619084357737283007054 |
| 2025-06 | 7 | 0 | 0.4285714285714285714285714285714285714286 | 1.236303427622623678687735054293975236416 | -0.9239826576885538579149418637057924124992 | 0.001854236016236514914776815436965151321457 | 0.0129796521136556044034377080587560592502 | 1.003511876550293070006869313246274840190 | 1.770304238203213426565864685280251075411 | 2 | 5 | 1528.9570864741850271828060169624209031 | 218.4224409248835753118294309946315575857 |

## Direction results

| Direction | Trades | Incomplete | Win rate | Mean win R | Mean loss R | Mean R | Sum R | Profit factor | Max drawdown R | Gross PnL / 1 BTC (USDT) | Mean gross PnL / 1 BTC (USDT) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LONG | 18 | 0 | 0.1666666666666666666666666666666666666667 | 0.4089916346009765986369215003302362830863 | -0.9573487264726576291860480830373927324927 | -0.7296253329603852578822198191427878965633 | -13.13325599328693464187995674457018213814 | 0.08544256095851350350378897925156496681439 | 13.13325599328693464187995674457018213814 | -7204.81727871885428338800658065986926686 | -400.2676265954919046326670322588816259367 |
| SHORT (hypothetical Spot price model) | 21 | 0 | 0.2380952380952380952380952380952380952381 | 1.883474072417637799386222803666034317643 | -0.9305336699436544615007818392799670497144 | -0.2605318265242991612895902576261572003435 | -5.471168357010282387081395410149301207214 | 0.6325248259594429981679262484752138284399 | 9.993572869471360979921029543507647301844 | 439.93098292335066221358516384561934267 | 20.94909442492146010540881732598187346048 |

These are saved research results, not evidence of profitability or
independent out-of-sample performance. LONG and hypothetical SHORT are
reported separately; the short model does not include borrowing, funding, or
a short account.

## Staging-only path note

The original canonical run directory contained JSON, CSV, HTML, and SVG
artifacts, but no Markdown report. This report is therefore a staging-only
rendering of saved aggregate artifacts, not a verbatim copy of an original
Markdown report. **Path-only redactions: none.** The source settings used a
relative input-data reference; no machine-specific absolute path was present
in the staged report or configuration.
