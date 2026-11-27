# -*- coding: utf-8 -*-
"""
Değerlendiricilerden gelen ton etiketleme formlarını denetleyip birleştirir.

Kullanım:
    ayse-env/bin/python tools/ton_formu_birlestir.py form1.csv form2.csv form3.csv
    ayse-env/bin/python tools/ton_formu_birlestir.py --cikti /tmp/deneme.csv form*.csv

Girdi CSV sütunları: metin_kodu, degerlendirici, etiket (B/E/Y/T), guven (1/2)
Çıktı: outputs/ton_etiketleme/etiketler_birlesik.csv

Denetimler (Fleiss' kappa metin başına eşit sayıda oy istediği için şart):
  - her form cevap anahtarındaki bütün metinleri içeriyor mu
  - etiketler geçerli mi, boş bırakılmış satır var mı
  - aynı değerlendirici iki kez gönderilmiş mi
  - metin başına oy sayısı eşit mi (en az 3 değerlendirici)
"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJE_KOK = Path(__file__).resolve().parent.parent
CIKTI_DIZIN = PROJE_KOK / "outputs" / "ton_etiketleme"
ANAHTAR = CIKTI_DIZIN / "cevap_anahtari.csv"
CIKTI = CIKTI_DIZIN / "etiketler_birlesik.csv"

GECERLI_ETIKET = {"B", "E", "Y", "T"}
GECERLI_GUVEN = {"1", "2", ""}
ASGARI_DEGERLENDIRICI = 3


def hata(mesaj):
    sys.exit(f"HATA: {mesaj}")


def anahtari_oku():
    if not ANAHTAR.exists():
        hata(f"cevap anahtarı yok: {ANAHTAR} — önce tools/ton_etiketleme_paketi.py çalıştır.")
    with ANAHTAR.open(encoding="utf-8") as f:
        return [s["metin_kodu"] for s in csv.DictReader(f)]


def formu_oku(yol, beklenen_kodlar):
    p = Path(yol)
    if not p.exists():
        hata(f"form bulunamadı: {yol}")
    with p.open(encoding="utf-8-sig") as f:
        satirlar = list(csv.DictReader(f))
    if not satirlar:
        hata(f"{p.name}: dosya boş")

    eksik_sutun = {"metin_kodu", "degerlendirici", "etiket"} - set(satirlar[0])
    if eksik_sutun:
        hata(f"{p.name}: eksik sütun(lar): {', '.join(sorted(eksik_sutun))}")

    kimler = {s["degerlendirici"].strip() for s in satirlar if s["degerlendirici"].strip()}
    if len(kimler) != 1:
        hata(f"{p.name}: tek bir değerlendirici adı bekleniyordu, bulunan: "
             f"{sorted(kimler) or 'yok — degerlendirici sütunu boş'}")
    kim = kimler.pop()

    temiz, bos = [], []
    for s in satirlar:
        kod = s["metin_kodu"].strip()
        etiket = s["etiket"].strip().upper()
        guven = s.get("guven", "").strip()
        if not etiket:
            bos.append(kod)
            continue
        if etiket not in GECERLI_ETIKET:
            hata(f"{p.name} / {kod}: geçersiz etiket {etiket!r} "
                 f"(geçerli: {', '.join(sorted(GECERLI_ETIKET))})")
        if guven not in GECERLI_GUVEN:
            hata(f"{p.name} / {kod}: geçersiz güven {guven!r} (1 veya 2 olmalı)")
        temiz.append({"metin_kodu": kod, "degerlendirici": kim,
                      "etiket": etiket, "guven": guven})

    if bos:
        hata(f"{p.name} ({kim}): {len(bos)} metin etiketsiz kalmış: {', '.join(bos)}")

    kodlar = [s["metin_kodu"] for s in temiz]
    if len(set(kodlar)) != len(kodlar):
        tekrar = [k for k, n in Counter(kodlar).items() if n > 1]
        hata(f"{p.name}: aynı metin birden çok kez etiketlenmiş: {', '.join(tekrar)}")
    fazla = set(kodlar) - set(beklenen_kodlar)
    if fazla:
        hata(f"{p.name}: cevap anahtarında olmayan metin kodları: {', '.join(sorted(fazla))}")
    eksik = set(beklenen_kodlar) - set(kodlar)
    if eksik:
        hata(f"{p.name} ({kim}): eksik metin(ler): {', '.join(sorted(eksik))}")

    return kim, temiz


def main():
    global CIKTI
    argv = sys.argv[1:]
    # Kuru çalışma / sınama için çıktıyı başka yere yaz: outputs/ altında
    # yalnızca gerçek etiketler dursun.
    if "--cikti" in argv:
        i = argv.index("--cikti")
        if i + 1 >= len(argv):
            hata("--cikti bir dosya yolu bekliyor")
        CIKTI = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    formlar = argv
    if not formlar:
        sys.exit(__doc__.strip())

    kodlar = anahtari_oku()
    tum, kimler = [], []
    for yol in formlar:
        kim, satirlar = formu_oku(yol, kodlar)
        if kim in kimler:
            hata(f"aynı değerlendirici iki kez verilmiş: {kim}")
        kimler.append(kim)
        tum.extend(satirlar)
        dagilim = Counter(s["etiket"] for s in satirlar)
        kararsiz = sum(1 for s in satirlar if s["guven"] == "1")
        print(f"  {kim}: {len(satirlar)} metin, dağılım "
              f"{dict(sorted(dagilim.items()))}, kararsız {kararsiz}")

    if len(kimler) < ASGARI_DEGERLENDIRICI:
        hata(f"protokol en az {ASGARI_DEGERLENDIRICI} bağımsız değerlendirici istiyor; "
             f"{len(kimler)} form verildi ({', '.join(kimler)})")

    oy = defaultdict(int)
    for s in tum:
        oy[s["metin_kodu"]] += 1
    if len(set(oy.values())) != 1:
        hata(f"metin başına oy sayısı eşit değil: {sorted(set(oy.values()))}")

    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    with CIKTI.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metin_kodu", "degerlendirici", "etiket", "guven"])
        for kod in kodlar:
            for s in tum:
                if s["metin_kodu"] == kod:
                    w.writerow([s["metin_kodu"], s["degerlendirici"],
                                s["etiket"], s["guven"]])

    try:
        gosterim = CIKTI.relative_to(PROJE_KOK)
    except ValueError:
        gosterim = CIKTI
    print(f"\n{len(kimler)} değerlendirici × {len(kodlar)} metin = {len(tum)} etiket "
          f"birleştirildi → {gosterim}")
    print("Sıradaki adım:")
    print(f"  ayse-env/bin/python tools/ton_dogrulugu_analiz.py {gosterim}")


if __name__ == "__main__":
    main()
