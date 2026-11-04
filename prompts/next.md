Шинэ ажил: 6E futures аудит ба order flow bar v1. Commit хийхгүй.
Эх: data/raw/databento/6E_v0/ (manifest.json). Raw файлуудыг өөрчлөхгүй.
Databento API-г ДУУДАХГҮЙ, зөвхөн локал файл.

1. Аудит (ohlcv-1m ба trades):
   - timestamp UTC (ns) монотон эсэх, давхардал, цоорхой
   - 2019: .part + tail файлыг нэгтгэж, давхцсан бичлэгүүдийг
     (ts_event, price, size, side, sequence)-аар арилга, тоог тайлагна
   - side баганы утгуудын тархалт (A/B/N)
   - Degraded 14 өдрийг flag-аар тэмдэглэ (устгахгүй)
   - Contract roll: 6E.v.0-ийн instrument_id солигдсон цэгүүдийг ол,
     roll-ийн үеийн үнийн үсрэлтийг (basis) тайлагна
2. Spot-той тулгалт: 6E ohlcv-1m close ба манай EURUSD M1 (C4, UTC)-ийн
   1 минутын өгөөжийн correlation, жил бүрээр. Timezone зөв бол r > 0.9
   байх ёстой. Хамгийн сайн lag (−5..+5 минут) 0 байх ёстой.
3. Order flow bar (M15 ба H1, UTC, bar-ийн эхлэх цагаар label):
   - volume, buy_volume (side=A), sell_volume (side=B), delta = buy − sell,
     trade_count, delta / volume, үнийн vwap
   - roll_flag: bar дотор instrument_id солигдсон бол
   - degraded_flag
   - Return-ийг roll-ийн хилээр тооцохгүй
     → data/processed/orderflow_6e/v1/ (parquet, manifest, SHA256SUMS)
4. Тест: delta = buy − sell, bar хилээр look-ahead байхгүй, давхардал
   арилсан, roll_flag зөв, ижил оролтоор ижил hash.
5. reports/orderflow*6e_audit*<ts>/summary.md
