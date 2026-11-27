"""
corpora_uret.py — İP2: CBS çıktılarından otomatik eğitim corpora'sı üretimi
===========================================================================

Plan: docs/ip2_ince_ayar_plani.md (Bölüm 3). Üç adım:

  1) girdi  — Gerçek CBS motorundan tabakalı senaryo örnekleme. Her konum için
              /api/analysis ile AYNI yapıda "analiz" sözlüğü üretilir
              (faktör dökümü, mekânsal olgular, bina profili). LLM gerekmez.
  2) metin  — Her girdi × 4 metin türü (ham + 3 ton) için öğretmen modelden
              metin üretir, rc.dogrula() süzgecinden geçirir. OpenAI-uyumlu
              herhangi bir uç çalışır (Groq/Together/Ollama/vLLM).
  3) bol    — Kabul edilen örnekleri KONUM bazında train/val/test'e böler
              (%80/10/10). Aynı konum asla iki kümeye düşmez.

Çalıştırma:
    python tools/corpora_uret.py --adim girdi --n-konum 30      # pilot
    OGRETMEN_URL=https://api.groq.com/openai/v1 \
    OGRETMEN_MODEL=llama-3.3-70b-versatile \
    OGRETMEN_API_KEY=... \
    python tools/corpora_uret.py --adim metin
    python tools/corpora_uret.py --adim bol

Notlar:
  - Deneydeki 3 sabit senaryonun 500 m çevresi üretime GİRMEZ (test sızıntısı).
  - `teknik_rapor` türü modele öğretilmez (deterministik kontrol kolu).
  - metin adımı kaldığı yerden devam eder (mevcut kayıtlar atlanır).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import threading
import time
from pathlib import Path

import numpy as np
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# langchain_google_genai kurulu olmayan ortamda da (yalnızca girdi/bol
# adımları için) çalışabilsin — corpora üretimi Gemini'ye bağımlı değildir.
try:
    import langchain_google_genai  # noqa: F401
except ImportError:
    import types
    _stub = types.ModuleType("langchain_google_genai")
    class _ChatStub:  # noqa: E301
        def __init__(self, *a, **k):
            raise RuntimeError("langchain_google_genai kurulu değil")
    _stub.ChatGoogleGenerativeAI = _ChatStub
    sys.modules["langchain_google_genai"] = _stub

import disaster_risk_v4 as drv  # noqa: E402
import gis_engine as ge         # noqa: E402
import risk_communication as rc # noqa: E402
import deney as dny             # noqa: E402
from pyproj import Transformer  # noqa: E402

CIKTI_DIR = PROJECT_ROOT / "outputs" / "corpora"
GIRDI_DOSYA = CIKTI_DIR / "girdiler.jsonl"
METIN_DOSYA = CIKTI_DIR / "metinler.jsonl"
ATILAN_DOSYA = CIKTI_DIR / "atilan.jsonl"

AFETLER = ("DEPREM", "HEYELAN", "SEL")
TONLAR = ("ham", "bilgilendirici", "eyleme_yonelik", "yatistirici")
SINIF_ESIKLERI = [(1.0, 3.0, "dusuk"), (3.0, 4.0, "orta"), (4.0, 5.01, "yuksek")]
DENEY_KORUMA_M = 500.0          # deney senaryolarının çevresinde üretim yapma

SORU_VARYANTLARI = [
    "",                                       # soru yok — genel açıklama
    "",
    "Ne yapmam gerekiyor?",
    "Bu sonuç kötü mü?",
    "Evim güvenli mi?",
    "Çocuklarımla birlikte yaşıyorum, nelere dikkat etmeliyim?",
    "Taşınmalı mıyım?",
    "Bu skorun anlamı ne?",
]
ENDISE_DUZEYLERI = ("düşük", "orta", "yüksek")

_T4326 = Transformer.from_crs("EPSG:23035", "EPSG:4326", always_xy=True)
_T23035 = Transformer.from_crs("EPSG:4326", "EPSG:23035", always_xy=True)


def _json_dump(o) -> str:
    def _default(v):
        if isinstance(v, (np.floating, np.integer)):
            return float(v)
        raise TypeError(f"Serileştirilemedi: {type(v)}")
    return json.dumps(o, ensure_ascii=False, default=_default)


def _jsonl_oku(dosya: Path) -> list[dict]:
    if not dosya.exists():
        return []
    kayitlar = []
    with dosya.open(encoding="utf-8") as f:
        for satir in f:
            satir = satir.strip()
            if satir:
                try:
                    kayitlar.append(json.loads(satir))
                except json.JSONDecodeError:
                    continue
    return kayitlar


# ---------------------------------------------------------------------------
# ADIM 1 — GİRDİ ÜRETİMİ
# ---------------------------------------------------------------------------

def _bina_profili(rng: random.Random) -> dict:
    """Gerçekçi rastgele bina profili (mevzuat sınırlarıyla tutarlı)."""
    malzeme = rng.choices([1, 2, 3], weights=[0.70, 0.22, 0.08])[0]  # betonarme/yığma/ahşap
    if malzeme == 1:
        kat = rng.randint(1, 10)
        yil = rng.randint(1965, 2024)
    else:
        kat = rng.randint(1, 3)
        yil = rng.randint(1950, 2015)
    return {
        "yapim_yili": yil,
        "malzeme_secim": malzeme,
        "bina_kat_sayisi": kat,
        "oturulan_kat": rng.randint(1, kat),
        "asansor_var": 1 if (malzeme == 1 and kat >= 4 and rng.random() < 0.8) else 0,
    }


def _deney_koruma_bolgesi() -> list[tuple[float, float]]:
    """Deney senaryolarının EPSG:23035 koordinatları."""
    noktalar = []
    for s in dny.SENARYOLAR:
        x, y = _T23035.transform(s["lon"], s["lat"])
        noktalar.append((x, y))
    return noktalar


def girdi_uret(n_konum: int, seed: int) -> None:
    """Her afet için ~n_konum konum, risk sınıfına göre tabakalı."""
    rng = random.Random(seed)
    CIKTI_DIR.mkdir(parents=True, exist_ok=True)
    korunan = _deney_koruma_bolgesi()
    _, _, transform, _ = ge.grid_info()

    mevcut = {k["konum_id"] for k in _jsonl_oku(GIRDI_DOSYA)}
    yeni = 0

    with GIRDI_DOSYA.open("a", encoding="utf-8") as f:
        for afet in AFETLER:
            print(f"[{afet}] çakıştırma hesaplanıyor...", flush=True)
            weights = drv.WEIGHTS.get(afet, drv.WEIGHTS["DEPREM"])
            matris, katman_meta = drv.perform_weighted_overlay(weights, map_type=afet)

            for lo, hi, sinif_adi in SINIF_ESIKLERI:
                satirlar, sutunlar = np.where(
                    np.isfinite(matris) & (matris >= lo) & (matris < hi))
                if satirlar.size == 0:
                    print(f"  {sinif_adi}: hücre yok, atlanıyor")
                    continue
                hedef = max(1, n_konum // len(SINIF_ESIKLERI))
                secim = rng.sample(range(satirlar.size), min(hedef * 3, satirlar.size))
                alinan = 0
                for idx in secim:
                    if alinan >= hedef:
                        break
                    r, c = int(satirlar[idx]), int(sutunlar[idx])
                    x, y = transform * (c + 0.5, r + 0.5)
                    if any((x - kx) ** 2 + (y - ky) ** 2 < DENEY_KORUMA_M ** 2
                           for kx, ky in korunan):
                        continue
                    konum_id = f"{afet}_{r}_{c}"
                    if konum_id in mevcut:
                        continue

                    hazard = ge.sample_at(matris, x, y)
                    if hazard is None:
                        continue
                    bina = _bina_profili(rng)
                    vuln = float(drv.calculate_vulnerability_score(bina))
                    if afet == "DEPREM":
                        skor = 0.60 * hazard + 0.40 * vuln
                    else:
                        skor = 0.80 * hazard + 0.20 * vuln
                    skor = float(np.clip(skor, 1.0, 5.0))
                    lon, lat = _T4326.transform(x, y)

                    # mesafe_bilgisi bazı noktalarda "None" STRING'i döndürüyor
                    # (örn. mahalle) — prompt'a "Yerleşim: None" sızmasın
                    olgular = {k: v for k, v in ge.mesafe_bilgisi(x, y).items()
                               if v not in (None, "None", "")}

                    analiz = {
                        "afet_tipi": afet,
                        "risk_score": round(skor, 4),
                        "hazard_score": round(float(hazard), 4),
                        "vulnerability_score": round(vuln, 4),
                        "faktor_dokumu": ge.factor_breakdown(x, y, weights, afet),
                        "mekansal_olgular": olgular,
                        "katman_meta": katman_meta,
                        "coordinates": {"x": x, "y": y,
                                        "lat": round(lat, 6), "lon": round(lon, 6)},
                        **bina,
                    }
                    kayit = {
                        "konum_id": konum_id,
                        "afet_tipi": afet,
                        "risk_sinifi": sinif_adi,
                        "endise_duzeyi": rng.choice(ENDISE_DUZEYLERI),
                        "kullanici_sorusu": rng.choice(SORU_VARYANTLARI),
                        "analiz": analiz,
                    }
                    f.write(_json_dump(kayit) + "\n")
                    mevcut.add(konum_id)
                    alinan += 1
                    yeni += 1
                print(f"  {sinif_adi}: {alinan} konum")

    print(f"\n✓ {yeni} yeni girdi -> {GIRDI_DOSYA} (toplam {len(mevcut)})")


# ---------------------------------------------------------------------------
# ADIM 2 — ÖĞRETMEN METİNLERİ
# ---------------------------------------------------------------------------

def _ogretmen_cagir(prompt: str, url: str, model: str, anahtar: str,
                    sicaklik: float = 0.7, deneme: int = 3) -> str:
    """OpenAI-uyumlu chat/completions çağrısı (Groq/Together/Ollama/vLLM)."""
    govde = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": sicaklik,
        # Groq TPM kotasını max_tokens üzerinden REZERVE ediyor: 1500 yerine
        # 1000 istemek aynı dakikalık kotadan ~%50 daha çok istek geçirir.
        # (Metinler <=260 kelime + düşük efor akıl yürütme; 1000 yeter.)
        "max_tokens": 1000,
    }
    # gpt-oss reasoning modeli: içsel akıl yürütme token bütçesini yer ve
    # yanıt boş kalabilir — düşük efor yeterli, bütçe asıl metne kalsın
    if "gpt-oss" in model:
        govde["reasoning_effort"] = "low"
    basliklar = {"Content-Type": "application/json"}
    if anahtar:
        basliklar["Authorization"] = f"Bearer {anahtar}"
    son_hata = None
    for i in range(deneme):
        try:
            r = requests.post(f"{url.rstrip('/')}/chat/completions",
                              json=govde, headers=basliklar, timeout=75)
            if r.status_code == 429:          # kota (TPM/TPD) — kısa bekle,
                son_hata = "429 kota siniri"  # düzelmezse sıradaki sağlayıcı
                bekle = r.headers.get("retry-after")
                bekle = float(bekle) + 1 if bekle else 10.0 * (i + 1)
                time.sleep(min(bekle, 25))
                continue
            if r.status_code in (401, 402, 404):
                # anahtar/ödeme/model hatası — tekrar denemek düzeltmez
                raise RuntimeError(f"HTTP {r.status_code} (kalıcı): {r.text[:120]}")
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except RuntimeError:                  # kalıcı hata — yukarı fırlat
            raise
        except Exception as e:                # ağ hatası vb.
            son_hata = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"Öğretmen çağrısı başarısız: {son_hata}")


def _kalite_filtresi(metin: str, analiz: dict) -> tuple[bool, str]:
    """Kabul/ret + gerekçe. Plandaki kalite kapısı (Bölüm 3.4)."""
    kelime = len(metin.split())
    if kelime < 30:
        return False, f"cok_kisa({kelime} kelime)"
    if kelime > 260:
        return False, f"cok_uzun({kelime} kelime)"
    d = rc.dogrula(metin, analiz)
    if d["uydurma_sayilar"]:
        return False, f"uydurma_sayi({d['uydurma_sayilar']})"
    if not d["risk_skoru_gecti"]:
        return False, "risk_skoru_yok"

    # Seviye kelimesi kontrolü: skor 2.98 iken "orta seviyede risk" diyen metin
    # sayı filtresini geçer ama yanlış sınıflandırmadır. Doğru seviye kelimesi
    # metinde hiç yoksa VE yanlış seviye "risk" bağlamında geçiyorsa ele.
    skor = float(analiz.get("risk_score", 0))
    beklenen = "yüksek" if skor >= 4.0 else ("orta" if skor >= 3.0 else "düşük")
    kucuk = metin.lower()
    if beklenen not in kucuk:
        digerleri = {"düşük", "orta", "yüksek"} - {beklenen}
        for yanlis in digerleri:
            if (f"{yanlis} risk" in kucuk or f"{yanlis} seviye" in kucuk
                    or f"{yanlis} düzey" in kucuk):
                return False, f"seviye_hatasi(beklenen={beklenen}, yazilan={yanlis})"

    # Güncelliğini yitirmiş güvenlik tavsiyesi (AFAD: çök-kapan-tutun)
    if "kapı çerçeve" in kucuk or "kapı kiriş" in kucuk:
        return False, "eski_tavsiye(kapi_cercevesi)"

    return True, "ok"


def _saglayicilar() -> list[dict]:
    """OGRETMEN_* (birincil) ve OGRETMEN2_* (yedek) ortam değişkenlerinden
    sağlayıcı listesi. Biri kotaya takılınca diğerine geçilir (failover)."""
    liste = []
    for onek in ["OGRETMEN"] + [f"OGRETMEN{i}" for i in range(2, 10)]:
        url = os.environ.get(f"{onek}_URL", "").strip()
        model = os.environ.get(f"{onek}_MODEL", "").strip()
        anahtar = os.environ.get(f"{onek}_API_KEY", "").strip()
        if url and model:
            liste.append({"url": url, "model": model, "anahtar": anahtar,
                          "ad": url.split("//")[-1].split("/")[0]})
    return liste


def metin_uret(bekleme_sn: float, limit: int | None,
               hedef_kabul: int | None = None) -> None:
    saglayicilar = _saglayicilar()
    if not saglayicilar:
        raise SystemExit(
            "OGRETMEN_URL ve OGRETMEN_MODEL ortam değişkenleri gerekli.\n"
            "Örn: OGRETMEN_URL=https://api.groq.com/openai/v1 "
            "OGRETMEN_MODEL=openai/gpt-oss-120b OGRETMEN_API_KEY=gsk_...\n"
            "Yedek: OGRETMEN2_URL=https://api.cerebras.ai/v1 ... (opsiyonel)\n"
            "Yerel: OGRETMEN_URL=http://localhost:11434/v1 OGRETMEN_MODEL=qwen2.5:72b")
    print("Sağlayıcılar:", " -> ".join(s["ad"] for s in saglayicilar))

    girdiler = _jsonl_oku(GIRDI_DOSYA)
    if not girdiler:
        raise SystemExit("Önce --adim girdi çalıştır.")

    mevcut_kabul = len(_jsonl_oku(METIN_DOSYA))
    bitmis = {(k["konum_id"], k["ton"])
              for k in _jsonl_oku(METIN_DOSYA) + _jsonl_oku(ATILAN_DOSYA)}
    print(f"{len(girdiler)} girdi × {len(TONLAR)} tür; {len(bitmis)} kayıt mevcut, atlanacak.")
    if hedef_kabul and mevcut_kabul >= hedef_kabul:
        print(f"Hedef zaten aşılmış: {mevcut_kabul}/{hedef_kabul} kabul. Çıkılıyor.")
        return

    # -----------------------------------------------------------------
    # PARALEL ÜRETİM: her sağlayıcıya bir işçi. Kotalar bağımsız olduğu
    # için Groq beklerken NVIDIA üretir (ve tersi) — sıralı failover'a
    # göre kabaca sağlayıcı sayısı kadar hızlanma.
    # -----------------------------------------------------------------
    sadece = os.environ.get("SADECE_AFET", "").strip().upper()
    kuyruk = [(g, ton) for g in girdiler for ton in TONLAR
              if (g["konum_id"], ton) not in bitmis
              and (not sadece or g["afet_tipi"] == sadece)]
    print(f"Kuyruk: {len(kuyruk)} çift; {len(saglayicilar)} paralel işçi."
          + (f" (yalnızca {sadece})" if sadece else ""))

    kilit = threading.Lock()
    durum = {"kabul": 0, "ret": 0, "i": 0, "dur": False}
    fk = METIN_DOSYA.open("a", encoding="utf-8")
    fr = ATILAN_DOSYA.open("a", encoding="utf-8")

    def isci(s: dict) -> None:
        ardarda = 0
        while True:
            with kilit:
                if durum["dur"] or durum["i"] >= len(kuyruk):
                    return
                if limit is not None and (durum["kabul"] + durum["ret"]) >= limit:
                    durum["dur"] = True
                    print(f"\nLimit ({limit}) doldu; aynı komutla devam edilebilir.")
                    return
                if hedef_kabul and (mevcut_kabul + durum["kabul"]) >= hedef_kabul:
                    durum["dur"] = True
                    print(f"\n🎯 Hedef tamam: toplam {mevcut_kabul + durum['kabul']} "
                          f"kabul (hedef {hedef_kabul}). Sıradaki adım: --adim bol")
                    return
                g, ton = kuyruk[durum["i"]]
                durum["i"] += 1
            prompt = rc.cot_prompt(g["analiz"], ton,
                                   kullanici_sorusu=g["kullanici_sorusu"],
                                   endise_duzeyi=g["endise_duzeyi"])
            try:
                metin = _ogretmen_cagir(prompt, s["url"], s["model"],
                                        s["anahtar"], deneme=3)
                ardarda = 0
            except RuntimeError as e:
                with kilit:
                    print(f"  ! {g['konum_id']}/{ton} [{s['ad']}]: {e}", flush=True)
                    kuyruk.append((g, ton))        # çifti başka işçiye bırak
                ardarda += 1
                kalici = "HTTP 402" in str(e) or "HTTP 401" in str(e)
                zaman_asimi = "timed out" in str(e).lower()
                if kalici or (not zaman_asimi and ardarda >= 6) or ardarda >= 12:
                    with kilit:
                        print(f"  -> {s['ad']} işçisi durdu "
                              f"({'kalıcı hata' if kalici else 'kota bitti'})", flush=True)
                    return
                if zaman_asimi:
                    time.sleep(45)   # kuyruk yoğunluğu geçici — sabırla bekle
                continue
            gecti, gerekce = _kalite_filtresi(metin, g["analiz"])
            kayit = {"konum_id": g["konum_id"], "ton": ton,
                     "afet_tipi": g["afet_tipi"], "risk_sinifi": g["risk_sinifi"],
                     "endise_duzeyi": g["endise_duzeyi"],
                     "kullanici_sorusu": g["kullanici_sorusu"],
                     "prompt": prompt, "cikti": metin,
                     "ogretmen": s["model"], "saglayici": s["ad"],
                     "filtre": gerekce}
            with kilit:
                if gecti:
                    fk.write(_json_dump(kayit) + "\n"); fk.flush()
                    durum["kabul"] += 1
                else:
                    fr.write(_json_dump(kayit) + "\n"); fr.flush()
                    durum["ret"] += 1
                toplam = durum["kabul"] + durum["ret"]
                if toplam % 20 == 0:
                    print(f"  ... kabul {durum['kabul']}, ret {durum['ret']}", flush=True)
            if bekleme_sn:
                time.sleep(bekleme_sn)

    isciler = [threading.Thread(target=isci, args=(s,), daemon=True)
               for s in saglayicilar]
    for t in isciler:
        t.start()
    for t in isciler:
        t.join()
    fk.close(); fr.close()

    kabul, ret = durum["kabul"], durum["ret"]
    toplam = kabul + ret
    if not durum["dur"] and durum["i"] >= len(kuyruk) and toplam == 0:
        print("\nHiçbir işçi üretemedi — kotalar bitmiş görünüyor; "
              "yenilenince aynı komutla devam edin.")
    elif not durum["dur"] and toplam and durum["i"] < len(kuyruk) + 1:
        print("\nTüm işçiler durdu (kota); kalan kuyruk sonraki koşuda işlenir.")
    print(f"\n✓ kabul {kabul}, ✗ ret {ret}"
          + (f" (atılma oranı %{100*ret/toplam:.1f} — rapora yazılacak)" if toplam else ""))


# ---------------------------------------------------------------------------
# ADIM 3 — TRAIN/VAL/TEST BÖLME (konum bazında)
# ---------------------------------------------------------------------------

def bol() -> None:
    metinler = _jsonl_oku(METIN_DOSYA)
    if not metinler:
        raise SystemExit("Önce --adim metin çalıştır.")

    def kume(konum_id: str) -> str:
        h = int(hashlib.sha256(konum_id.encode()).hexdigest(), 16) % 10
        return "train" if h < 8 else ("val" if h == 8 else "test")

    sayac = {"train": 0, "val": 0, "test": 0}
    dosyalar = {ad: (CIKTI_DIR / f"{ad}.jsonl").open("w", encoding="utf-8")
                for ad in sayac}
    try:
        for m in metinler:
            ad = kume(m["konum_id"])
            dosyalar[ad].write(_json_dump(
                {"prompt": m["prompt"], "cikti": m["cikti"], "ton": m["ton"],
                 "afet_tipi": m["afet_tipi"], "konum_id": m["konum_id"]}) + "\n")
            sayac[ad] += 1
    finally:
        for f in dosyalar.values():
            f.close()

    konumlar = {m["konum_id"] for m in metinler}
    print(f"✓ {len(metinler)} örnek, {len(konumlar)} konum -> "
          + ", ".join(f"{ad}: {n}" for ad, n in sayac.items()))
    print(f"  Dosyalar: {CIKTI_DIR}/train|val|test.jsonl")


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="İP2 corpora üretimi")
    ap.add_argument("--adim", choices=["girdi", "metin", "bol", "hepsi"],
                    default="hepsi")
    ap.add_argument("--n-konum", type=int, default=300,
                    help="Afet başına hedef konum sayısı (pilot: 30)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--bekleme-sn", type=float, default=0.5,
                    help="Öğretmen çağrıları arası bekleme (kota dostu)")
    ap.add_argument("--limit", type=int, default=None,
                    help="metin adımında bu oturumda üretilecek en fazla örnek")
    ap.add_argument("--hedef-kabul", type=int, default=None,
                    help="toplam kabul edilmiş örnek bu sayıya ulaşınca dur")
    args = ap.parse_args()

    if args.adim in ("girdi", "hepsi"):
        girdi_uret(args.n_konum, args.seed)
    if args.adim in ("metin", "hepsi"):
        metin_uret(args.bekleme_sn, args.limit, args.hedef_kabul)
    if args.adim in ("bol", "hepsi"):
        bol()


if __name__ == "__main__":
    main()
