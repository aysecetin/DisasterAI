# -*- coding: utf-8 -*-
"""
Ek 6 için örnek ton çıktılarını üretir.

Üç deney senaryosunun (src/deney.py: SENARYOLAR) her biri için beş metin
türünü (teknik_rapor, ham, bilgilendirici, eyleme_yonelik, yatistirici)
/api/aciklama ucundan üretir ve doğrulama sonuçlarıyla birlikte
outputs/ek6_ton_ciktilari.md dosyasına yazar.

Üretilen çıktılar outputs/ek6_ton_ciktilari.json dosyasında önbelleğe alınır:
script yeniden çalıştırıldığında yalnızca eksik/hatalı tonları üretir
(Gemini ücretsiz kotası günde 20 istek olduğundan kaldığı yerden devam
edebilmek önemli). 429 kota hatasında bekleyip yeniden dener; kota o gün
için bitmişse eksikleri bırakır — ertesi gün aynı komut tamamlar.

Kullanım (backend 8514'te çalışırken):
    ayse-env/bin/python tools/ton_ciktilari_uret.py
Önbelleği yok sayıp her şeyi baştan üretmek için: --sifirla
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJE_KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJE_KOK / "src"))

from deney import SENARYOLAR  # noqa: E402

API = "http://127.0.0.1:8514/api/aciklama"
CIKTI_MD = PROJE_KOK / "outputs" / "ek6_ton_ciktilari.md"
ONBELLEK = PROJE_KOK / "outputs" / "ek6_ton_ciktilari.json"

TON_BASLIKLARI = [
    ("teknik_rapor", "A — Teknik rapor (kontrol; BDM kullanılmaz)"),
    ("ham", "B — Ham BDM çıktısı (ablasyon; ton yönergesi yok)"),
    ("bilgilendirici", "C1 — Bilgilendirici ton"),
    ("eyleme_yonelik", "C2 — Eyleme yönelik ton"),
    ("yatistirici", "C3 — Yatıştırıcı ton"),
]
KOTA_DENEME = 3          # 429 başına yeniden deneme sayısı
KOTA_BEKLEME_SN = 70     # dakikalık pencere için bekleme


def api_cagir(senaryo, ton):
    govde = {
        "lat": senaryo["lat"], "lon": senaryo["lon"],
        "afet_tipi": senaryo["afet_tipi"], **senaryo["bina"],
        "ton": ton, "katilimci_kodu": "EK6-ORNEK",
    }
    istek = urllib.request.Request(
        API, data=json.dumps(govde).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(istek, timeout=300) as yanit:
        return json.loads(yanit.read())


def ton_uret(senaryo, ton):
    """Bir tonu üretir; 429 kota hatasında bekleyip yeniden dener."""
    for deneme in range(1, KOTA_DENEME + 1):
        try:
            return api_cagir(senaryo, ton)
        except urllib.error.HTTPError as e:
            detay = e.read().decode(errors="replace")
            if "RESOURCE_EXHAUSTED" in detay or "429" in detay:
                if deneme < KOTA_DENEME:
                    print(f"    kota doldu, {KOTA_BEKLEME_SN} sn bekleniyor "
                          f"({deneme}/{KOTA_DENEME})...")
                    time.sleep(KOTA_BEKLEME_SN)
                    continue
                return {"hata": "Gemini kotası doldu (429). Ertesi gün aynı "
                                "komutla kaldığı yerden devam eder."}
            return {"hata": detay[:500]}
    return None


def dogrulama_ozeti(d):
    if not d:
        return "—"
    adet = d.get("kontrol_edilen_sayi_adedi", 0)
    uydurma = d.get("uydurma_sayilar") or []
    risk_gecti = "evet" if d.get("risk_skoru_gecti") else "HAYIR"
    if uydurma:
        return (f"⚠ uydurma sayı: {', '.join(str(u) for u in uydurma)} — "
                f"sayısal doğruluk {d.get('sayisal_dogruluk')}, "
                f"risk skoru metinde doğru: {risk_gecti}")
    return (f"✓ kontrol edilen {adet} sayının tamamı CBS çıktısıyla eşleşti; "
            f"risk skoru metinde doğru: {risk_gecti}")


def md_yaz(onbellek):
    bolumler = [
        "# Ek 5 — Örnek Ton Çıktıları (Üç Senaryo × Beş Metin Türü)\n",
        "Bu dosya `tools/ton_ciktilari_uret.py` ile üretilmiştir "
        "(backend + GOOGLE_API_KEY gerekir). Elle düzenleme.\n",
        f"Son güncelleme: {time.strftime('%Y-%m-%d %H:%M')}. "
        "BDM: Gemini 2.5 Flash. Ağırlık seti: literatür tabanlı. "
        "Endişe düzeyi girdisi: orta (varsayılan).\n",
    ]
    for senaryo in SENARYOLAR:
        kayit = onbellek.get(senaryo["kod"], {})
        analiz = kayit.get("analiz", {})
        bolumler.append(
            f"\n## Senaryo {senaryo['kod']} — {senaryo['ad']} "
            f"({senaryo['afet_tipi'].capitalize()})\n\n"
            f"- Konum: {senaryo['lat']}, {senaryo['lon']} — {senaryo['aciklama']}\n"
            f"- Risk skoru: **{analiz.get('risk_score', 0):.2f}** "
            f"(bölgesel tehlike {analiz.get('hazard_score', 0):.2f}, "
            f"bina hassasiyeti {analiz.get('vulnerability_score', 0):.2f})\n"
            f"- Bina: {senaryo['bina']['yapim_yili']} yapımı, "
            f"{senaryo['bina']['bina_kat_sayisi']} katlı\n"
        )
        for ton, baslik in TON_BASLIKLARI:
            cikti = kayit.get("tonlar", {}).get(ton, {})
            bolumler.append(f"\n### {baslik}\n")
            if not cikti or "hata" in cikti:
                bolumler.append(f"> ÜRETİLEMEDİ: {cikti.get('hata', 'henüz üretilmedi')}\n")
                continue
            metin = cikti["metin"].strip()
            bolumler.append("\n".join("> " + satir for satir in metin.splitlines()) + "\n")
            bolumler.append(f"\n*Doğrulama:* {dogrulama_ozeti(cikti.get('dogrulama'))}\n")
    CIKTI_MD.write_text("\n".join(bolumler), encoding="utf-8")


def main():
    sifirla = "--sifirla" in sys.argv
    onbellek = {}
    if ONBELLEK.exists() and not sifirla:
        onbellek = json.loads(ONBELLEK.read_text(encoding="utf-8"))

    eksik_kaldi = False
    for senaryo in SENARYOLAR:
        kayit = onbellek.setdefault(senaryo["kod"], {"tonlar": {}})
        for ton, _ in TON_BASLIKLARI:
            mevcut = kayit["tonlar"].get(ton)
            if mevcut and "hata" not in mevcut:
                continue
            print(f"{senaryo['kod']} / {ton} üretiliyor...")
            yanit = ton_uret(senaryo, ton)
            if yanit is None or "hata" in yanit:
                kayit["tonlar"][ton] = {"hata": (yanit or {}).get("hata", "bilinmeyen")}
                eksik_kaldi = True
                continue
            kayit["analiz"] = yanit["analiz"]
            kayit["tonlar"][ton] = {
                "metin": yanit["metin"],
                "dogrulama": yanit.get("dogrulama"),
                "llm_kullanildi": yanit.get("llm_kullanildi"),
            }
            ONBELLEK.write_text(json.dumps(onbellek, ensure_ascii=False, indent=2),
                                encoding="utf-8")

    ONBELLEK.write_text(json.dumps(onbellek, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    md_yaz(onbellek)
    print(f"Yazıldı: {CIKTI_MD}")
    if eksik_kaldi:
        print("⚠ Bazı tonlar üretilemedi (muhtemelen günlük Gemini kotası). "
              "Ertesi gün aynı komutla kaldığı yerden devam eder.")


if __name__ == "__main__":
    main()
