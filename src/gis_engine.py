"""
gis_engine.py — Gerçek CBS tabanlı afet risk analizi motoru
============================================================

Bu modül, `simulate_spatial_risk()` fonksiyonunun yerini alır.

Önceki durum: risk katmanları katman adından türetilen bir rastgele sayı
üreteci ile SİMÜLE ediliyordu; data/ altındaki .gdb dosyaları okunmuyordu.

Yeni durum: her faktör gerçek CBS katmanından üretilir:
  - Fay hattına uzaklık   -> Öklidyen mesafe rasteri + yeniden sınıflandırma
  - Akarsuya uzaklık      -> Öklidyen mesafe rasteri + yeniden sınıflandırma
  - Litoloji (Formasyon)  -> öznitelik tabanlı yeniden sınıflandırma
  - Arazi kullanımı       -> öznitelik tabanlı yeniden sınıflandırma
  - Eğim                  -> DEM/eğim rasterinden yeniden sınıflandırma
                             (GeoTIFF olarak dışa aktarılmalı, aşağıya bkz.)

Tüm faktörler 1-5 ölçeğine getirilir, sonra ağırlıklı çakıştırmaya girer.

ÖNEMLİ - KOORDİNAT SİSTEMİ
--------------------------
Vektör katmanların CRS'i EPSG:23035 (ED50 / UTM zone 35N).
Fay hattı katmanı EPSG:4022 (coğrafi, derece) — otomatik dönüştürülür.
Eski kodda EPSG:32635 (WGS84 / UTM 35N) varsayılıyordu; ED50 ile WGS84
arasında Türkiye'de ~90-100 m yatay fark vardır (30 m pikselde ~3 piksel
kayma). Bu modül her şeyi TARGET_CRS'e getirir.

EKSİK VERİ - EĞİM
-----------------
Eğim ve yeniden sınıflandırma rasterleri ESRI File Geodatabase içinde
raster olarak duruyor (Eğim Analizi.gdb -> Seferihisar_Dem,
Yeniden Sınıflandırma.gdb -> re_fay/re_jeo/re_akarsu/re_arazi,
Uygunluk Analizi.gdb -> Uygunluk). Açık kaynak GDAL, ESRI gdb *raster*
veri setlerini okuyamaz. Bu yüzden bunları ArcGIS Pro'dan GeoTIFF olarak
dışa aktarman gerekiyor (bkz. tools/arcgis_export.py).

Dışa aktarılan GeoTIFF'ler RASTER_DIR altına konursa bu modül onları
otomatik kullanır ve kendi hesabı yerine SENİN ArcGIS analizini kullanır.
Bulamazsa vektörlerden kendi hesaplar. Hiç eğim verisi yoksa eğim faktörü
devre dışı kalır ve ağırlıklar yeniden normalize edilir; sonuç sözlüğünde
`eksik_katmanlar` alanıyla açıkça bildirilir (sessizce sahte veri
ÜRETİLMEZ).
"""

from __future__ import annotations

import functools
import math
import warnings
from pathlib import Path

import numpy as np
import geopandas as gpd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import Affine

# Yeniden sınıflandırma tabloları ve kaynakları ayrı dosyada tutulur.
try:
    from . import reclass_tables as rt
except ImportError:
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import reclass_tables as rt

# ---------------------------------------------------------------------------
# TEMEL AYARLAR
# ---------------------------------------------------------------------------

TARGET_CRS = "EPSG:23035"   # ED50 / UTM zone 35N — veri setinin kendi CRS'i
PIXEL_SIZE = 30             # metre

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RASTER_DIR = PROJECT_ROOT / "data" / "raster"   # ArcGIS'ten dışa aktarılan GeoTIFF'ler

GDB = {
    "akarsu": "Akarsu Analizi.gdb",
    "arazi": "Arazi Kullanım Analizi.gdb",
    "egim": "Eğim Analizi.gdb",
    "fay": "Fay Hattı Analizi.gdb",
    "litoloji": "Litoloji Analizi.gdb",
}

LAYER = {
    "sinir": "Seferihisar_Sınır",
    "akarsu": "Akarsu",
    "arazi": "Arazi_Kullanım",
    "fay": "Fay_Hattı",
    "litoloji": "Formasyon",
}

# ---------------------------------------------------------------------------
# YENİDEN SINIFLANDIRMA TABLOLARI
#
# Tablolar ve kaynakları reclass_tables.py dosyasında. Her satırın hangi
# yayına dayandığı ve güven seviyesi ([K] kaynaklı / [U] uyarlama /
# [E] eksper ataması) orada belirtilmiştir.
#
# ÖNEMLİ: Tablolar AFET TİPİNE GÖRE DEĞİŞİR. Aynı litolojik birim deprem için
# yüksek (alüvyon = zemin büyütmesi), heyelan için düşük (alüvyon = düz zemin)
# puan alır. İlk sürümde tek bir litoloji tablosu bütün afetler için
# kullanılıyordu; bu hatalıydı ve düzeltildi.
# ---------------------------------------------------------------------------

LITOLOJI_VARSAYILAN = rt.VARSAYILANLAR["litoloji"]
ARAZI_VARSAYILAN = rt.VARSAYILANLAR["arazi"]


def _tablo(map_type: str, faktor: str):
    """Afet tipine göre ilgili yeniden sınıflandırma tablosunu döndürür."""
    mt = (map_type or "DEPREM").upper()
    return rt.TABLOLAR.get(mt, rt.TABLOLAR["DEPREM"])[faktor]


# ArcGIS'ten dışa aktarılmışsa doğrudan kullanılacak GeoTIFF adları
HAZIR_RASTER = {
    "Fay_Hattı_Uzaklığı": ["re_fay.tif"],
    "Litoloji":           ["re_jeo.tif"],
    "Akarsu_Uzaklığı":    ["re_akarsu.tif"],
    "Arazi_Kullanımı":    ["re_arazi.tif"],
    "Eğim":               ["re_egim.tif"],
}
EGIM_KAYNAK_RASTER = ["egim.tif", "slope.tif", "Seferihisar_Dem.tif", "dem.tif"]


# ---------------------------------------------------------------------------
# YARDIMCILAR
# ---------------------------------------------------------------------------

def _data_dir() -> Path:
    """data/ altındaki 'İZMİR SEFERİHİSAR' klasörünü bulur."""
    root = PROJECT_ROOT / "data"
    if not root.exists():
        raise FileNotFoundError(f"data klasörü bulunamadı: {root}")
    for c in sorted(root.iterdir()):
        if c.is_dir() and any(c.glob("*.gdb")):
            return c
    raise FileNotFoundError(f"{root} altında .gdb içeren bir klasör bulunamadı")


@functools.lru_cache(maxsize=32)
def _read_layer(gdb_key: str, layer_key: str) -> gpd.GeoDataFrame:
    """Katmanı okur ve TARGET_CRS'e dönüştürür (önbellekli)."""
    path = _data_dir() / GDB[gdb_key]
    gdf = gpd.read_file(path, layer=LAYER[layer_key])
    if gdf.crs is None:
        warnings.warn(f"{layer_key}: CRS tanımsız, {TARGET_CRS} varsayıldı")
        gdf = gdf.set_crs(TARGET_CRS)
    elif gdf.crs.to_string() != TARGET_CRS:
        gdf = gdf.to_crs(TARGET_CRS)
    return gdf


@functools.lru_cache(maxsize=1)
def grid_info():
    """Analiz gridini ilçe sınırından üretir -> (width, height, transform, bounds)."""
    sinir = _read_layer("akarsu", "sinir")
    minx, miny, maxx, maxy = sinir.total_bounds
    # Piksel sınırlarına hizala
    minx = math.floor(minx / PIXEL_SIZE) * PIXEL_SIZE
    miny = math.floor(miny / PIXEL_SIZE) * PIXEL_SIZE
    maxx = math.ceil(maxx / PIXEL_SIZE) * PIXEL_SIZE
    maxy = math.ceil(maxy / PIXEL_SIZE) * PIXEL_SIZE
    width = int((maxx - minx) / PIXEL_SIZE)
    height = int((maxy - miny) / PIXEL_SIZE)
    transform = Affine(PIXEL_SIZE, 0, minx, 0, -PIXEL_SIZE, maxy)
    return width, height, transform, (minx, miny, maxx, maxy)


@functools.lru_cache(maxsize=1)
def district_mask() -> np.ndarray:
    """İlçe sınırı içi True olan maske."""
    width, height, transform, _ = grid_info()
    sinir = _read_layer("akarsu", "sinir")
    m = rasterize(
        [(geom, 1) for geom in sinir.geometry],
        out_shape=(height, width),
        transform=transform,
        fill=0,
        all_touched=True,
        dtype="uint8",
    )
    return m.astype(bool)


# --- Öklidyen mesafe dönüşümü (scipy varsa onu, yoksa saf numpy kullanır) ---

def _edt_1d(f: np.ndarray) -> np.ndarray:
    """Felzenszwalb & Huttenlocher tek boyutlu kare mesafe dönüşümü (tam sonuç)."""
    n = f.shape[0]
    d = np.empty(n, dtype=np.float64)
    v = np.zeros(n, dtype=np.intp)
    z = np.empty(n + 1, dtype=np.float64)
    k = 0
    v[0] = 0
    z[0] = -np.inf
    z[1] = np.inf
    for q in range(1, n):
        while True:
            s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2.0 * q - 2.0 * v[k])
            if s <= z[k]:
                k -= 1
                if k < 0:
                    k = 0
                    break
            else:
                break
        k += 1
        v[k] = q
        z[k] = s
        z[k + 1] = np.inf
    k = 0
    for q in range(n):
        while z[k + 1] < q:
            k += 1
        d[q] = (q - v[k]) ** 2 + f[v[k]]
    return d


def _distance_transform(mask: np.ndarray, pixel_size: float) -> np.ndarray:
    """mask==True olan hücrelere en yakın mesafeyi metre cinsinden döndürür."""
    try:
        from scipy.ndimage import distance_transform_edt
        return distance_transform_edt(~mask, sampling=pixel_size).astype(np.float32)
    except ImportError:
        pass
    INF = 1e12
    f = np.where(mask, 0.0, INF)
    # sütunlar
    out = np.empty_like(f, dtype=np.float64)
    for j in range(f.shape[1]):
        out[:, j] = _edt_1d(f[:, j])
    # satırlar
    for i in range(f.shape[0]):
        out[i, :] = _edt_1d(out[i, :])
    return (np.sqrt(out) * pixel_size).astype(np.float32)


def _reclass(values: np.ndarray, sinif_tablosu) -> np.ndarray:
    """Sürekli değerleri (aralık, puan) tablosuna göre 1-5'e sınıflandırır."""
    out = np.full(values.shape, np.nan, dtype=np.float32)
    for lo, hi, score in sinif_tablosu:
        out[(values >= lo) & (values < hi)] = score
    out[np.isnan(out)] = sinif_tablosu[-1][2]
    return out


def _load_ready_raster(names) -> np.ndarray | None:
    """RASTER_DIR altında hazır (ArcGIS'ten aktarılmış) raster varsa okur ve gride oturtur."""
    if not RASTER_DIR.exists():
        return None
    width, height, transform, _ = grid_info()
    for name in names:
        p = RASTER_DIR / name
        if not p.exists():
            continue
        try:
            from rasterio.warp import reproject, Resampling
            with rasterio.open(p) as src:
                dst = np.full((height, width), np.nan, dtype=np.float32)
                reproject(
                    source=rasterio.band(src, 1),
                    destination=dst,
                    src_transform=src.transform,
                    src_crs=src.crs or TARGET_CRS,
                    dst_transform=transform,
                    dst_crs=TARGET_CRS,
                    resampling=Resampling.nearest,
                    dst_nodata=np.nan,
                )
                if src.nodata is not None:
                    dst[dst == src.nodata] = np.nan
                return dst
        except Exception as e:  # pragma: no cover
            warnings.warn(f"{p.name} okunamadı: {e}")
    return None


# ---------------------------------------------------------------------------
# FAKTÖR RASTERLERİ
# ---------------------------------------------------------------------------

def _factor_fay(map_type: str = "DEPREM") -> np.ndarray:
    width, height, transform, _ = grid_info()
    fay = _read_layer("fay", "fay")
    m = rasterize(
        [(g, 1) for g in fay.geometry if g is not None and not g.is_empty],
        out_shape=(height, width), transform=transform,
        fill=0, all_touched=True, dtype="uint8",
    ).astype(bool)
    dist = _distance_transform(m, PIXEL_SIZE)
    return _reclass(dist, _tablo(map_type, "Fay_Hattı_Uzaklığı"))


def _factor_akarsu(map_type: str = "DEPREM") -> np.ndarray:
    width, height, transform, _ = grid_info()
    ak = _read_layer("akarsu", "akarsu")
    m = rasterize(
        [(g, 1) for g in ak.geometry if g is not None and not g.is_empty],
        out_shape=(height, width), transform=transform,
        fill=0, all_touched=True, dtype="uint8",
    ).astype(bool)
    dist = _distance_transform(m, PIXEL_SIZE)
    return _reclass(dist, _tablo(map_type, "Akarsu_Uzaklığı"))


def _factor_litoloji(map_type: str = "DEPREM") -> np.ndarray:
    width, height, transform, _ = grid_info()
    lit = _read_layer("litoloji", "litoloji")
    tablo = _tablo(map_type, "Litoloji")
    shapes = []
    for geom, ad in zip(lit.geometry, lit["Ad"]):
        if geom is None or geom.is_empty:
            continue
        key = (ad or "").strip()
        shapes.append((geom, tablo.get(key, LITOLOJI_VARSAYILAN)))
    return rasterize(
        shapes, out_shape=(height, width), transform=transform,
        fill=LITOLOJI_VARSAYILAN, all_touched=True, dtype="float32",
    )


def _factor_arazi(map_type: str) -> np.ndarray:
    width, height, transform, _ = grid_info()
    az = _read_layer("arazi", "arazi")
    tablo = _tablo(map_type, "Arazi_Kullanımı")
    shapes = []
    for geom, kul in zip(az.geometry, az["AraziKullanim"]):
        if geom is None or geom.is_empty:
            continue
        shapes.append((geom, tablo.get((kul or "").strip(), ARAZI_VARSAYILAN)))
    return rasterize(
        shapes, out_shape=(height, width), transform=transform,
        fill=ARAZI_VARSAYILAN, all_touched=True, dtype="float32",
    )


def _factor_egim(map_type: str) -> np.ndarray | None:
    """Eğim faktörü. Veri yoksa None döner (sahte veri ÜRETİLMEZ)."""
    hazir = _load_ready_raster(HAZIR_RASTER["Eğim"])
    if hazir is not None:
        return np.clip(np.nan_to_num(hazir, nan=3.0), 1.0, 5.0)
    ham = _load_ready_raster(EGIM_KAYNAK_RASTER)
    if ham is None:
        return None
    ham = np.nan_to_num(ham, nan=0.0)
    if np.nanmax(ham) > 90:          # DEM (yükseklik) gelmiş, eğime çevir
        gy, gx = np.gradient(ham, PIXEL_SIZE, PIXEL_SIZE)
        ham = np.degrees(np.arctan(np.sqrt(gx ** 2 + gy ** 2)))
    return _reclass(ham, _tablo(map_type, "Eğim"))


FAKTOR_URETICILERI = {
    "Fay_Hattı_Uzaklığı": _factor_fay,
    "Akarsu_Uzaklığı":    _factor_akarsu,
    "Litoloji":           _factor_litoloji,
    "Arazi_Kullanımı":    _factor_arazi,
    "Eğim":               _factor_egim,
}


@functools.lru_cache(maxsize=8)
def _factor_raster_cached(factor_key: str, map_type: str):
    hazir = _load_ready_raster(HAZIR_RASTER.get(factor_key, []))
    if hazir is not None and factor_key != "Eğim":
        return np.clip(np.nan_to_num(hazir, nan=3.0), 1.0, 5.0), "arcgis"
    arr = FAKTOR_URETICILERI[factor_key](map_type)
    if arr is None:
        return None, "eksik"
    return np.clip(arr, 1.0, 5.0), ("arcgis" if hazir is not None else "python")


# ---------------------------------------------------------------------------
# AĞIRLIKLI ÇAKIŞTIRMA
# ---------------------------------------------------------------------------

def weighted_overlay(weights: dict, map_type: str):
    """
    Gerçek katmanlardan ağırlıklı çakıştırma yapar.

    Dönüş: (risk_matrisi, meta)
      meta = {"kullanilan": {faktor: {"agirlik":.., "kaynak":..}},
              "eksik_katmanlar": [...],
              "agirliklar_normalize_edildi": bool}
    """
    width, height, transform, _ = grid_info()
    map_type = map_type.upper()

    hazir_faktorler, eksik = {}, []
    for factor_key, w in weights.items():
        if w == 0:
            continue
        arr, kaynak = _factor_raster_cached(factor_key, map_type)
        if arr is None:
            eksik.append(factor_key)
            continue
        hazir_faktorler[factor_key] = (arr, w, kaynak)

    if not hazir_faktorler:
        raise RuntimeError("Hiçbir CBS katmanı yüklenemedi — data/ klasörünü kontrol et.")

    toplam_agirlik = sum(w for _, w, _ in hazir_faktorler.values())
    normalize_edildi = abs(toplam_agirlik - 1.0) > 1e-9

    risk = np.zeros((height, width), dtype=np.float32)
    kullanilan = {}
    for factor_key, (arr, w, kaynak) in hazir_faktorler.items():
        wn = w / toplam_agirlik
        risk += arr * wn
        kullanilan[factor_key] = {"agirlik": round(wn, 4), "kaynak": kaynak}

    mask = district_mask()
    risk = np.where(mask, risk, np.nan)

    meta = {
        "kullanilan": kullanilan,
        "eksik_katmanlar": eksik,
        "agirliklar_normalize_edildi": normalize_edildi,
    }
    return np.clip(risk, 1.0, 5.0), meta


def sample_at(risk_matrix: np.ndarray, x: float, y: float, pencere: int = 1) -> float | None:
    """
    Kullanıcının seçtiği (x, y) TARGET_CRS koordinatındaki risk değerini döndürür.

    Eski kod matrisin ORTASINI örneklediği için skor konumdan bağımsızdı;
    bu fonksiyon o hatayı giderir.
    `pencere` > 0 ise NxN komşuluk ortalaması alınır (tek piksel gürültüsünü azaltır).
    Nokta çalışma alanı dışındaysa None döner.
    """
    width, height, transform, _ = grid_info()
    inv = ~transform
    col_f, row_f = inv * (x, y)
    col, row = int(math.floor(col_f)), int(math.floor(row_f))
    if not (0 <= row < height and 0 <= col < width):
        return None
    r0, r1 = max(0, row - pencere), min(height, row + pencere + 1)
    c0, c1 = max(0, col - pencere), min(width, col + pencere + 1)
    pencere_dizi = risk_matrix[r0:r1, c0:c1]
    gecerli = pencere_dizi[~np.isnan(pencere_dizi)]
    if gecerli.size == 0:
        val = risk_matrix[row, col]
        return None if np.isnan(val) else float(val)
    return float(gecerli.mean())


def factor_breakdown(x: float, y: float, weights: dict, map_type: str) -> dict:
    """
    "Skor Neden Böyle?" bölümü için: her faktörün o noktadaki ham puanı,
    ağırlığı ve toplam skora katkısı. LLM'e verilecek yapılandırılmış girdi.
    """
    map_type = map_type.upper()
    width, height, transform, _ = grid_info()
    inv = ~transform
    col_f, row_f = inv * (x, y)
    col, row = int(math.floor(col_f)), int(math.floor(row_f))
    if not (0 <= row < height and 0 <= col < width):
        return {}

    ham = {}
    for factor_key, w in weights.items():
        if w == 0:
            continue
        arr, kaynak = _factor_raster_cached(factor_key, map_type)
        if arr is None:
            continue
        ham[factor_key] = (float(arr[row, col]), w, kaynak)

    toplam_w = sum(w for _, w, _ in ham.values()) or 1.0
    return {
        k: {
            "puan": round(v, 2),
            "agirlik": round(w / toplam_w, 3),
            "katki": round(v * w / toplam_w, 3),
            "kaynak": kaynak,
        }
        for k, (v, w, kaynak) in ham.items()
    }


def mesafe_bilgisi(x: float, y: float) -> dict:
    """
    LLM'in doğal dil yanıtında kullanacağı somut mekânsal olgular.
    (Yanıttaki sayıların doğrulanabilmesi için de kullanılır.)
    """
    from shapely.geometry import Point
    p = Point(x, y)
    out = {}
    try:
        fay = _read_layer("fay", "fay")
        out["en_yakin_fay_m"] = round(float(fay.distance(p).min()), 1)
    except Exception:
        pass
    try:
        ak = _read_layer("akarsu", "akarsu")
        i = ak.distance(p).idxmin()
        out["en_yakin_akarsu_m"] = round(float(ak.distance(p).min()), 1)
        out["en_yakin_akarsu_adi"] = str(ak.loc[i, "ADI_NUMARA"]).strip()
    except Exception:
        pass
    try:
        lit = _read_layer("litoloji", "litoloji")
        hit = lit[lit.contains(p)]
        if len(hit):
            out["litoloji"] = str(hit.iloc[0]["Ad"]).strip()
            acik = str(hit.iloc[0]["Aciklama"] or "").strip()
            if acik and acik.lower() != "nan":
                out["litoloji_aciklama"] = acik
    except Exception:
        pass
    try:
        az = _read_layer("arazi", "arazi")
        hit = az[az.contains(p)]
        if len(hit):
            out["arazi_kullanimi"] = str(hit.iloc[0]["AraziKullanim"]).strip()
            out["mahalle"] = str(hit.iloc[0]["Adi"]).strip()
    except Exception:
        pass
    return out
