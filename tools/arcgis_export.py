"""
arcgis_export.py — ArcGIS Pro raster katmanlarını GeoTIFF'e aktarır
===================================================================

>>> BU DOSYA ARTIK OPSİYONEL <<<
ArcGIS Pro macOS'ta çalışmaz (Esri'nin resmî yolu Parallels Desktop 18+ ile
Windows 11 ARM). MacBook'unda ArcGIS yoksa bu dosyaya İHTİYACIN YOK:
`tools/egim_uret.py` eksik olan tek katmanı (eğim) bağımsız bir DEM'den
üretir ve analiz tamamen açık kaynakla tamamlanır.

Bu dosya yalnızca ArcGIS'e erişimin varsa (üniversite laboratuvarı, Windows
bilgisayar, Parallels) ve tezinde "yeniden sınıflandırma ArcGIS'te yapıldı"
demek istiyorsan gerekli. O durumda çıktılar `kaynak: "arcgis"` olarak
işaretlenir ve senin ArcGIS analizin kullanılır.

NEDEN GEREKLİ?
-------------
Senin ArcGIS analizin aslında ZATEN YAPILMIŞ ve .gdb dosyalarının içinde duruyor:

  Eğim Analizi.gdb          -> Seferihisar_Dem            (DEM / yükseklik)
  Yeniden Sınıflandırma.gdb -> re_fay, re_jeo,
                               re_akarsu, re_arazi        (1-5 sınıflandırılmış)
  Uygunluk Analizi.gdb      -> Uygunluk                   (ağırlıklı çakıştırma sonucu)

Ancak açık kaynak GDAL (geopandas/rasterio/fiona) ESRI File Geodatabase
içindeki *raster* veri setlerini OKUYAMAZ — sadece vektör katmanları okur.
Bu yüzden Python tarafı bu rasterlere erişemiyor.

Çözüm: bunları ArcGIS Pro'da bir kez GeoTIFF'e aktar. Sonra gis_engine.py
otomatik olarak bulup kullanır ve kendi hesabı yerine SENİN ArcGIS
analizini kullanır (yanıtta kaynak "arcgis" olarak işaretlenir).

NASIL ÇALIŞTIRILIR?
-------------------
1. ArcGIS Pro'yu aç.
2. Analysis sekmesi -> Python -> Python Window
3. Bu dosyanın içeriğini oraya yapıştır ve çalıştır.
   (Veya: Project klasörüne kopyalayıp `exec(open(r"...arcgis_export.py").read())`)

Notlar:
  - PROJE_KLASORU'nu kendi yoluna göre düzelt.
  - Çıktılar data/raster/ altına yazılır; gis_engine.py oraya bakar.
  - re_egim yoksa Seferihisar_Dem yeterli — gis_engine eğimi DEM'den hesaplar.

ArcGIS yoksa ne olur?
---------------------
Sistem yine çalışır. Eğim faktörü devre dışı kalır, ağırlıklar kalan
katmanlar üzerinden yeniden normalize edilir ve API yanıtında
`katman_meta.eksik_katmanlar` alanında bu durum açıkça bildirilir.
Tezde "eğim katmanı X nedeniyle dahil edilememiştir" diye yazmak,
sahte veriyle doldurmaktan çok daha savunulabilir bir tercihtir.
"""

import os

# --- BURAYI KENDİ YOLUNA GÖRE DÜZELT ---
PROJE_KLASORU = r"/Users/aysecetin/Downloads/tez-final-main"
# Windows'ta örnek: r"C:\Users\ayse\Desktop\tez-final-main"

VERI_KLASORU = os.path.join(PROJE_KLASORU, "data", "İZMİR SEFERİHİSAR")
CIKTI_KLASORU = os.path.join(PROJE_KLASORU, "data", "raster")

# (gdb adı, raster adı, çıktı dosya adı)
AKTARILACAKLAR = [
    ("Eğim Analizi.gdb",          "Seferihisar_Dem", "Seferihisar_Dem.tif"),
    ("Yeniden Sınıflandırma.gdb", "re_fay",          "re_fay.tif"),
    ("Yeniden Sınıflandırma.gdb", "re_jeo",          "re_jeo.tif"),
    ("Yeniden Sınıflandırma.gdb", "re_akarsu",       "re_akarsu.tif"),
    ("Yeniden Sınıflandırma.gdb", "re_arazi",        "re_arazi.tif"),
    ("Uygunluk Analizi.gdb",      "Uygunluk",        "Uygunluk.tif"),
    # Eğimi ArcGIS'te ayrıca yeniden sınıflandırdıysan onu da ekle:
    # ("Yeniden Sınıflandırma.gdb", "re_egim",       "re_egim.tif"),
]


def main():
    import arcpy

    os.makedirs(CIKTI_KLASORU, exist_ok=True)
    arcpy.env.overwriteOutput = True

    basarili, atlanan = [], []
    for gdb, raster_adi, cikti_adi in AKTARILACAKLAR:
        kaynak = os.path.join(VERI_KLASORU, gdb, raster_adi)
        hedef = os.path.join(CIKTI_KLASORU, cikti_adi)
        if not arcpy.Exists(kaynak):
            print(f"  ATLANDI (bulunamadı): {gdb} -> {raster_adi}")
            atlanan.append(raster_adi)
            continue
        try:
            arcpy.management.CopyRaster(
                in_raster=kaynak,
                out_rasterdataset=hedef,
                format="TIFF",
                nodata_value="-9999",
            )
            print(f"  OK: {raster_adi} -> data/raster/{cikti_adi}")
            basarili.append(cikti_adi)
        except Exception as e:
            print(f"  HATA: {raster_adi}: {e}")
            atlanan.append(raster_adi)

    print("\n" + "=" * 60)
    print(f"Aktarılan: {len(basarili)}  |  Atlanan: {len(atlanan)}")
    if basarili:
        print("\nBunları data/raster/ altında bırak. gis_engine.py otomatik bulacak.")
        print("Backend'i yeniden başlatınca /api/analysis yanıtındaki")
        print("`katman_meta.kullanilan.*.kaynak` alanı 'arcgis' olarak görünmeli.")
    if atlanan:
        print(f"\nAktarılamayanlar: {', '.join(atlanan)}")


if __name__ == "__main__":
    main()
