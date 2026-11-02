Шинэ ажил: exploratory статистик судалгаа. Зөвхөн TRAIN split (2015–2021).
Validation, test-д хүрэхгүй. Commit хийхгүй.
Эх: data/processed/eurusd_bars/v1/ (M15, H1), any_gap/any_flag bar-уудыг хас.
Зардал: src/data/cost_model.py-ийн cost_for (p75).

1. Цаг × гараг (UTC): дундаж өгөөж (pip), өсөх магадлал, std, |өгөөж|-ийн
   median. "|хөдөлгөөн| median / зардал" харьцаа нэм.
2. Autocorrelation: M15, H1 өгөөжийн lag 1–8, мөн session тус бүрээр.
3. Том хөдөлгөөний дараах үр дүн: |өгөөж| > p95 bar-ийн дараах 1, 4, 24 H1
   өгөөж, чиглэлээр ангилж.
4. Session-ийн хамаарал: Asia (00–07 UTC), London (07–12), NY (12–21)
   өгөөжүүдийн correlation, өмнөх session дараагийнхыг таамаглах эсэх.
5. Сарын сүүлийн ажлын өдөр London 16:00 Fix-ийн орчим (London local цагаар
   15:00–17:00, UTC руу DST-тэй хөрвүүл) хөдөлгөөн vs бусад өдөр.

Тест бүрт p-value, нийт тестийн тоо, Benjamini-Hochberg (FDR) засвар.

Тайлан: reports/exploratory*stats*<timestamp>/ — хүснэгт, chart (PNG),
summary.md-д:
a) FDR-ийн дараа ач холбогдолтой хэвээр олдворууд
b) "хөдөлгөөн / зардал > 2" олдворууд
c) хоёуланд нь орсон олдворууд (хамгийн сонирхолтой)
