Шинэ ажил: order flow exploratory статистик. Зөвхөн TRAIN (2019–2021).
Validation-д хүрэхгүй. Commit хийхгүй. Side mapping: одоогийн v1 (B=buy) зөв.

Эх: data/processed/orderflow_6e/v1/ (M15, H1) + манай spot EURUSD bars v1.
roll_flag, degraded_flag, roll-ийн өмнөх Баасан гаригийн bar-уудыг хас
(шинэ flag: pre_roll_thin — roll-оос өмнөх ажлын өдөр).

Асуулт: order flow дараагийн өгөөжийг таамагладаг уу?

1. delta_ratio (delta/volume), delta-ийн z-score (сүүлийн 20 bar),
   cumulative delta (session дотор), volume spike (volume / 20 bar median)
   → ДАРААГИЙН 1, 2, 4 bar-ийн spot өгөөж (pip). M15 ба H1.
2. Квинтилээр: delta_ratio-ийн 5 бүлэг тус бүрийн дараагийн өгөөжийн дундаж,
   t-stat. Monotonic хамаарал байгаа эсэх.
3. Нөхцөлт: том delta + үнэ хөдлөөгүй (absorption), том delta + үнэ
   эсрэг хөдөлсөн (divergence) → дараагийн өгөөж.
4. Session тус бүрээр (Asia / London / NY).
5. Харьцуулалт: зардал ~1.0 pip. Хамгийн хүчтэй олдвор зардлыг даах уу?
   Олон тестийн засвар: BH-FDR, нийт тестийн тоог тайлагна.
   reports/orderflow*exploratory*<ts>/summary.md
