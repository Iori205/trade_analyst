Cost model v1-ийн дутуу хэсэг (өмнөх prompt тасарсан):

1. config/cost_model_v1.yaml-д нэм:
   spread_percentile: p75 (default)
   commission_pips_round_trip: 0.6
   slippage_pips: 0.2
   Эдгээр нь брокероос хамаарах таамаг гэдгийг тайланд бич.
2. Функц cost_for(timestamp_utc) → нэг арилжааны (round trip) нийт зардал
   pip-ээр = spread(percentile) + commission + slippage.
   Rollover / weekly_open цагт тусдаа flag буцаа (backtest тэр цагт
   арилжаа хаахыг шийдэхэд хэрэгтэй).
3. Тест: зардал үргэлж ≥ commission + slippage, percentile солиход өөрчлөгддөг.
4. Тайлангийн summary.md-д нийт зардлын хүснэгт нэм.
   Commit хийхгүй.
