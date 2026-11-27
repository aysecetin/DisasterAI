"""
tablo_uret.py — reclass_tables.py'yi teze konulabilir tabloya dönüştürür
========================================================================

Çalıştır:
    ayse-env/bin/python tools/tablo_uret.py

Çıktı:
    outputs/yeniden_siniflandirma_tablolari.md

Amaç: kodla tez metni arasındaki tutarsızlığı önlemek. Tabloyu elle kopyalamak
yerine buradan üret; kodda bir eşiği değiştirdiğinde tez tablosu da değişir.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import reclass_tables as rt  # noqa: E402

CIKTI = PROJECT_ROOT / "outputs" / "yeniden_siniflandirma_tablolari.md"

ETIKET_ACIKLAMA = {
    "K": "Kaynaklı — yayımlanmış bir çalışmadan alınmış/ölçeklenmiş",
    "U": "Uyarlama — yayımlanmış şemalardan uyarlanmış, birebir alıntı değil",
    "E": "Eksper ataması — literatürde karşılığı bulunamadı",
}

FAKTOR_BASLIK = {
    "Fay_Hattı_Uzaklığı": "Fay hattına uzaklık (m)",
    "Akarsu_Uzaklığı": "Akarsuya uzaklık (m)",
    "Eğim": "Eğim (derece)",
    "Litoloji": "Litoloji (Formasyon)",
    "Arazi_Kullanımı": "Arazi kullanımı",
}


# Etiket okuyucu, tabloların kendi kaynağında durur (src/reclass_tables.py);
# arayüzdeki /api/yontem ucu da aynı fonksiyonu kullanır.
_etiketleri_oku = rt.etiketleri_oku


SABIT_ADLARI = {
    ("DEPREM", "Fay_Hattı_Uzaklığı"): "FAY_MESAFE_SINIFLARI",
    ("DEPREM", "Akarsu_Uzaklığı"): "AKARSU_MESAFE_SINIFLARI_DEPREM",
    ("DEPREM", "Eğim"): "EGIM_SINIFLARI_DEPREM",
    ("DEPREM", "Litoloji"): "LITOLOJI_TBDY_SINIFI",
    ("DEPREM", "Arazi_Kullanımı"): "ARAZI_SKORLARI_DEPREM",
    ("HEYELAN", "Fay_Hattı_Uzaklığı"): "FAY_MESAFE_SINIFLARI_HEYELAN",
    ("HEYELAN", "Akarsu_Uzaklığı"): "AKARSU_MESAFE_SINIFLARI_HEYELAN",
    ("HEYELAN", "Eğim"): "EGIM_SINIFLARI_HEYELAN",
    ("HEYELAN", "Litoloji"): "LITOLOJI_SKORLARI_HEYELAN",
    ("HEYELAN", "Arazi_Kullanımı"): "ARAZI_SKORLARI_HEYELAN",
    ("SEL", "Fay_Hattı_Uzaklığı"): "FAY_MESAFE_SINIFLARI_SEL",
    ("SEL", "Akarsu_Uzaklığı"): "AKARSU_MESAFE_SINIFLARI_SEL",
    ("SEL", "Eğim"): "EGIM_SINIFLARI_SEL",
    ("SEL", "Litoloji"): "LITOLOJI_SKORLARI_SEL",
    ("SEL", "Arazi_Kullanımı"): "ARAZI_SKORLARI_SEL",
}


def _aralik_metni(lo, hi) -> str:
    if hi == float("inf"):
        return f"> {lo:,.0f}".replace(",", ".")
    return f"{lo:,.0f} – {hi:,.0f}".replace(",", ".")


def main() -> int:
    etiketler = _etiketleri_oku()
    sat: list[str] = []
    ek = sat.append

    ek("# Yeniden Sınıflandırma Tabloları")
    ek("")
    ek("Seferihisar (İzmir) afet risk analizi — ağırlıklı çakıştırmada kullanılan")
    ek("faktörlerin 1–5 risk puanına dönüştürülme kuralları.")
    ek("")
    ek("Bu dosya `src/reclass_tables.py` dosyasından otomatik üretilmiştir.")
    ek("Elle düzenleme; kodu değiştir ve `tools/tablo_uret.py` scriptini yeniden çalıştır.")
    ek("")
    ek("## Güven seviyeleri")
    ek("")
    ek("| Etiket | Anlamı |")
    ek("|---|---|")
    for k, v in ETIKET_ACIKLAMA.items():
        ek(f"| **[{k}]** | {v} |")
    ek("")
    ek("> **[E]** etiketli değerler tezde *\"tarafımızca atanmıştır\"* diye belirtilmeli.")
    ek("> Bunları kaynaklı gibi sunmak akademik hata olur.")
    ek("")

    for afet in ("DEPREM", "HEYELAN", "SEL"):
        ek(f"## {afet.capitalize()}")
        ek("")
        for faktor, tablo in rt.TABLOLAR[afet].items():
            sabit = SABIT_ADLARI.get((afet, faktor), "")
            ek(f"### {FAKTOR_BASLIK.get(faktor, faktor)}")
            ek("")
            if isinstance(tablo, list):
                ek("| Sınıf | Risk puanı | Dayanak |")
                ek("|---|---|---|")
                for lo, hi, puan in tablo:
                    hi_s = "INF" if hi == float("inf") else f"{hi:g}"
                    anahtar = f"{sabit}|({lo:g},{hi_s},{puan:.1f})"
                    not_ = etiketler.get(anahtar, "")
                    ek(f"| {_aralik_metni(lo, hi)} | {puan:g} | {not_} |")
            else:
                ek("| Sınıf | Risk puanı | Dayanak |")
                ek("|---|---|---|")
                for ad, puan in sorted(tablo.items(), key=lambda kv: -kv[1]):
                    if sabit == "LITOLOJI_TBDY_SINIFI":
                        sinif = rt.LITOLOJI_TBDY_SINIFI.get(ad, "")
                        anahtar = f'{sabit}|"{ad}":"{sinif}"'
                    else:
                        anahtar = f'{sabit}|"{ad}":{puan:.1f}'
                    not_ = etiketler.get(anahtar, "")
                    ek(f"| {ad} | {puan:g} | {not_} |")
            ek("")

    ek("## Ağırlıklar")
    ek("")
    ek("Analizde **literatür tabanlı** set kullanılıyor (varsayılan). Projenin ilk")
    ek("sürümündeki ağırlıklar duyarlılık analizi için korundu; `AGIRLIK_SETI=mevcut`")
    ek("ortam değişkeniyle o sete geçilebilir. Karşılaştırma için:")
    ek("`python tools/agirlik_karsilastir.py`")
    ek("")
    for afet in ("DEPREM", "HEYELAN", "SEL"):
        ek(f"### {afet.capitalize()}")
        ek("")
        ek("| Faktör | Eski (mevcut) | **Literatür tabanlı (kullanılan)** |")
        ek("|---|---|---|")
        mv, lt = rt.AGIRLIKLAR_MEVCUT[afet], rt.AGIRLIKLAR_LITERATUR[afet]
        for f in sorted(set(mv) | set(lt), key=lambda k: -lt.get(k, 0)):
            ek(f"| {FAKTOR_BASLIK.get(f, f)} | {mv.get(f, 0):.2f} | {lt.get(f, 0):.2f} |")
        ek("")

    ek("## Atıf verilmemesi gereken kaynaklar")
    ek("")
    ek("Literatür taramasında iç çelişki tespit edilen çalışmalar. Tabloları")
    ek("metinlerindeki ifadeyle uyuşmuyor; bu haliyle atıf verilmesi risklidir.")
    ek("")
    ek("| Kaynak | Sorun |")
    ek("|---|---|")
    for k, v in rt.ATIF_VERME.items():
        ek(f"| {k} | {v} |")
    ek("")

    ek("## Kaynakça")
    ek("")
    for kaynak in rt.KAYNAKLAR:
        ek(f"- {kaynak}")
        ek("")

    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    CIKTI.write_text("\n".join(sat), encoding="utf-8")

    kk = sum(1 for v in etiketler.values() if v.startswith("[K]"))
    ku = sum(1 for v in etiketler.values() if v.startswith("[U]"))
    ke = sum(1 for v in etiketler.values() if v.startswith("[E]"))
    print(f"✓ Yazıldı: outputs/{CIKTI.name}")
    print(f"  Kaynaklı [K]: {kk}   Uyarlama [U]: {ku}   Eksper [E]: {ke}")
    print(f"  Kaynakça: {len(rt.KAYNAKLAR)} kayıt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
