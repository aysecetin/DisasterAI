"""
egim_uret.py — Eğim katmanını ArcGIS OLMADAN üretir
====================================================

NEDEN?
------
Analizde eksik olan tek katman EĞİM. Diğer dört faktörü (fay mesafesi,
litoloji, akarsu mesafesi, arazi kullanımı) gis_engine.py zaten .gdb'lerdeki
VEKTÖR katmanlardan hesaplıyor. Eğim ise .gdb içinde RASTER olarak duruyor
(Eğim Analizi.gdb -> Seferihisar_Dem) ve açık kaynak GDAL bunu okuyamıyor.

ArcGIS Pro macOS'ta çalışmadığı için (Esri'nin resmî yolu Parallels + Windows 11
ARM), bu script eğimi bağımsız bir DEM'den üretir. Böylece ArcGIS'e hiç
gerek kalmaz ve analiz tamamen açık kaynak + yeniden üretilebilir olur —
tez açısından da savunması daha kolay bir tercih.

NASIL ÇALIŞTIRILIR
------------------
    cd ~/Downloads/tez-final-main
    ayse-env/bin/python tools/egim_uret.py

Script sırayla şunu dener:
  1. data/raster/ altında zaten bir DEM dosyası var mı? (varsa onu kullanır)
  2. Yoksa Copernicus DEM GLO-30'u internetten indirmeye çalışır.

İnternetten indirme başarısız olursa (kurum ağı, proxy vb.), aşağıdaki
"ELLE İNDİRME" bölümünü izle — dosyayı kendin indirip data/raster/ içine
koyman yeterli, sonra scripti tekrar çalıştır.

ELLE İNDİRME (indirme adımı çalışmazsa)
---------------------------------------
En kolayı OpenTopography:
  1. https://portal.opentopography.org/raster?opentopoID=OTSDEM.032021.4326.3
     adresine git (ücretsiz üyelik gerekebilir).
  2. Koordinat kutusu olarak şunu gir:
         Kuzey: 38.32    Güney: 38.02
         Batı : 26.74    Doğu : 27.03
  3. "Copernicus GLO-30" veya "SRTM GL1 (30m)" seç, GeoTIFF olarak indir.
  4. İnen dosyayı data/raster/dem.tif adıyla kaydet.
  5. Bu scripti tekrar çalıştır.

ÇIKTI
-----
  data/raster/egim.tif   — derece cinsinden eğim, EPSG:23035, 30 m hücre

gis_engine.py bu dosyayı otomatik bulur; backend'i yeniden başlatınca
/api/analysis yanıtındaki `katman_meta.eksik_katmanlar` listesi boşalır ve
Eğim faktörü ağırlığıyla (deprem 0.05, heyelan 0.40, sel 0.10) analize girer.

ALINTI (tezde kaynak göstermek için)
------------------------------------
Copernicus DEM GLO-30 kullanıldıysa:
  European Space Agency (2024). Copernicus Global Digital Elevation Model
  GLO-30. https://doi.org/10.5270/ESA-c5d3d65
SRTM kullanıldıysa:
  Farr, T. G., et al. (2007). The Shuttle Radar Topography Mission.
  Reviews of Geophysics, 45(2), RG2004.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.merge import merge

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RASTER_DIR = PROJECT_ROOT / "data" / "raster"
CIKTI = RASTER_DIR / "egim.tif"

HEDEF_CRS = "EPSG:23035"
PIKSEL = 30

# Seferihisar sınırlarını kapsayan 1x1 derecelik DEM karoları
KAROLAR = [
    "Copernicus_DSM_COG_10_N38_00_E026_00_DEM",
    "Copernicus_DSM_COG_10_N38_00_E027_00_DEM",
]
AYNALAR = [
    "https://copernicus-dem-30m.s3.amazonaws.com/{t}/{t}.tif",
    "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com/{t}/{t}.tif",
    "https://prism-dem-open.copernicus.eu/pd-desk-open-access/prismDownload/COP-DEM_GLO-30-DGED__2023_1/{t}.tar",
]

DEM_ADAYLARI = ["dem.tif", "Seferihisar_Dem.tif", "srtm.tif", "cop30.tif", "dem.tiff"]


def _log(msg=""):
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# 1. DEM BUL
# ---------------------------------------------------------------------------

def _yerel_dem() -> Path | None:
    """data/raster/ altında zaten bir DEM var mı?"""
    if not RASTER_DIR.exists():
        return None
    for ad in DEM_ADAYLARI:
        p = RASTER_DIR / ad
        if p.exists():
            return p
    # Bilinen adlar yoksa: yükseklik değerine benzeyen herhangi bir tif
    for p in sorted(RASTER_DIR.glob("*.tif")):
        if p.name == CIKTI.name:
            continue
        try:
            with rasterio.open(p) as s:
                ornek = s.read(1, out_shape=(1, min(256, s.height), min(256, s.width)))
                ornek = ornek[np.isfinite(ornek)]
                if ornek.size and 50 < float(np.nanmax(ornek)) < 9000:
                    _log(f"  Yükseklik verisine benzeyen dosya bulundu: {p.name}")
                    return p
        except Exception:
            continue
    return None


def _indir() -> list[Path]:
    """Copernicus DEM karolarını indirmeyi dener."""
    RASTER_DIR.mkdir(parents=True, exist_ok=True)
    inenler = []
    for t in KAROLAR:
        hedef = RASTER_DIR / f"{t}.tif"
        if hedef.exists():
            inenler.append(hedef)
            continue
        for kalip in AYNALAR:
            if kalip.endswith(".tar"):
                continue  # tar arşivi bu scriptte desteklenmiyor
            url = kalip.format(t=t)
            try:
                _log(f"  indiriliyor: {t} ...")
                urllib.request.urlretrieve(url, hedef)
                _log(f"    ✓ {hedef.name} ({hedef.stat().st_size/1e6:.1f} MB)")
                inenler.append(hedef)
                break
            except Exception as e:
                _log(f"    başarısız ({type(e).__name__}: {str(e)[:80]})")
                if hedef.exists():
                    hedef.unlink()
    return inenler


# ---------------------------------------------------------------------------
# 2. EĞİM HESABI
# ---------------------------------------------------------------------------

def _hedef_grid():
    """gis_engine ile birebir aynı analiz gridini kullan."""
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    import gis_engine as ge
    return ge.grid_info()


def _egim_hesapla(dem: np.ndarray, piksel_m: float) -> np.ndarray:
    """
    Horn (1981) 3x3 yöntemiyle derece cinsinden eğim.
    ArcGIS'in Slope aracının da kullandığı yöntem — sonuçlar karşılaştırılabilir.
    """
    z = dem.astype("float64")
    # 3x3 komşuluk (a b c / d e f / g h i)
    a = np.roll(np.roll(z, 1, 0), 1, 1);  b = np.roll(z, 1, 0);  c = np.roll(np.roll(z, 1, 0), -1, 1)
    d = np.roll(z, 1, 1);                                        f = np.roll(z, -1, 1)
    g = np.roll(np.roll(z, -1, 0), 1, 1); h = np.roll(z, -1, 0); i = np.roll(np.roll(z, -1, 0), -1, 1)

    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * piksel_m)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * piksel_m)
    egim = np.degrees(np.arctan(np.sqrt(dzdx ** 2 + dzdy ** 2)))

    # Kenar pikselleri güvenilmez (roll sarmalı) — komşusuna eşitle
    egim[0, :] = egim[1, :]; egim[-1, :] = egim[-2, :]
    egim[:, 0] = egim[:, 1]; egim[:, -1] = egim[:, -2]
    return egim.astype("float32")


def main() -> int:
    _log("=" * 66)
    _log("EĞİM KATMANI ÜRETİMİ (ArcGIS gerektirmez)")
    _log("=" * 66)

    RASTER_DIR.mkdir(parents=True, exist_ok=True)

    # --- DEM bul ---
    _log("\n[1/4] DEM aranıyor...")
    dem_yolu = _yerel_dem()
    if dem_yolu:
        _log(f"  ✓ Yerel DEM kullanılacak: {dem_yolu.name}")
        kaynaklar = [dem_yolu]
    else:
        _log("  Yerelde DEM yok, indirilmeye çalışılıyor...")
        kaynaklar = _indir()
        if not kaynaklar:
            _log("\n  ✗ DEM indirilemedi.")
            _log("  Bu genellikle ağ/proxy kısıtından kaynaklanır ve bir kod hatası değildir.")
            _log("  Bu dosyanın başındaki 'ELLE İNDİRME' bölümünü izleyip DEM'i")
            _log("  data/raster/dem.tif olarak kaydet, sonra bu scripti tekrar çalıştır.")
            return 1

    # --- Mozaikle ---
    _log("\n[2/4] DEM hazırlanıyor...")
    acik = [rasterio.open(p) for p in kaynaklar]
    try:
        if len(acik) == 1:
            src_dizi = acik[0].read(1).astype("float32")
            src_transform = acik[0].transform
            src_crs = acik[0].crs
            nodata = acik[0].nodata
        else:
            mozaik, src_transform = merge(acik)
            src_dizi = mozaik[0].astype("float32")
            src_crs = acik[0].crs
            nodata = acik[0].nodata
        _log(f"  kaynak: {src_dizi.shape[1]}x{src_dizi.shape[0]} piksel, CRS={src_crs}")
        if nodata is not None:
            src_dizi[src_dizi == nodata] = np.nan
        gecerli = src_dizi[np.isfinite(src_dizi)]
        if gecerli.size == 0:
            _log("  ✗ DEM tamamen boş görünüyor."); return 1
        _log(f"  yükseklik aralığı: {gecerli.min():.0f} – {gecerli.max():.0f} m")
    finally:
        for s in acik:
            s.close()

    # --- Analiz gridine yeniden projeksiyonla ---
    _log("\n[3/4] Analiz gridine oturtuluyor (EPSG:23035, 30 m)...")
    width, height, transform, bounds = _hedef_grid()
    hedef = np.full((height, width), np.nan, dtype="float32")
    reproject(
        source=src_dizi, destination=hedef,
        src_transform=src_transform, src_crs=src_crs,
        dst_transform=transform, dst_crs=HEDEF_CRS,
        src_nodata=np.nan, dst_nodata=np.nan,
        resampling=Resampling.bilinear,     # yükseklik için bilinear doğru tercih
    )
    kapsam = np.isfinite(hedef).mean() * 100
    _log(f"  hedef grid: {width}x{height}, veri kapsamı %{kapsam:.1f}")
    if kapsam < 50:
        _log("  ! Uyarı: DEM çalışma alanının yarısından azını kaplıyor.")
        _log("    İndirdiğin karoların Seferihisar'ı kapsadığından emin ol.")

    # --- Eğim ---
    _log("\n[4/4] Eğim hesaplanıyor (Horn 1981, 3x3)...")
    dolu = np.where(np.isfinite(hedef), hedef, np.nanmedian(hedef))
    egim = _egim_hesapla(dolu, PIKSEL)
    egim[~np.isfinite(hedef)] = np.nan

    g = egim[np.isfinite(egim)]
    _log(f"  eğim: min={g.min():.1f}° ort={g.mean():.1f}° maks={g.max():.1f}°")
    for lo, hi in [(0, 5), (5, 10), (10, 20), (20, 35), (35, 90)]:
        pay = ((g >= lo) & (g < hi)).mean() * 100
        _log(f"    {lo:>2}–{hi:<2}° : %{pay:5.1f}")

    with rasterio.open(
        CIKTI, "w", driver="GTiff", height=height, width=width, count=1,
        dtype="float32", crs=HEDEF_CRS, transform=transform,
        nodata=np.nan, compress="deflate",
    ) as dst:
        dst.write(egim, 1)

    _log(f"\n✓ Yazıldı: data/raster/{CIKTI.name}")
    _log("\nŞimdi backend'i yeniden başlat. /api/analysis yanıtında")
    _log("`katman_meta.eksik_katmanlar` boş liste olmalı ve `Eğim` faktörü görünmeli.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
