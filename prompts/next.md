Шинэ ажил: Sweep + MSS стратеги, TRAIN дээр. Commit хийхгүй.
Engine: src/backtest/engine.py, trial log-д бүртгэ.

Дүрмүүд урьдчилан царцаасан, үр дүнг хараад параметр өөрчлөхгүй:

- Trend (H4, M15 bar-уудаас үүсгэ): хаагдсан H4 close > EMA50 → зөвхөн long,
  < EMA50 → зөвхөн short
- Asia range: тухайн өдрийн 00:00–07:00 UTC-ийн high/low
- Sweep (M15, 12:00–17:00 UTC): long-д bar-ийн low < Asia low БА close > Asia low.
  Short-д эсрэгээр (high > Asia high БА close < Asia high).
- MSS: sweep-ээс хойш 8 M15 bar дотор close нь sweep-ийн өмнөх сүүлийн
  swing high-аас (long) / swing low-оос (short) давж хаагдах.
  Swing = 2 bar-ийн fractal (хоёр талдаа 2 bar).
- Орох: MSS bar-ийн дараагийн bar-ийн open. Өдөрт хамгийн ихдээ 1 арилжаа.
- Гарах: 4 цаг, эсвэл 20:45 UTC, аль нь түрүүлнэ.
- Stop/target байхгүй (v1). Зөвхөн хугацаагаар гарна.

Үр дүн: engine-ийн бүх хэмжүүр, жил бүрээр, long/short тусад нь,
санамсаргүй baseline-тай харьцуулалт.
reports/strategy*sweep_mss*<ts>/summary.md
