"""
agirlik_karsilastir.py — Ağırlık seti duyarlılık analizi
=========================================================

İki ağırlık setiyle üretilen risk haritalarını karşılaştırır:

  "mevcut"    — projenin ilk sürümündeki ağırlıklar (deprem: fay 0.50)
  "literatur" — yayımlanmış Türkiye AHP çalışmalarının aralığına oturan set

NEDEN GEREKLİ?
--------------
Ağırlık seçimi AHP tabanlı çalışmalarda en çok eleştirilen noktadır. "Şu
ağırlıkları seçtim" demek yerine "iki seti de denedim, sonuç şu kadar değişti"
diyebilmek tezin savunmasını belirgin şekilde güçlendirir. Bu scriptin çıktısı
doğrudan tezin duyarlılık analizi (sensitivity analysis) bölümüdür.

Çalıştır:
    ayse-env/bin/python tools/agirlik_karsilastir.py

Çıktı:
    outputs/agirlik_duyarlilik_analizi.md
    outputs/agirlik_karsilastirma_<afet>.png   (üç afet için harita çifti)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import gis_engine as ge          # noqa: E402
import reclass_tables as rt      # noqa: E402

CIKTI_MD = PROJECT_ROOT / "outputs" / "agirlik_duyarlilik_analizi.md"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

AFETLER = ("DEPREM", "HEYELAN", "SEL")

# Risk sınıfı eşikleri (uygulamadaki tavsiye metniyle aynı)
SINIF_ESIKLERI = [(1.0, 3.0, "Düşük"), (3.0, 4.0, "Orta"), (4.0, 5.01, "Yüksek")]


def _siniflandir(dizi: np.ndarray) -> np.ndarray:
    out = np.full(dizi.shape, -1, dtype=np.int8)
    for i, (lo, hi, _) in enumerate(SINIF_ESIKLERI):
        out[(dizi >= lo) & (dizi < hi)] = i
    return out


def _kappa(a: np.ndarray, b: np.ndarray, n_sinif: int = 3) -> float:
    """Cohen's kappa — iki sınıflandırmanın şanstan arındırılmış uyumu."""
    gecerli = (a >= 0) & (b >= 0)
    a, b = a[gecerli], b[gecerli]
    if a.size == 0:
        return float("nan")
    n = a.size
    gozlenen = float((a == b).sum()) / n
    beklenen = sum(
        (float((a == k).sum()) / n) * (float((b == k).sum()) / n)
        for k in range(n_sinif)
    )
    if beklenen >= 1.0:
        return float("nan")
    return (gozlenen - beklenen) / (1.0 - beklenen)


def _kappa_yorum(k: float) -> str:
    if np.isnan(k):
        return "hesaplanamadı"
    if k < 0.20:
        return "zayıf uyum"
    if k < 0.40:
        return "vasat uyum"
    if k < 0.60:
        return "orta uyum"
    if k < 0.80:
        return "iyi uyum"
    return "çok iyi uyum"


def _harita_ciz(afet: str, mevcut: np.ndarray, literatur: np.ndarray) -> str | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import ListedColormap, BoundaryNorm
    except Exception as e:
        print(f"  (harita çizilemedi: {e})")
        return None

    cmap = ListedColormap(['#00FF00', '#FFFF00', '#FFA500', '#FF4500', '#FF0000'])
    norm = BoundaryNorm(np.linspace(1, 5, 6), cmap.N)

    fig, axes = plt.subplots(1, 3, figsize=(16, 7))
    for ax, (dizi, baslik) in zip(axes[:2], [(mevcut, "Eski ağırlıklar"),
                                             (literatur, "Literatür ağırlıkları")]):
        ax.imshow(dizi, cmap=cmap, norm=norm)
        ax.set_title(f"{afet} — {baslik}", fontsize=11, fontweight="bold")
        ax.axis("off")

    fark = literatur - mevcut
    im = axes[2].imshow(fark, cmap="RdBu_r", vmin=-1.5, vmax=1.5)
    axes[2].set_title(f"{afet} — Fark (literatür − eski)", fontsize=11, fontweight="bold")
    axes[2].axis("off")
    fig.colorbar(im, ax=axes[2], fraction=0.046, shrink=0.8, label="risk puanı farkı")

    plt.tight_layout()
    ad = f"agirlik_karsilastirma_{afet.lower()}.png"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUTPUT_DIR / ad, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return ad


def main() -> int:
    sat: list[str] = []
    ek = sat.append

    ek("# Ağırlık Seti Duyarlılık Analizi")
    ek("")
    ek("Seferihisar (İzmir) — ağırlıklı çakıştırmada kullanılan faktör ağırlıklarının")
    ek("sonuç haritası üzerindeki etkisi.")
    ek("")
    ek("İki set karşılaştırıldı:")
    ek("")
    ek("- **Eski (mevcut):** projenin ilk sürümündeki ağırlıklar. Deprem için fay")
    ek("  mesafesine 0.50 ağırlık veriyordu; yayımlanmış Türkiye çalışmalarında bu")
    ek("  faktör 0.07–0.15 aralığında.")
    ek("- **Literatür tabanlı (kullanılan):** Ocak & Bahadır (2022, CR 0.08),")
    ek("  Demir & Altaş (2024, CR 0.023), Berber & Ceryan (2023, CR 0.054),")
    ek("  Öz (2025, CR 0.080) ve Yurteri (2024, CR 0.058) çalışmalarının bildirdiği")
    ek("  aralıkların ortasına oturur.")
    ek("")
    ek("Uyum ölçütü olarak üç risk sınıfı (Düşük / Orta / Yüksek) üzerinden")
    ek("**Cohen's kappa** hesaplanmıştır.")
    ek("")

    ozet: list[tuple] = []

    for afet in AFETLER:
        print(f"[{afet}] hesaplanıyor...")
        ge._factor_raster_cached.cache_clear()
        mevcut, _ = ge.weighted_overlay(rt.AGIRLIKLAR_MEVCUT[afet], afet)
        literatur, _ = ge.weighted_overlay(rt.AGIRLIKLAR_LITERATUR[afet], afet)

        maske = ~np.isnan(mevcut) & ~np.isnan(literatur)
        m, l = mevcut[maske], literatur[maske]
        fark = l - m

        sm, sl = _siniflandir(mevcut), _siniflandir(literatur)
        k = _kappa(sm[maske], sl[maske])
        sinif_degisti = float((sm[maske] != sl[maske]).mean()) * 100

        ozet.append((afet, float(m.mean()), float(l.mean()), float(np.abs(fark).mean()),
                     float(np.abs(fark).max()), sinif_degisti, k))

        ek(f"## {afet.capitalize()}")
        ek("")
        ek("### Ağırlıklar")
        ek("")
        ek("| Faktör | Eski | Literatür | Değişim |")
        ek("|---|---|---|---|")
        mv, lt = rt.AGIRLIKLAR_MEVCUT[afet], rt.AGIRLIKLAR_LITERATUR[afet]
        for f in sorted(set(mv) | set(lt), key=lambda x: -lt.get(x, 0)):
            d = lt.get(f, 0) - mv.get(f, 0)
            ek(f"| {f} | {mv.get(f, 0):.2f} | **{lt.get(f, 0):.2f}** | {d:+.2f} |")
        ek("")
        ek("### Sonuç haritası üzerindeki etki")
        ek("")
        ek("| Ölçüt | Değer |")
        ek("|---|---|")
        ek(f"| Ortalama risk skoru (eski) | {m.mean():.3f} |")
        ek(f"| Ortalama risk skoru (literatür) | {l.mean():.3f} |")
        ek(f"| Ortalama mutlak fark | {np.abs(fark).mean():.3f} |")
        ek(f"| En büyük fark | {np.abs(fark).max():.3f} |")
        ek(f"| Risk sınıfı değişen hücre oranı | %{sinif_degisti:.1f} |")
        ek(f"| Cohen's kappa | {k:.3f} ({_kappa_yorum(k)}) |")
        ek("")

        for etiket, dizi in (("Eski", sm), ("Literatür", sl)):
            dagilim = [float((dizi[maske] == i).mean()) * 100 for i in range(3)]
            ek(f"{etiket} set sınıf dağılımı — "
               f"Düşük %{dagilim[0]:.1f} · Orta %{dagilim[1]:.1f} · Yüksek %{dagilim[2]:.1f}")
            ek("")

        ad = _harita_ciz(afet, mevcut, literatur)
        if ad:
            ek(f"![{afet} karşılaştırma]({ad})")
            ek("")

    ek("## Özet")
    ek("")
    ek("| Afet | Ort. skor (eski) | Ort. skor (lit.) | Ort. mutlak fark | Sınıf değişimi | Kappa |")
    ek("|---|---|---|---|---|---|")
    for afet, om, ol, of, mf, sd, k in ozet:
        ek(f"| {afet.capitalize()} | {om:.3f} | {ol:.3f} | {of:.3f} | %{sd:.1f} | {k:.3f} |")
    ek("")
    ek("### Tezde nasıl yorumlanır")
    ek("")
    ek("Kappa değeri yüksekse (>0.60) sonuç haritasının ağırlık seçimine görece")
    ek("**dayanıklı** olduğu söylenebilir — bu, yönteminin güçlü yanıdır ve rapor")
    ek("edilmelidir. Kappa düşükse ağırlık seçimi sonucu belirleyen kritik bir karar")
    ek("demektir; o zaman literatür tabanlı seti tercih etme gerekçesini (yayımlanmış")
    ek("aralıklara ve bildirilen CR değerlerine uygunluk) açıkça yazmalısın.")
    ek("")
    ek("Her iki durumda da bu analizin kendisi tezde bir katkıdır: AHP çalışmalarının")
    ek("en sık eleştirilen yanı ağırlıkların keyfîliğidir ve çoğu çalışma duyarlılık")
    ek("analizi sunmaz.")
    ek("")

    CIKTI_MD.parent.mkdir(parents=True, exist_ok=True)
    CIKTI_MD.write_text("\n".join(sat), encoding="utf-8")
    print(f"\n✓ Yazıldı: outputs/{CIKTI_MD.name}")
    for afet, om, ol, of, mf, sd, k in ozet:
        print(f"  {afet:<8} ort.fark={of:.3f}  sınıf değişimi=%{sd:.1f}  kappa={k:.3f} ({_kappa_yorum(k)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
