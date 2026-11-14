# Range Reversal Apr-Jun 2025 independent validation

Commission 0%; adverse slippage 0.02% per side is included once in fills. This is a unit-size price model, not account equity. SHORT is hypothetical on Spot OHLCV.

|Run|eligible|TARGET|STOP|EOD|mean win R|mean loss R|mean net R|win rate|profit factor|total net R|max cumulative-R drawdown|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|baseline|68|13|47|8|1.629648150642928559719430474167003165845|-1.010352893612912631896168865251848868236|-0.3503526325489523339922690303971358597156|0.25|0.5517168793935163829917440956075052880064|-23.82397901332875871147429406700523846066|27.56523270834822836608457041855085787532|
|filtered|32|4|28|0|1.890789423752976338243460171643532446021|-1.101089519888363738686139472326310544780|-0.7271046519331962290699395168300801709297|0.125|0.2555453046054047652814082493926694571342|-23.26734886186227933023806453856256546975|27.18384090529992391434898015176141752482|
|excluded_shadow_baseline|36|9|19|8|1.549296989685990781712036721097301848868|-0.8998909137993199801518568218568520446157|-0.01546194865184664947878415356785202752475|0.3611111111111111111111111111111111111111|0.7178616651950952090255699164214190584680|-0.556630151466479381236229528442672990891|8.029721194375441109854203780770291958820|

Filter is evaluated only for delayed-eligible E3 rows. Excluded shadow outcomes are descriptive and do not enter the filtered run or permit another same-day signal.


## Decimal audit of filtered TARGET trades

All targets below use initial risk `abs(entry_fill - stop)` and target 2R from E3. `gross_r = gross_pnl_per_btc / initial_risk`; slippage is already present in fills.

|episode_key|direction|entry_fill|initial_stop|target_used|exit_fill|initial_risk|gross_pnl|gross_r|
|---|---|---:|---:|---:|---:|---:|---:|---:|
|2025-04-01|LONG|2025-04-01T14:15:00Z|LONG|83172.86124600|82544.00000000|84430.58373800|84413.69762125|628.86124600|1240.83637525|1.97314810|
|2025-04-03|SHORT|2025-04-03T09:35:00Z|SHORT|83466.34339200|83758.92000000|82881.19017600|82897.76641404|292.57660800|568.57697796|1.94334394|
|2025-05-05|LONG|2025-05-05T11:25:00Z|LONG|94056.99763800|93888.00000000|94394.99291400|94376.11391542|168.99763800|319.11627742|1.88828839|
|2025-06-10|LONG|2025-06-10T08:50:00Z|LONG|109147.39511400|109056.90000000|109328.38534200|109306.51966493|90.49511400|159.12455093|1.75837726|

For LONG, `target = entry_fill + 2*initial_risk`; for SHORT, `target = entry_fill - 2*initial_risk`. Decimal delta was zero for all four corrected filtered TARGET rows. Mean win R is computed only over positive `net_r`; it is `1.890789423752976...` for the corrected filtered run.

## Local-day completeness correction

The last minute is `2025-06-30T23:59:00Z` (`2025-06-30 19:59 UTC-04:00`). Local 2025-06-30 requires through `2025-07-01T03:59:00Z`, which is unavailable. The day is therefore marked `INCOMPLETE_LOCAL_DAY` and skipped; no final candle was substituted. Corrected run: 90 complete days, 1 skipped day.

The superseded report used the wrong E1 target mode and treated June 30 as complete. It is preserved in `../range_reversal_validation_apr_jun_2025_superseded/`.
