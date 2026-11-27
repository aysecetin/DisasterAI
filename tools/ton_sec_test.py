"""
ton_sec_test.py — Otomatik ton seçicisinin regresyon testi

Kural katmanının (rc.ton_sec) beklenen tonu seçtiğini doğrular. Kural
tablosunu (TON_IPUCLARI) her değiştirdiğinde bunu çalıştır:

    python tools/ton_sec_test.py

Neden test şart: ton seçimi tezde "denetlenebilir" diye savunuluyor. Bir
kalıp eklenince başka bir kategoriyi bozmadığını göstermek gerekir.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import risk_communication as rc  # noqa: E402

# (kullanıcı metni, endişe düzeyi, beklenen ton)
DURUMLAR = [
    # --- yatıştırıcı: duygusal yük ---
    ("Çok korkuyorum, geceleri uyuyamıyorum", "orta", "yatistirici"),
    ("Panikliyorum, evim yıkılacak mı", "orta", "yatistirici"),
    ("Çocuklarım için korkuyorum", "düşük", "yatistirici"),
    ("Bu haberden sonra çok tedirginim", "orta", "yatistirici"),

    # --- eyleme yönelik: somut adım talebi ---
    ("Ne yapmalıyım, nereden başlayayım?", "orta", "eyleme_yonelik"),
    ("Afet çantası hazırlamalı mıyım, hangi önlemleri alayım", "orta", "eyleme_yonelik"),
    ("Nasıl hazırlanırım", "yüksek", "eyleme_yonelik"),
    ("Taşınmalı mıyım", "orta", "eyleme_yonelik"),

    # --- bilgilendirici: açıklama/yöntem talebi ---
    ("Bu skor nasıl hesaplandı, hangi faktörler etkili?", "orta", "bilgilendirici"),
    ("Risk skorum ne anlama geliyor", "orta", "bilgilendirici"),
    ("Hangi verileri kullandınız", "yüksek", "bilgilendirici"),

    # --- ipucu yok: endişe düzeyine düşer (deneydeki eşleme) ---
    ("", "yüksek", "yatistirici"),
    ("", "orta", "bilgilendirici"),
    ("", "düşük", "eyleme_yonelik"),
    ("Merhaba", "orta", "bilgilendirici"),

    # --- tuzak: "nasıl" iki kategoride de geçer, kalıp ayırmalı ---
    ("Nasıl hesaplandı bu", "orta", "bilgilendirici"),
    ("Nasıl korunurum", "orta", "eyleme_yonelik"),
]


def calistir() -> int:
    basarisiz = 0
    for metin, endise, beklenen in DURUMLAR:
        sonuc = rc.ton_sec(metin, endise)
        if sonuc["ton"] != beklenen:
            basarisiz += 1
            print(f"✗ {metin!r} [{endise}]")
            print(f"    beklenen={beklenen} bulunan={sonuc['ton']} "
                  f"skorlar={sonuc['skorlar']}")
        else:
            print(f"✓ {sonuc['ton']:16} <- {metin[:42]!r} [{endise}] "
                  f"({sonuc['kaynak']})")
    toplam = len(DURUMLAR)
    print(f"\n{toplam - basarisiz}/{toplam} durum geçti")
    return 1 if basarisiz else 0


if __name__ == "__main__":
    sys.exit(calistir())
