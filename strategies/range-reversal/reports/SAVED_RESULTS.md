# Saved Range Reversal results

## Corrected April–June 2025 executed-trade validation

The saved report is the corrected run, not the superseded result. It covers
90 complete local days; June 30 was skipped because minute data ended before
the end of that fixed UTC−04:00 day. The test is a unit-size price model with
0% commission and 0.02% adverse slippage per side in fills. SHORT is
hypothetical on Spot OHLCV.

| Corrected run | Eligible trades | Target | Stop | End of day | Mean win R | Mean loss R | Mean net R | Win rate | Profit factor | Total net R | Max cumulative-R drawdown |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 68 | 13 | 47 | 8 | 1.629648150642928559719430474167003165845 | -1.010352893612912631896168865251848868236 | -0.3503526325489523339922690303971358597156 | 0.25 | 0.5517168793935163829917440956075052880064 | -23.82397901332875871147429406700523846066 | 27.56523270834822836608457041855085787532 |
| Filtered | 32 | 4 | 28 | 0 | 1.890789423752976338243460171643532446021 | -1.101089519888363738686139472326310544780 | -0.7271046519331962290699395168300801709297 | 0.125 | 0.2555453046054047652814082493926694571342 | -23.26734886186227933023806453856256546975 | 27.18384090529992391434898015176141752482 |
| Excluded shadow baseline | 36 | 9 | 19 | 8 | 1.549296989685990781712036721097301848868 | -0.8998909137993199801518568218568520446157 | -0.01546194865184664947878415356785202752475 | 0.3611111111111111111111111111111111111111 | 0.7178616651950952090255699164214190584680 | -0.556630151466479381236229528442672990891 | 8.029721194375441109854203780770291958820 |

The filtered run evaluates the filter only on delayed-eligible E3 rows.
Excluded-shadow values do not enter the filtered run and do not permit another
same-day signal. These are historical outcomes, not evidence that the strategy
is profitable or suitable for live trading.

## Corrected delayed-N3 annotation comparison (not an executed-trade result)

The corrected annotation holds the initial first-return time immutable and
keeps the breakout-extremum and local-pivot stop variants separate. For
`BREAKOUT_EXTREMUM_FIRST_RETURN`, the E1 timestamp changed in 33 rows; 41 were
unchanged. Stops had 18 numerical changes and 56 numerically unchanged rows.
There were zero cases where E1 was unchanged while the stop changed
numerically. The E1-fixed targets had 33 numerical changes and 41 unchanged.

For `LOCAL_PIVOT_2X2`, there were 14 value-to-empty cancellations, 10 numeric
stop changes, and 12 numerically unchanged stops. The corrected set contains
52 `NO_LOCAL_PIVOT` rows: 52 had no geometric 2-left/2-right strict pivot,
with zero wrong-side pivots and zero pivots already reached before E3.

This annotation comparison uses an E1-fixed target and is **not** pooled with
the executed validation above, which uses E3-rebased 2R targets.
