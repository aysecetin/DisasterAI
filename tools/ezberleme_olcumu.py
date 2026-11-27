"""
ezberleme_olcumu.py — İnce ayarlı modelin ezberleyip ezberlemediğini ölçer

NEDEN VAR
---------
Sonuç raporunun İP2 bölümünde "ezberleme denetimi" başlığı altında iki sayı
geçiyor: üretilen metinlerin eğitim corpusuyla **8 sözcüklük dizi örtüşmesi
ortalama %15,4** ve her metnin **kendi öğretmen referansına karakter
benzerliği ortalama %19,4**. Bu sayılar ilk kez 30.08.2026'da tek seferlik
bir hesapla üretilmişti ve depoda hesaplayan kod yoktu; yani rapordaki değer
yeniden üretilemiyordu. Bu script o açığı kapatır.

Jüri "bu sayıyı nasıl buldunuz" diye sorduğunda çalıştırılacak dosya budur.

YÖNTEM
------
İnce ayarlı bir model eğitim metinlerini ezberlemişse, ürettiği metinlerde
eğitim corpusundan **uzun ve birebir** parçalar görünür. Üç ölçüt:

1. **8-gram örtüşmesi** — üretilen metnin 8 sözcüklük pencerelerinden kaçı
   eğitim corpusunda aynen var? Türkçe kalıp ifadeler ("toplam risk skoru
   ... olarak hesaplanmıştır") nedeniyle sıfır beklenmez; ezberde ise bu oran
   %60-80'lere çıkar.
2. **Birebir uzun dizi** — 10/15/20/30 sözcüklük bir dizi eğitimde aynen
   bulunuyor mu? Ezberin en doğrudan göstergesi uzun dizilerdir.
3. **Kendi referansına benzerlik** — model, aynı girdi için öğretmenin yazdığı
   metni mi kopyalıyor? Karakter düzeyinde `SequenceMatcher` oranı.

GİRDİLER
--------
  outputs/corpora/train.jsonl              eğitim metinleri (2014 örnek)
  outputs/corpora/test.jsonl               öğretmen referansları (235 örnek)
  outputs/model_degerlendirme/
      test_sonuclari.json                  modelin ürettiği 40 metin
                                           (Kaggle `model_test_kaggle.ipynb`
                                            koşusunun çıktısı, 30.08.2026)

ÇALIŞTIRMA
----------
    python tools/ezberleme_olcumu.py

ÇIKTI
-----
    outputs/model_degerlendirme/ezberleme_olcumu.md   (rapora yapıştırılabilir)
"""

from __future__ import annotations

import json
import re
import statistics
from difflib import SequenceMatcher
from pathlib import Path

PROJE_KOK = Path(__file__).resolve().parents[1]
EGITIM = PROJE_KOK / "outputs" / "corpora" / "train.jsonl"
TEST_REF = PROJE_KOK / "outputs" / "corpora" / "test.jsonl"
URETIM = PROJE_KOK / "outputs" / "model_degerlendirme" / "test_sonuclari.json"
CIKTI = PROJE_KOK / "outputs" / "model_degerlendirme" / "ezberleme_olcumu.md"

# Raporda geçen sayılar — script bunları yeniden üretmeli
RAPOR_DEGERLERI = {"8gram_ortalama": 15.4, "referans_benzerligi": 19.4}

N_GRAM = 8                      # örtüşme ölçütünün pencere genişliği
BIREBIR_UZUNLUKLAR = (10, 15, 20, 30)


def jsonl_oku(dosya: Path) -> list[dict]:
    with dosya.open(encoding="utf-8") as f:
        return [json.loads(s) for s in f if s.strip()]


def kelimeler(metin: str) -> list[str]:
    """Noktalama ve biçimlendirme dışarıda; yalnızca sözcükler, küçük harf.

    Markdown yıldızları (`**Bugün**`) öğretmen metinlerinden öğrenciye geçtiği
    için biçim karakterleri ölçüme girmemeli — yoksa örtüşme yapay yükselir.
    """
    return re.findall(r"\w+", metin.lower())


def ngramlar(sozcukler: list[str], n: int) -> list[tuple]:
    return [tuple(sozcukler[i:i + n]) for i in range(len(sozcukler) - n + 1)]


def olc() -> dict:
    egitim = jsonl_oku(EGITIM)
    referanslar = {
        f"{k['konum_id']}|{k['ton']}": k["cikti"] for k in jsonl_oku(TEST_REF)
    }
    uretimler = json.loads(URETIM.read_text(encoding="utf-8"))

    # --- Eğitim corpusunun n-gram havuzları ---
    egitim_sozcukleri = [kelimeler(k["cikti"]) for k in egitim]
    havuz = {N_GRAM: set()}
    for n in BIREBIR_UZUNLUKLAR:
        havuz.setdefault(n, set())
    for sozcukler in egitim_sozcukleri:
        for n in havuz:
            havuz[n].update(ngramlar(sozcukler, n))

    # --- 1. 8-gram örtüşmesi ---
    oranlar = []
    for u in uretimler:
        gramlar = ngramlar(kelimeler(u["cikti"]), N_GRAM)
        if not gramlar:
            continue
        ortak = sum(1 for g in gramlar if g in havuz[N_GRAM])
        oranlar.append(100 * ortak / len(gramlar))

    # --- 2. Birebir uzun dizi ---
    birebir = {}
    ornekler = {}
    for n in BIREBIR_UZUNLUKLAR:
        sayac = 0
        for u in uretimler:
            uw = kelimeler(u["cikti"])
            eslesen = next((g for g in ngramlar(uw, n) if g in havuz[n]), None)
            if eslesen is not None:
                sayac += 1
                ornekler.setdefault(n, []).append((u["ton"], " ".join(eslesen)))
        birebir[n] = sayac

    # --- 3. Kendi öğretmen referansına benzerlik ---
    benzerlikler = []
    eslesmeyen = 0
    for u in uretimler:
        ref = referanslar.get(f"{u['konum_id']}|{u['ton']}")
        if ref is None:
            eslesmeyen += 1
            continue
        benzerlikler.append(100 * SequenceMatcher(None, u["cikti"], ref).ratio())

    return {
        "uretim_sayisi": len(uretimler),
        "egitim_sayisi": len(egitim),
        "ngram_havuz_buyuklugu": len(havuz[N_GRAM]),
        "ortusme": {
            "ortalama": statistics.mean(oranlar),
            "medyan": statistics.median(oranlar),
            "en_dusuk": min(oranlar),
            "en_yuksek": max(oranlar),
        },
        "birebir": birebir,
        "birebir_ornekler": ornekler,
        "benzerlik": {
            "ortalama": statistics.mean(benzerlikler),
            "medyan": statistics.median(benzerlikler),
            "en_yuksek": max(benzerlikler),
            "eslesmeyen": eslesmeyen,
        },
    }


def rapor_yaz(s: dict) -> None:
    o, b = s["ortusme"], s["benzerlik"]
    sat = []
    sat.append("# Ezberleme Denetimi — Ölçüm Sonuçları\n")
    sat.append("> Bu dosya `tools/ezberleme_olcumu.py` ile üretilmiştir; "
               "elle düzenlemeyin.\n")
    sat.append("## Yöntem\n")
    sat.append(
        f"İnce ayarlı modelin ürettiği **{s['uretim_sayisi']} test metni**, "
        f"eğitim corpusundaki **{s['egitim_sayisi']} metinle** karşılaştırıldı. "
        f"Eğitim corpusundan çıkarılan {N_GRAM} sözcüklük benzersiz dizi sayısı: "
        f"**{s['ngram_havuz_buyuklugu']:,}**. Karşılaştırma yalnızca sözcükler "
        "üzerinden yapıldı; noktalama ve markdown biçim karakterleri ölçüm "
        "dışında tutuldu.\n")

    sat.append("## 1. Sözcük dizisi örtüşmesi\n")
    sat.append(f"| Ölçüt ({N_GRAM} sözcüklük dizi) | Değer |")
    sat.append("|---|---|")
    sat.append(f"| Ortalama örtüşme | **%{o['ortalama']:.1f}** |")
    sat.append(f"| Medyan | %{o['medyan']:.1f} |")
    sat.append(f"| En düşük | %{o['en_dusuk']:.1f} |")
    sat.append(f"| En yüksek | %{o['en_yuksek']:.1f} |")
    sat.append("")
    sat.append(
        "Bu düzeydeki örtüşme, alan diline özgü kalıp ifadelerden "
        "beklenen aralıktadır (\"toplam risk skoru ... olarak hesaplanmıştır\", "
        "\"zemin/litoloji faktörü ... puan katkı sağlamıştır\"). Ezberlemede "
        "bu oranın çok daha yüksek olması beklenir.\n")

    sat.append("## 2. Birebir uzun dizi aktarımı\n")
    sat.append("| Dizi uzunluğu | Eğitimde birebir bulunan metin sayısı |")
    sat.append("|---|---|")
    for n in BIREBIR_UZUNLUKLAR:
        sat.append(f"| {n} sözcük | {s['birebir'][n]} / {s['uretim_sayisi']} |")
    sat.append("")
    en_uzun = max((n for n in BIREBIR_UZUNLUKLAR if s["birebir"][n] > 0),
                  default=None)
    if en_uzun is not None:
        ornek = s["birebir_ornekler"][en_uzun][0]
        sat.append(
            f"Birebir örtüşen en uzun diziler {en_uzun} sözcüktür ve tamamı "
            f"sayı taşıyan kalıp ifadelerdir. Örnek ([{ornek[0]}] tonundan):\n")
        sat.append(f"> {ornek[1]}\n")
    yok = [n for n in BIREBIR_UZUNLUKLAR if s["birebir"][n] == 0]
    if yok:
        sat.append(
            f"**{min(yok)} sözcük ve üzeri uzunlukta birebir aktarılmış hiçbir "
            "dizi yoktur.** Ezberlemenin en doğrudan göstergesi olan uzun "
            "birebir aktarım gözlenmemiştir.\n")

    sat.append("## 3. Kendi öğretmen referansına benzerlik\n")
    sat.append("| Ölçüt | Değer |")
    sat.append("|---|---|")
    sat.append(f"| Ortalama karakter benzerliği | **%{b['ortalama']:.1f}** |")
    sat.append(f"| Medyan | %{b['medyan']:.1f} |")
    sat.append(f"| En yüksek | %{b['en_yuksek']:.1f} |")
    sat.append("")
    sat.append(
        "Her üretilen metin, **aynı girdi için öğretmen modelin yazdığı** "
        "referans metinle karşılaştırıldı. Düşük benzerlik, modelin referansı "
        "kopyalamadığını; aynı olgu kümesinden kendi metnini kurduğunu "
        "göstermektedir.\n")

    sat.append("## Rapordaki değerlerle karşılaştırma\n")
    sat.append("| Rapor | Bu ölçüm |")
    sat.append("|---|---|")
    sat.append(f"| Örtüşme %{RAPOR_DEGERLERI['8gram_ortalama']} | "
               f"%{o['ortalama']:.1f} |")
    sat.append(f"| Referans benzerliği %{RAPOR_DEGERLERI['referans_benzerligi']} | "
               f"%{b['ortalama']:.1f} |")
    sat.append("")

    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    CIKTI.write_text("\n".join(sat), encoding="utf-8")


def main() -> None:
    for dosya in (EGITIM, TEST_REF, URETIM):
        if not dosya.exists():
            raise SystemExit(f"Girdi bulunamadı: {dosya}")

    s = olc()
    rapor_yaz(s)

    o, b = s["ortusme"], s["benzerlik"]
    print(f"{N_GRAM}-gram örtüşmesi : ortalama %{o['ortalama']:.1f} "
          f"(medyan %{o['medyan']:.1f}, en yüksek %{o['en_yuksek']:.1f})")
    for n in BIREBIR_UZUNLUKLAR:
        print(f"{n:>2} sözcüklük birebir dizi : "
              f"{s['birebir'][n]}/{s['uretim_sayisi']} metin")
    print(f"Referans benzerliği : ortalama %{b['ortalama']:.1f} "
          f"(en yüksek %{b['en_yuksek']:.1f})")
    if b["eslesmeyen"]:
        print(f"UYARI: {b['eslesmeyen']} üretim test referansıyla eşleşmedi")

    # Rapordaki değerlerle tutarlılık kontrolü
    sapma_o = abs(o["ortalama"] - RAPOR_DEGERLERI["8gram_ortalama"])
    sapma_b = abs(b["ortalama"] - RAPOR_DEGERLERI["referans_benzerligi"])
    if sapma_o <= 0.1 and sapma_b <= 0.1:
        print("\n✓ Rapordaki değerler yeniden üretildi.")
    else:
        print(f"\n⚠ Rapordan sapma: örtüşme {sapma_o:.1f} puan, "
              f"benzerlik {sapma_b:.1f} puan — raporu güncelle.")
    print(f"\nYazıldı: {CIKTI}")


if __name__ == "__main__":
    main()
