# Tablo 2 — Ölçümün Yeniden Üretimi

> `tools/tablo2_dogrula.py` çıktısı; elle düzenlemeyin.

Kaynak: `outputs/model_degerlendirme/test_sonuclari.json` (40 test üretimi).

| Ölçüt | Raporda | Bu ölçüm | Durum |
|---|---|---|---|
| Olgu sadakati (uydurma sayı içermeyen yanıt) | %97,5 (39/40) | %97,5 (39/40) | ✓ aynı |
| Uydurma sayı / üretilen toplam sayı | %0,3 (1/390) | %0,3 (1/390) | ✓ aynı |
| Kompozit risk skorunu metinde aktaran yanıt | %87,5 (35/40) | %87,5 (35/40) | ✓ aynı |
| Risk seviyesi adının skorla tutarlılığı | %80,0 (28/35) | %80,0 (28/35) | ✓ aynı |
| Güncelliğini yitirmiş güvenlik tavsiyesi | 0/40 | 0/40 | ✓ aynı |
| Ortalama yanıt uzunluğu | 109 kelime | 109 kelime | ✓ aynı |

Tablo 2'nin altı satırı da ham çıktılardan yeniden üretilmiştir.
