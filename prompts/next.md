Шинэ ажил: backtest engine v1. Commit хийхгүй.

1. src/backtest/engine.py:
   - Оролт: bar DataFrame (M15/H1, UTC), signal функц, cost_model (p75)
   - Signal нь зөвхөн тухайн bar хаагдсаны дараах мэдээллийг ашиглана;
     орох үнэ = ДАРААГИЙН bar-ийн open (look-ahead хамгаалалт)
   - Long/short, нэг позиц, тогтмол хэмжээ (1 lot), барих хугацаа эсвэл
     signal-ээр хаах
   - Rollover / weekly_open цагт шинээр орохгүй (cost_for flag)
   - any_gap/any_flag bar-т шинээр орохгүй
   - Зардлыг арилжаа бүрт cost_for(entry_time)-аар хасна
2. Хэмжүүр: арилжааны тоо, win rate, avg win, avg loss, expectancy (pip,
   зардлын дараа), нийт pip, max drawdown, Sharpe (өдрийн), жил бүрийн
   үр дүн, t-stat.
3. Trial log: ажиллуулалт бүрийг reports/trials/trials.csv-д нэмнэ
   (огноо, стратеги, параметр, split, хэмжүүрүүд, git hash). Устгахгүй.
4. Splits guard ашигла: default нь зөвхөн train.
5. Baseline-ууд (train дээр ажиллуул):
   a) Санамсаргүй: H1, өдөрт ~1 арилжаа, 4 цаг барих, тогтмол seed,
   100 удаа давтаад expectancy-ийн тархалт
   b) MA crossover H1 (20/50)
   c) Pre-registered: Даваа 13:00 UTC long, 14:00 хаах
6. Тест: look-ahead (signal ирээдүйн bar харахгүй), зардал зөв хасагдсан,
   санамсаргүй стратегийн expectancy ≈ −зардал.
7. reports/backtest*baselines*<ts>/summary.md
