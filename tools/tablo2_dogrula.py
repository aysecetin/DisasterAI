"""
tablo2_dogrula.py — Raporun Tablo 2 değerlerini veriden yeniden üretir

NEDEN VAR
---------
Sonuç raporunun Tablo 2'si (ince ayarlı modelin 40 test örneği üzerindeki
değerlendirme sonuçları) altı satır içeriyor. Bu satırlardan yalnızca
"uydurma sayı" ölçütü Kaggle defterinde (`tools/model_test_kaggle.ipynb`)
hesaplanıyordu; kalan dört satır (risk skorunu aktaran yanıt oranı, seviye
adı tutarlılığı, eski güvenlik tavsiyesi, ortalama uzunluk) 30.08.2026'da
sohbet içinde tek seferlik hesaplanmış ve depoda hesaplayan kod kalmamıştı.

Bu script o açığı kapatır: Tablo 2'nin **altı satırını da** modelin ham
çıktılarından yeniden üretir ve rapordaki değerlerle karşılaştırır.

ÖLÇÜTLER
--------
1. **Olgu sadakati** — `uydurma` alanı boş olan yanıtların oranı. Uydurma
   sayı, metinde geçip de analiz girdisinde karşılığı bulunmayan sayıdır.
2. **Uydurma sayı / toplam sayı** — metinlerdeki tüm sayılar içinde
   karşılıksız olanların payı.
3. **Risk skorunu aktaran yanıt** — metinde "X,XX/5" kalıbının geçmesi.
   Raporun "ton değişir, olgular değişmez" ilkesinin asgari koşulu.
4. **Seviye adı tutarlılığı** — skoru aktaran metinlerde, skorun karşılığı
   olan seviye adının ("düşük" <3, "orta" 3–4, "yüksek" ≥4) doğru
   kullanılması. `rc.dogrula()` içindeki kuralla aynı mantık.
5. **Eski güvenlik tavsiyesi** — güncelliğini yitirmiş "kapı çerçevesine
   sığının" yönergesini içeren metin sayısı (AFAD: çök-kapan-tutun).
6. **Ortalama uzunluk** — sözcük sayısı.

GİRDİ
-----
  outputs/model_degerlendirme/test_sonuclari.json   (40 üretim, 30.08.2026)

ÇALIŞTIRMA
----------
    python tools/tablo2_dogrula.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJE_KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJE_KOK / "src"))

URETIM = PROJE_KOK / "outputs" / "model_degerlendirme" / "test_sonuclari.json"
CIKTI = PROJE_KOK / "outputs" / "model_degerlendirme" / "tablo2_olcumu.md"

# Rapordaki Tablo 2 değerleri — script bunları yeniden üretmeli
RAPOR = {
    "olgu_sadakati": "%97,5 (39/40)",
    "uydurma_oran": "%0,3 (1/390)",
    "skoru_aktaran": "%87,5 (35/40)",
    "seviye_tutarli": "%80,0 (28/35)",
    "eski_tavsiye": "0/40",
    "ortalama_uzunluk": "109 kelime",
}

SAYI = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)(?![\w])")
SKOR_KALIBI = re.compile(r"(\d[.,]\d{1,2})\s*/\s*5")
ESKI_TAVSIYE = ("kapı çerçeve", "kapı kiriş")


def seviye_adi(skor: float) -> str:
    return "yüksek" if skor >= 4.0 else ("orta" if skor >= 3.0 else "düşük")


def seviye_tutarli_mi(metin: str) -> bool | None:
    """Skoru aktaran metinlerde seviye adı doğru mu? Skor yoksa None.

    `rc.dogrula()` ile aynı kural: doğru seviye adı metinde hiç geçmiyorsa ve
    yanlış bir seviye adı 'risk/seviye/düzey' bağlamında geçiyorsa tutarsız.
    """
    m = SKOR_KALIBI.search(metin)
    if not m:
        return None
    beklenen = seviye_adi(float(m.group(1).replace(",", ".")))
    kucuk = metin.lower()
    if beklenen in kucuk:
        return True
    for yanlis in {"düşük", "orta", "yüksek"} - {beklenen}:
        if (f"{yanlis} risk" in kucuk or f"{yanlis} seviye" in kucuk
                or f"{yanlis} düzey" in kucuk or f"“{yanlis}”" in kucuk):
            return False
    return True


def olc() -> dict:
    uretimler = json.loads(URETIM.read_text(encoding="utf-8"))
    n = len(uretimler)

    uydurma_iceren = sum(1 for u in uretimler if u["uydurma"])
    toplam_sayi = sum(len(set(
        round(float(m.group(1).replace(",", ".")), 2)
        for m in SAYI.finditer(u["cikti"])
    )) for u in uretimler)
    toplam_uydurma = sum(len(u["uydurma"]) for u in uretimler)

    skoru_aktaran = sum(1 for u in uretimler if SKOR_KALIBI.search(u["cikti"]))
    seviye = [seviye_tutarli_mi(u["cikti"]) for u in uretimler]
    seviye_olculen = [s for s in seviye if s is not None]
    seviye_dogru = sum(1 for s in seviye_olculen if s)

    eski = sum(1 for u in uretimler
               if any(k in u["cikti"].lower() for k in ESKI_TAVSIYE))
    uzunluklar = [len(u["cikti"].split()) for u in uretimler]

    return {
        "n": n,
        "olgu_sadakati": (n - uydurma_iceren, n),
        "uydurma": (toplam_uydurma, toplam_sayi),
        "skoru_aktaran": (skoru_aktaran, n),
        "seviye": (seviye_dogru, len(seviye_olculen)),
        "eski_tavsiye": (eski, n),
        "ortalama_uzunluk": sum(uzunluklar) / len(uzunluklar),
    }


def bicim(s: dict) -> dict:
    a, b = s["olgu_sadakati"]
    c, dd = s["uydurma"]
    e, f = s["skoru_aktaran"]
    g, h = s["seviye"]
    return {
        "olgu_sadakati": f"%{100*a/b:.1f} ({a}/{b})".replace(".", ","),
        "uydurma_oran": f"%{100*c/dd:.1f} ({c}/{dd})".replace(".", ","),
        "skoru_aktaran": f"%{100*e/f:.1f} ({e}/{f})".replace(".", ","),
        "seviye_tutarli": f"%{100*g/h:.1f} ({g}/{h})".replace(".", ","),
        "eski_tavsiye": f"{s['eski_tavsiye'][0]}/{s['eski_tavsiye'][1]}",
        "ortalama_uzunluk": f"{s['ortalama_uzunluk']:.0f} kelime",
    }


ETIKETLER = {
    "olgu_sadakati": "Olgu sadakati (uydurma sayı içermeyen yanıt)",
    "uydurma_oran": "Uydurma sayı / üretilen toplam sayı",
    "skoru_aktaran": "Kompozit risk skorunu metinde aktaran yanıt",
    "seviye_tutarli": "Risk seviyesi adının skorla tutarlılığı",
    "eski_tavsiye": "Güncelliğini yitirmiş güvenlik tavsiyesi",
    "ortalama_uzunluk": "Ortalama yanıt uzunluğu",
}


def main() -> None:
    if not URETIM.exists():
        raise SystemExit(f"Girdi bulunamadı: {URETIM}")
    s = olc()
    olculen = bicim(s)

    sat = ["# Tablo 2 — Ölçümün Yeniden Üretimi\n",
           "> `tools/tablo2_dogrula.py` çıktısı; elle düzenlemeyin.\n",
           f"Kaynak: `outputs/model_degerlendirme/test_sonuclari.json` "
           f"({s['n']} test üretimi).\n",
           "| Ölçüt | Raporda | Bu ölçüm | Durum |", "|---|---|---|---|"]

    uyumsuz = 0
    print(f"{'Ölçüt':<46} {'Raporda':<18} {'Ölçülen':<18}")
    print("-" * 84)
    for anahtar, etiket in ETIKETLER.items():
        beklenen, bulunan = RAPOR[anahtar], olculen[anahtar]
        ayni = beklenen == bulunan
        uyumsuz += not ayni
        print(f"{etiket:<46} {beklenen:<18} {bulunan:<18} {'✓' if ayni else '✗'}")
        sat.append(f"| {etiket} | {beklenen} | {bulunan} | "
                   f"{'✓ aynı' if ayni else '✗ FARKLI'} |")

    sat.append("")
    if uyumsuz:
        sat.append(f"**{uyumsuz} satır rapordaki değerden farklı — raporu "
                   "güncelleyin veya farkın nedenini araştırın.**\n")
    else:
        sat.append("Tablo 2'nin altı satırı da ham çıktılardan yeniden "
                   "üretilmiştir.\n")

    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    CIKTI.write_text("\n".join(sat), encoding="utf-8")

    print()
    if uyumsuz:
        print(f"⚠ {uyumsuz} satır uyuşmuyor.")
    else:
        print("✓ Tablo 2'nin tamamı yeniden üretildi.")
    print(f"Yazıldı: {CIKTI}")


if __name__ == "__main__":
    main()
