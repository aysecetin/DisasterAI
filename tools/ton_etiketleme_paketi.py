# -*- coding: utf-8 -*-
"""
Ton doğruluğu etiketlemesi için körlenmiş değerlendirme paketini üretir.

Protokol: docs/deney/ton_dogrulugu_protokolu.md

Girdi:  outputs/ek6_ton_ciktilari.json  (tools/ton_ciktilari_uret.py üretir)
Çıktı:  outputs/ton_etiketleme/
          etiketleme_paketi.md   değerlendiriciye verilecek körlenmiş metinler
          etiket_formu.csv       boş etiketleme formu
          cevap_anahtari.csv     kod ↔ gerçek tür (değerlendiriciyle PAYLAŞMA)

Metin sırası sabit tohumla (42) karıştırılır: paket yeniden üretildiğinde
aynı kodlar aynı metinlere gider (üretilebilirlik).
"""
import csv
import json
import random
import sys
from pathlib import Path

PROJE_KOK = Path(__file__).resolve().parent.parent
GIRDI = PROJE_KOK / "outputs" / "ek6_ton_ciktilari.json"
CIKTI_DIZIN = PROJE_KOK / "outputs" / "ton_etiketleme"

# Etiketlemeye giren türler (teknik_rapor bilinçli olarak dışarıda; protokol §2)
TURLER = ["ham", "bilgilendirici", "eyleme_yonelik", "yatistirici"]
SENARYO_ADLARI = {"S1": "Deprem", "S2": "Heyelan", "S3": "Sel"}

YONERGE = """\
# Ton Etiketleme Paketi

Aşağıda, bir afet risk analizi sonucunu vatandaşa açıklamak için yazılmış
{adet} kısa metin göreceksiniz. Her metni okuyup **yazılış amacını en iyi
tanımlayan TEK etiketi** seçiniz ve `etiket_formu.csv` dosyasındaki
satırına işleyiniz:

- **B — Bilgilendirici:** Ana amaç durumu tarafsız ve düzenli biçimde
  AÇIKLAMAK. Sayıları ve nedenleri aktarır; ne yapmanız gerektiğini uzun
  uzun söylemez, sizi sakinleştirmeye de özel çaba harcamaz.
- **E — Eyleme yönelik:** Ana amaç sizi HAREKETE GEÇİRMEK. Somut adımlar,
  yapılacaklar listesi, zaman ifadeleri ("bugün", "bu hafta") öne çıkar.
- **Y — Yatıştırıcı:** Ana amaç endişeyi AZALTMAK. Güven veren dil,
  kontrol edilebilirlik vurgusu, olumlu çerçeveleme öne çıkar; riski yine
  de söyler ama sakinleştirerek.
- **T — Belirgin bir ton yok / karışık:** Metin yukarıdakilerden birine
  net biçimde oturmuyor; açıklama, tavsiye ve duygu öğeleri plansız
  biçimde karışmış.

Kurallar: (1) Her metne yalnız bir etiket verin. (2) Metnin İÇERİĞİNİN
doğruluğunu değil, ÜSLUBUNU değerlendirin. (3) Metinleri kimseyle
tartışmadan, kendi başınıza etiketleyin. (4) Kararsız kaldığınızda en
baskın bulduğunuz amacı seçin ve formun "guven" sütununa 1 (düşük) yazın;
emin olduklarınızda 2 (yüksek) yazın.
"""


# Protokol en az üç bağımsız değerlendirici istiyor (Fleiss' kappa için de
# metin başına eşit sayıda oy gerekir).
DEGERLENDIRICILER = ["D1", "D2", "D3"]

DAGITIM_NOTU = """# Ton etiketleme — değerlendiriciye verilecek yönerge

Bu klasörde {adet} kısa metin ve her değerlendirici için ayrı bir form var:
{liste}

## Değerlendiriciye ne gönderilir

1. `etiketleme_paketi.md` (metinler + etiket tanımları)
2. Yalnızca kendi formu (ör. D1'e `etiket_formu_D1.csv`)

**`cevap_anahtari.csv` GÖNDERİLMEZ.** Anahtar gönderilirse körleme bozulur ve
ölçülen uyum geçersiz olur.

## Değerlendirici ne yapar

Formdaki her satırın `etiket` sütununa **B**, **E**, **Y** veya **T** yazar;
`guven` sütununa 1 (kararsız) ya da 2 (emin) yazar. `metin_kodu` ve
`degerlendirici` sütunlarına dokunmaz. Değerlendiriciler metinleri birbirleriyle
tartışmadan, kendi başlarına etiketler.

## Formlar geri geldiğinde

    ayse-env/bin/python tools/ton_formu_birlestir.py \\
        outputs/ton_etiketleme/etiket_formu_D1.csv \\
        outputs/ton_etiketleme/etiket_formu_D2.csv \\
        outputs/ton_etiketleme/etiket_formu_D3.csv

Bu komut formları denetler (eksik satır, geçersiz etiket, tekrar eden
değerlendirici) ve birleştirilmiş dosyayı üretir. Ardından:

    ayse-env/bin/python tools/ton_dogrulugu_analiz.py \\
        outputs/ton_etiketleme/etiketler_birlesik.csv

Çıktı: Fleiss' kappa + Landis & Koch bandı, çoğunluk-oyu doğruluğu ve
karışıklık matrisi. Bu değerler sonuç raporunun 4.3 bölümüne yazılır.
"""


def main():
    if not GIRDI.exists():
        sys.exit(f"Girdi yok: {GIRDI} — önce tools/ton_ciktilari_uret.py çalıştır.")
    veri = json.loads(GIRDI.read_text(encoding="utf-8"))

    metinler, eksikler = [], []
    for kod in sorted(veri):
        for tur in TURLER:
            cikti = veri[kod].get("tonlar", {}).get(tur, {})
            if not cikti or "hata" in cikti:
                eksikler.append(f"{kod}/{tur}")
                continue
            metinler.append({"senaryo": kod, "tur": tur, "metin": cikti["metin"].strip()})

    if eksikler:
        print(f"⚠ Eksik metinler paket dışı kaldı: {', '.join(eksikler)}")
        print("  (tools/ton_ciktilari_uret.py ile tamamlayıp paketi yeniden üret)")

    random.Random(42).shuffle(metinler)
    for i, m in enumerate(metinler, 1):
        m["kod"] = f"M{i:02d}"

    CIKTI_DIZIN.mkdir(parents=True, exist_ok=True)

    parcalar = [YONERGE.format(adet=len(metinler))]
    for m in metinler:
        afet = SENARYO_ADLARI.get(m["senaryo"], m["senaryo"])
        parcalar.append(f"\n---\n\n## {m['kod']} (senaryo: {afet})\n")
        parcalar.append("\n".join("> " + s for s in m["metin"].splitlines()) + "\n")
    (CIKTI_DIZIN / "etiketleme_paketi.md").write_text("\n".join(parcalar), encoding="utf-8")

    with (CIKTI_DIZIN / "etiket_formu.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metin_kodu", "degerlendirici", "etiket", "guven"])
        for m in metinler:
            w.writerow([m["kod"], "", "", ""])

    # Her değerlendirici için ayrı, adı önceden doldurulmuş form: karışmasın diye
    for d in DEGERLENDIRICILER:
        with (CIKTI_DIZIN / f"etiket_formu_{d}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["metin_kodu", "degerlendirici", "etiket", "guven"])
            for m in metinler:
                w.writerow([m["kod"], d, "", ""])

    (CIKTI_DIZIN / "NASIL_DOLDURULUR.md").write_text(
        DAGITIM_NOTU.format(adet=len(metinler),
                            liste=", ".join(f"`etiket_formu_{d}.csv`" for d in DEGERLENDIRICILER)),
        encoding="utf-8")

    with (CIKTI_DIZIN / "cevap_anahtari.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metin_kodu", "senaryo", "gercek_tur"])
        for m in metinler:
            w.writerow([m["kod"], m["senaryo"], m["tur"]])

    print(f"{len(metinler)} metin paketlendi → {CIKTI_DIZIN}")
    print(f"Değerlendirici formları: {', '.join(DEGERLENDIRICILER)}")
    print("cevap_anahtari.csv dosyasını değerlendiricilerle PAYLAŞMA.")


if __name__ == "__main__":
    main()
