"""Sonuç raporu Şekil 1 — sistemin uçtan uca akış şeması.

Rapordaki yöntem anlatımı uzman olmayan bir okuyucu için üç paragraf sürüyor;
aynı şey tek bir kutu-ok şemasıyla bir bakışta anlaşılıyor. Şema tamamen bu
scriptten üretilir, elle düzenlenmez.

Kullanım:
    MPLBACKEND=Agg ayse-env/bin/python tools/akis_semasi_uret.py
Çıktı:
    outputs/rapor_sekilleri/akis_semasi.png (200 dpi)
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

CIKTI = Path(__file__).resolve().parent.parent / "outputs" / "rapor_sekilleri" / "akis_semasi.png"

# (başlık, açıklama, dolgu rengi, kenar rengi)
ADIMLAR = [
    ("1 · GİRDİ — mekânsal veri",
     "Fay hattı · litoloji · akarsu · arazi kullanımı (vektör katmanlar)\n"
     "Copernicus GLO-30 sayısal yükseklik modelinden üretilen eğim",
     "#E8EEF6", "#4A6FA5"),
    ("2 · CBS ANALİZİ",
     "Her faktör, afet tipine özgü tabloyla 1–5 risk puanına çevrilir →\n"
     "literatür tabanlı ağırlıklarla çakıştırılır → 30 m risk haritası",
     "#E8EEF6", "#4A6FA5"),
    ("3 · KİŞİSELLEŞTİRME",
     "Kullanıcının haritada seçtiği nokta + bina bilgisi (yapım yılı, kat\n"
     "sayısı, taşıyıcı sistem) → o kişiye özgü risk skoru",
     "#FDF0E3", "#C77F32"),
    ("4 · İLETİŞİM — büyük dil modeli",
     "Aynı skor beş metin türünde anlatılır: teknik rapor · yönergesiz çıktı\n"
     "· bilgilendirici · eyleme yönelik · yatıştırıcı",
     "#FDF0E3", "#C77F32"),
    ("5 · DOĞRULAMA",
     "Metindeki HER sayı CBS çıktısıyla karşılaştırılır; karşılığı olmayan\n"
     "sayı ve tutarsız risk seviyesi adı işaretlenir",
     "#EAF5EC", "#3E8E55"),
    ("6 · ÇIKTI — vatandaş",
     "Okunabilir metin + harita + PDF rapor + en yakın toplanma alanına rota",
     "#EAF5EC", "#3E8E55"),
]


def uret():
    yukseklik_kutu = 1.0
    aralik = 0.52
    n = len(ADIMLAR)
    toplam = n * yukseklik_kutu + (n - 1) * aralik

    fig, ax = plt.subplots(figsize=(8.6, 9.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.5, toplam + 0.6)
    ax.axis("off")

    sol, genislik = 0.35, 8.1
    for i, (baslik, aciklama, dolgu, kenar) in enumerate(ADIMLAR):
        alt = toplam - (i + 1) * yukseklik_kutu - i * aralik
        ax.add_patch(FancyBboxPatch(
            (sol, alt), genislik, yukseklik_kutu,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            facecolor=dolgu, edgecolor=kenar, linewidth=1.6, zorder=2))
        ax.text(sol + 0.25, alt + yukseklik_kutu - 0.27, baslik,
                fontsize=11.5, fontweight="bold", color=kenar, va="center", zorder=3)
        ax.text(sol + 0.25, alt + 0.33, aciklama,
                fontsize=9.6, color="#1F2933", va="center", linespacing=1.45, zorder=3)

        if i < n - 1:
            ax.add_patch(FancyArrowPatch(
                (sol + genislik / 2, alt - 0.04), (sol + genislik / 2, alt - aralik + 0.04),
                arrowstyle="-|>", mutation_scale=17, linewidth=1.8,
                color="#5A6B7B", zorder=3))

    # Doğrulamadan iletişime geri besleme: hata bulunursa metin kabul edilmez
    ust_alt = toplam - 4 * yukseklik_kutu - 3 * aralik          # 4. kutunun altı
    dogrulama_alt = toplam - 5 * yukseklik_kutu - 4 * aralik    # 5. kutunun altı
    x_geri = sol + genislik + 0.42
    ax.add_patch(FancyArrowPatch(
        (x_geri, dogrulama_alt + 0.5), (x_geri, ust_alt + 0.5),
        connectionstyle="arc3,rad=-0.42", arrowstyle="-|>", mutation_scale=15,
        linewidth=1.5, linestyle="--", color="#B23A48", zorder=3))
    ax.text(x_geri + 0.55, (dogrulama_alt + ust_alt) / 2 + 0.5,
            "karşılıksız sayı\nbulunursa\nmetin kabul\nedilmez",
            fontsize=8.4, color="#B23A48", ha="left", va="center", linespacing=1.35)

    ax.text(sol, toplam + 0.34,
            "Sayısal risk verisinden vatandaşa: sistemin uçtan uca akışı",
            fontsize=12.5, fontweight="bold", color="#1F2933")

    fig.savefig(CIKTI, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("Yazıldı:", CIKTI)


if __name__ == "__main__":
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    uret()
