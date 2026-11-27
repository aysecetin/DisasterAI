# -*- coding: utf-8 -*-
"""
Ton doğruluğu etiketlemesinin analizi: Fleiss' kappa + doğruluk.

Protokol: docs/deney/ton_dogrulugu_protokolu.md

Kullanım:
    ayse-env/bin/python tools/ton_dogrulugu_analiz.py <doldurulmus_form.csv>

Girdi CSV sütunları: metin_kodu, degerlendirici, etiket (B/E/Y/T), guven
Cevap anahtarı: outputs/ton_etiketleme/cevap_anahtari.csv (paket scripti üretir)

Hesaplananlar:
  - Fleiss' kappa (Fleiss, 1971) — 4 kategori, tüm metinler
  - Landis & Koch (1977) yorum bandı
  - Çoğunluk-oyu doğruluğu (yalnız hedefli 3 ton × 3 senaryo metinleri)
  - Karışıklık matrisi (gerçek tür × verilen etiket)
  - Ham metinlerin etiket dağılımı (yan bulgu)
"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJE_KOK = Path(__file__).resolve().parent.parent
ANAHTAR = PROJE_KOK / "outputs" / "ton_etiketleme" / "cevap_anahtari.csv"

KATEGORILER = ["B", "E", "Y", "T"]
TUR2ETIKET = {"bilgilendirici": "B", "eyleme_yonelik": "E",
              "yatistirici": "Y", "ham": "T"}
ETIKET_ADI = {"B": "Bilgilendirici", "E": "Eyleme yönelik",
              "Y": "Yatıştırıcı", "T": "Ton yok/karışık"}


def fleiss_kappa(matris):
    """matris: her metin için {kategori: oy sayısı}. Tüm metinlerde
    değerlendirici sayısı eşit olmalı."""
    n_oy = {sum(sat.values()) for sat in matris}
    if len(n_oy) != 1:
        sys.exit(f"HATA: metin başına oy sayıları eşit değil: {sorted(n_oy)} "
                 "— her değerlendirici her metni etiketlemeli.")
    n = n_oy.pop()
    if n < 2:
        sys.exit("HATA: Fleiss' kappa için metin başına en az 2 oy gerekir.")
    N = len(matris)
    p_j = {k: sum(sat.get(k, 0) for sat in matris) / (N * n) for k in KATEGORILER}
    P_i = [(sum(v * v for v in sat.values()) - n) / (n * (n - 1)) for sat in matris]
    P_bar = sum(P_i) / N
    P_e = sum(p * p for p in p_j.values())
    if P_e >= 1.0:
        return 1.0, n
    return (P_bar - P_e) / (1 - P_e), n


def landis_koch(k):
    for esik, ad in [(0.80, "neredeyse tam uyum"), (0.60, "önemli uyum"),
                     (0.40, "orta uyum"), (0.20, "vasat uyum"),
                     (0.00, "zayıf uyum")]:
        if k > esik:
            return ad
    return "uyum yok / şansın altında"


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    form_yolu = Path(sys.argv[1])
    if not form_yolu.exists():
        sys.exit(f"Form bulunamadı: {form_yolu}")
    if not ANAHTAR.exists():
        sys.exit(f"Cevap anahtarı yok: {ANAHTAR} — önce tools/ton_etiketleme_paketi.py")

    anahtar = {}
    with ANAHTAR.open(encoding="utf-8") as f:
        for sat in csv.DictReader(f):
            anahtar[sat["metin_kodu"]] = sat["gercek_tur"]

    oylar = defaultdict(dict)   # metin_kodu -> {degerlendirici: etiket}
    with form_yolu.open(encoding="utf-8") as f:
        for sat in csv.DictReader(f):
            kod = sat["metin_kodu"].strip()
            deg = sat["degerlendirici"].strip()
            et = sat["etiket"].strip().upper()
            if not (kod and deg and et):
                continue
            if kod not in anahtar:
                sys.exit(f"HATA: cevap anahtarında olmayan kod: {kod}")
            if et not in KATEGORILER:
                sys.exit(f"HATA: geçersiz etiket '{et}' ({kod}, {deg}) — "
                         f"geçerli: {'/'.join(KATEGORILER)}")
            if deg in oylar[kod]:
                sys.exit(f"HATA: {deg} {kod} için iki kez oy vermiş.")
            oylar[kod][deg] = et

    if set(oylar) != set(anahtar):
        eksik = sorted(set(anahtar) - set(oylar))
        sys.exit(f"HATA: formda hiç oyu olmayan metin(ler): {', '.join(eksik)}")

    kodlar = sorted(anahtar)
    matris = [Counter(oylar[k].values()) for k in kodlar]
    kappa, n = fleiss_kappa(matris)
    degerlendiriciler = sorted({d for k in oylar for d in oylar[k]})

    print("=" * 64)
    print("TON DOĞRULUĞU ANALİZİ")
    print("=" * 64)
    print(f"Metin: {len(kodlar)}  Değerlendirici: {len(degerlendiriciler)} "
          f"({', '.join(degerlendiriciler)})  Kategori: {len(KATEGORILER)}")
    print(f"\nFleiss' kappa = {kappa:.3f}  → {landis_koch(kappa)} "
          "(Landis & Koch, 1977)")

    # Çoğunluk oyu + doğruluk (yalnız tonlu metinler)
    print("\n--- Çoğunluk oyu vs hedeflenen tür ---")
    dogru, toplam = 0, 0
    karisiklik = defaultdict(Counter)   # gercek etiket -> verilen etiket sayacı
    for kod in kodlar:
        gercek = TUR2ETIKET[anahtar[kod]]
        sayim = Counter(oylar[kod].values())
        for et, adet in sayim.items():
            karisiklik[gercek][et] += adet
        en_cok = sayim.most_common()
        cogunluk = en_cok[0][0]
        beraberlik = len(en_cok) > 1 and en_cok[0][1] == en_cok[1][1]
        if anahtar[kod] == "ham":
            continue
        toplam += 1
        isabet = (cogunluk == gercek) and not beraberlik
        dogru += isabet
        durum = "✓" if isabet else ("beraberlik" if beraberlik else "✗")
        print(f"  {kod}  hedef={ETIKET_ADI[gercek]:<15} "
              f"çoğunluk={ETIKET_ADI[cogunluk]:<15} {durum}")
    print(f"\nDoğruluk (tonlu metinler): {dogru}/{toplam} "
          f"= %{100 * dogru / toplam:.0f}" if toplam else "\nTonlu metin yok.")

    print("\n--- Karışıklık matrisi (satır: gerçek, sütun: verilen oy) ---")
    print("               " + "".join(f"{ETIKET_ADI[k][:12]:>14}" for k in KATEGORILER))
    for gercek in KATEGORILER:
        satir = karisiklik.get(gercek, Counter())
        print(f"{ETIKET_ADI[gercek]:<15}" +
              "".join(f"{satir.get(k, 0):>14}" for k in KATEGORILER))

    ham_kodlar = [k for k in kodlar if anahtar[k] == "ham"]
    if ham_kodlar:
        dagilim = Counter(et for k in ham_kodlar for et in oylar[k].values())
        print("\n--- Ham (yönergesiz) metinlere verilen etiketler ---")
        for et in KATEGORILER:
            print(f"  {ETIKET_ADI[et]:<16} {dagilim.get(et, 0)}")

    print("\nKarar kuralları için: docs/deney/ton_dogrulugu_protokolu.md §5")


if __name__ == "__main__":
    main()
