"""
reclass_tables.py — Yeniden sınıflandırma tabloları ve kaynakları
==================================================================

Bu dosya, ağırlıklı çakıştırmada kullanılan her faktörün 1-5 puana nasıl
dönüştürüldüğünü tanımlar. Her tablonun üstünde hangi yayına dayandığı yazılıdır.

TEZDE NASIL KULLANILIR
----------------------
Bu dosya doğrudan yöntem bölümünün "yeniden sınıflandırma" tablosudur.
`tools/tablo_uret.py` bunu tezde kullanılabilir bir tabloya dönüştürür.

GÜVEN SEVİYELERİ
----------------
Her satırın sonundaki etiket, o değerin ne kadar sağlam dayandığını gösterir:

  [K]  KAYNAKLI   — yayımlanmış bir çalışmadan doğrudan alınmış/ölçeklenmiş
  [U]  UYARLAMA   — yayımlanmış şemalardan uyarlanmış, birebir alıntı değil
  [E]  EKSPER     — literatürde karşılığı bulunamadı, uzman ataması

[E] etiketli satırları tezde "tarafımızca atanmıştır" diye belirtmek ZORUNLU.
Bunları kaynaklı gibi sunmak en ciddi akademik hatadır.

ÖNEMLİ UYARI — AĞIRLIKLAR
-------------------------
Koddaki mevcut ağırlıklar (deprem: fay 0.50, litoloji 0.30, eğim 0.05)
literatürdeki yaygın aralıkların DIŞINDA. Yayımlanmış Türkiye çalışmalarında
deprem için tipik değerler:

    litoloji/zemin  0.24 – 0.37   (en ağır faktör)
    yer ivmesi      0.09 – 0.38
    fay mesafesi    0.07 – 0.15   (senin kodunda 0.50)
    eğim            0.04 – 0.06

Bu dosyada literatüre dayalı alternatif ağırlık setleri de var
(bkz. AGIRLIKLAR_LITERATUR). Hangisini kullanacağın bir TEZ KARARI —
danışmanınla konuş. İkisiyle de çalıştırıp sonucu karşılaştırmak
(duyarlılık analizi) en güçlü seçenek olur.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

INF = math.inf

# ===========================================================================
# DEPREM
# ===========================================================================

# --- Fay hattına uzaklık (metre) ---
#
# ÖNEMLİ: Literatürde 500 m aralıklı 5 sınıflı bir şema BULUNAMADI. Doğrulanan
# şemalar 3 ve 4 sınıflı:
#   Ocak & Bahadır (2022): 0-1000 / 1000-2000 / >2000  (alt ağırlık .633/.260/.106)
#   Demir & Altaş (2024) : 0-1000 / 1000-2000 / 2000-5000 / 10000+
#
# Aşağıdaki 5 sınıflı tablo bu ikisinden UYARLANMIŞTIR. En içteki 500 m bandı,
# Sözbilir vd. (2015)'in Seferihisar Fayı için önerdiği 40 m'lik fay sakınım
# bandı ve planlama önlem alanı mantığından hareketle eklenmiştir.
#
# NOT (Seferihisar'a özel, tezde mutlaka kullan):
#   Sözbilir vd. (2015), Seferihisar Fay Zonu için fay izinin her iki yanında
#   20'şer metre, toplam 40 m "fay sakınım bandı" önerir. Bu, yüzey faylanması
#   tehlikesidir ve buradaki "sarsıntı yakınlığı" tamponundan FARKLI bir
#   olgudur. Tezde ikisini ayrı ayrı ele al.
FAY_MESAFE_SINIFLARI = [
    (0,    500,  5.0),   # [U] Sözbilir vd. 2015 sakınım bandı mantığıyla eklendi
    (500,  1000, 4.5),   # [K] Ocak & Bahadır 2022 en yüksek sınıfın devamı
    (1000, 2000, 3.5),   # [K] Ocak & Bahadır 2022 orta sınıf
    (2000, 5000, 2.0),   # [K] Demir & Altaş 2024 "az riskli"
    (5000, INF,  1.0),   # [K] Demir & Altaş 2024 "risksiz"
]

# Duyarlılık analizi için: doğrudan alıntılanabilir 3 sınıflı şema.
# gis_engine'de FAY_MESAFE_SINIFLARI yerine bunu koyup sonucu karşılaştır.
FAY_MESAFE_SINIFLARI_OCAK2022 = [
    (0,    1000, 5.0),   # [K] alt ağırlık 0.633
    (1000, 2000, 3.0),   # [K] alt ağırlık 0.260
    (2000, INF,  1.0),   # [K] alt ağırlık 0.106
]

# --- Eğim (derece) — DEPREM ---
#
# !!! BU TABLO DÜZELTİLDİ !!!
# İlk sürümde "düz alüvyal ovalar zemin büyütmesi nedeniyle daha riskli"
# varsayımıyla ters kurulmuştu (0-2° = 5 puan). Literatür taraması bunun
# YANLIŞ olduğunu gösterdi: doğrulanan bütün Türkiye deprem AHP çalışmaları
# eğimi DEPREM TETİKLEMELİ KÜTLE HAREKETİ olarak ele alır ve dik yamaçlara
# yüksek puan verir.
#
#   Ocak & Bahadır (2022): 0-2°:.035  2-5°:.068  5-15°:.134  15-35°:.260  35+:.503
#   Demir & Altaş (2024) : 30°+ = "çok riskli", 0-5° = "risksiz"
#   Erden & Karaman (2012): 0-10 / 10-15 / 15-30 / 30+ -> sınıf 1..4, 4 en kötü
#
# Zemin büyütmesi argümanı geçersiz değil — ama EĞİM katmanında değil,
# LİTOLOJİ katmanında ifade edilmeli (alüvyon = ZE/ZF = en yüksek puan).
# Ocak & Bahadır'ın ayrı bir "yeryüzü şekilleri" katmanı da vardır ve orada
# Ova 0.394, Alüvyon yelpazesi 0.267 ile en yüksek puanları alır.
EGIM_SINIFLARI_DEPREM = [
    (0,  2,  1.0),   # [K] Ocak & Bahadır 2022 (0.035)
    (2,  5,  1.5),   # [K] Ocak & Bahadır 2022 (0.068)
    (5,  15, 2.5),   # [K] Ocak & Bahadır 2022 (0.134)
    (15, 35, 3.5),   # [K] Ocak & Bahadır 2022 (0.260)
    (35, INF, 5.0),  # [K] Ocak & Bahadır 2022 (0.503)
]

# --- Litoloji — DEPREM (TBDY 2018 yerel zemin sınıfı üzerinden) ---
#
# Doğrulanan Türkiye çalışmalarının ikisi de kaya adını doğrudan puanlamaz;
# önce TBDY 2018 ZA-ZF yerel zemin sınıfına çevirir, sonra onu puanlar.
# Tezde savunması en kolay yol budur.
#
#   Ocak & Bahadır (2022): ZA .035 / ZB .068 / ZC .134 / ZD .260 / ZE .503
#   Demir & Altaş (2024) : ZF(alüvyon)=en riskli ... ZA(bazalt)=risksiz
#   TBDY 2018 Vs30: ZA >1500, ZB 760-1500, ZC 360-760, ZD 180-360, ZE <180,
#                   ZF sahaya özel (sıvılaşma riski dahil)
#
# UYARI: İzmir filişi ve Peridotit için yayımlanmış bir puan BULUNAMADI.
# Bu iki satır TBDY 2018 tanımlarından uzman ataması olarak türetilmiştir.
LITOLOJI_TBDY_SINIFI = {
    "Akarsu alüvyonları":              "ZF",  # [K] Demir & Altaş 2024: QAL = ZF
    "Ayrılmamış kuvaterner çökelleri": "ZE",  # [K] Ocak & Bahadır 2022: alüvyon = ZE
    "Alüvyon yelpazesi, Taraça":       "ZD",  # [U] daha iri/sıkı çökel
    "Yeniköy formasyonu":              "ZD",  # [K] kumtaşı+konglomera ~ ZC-ZD
    "Soma formasyonu":                 "ZC",  # [K] marn/kil içerikli
    "İzmir filişi":                    "ZC",  # [E] zayıf, çatlaklı kaya -> ZC tanımı
    "Rahmanlar aglomerası":            "ZB",  # [K] Demir & Altaş 2024: aglomera/andezit = ZB
    "Foça tüfleri":                    "ZB",  # [K] Demir & Altaş 2024: tüf = ZB
    "Kırkağaç formasyonu":             "ZB",  # [K] Ocak & Bahadır 2022: kireçtaşı = ZA
    "Peridotit":                       "ZA",  # [E] sağlam sert kaya -> ZA tanımı
}

TBDY_PUANLARI = {   # [K] Ocak & Bahadır 2022 alt ağırlıklarından ölçeklendi
    "ZA": 1.0, "ZB": 2.0, "ZC": 3.0, "ZD": 4.0, "ZE": 4.5, "ZF": 5.0,
}

LITOLOJI_SKORLARI_DEPREM = {
    ad: TBDY_PUANLARI[sinif] for ad, sinif in LITOLOJI_TBDY_SINIFI.items()
}

# --- Arazi kullanımı — DEPREM ---
#
# EN ZAYIF DAYANAKLI KATMAN. Türkiye deprem AHP literatüründe CORINE tabanlı
# bir yeniden sınıflandırma tablosu BULUNAMADI. Tek doğrulanan yön:
#   Partigöç & Dinçer (2024): tarım/mera = 1, orman/sanayi = 2, yerleşim = 3
# (çok tehlikeli bir afet risk analizi, saf deprem duyarlılığı değil; AHP
#  ağırlığı ve CR bildirilmemiş)
#
# Aşağıdaki tablo bu yönü korur ama ara değerler uzman atamasıdır [E].
# Tezde bu katmanın dayanağının zayıf olduğunu açıkça yaz ve ağırlığını
# düşük tut.
ARAZI_SKORLARI_DEPREM = {
    "Planı Olmayan Kentsel Yerleşik Alanlar": 5.0,  # [E]
    "Köy Yerleşik Alanları":                  4.5,  # [E]
    "Yapılaşmış Alanlar":                     4.0,  # [K] yerleşim en yüksek
    "Diğer Yapılaşmış Alanlar":               4.0,  # [K]
    "Sanayi Alanları":                        4.0,  # [K] sanayi orta-üst
    "Küçük Sanayi Siteleri":                  4.0,  # [K]
    "Plan İçi Yerleşim Alanları":             3.5,  # [E]
    "Turizm ve İkinci Konut Alanları":        3.0,  # [E]
    "Turizm Tesis Alanları":                  3.0,  # [E]
    "İdari ve Sosyal Tesis Alanları":         3.0,  # [E]
    "Arıtma Tesisleri":                       3.0,  # [E]
    "Kumsal ve Plajlar":                      3.0,  # [E] sıvılaşma/tsunami
    "Askeri Alanlar":                         2.0,  # [E]
    "Arkeolojik Alanlar":                     2.0,  # [E]
    "Orman Alanları":                         2.0,  # [K] orman orta (Partigöç 2)
    "Kuru Tarım Alanları":                    1.0,  # [K] tarım en düşük
    "Bağlık Alanlar":                         1.0,  # [K]
    "Zeytinlik Alanlar":                      1.0,  # [K]
    "Narenciye Bahçeleri":                    1.0,  # [K]
    "Diğer Meyve Bahçeleri ve Seralar":       1.0,  # [K]
    "Mera - Çayırlık Alanlar":                1.0,  # [K] mera en düşük
    "Fundalık Makilik Alanlar":               1.0,  # [E]
}

# --- Akarsuya uzaklık — DEPREM ---
# Deprem bağlamında akarsu yakınlığı doğrudan bir tehlike değil; genç alüvyal
# çökel ve sığ yeraltı suyu için dolaylı bir göstergedir (sıvılaşma).
# Ağırlığı düşük tutulmalı. [E]
AKARSU_MESAFE_SINIFLARI_DEPREM = [
    (0,    250,  4.0),   # [E] sıvılaşma için dolaylı gösterge
    (250,  500,  3.0),   # [E]
    (500,  1000, 2.0),   # [E]
    (1000, INF,  1.0),   # [E]
]


# ===========================================================================
# HEYELAN
# ===========================================================================

# --- Eğim (derece) — HEYELAN ---
#
# "Önce artar sonra azalır" davranışı literatürde TARTIŞMALI; tezde kesin
# gerçek gibi sunma, "çalışmaların çoğu..." diye çerçevele.
#
#   DESTEKLEYEN:
#     Berber & Ceryan (2023), Çanakkale/Biga — coğrafi olarak sana en yakın:
#        0-5°:.035  5-10°:.146  10-15°:.418(TEPE)  15-25°:.255  >25°:.146
#     Öz (2025), Elazığ (FR): 0-15:0.69  15-25:1.27  25-35:1.54(TEPE)
#                             35-45:0.20  >45:0.10  -> 35°'de çöküş
#     Liu vd. (2024), Xi'an: tepe 10-20°
#     Çellek (2020) derlemesi: heyelanların çoğu 15-35° arasında; çok dik
#        yamaçlarda ayrışma zonu ince kaldığı ve malzeme erozyonla
#        taşındığı için duyarlılık düşer (1-2 m örtü kalınlığına ulaşamaz)
#   ÇELİŞEN:
#     Sayın & Öztürk (2025): en yüksek FO en dik sınıfta (32-70°)
#     Dağ & Bulut (2012): en yüksek en düz sınıfta, monoton azalıyor
#
# 35° eşiği iki bağımsız kaynakta desteklendiği için burada kullanıldı.
EGIM_SINIFLARI_HEYELAN = [
    (0,  5,   1.0),   # [K] Berber & Ceryan 2023 (0.035)
    (5,  10,  2.5),   # [K] Berber & Ceryan 2023 (0.146)
    (10, 15,  5.0),   # [K] Berber & Ceryan 2023 (0.418) — TEPE
    (15, 25,  4.0),   # [K] Berber & Ceryan 2023 (0.255)
    (25, 35,  2.5),   # [U] Berber & Ceryan >25° (0.146) ile Öz 25-35 (1.54) arası
    (35, INF, 1.5),   # [K] Öz 2025: 35-45° FR 0.20, >45° FR 0.10
]

# --- Litoloji — HEYELAN ---
#
#   Berber & Ceryan (2023) AHP alt ağırlıkları (CR 0.071):
#     kumtaşı-çamurtaşı .460 | kireçtaşı-kumtaşı .254 | volkanik .201
#     kuvaterner birikim .054 | alüvyon .032
#   Sayın & Öztürk (2025) FO: ofiyolitik melanj 1.200 (yüksek!),
#     neritik kireçtaşı 1.268, "Ayrılmamış Kuvaterner" 0.000 (tam etiket eşleşmesi)
#
# EN ÖNEMLİ METODOLOJİK NOT (Dağ & Bulut 2012):
#   Ayrışma derecesi kaya türünden daha belirleyici. Aynı kayacın "az ayrışmış"
#   hâli 0.0000, "tamamen ayrışmış" hâli 1.5936 puan alıyor. Elinde ayrışma
#   verisi olmadığı için bu katmanın belirsizliğini tezde belirt.
#
# UYARI: İzmir filişi ve Foça tüfleri için yayımlanmış heyelan puanı YOK.
LITOLOJI_SKORLARI_HEYELAN = {
    "Yeniköy formasyonu":              5.0,  # [K] kumtaşı-çamurtaşı (0.460, en yüksek)
    "İzmir filişi":                    4.5,  # [E] fliş = zayıf kırıntılı; yayın yok
    "Soma formasyonu":                 3.0,  # [K] kireçtaşı-marn-kil (0.254)
    "Kırkağaç formasyonu":             3.0,  # [K] neritik kireçtaşı (FO 1.268)
    "Peridotit":                       3.0,  # [K] ofiyolitik melanj (FO 1.200)
    "Rahmanlar aglomerası":            2.5,  # [K] volkanik (0.201)
    "Foça tüfleri":                    2.5,  # [E] volkanik grubuna atandı
    "Alüvyon yelpazesi, Taraça":       1.5,  # [K] kuvaterner birikim (0.054)
    "Akarsu alüvyonları":              1.0,  # [K] alüvyon (0.032)
    "Ayrılmamış kuvaterner çökelleri": 1.0,  # [K] "Ayrılmamış Kuvaterner" FO 0.000
}

# --- Akarsuya uzaklık — HEYELAN ---
# Şev topuğu aşındırması yalnızca DAR tamponlarda görülüyor. Geniş tamponlarda
# (>400 m) ilişki sık sık tersine dönüyor — tezde ölçeğe bağımlı olduğunu yaz.
#   Öz (2025) FR       : 0-50 m 1.31 | 50-100 1.27 | 100-150 0.94 | 150-200 0.58
#   Dağ & Bulut (2012) : 0-50 m 0.1504 (en yüksek), sonrası düşük ve düz
#   Güneş & Kömüşcü    : 0-50 m 5 ... >250 m 1
LITOLOJI_VARSAYILAN = 3.0
AKARSU_MESAFE_SINIFLARI_HEYELAN = [
    (0,   50,  5.0),   # [K] Öz 2025 (FR 1.31), Dağ & Bulut 2012
    (50,  100, 4.0),   # [K] Öz 2025 (FR 1.27)
    (100, 150, 3.0),   # [K] Öz 2025 (FR 0.94)
    (150, 250, 2.0),   # [K] Öz 2025 (FR 0.58)
    (250, INF, 1.0),   # [K] Güneş & Kömüşcü 2025
]

# --- Fay hattına uzaklık — HEYELAN ---
# Bu faktörde doğrulanan kaynakların HEPSİ hemfikir: mesafeyle azalıyor.
#   Öz (2025) FR: 0-500 m 2.16 | 500-1000 2.00 | 1000-5000 1.75 | >5000 0.17
FAY_MESAFE_SINIFLARI_HEYELAN = [
    (0,    500,  5.0),   # [K] Öz 2025 (FR 2.16)
    (500,  1000, 4.5),   # [K] Öz 2025 (FR 2.00)
    (1000, 5000, 3.5),   # [K] Öz 2025 (FR 1.75)
    (5000, INF,  1.0),   # [K] Öz 2025 (FR 0.17)
]

# --- Arazi kullanımı — HEYELAN ---
#
# !!! TEZDE MUTLAKA AÇIKLA — LİTERATÜRDE ÇELİŞKİ VAR !!!
#
# "Orman kök sistemiyle heyelanı azaltır" görüşü 5 kaynağın 3'ünde destekleniyor:
#   Öz (2025): orman FR = 0.00 (ormanda hiç heyelan yok), ağaçlandırma 0.01,
#              buna karşılık bağ-bahçe 2.85
#   Şengür & Uncu (2025): çıplak alan .372 > mera .243 > orman .162
#   Dağ & Bulut (2012): tarım .0761 > yerleşim .0497 > orman .0474
#
# AMA: Berber & Ceryan (2023) — Çanakkale/Biga, sana COĞRAFİ OLARAK EN YAKIN
# çalışma — ORMANA EN YÜKSEK puanı veriyor (0.342). Muhtemel açıklama
# karıştırıcı değişken: orman zaten dik, nemli, ayrışmış yamaçları kaplıyor.
# Ama yazarlar bunu söylemiyor, o yüzden bu gerekçeyi onlara atfetme.
#
# Bu tabloda çoğunluk görüşü + mekanizma benimsendi. Duyarlılık analizi için
# ARAZI_SKORLARI_HEYELAN_BERBER2023 alternatifini kullan.
ARAZI_SKORLARI_HEYELAN = {
    "Planı Olmayan Kentsel Yerleşik Alanlar": 4.5,  # [E]
    "Kuru Tarım Alanları":                    4.0,  # [K] Öz 2025 bağ-bahçe/tarım yüksek
    "Bağlık Alanlar":                         4.5,  # [K] Öz 2025 bağ-bahçe FR 2.85
    "Narenciye Bahçeleri":                    4.0,  # [K] bağ-bahçe grubu
    "Diğer Meyve Bahçeleri ve Seralar":       4.0,  # [K] bağ-bahçe grubu
    "Zeytinlik Alanlar":                      3.5,  # [U] kalıcı ürün
    "Mera - Çayırlık Alanlar":                3.0,  # [K] Öz 2025 mera FR 1.41
    "Diğer Yapılaşmış Alanlar":               3.0,  # [E]
    "Yapılaşmış Alanlar":                     3.0,  # [E]
    "Köy Yerleşik Alanları":                  3.0,  # [E]
    "Küçük Sanayi Siteleri":                  2.5,  # [E]
    "Sanayi Alanları":                        2.5,  # [E]
    "Plan İçi Yerleşim Alanları":             2.0,  # [K] yerleşim düşük (Öz 2025: 0)
    "Turizm ve İkinci Konut Alanları":        2.0,  # [E]
    "Turizm Tesis Alanları":                  2.0,  # [E]
    "İdari ve Sosyal Tesis Alanları":         2.0,  # [E]
    "Arıtma Tesisleri":                       2.0,  # [E]
    "Arkeolojik Alanlar":                     2.0,  # [E]
    "Askeri Alanlar":                         2.0,  # [E]
    "Fundalık Makilik Alanlar":               2.0,  # [U] seyrek bitki örtüsü
    "Kumsal ve Plajlar":                      1.0,  # [E]
    "Orman Alanları":                         1.0,  # [K] Öz 2025 FR 0.00
}

# Duyarlılık analizi alternatifi: ormanı en yüksek sayan yakın-bölge şeması
ARAZI_SKORLARI_HEYELAN_BERBER2023 = dict(ARAZI_SKORLARI_HEYELAN, **{
    "Orman Alanları":             5.0,   # [K] Berber & Ceryan 2023 (0.342)
    "Kuru Tarım Alanları":        4.0,   # [K] (0.268)
    "Mera - Çayırlık Alanlar":    3.5,   # [K] çayır-mera (0.218)
    "Plan İçi Yerleşim Alanları": 1.5,   # [K] şehir yapısı (0.072)
    "Sanayi Alanları":            1.5,   # [K] endüstriyel-ticari (0.069)
})


# ===========================================================================
# SEL / TAŞKIN
# ===========================================================================

# --- Akarsuya uzaklık — SEL ---
#
# Taşkın çalışmalarında genellikle EN AĞIR faktör (0.22-0.35).
# En içteki "çok yüksek" bandı kaynaklarda 100-250 m arasında değişiyor.
#   Köroğlu & Akıncı (2023): 0-100 / 100-200 / 200-300 / 300-400 / >400 -> 5..1
#   Koralay & Kara (2024)  : 0-250 / 250-500 / 500-750 / 750-1000 / >1000 -> 5..1
#   Kazakis (2015) şeması  : <200 / 200-500 / 500-1000 / 1000-2000 / >2000 -> 10..2
#
# Aşağıdaki dizi bu üçünden UYARLANMIŞTIR; birebir aynısını kullanan tek bir
# yayın bulunamadı. Tezde "…'dan uyarlanmıştır" diye yaz, doğrudan atıf verme.
AKARSU_MESAFE_SINIFLARI_SEL = [
    (0,    100,  5.0),   # [U] Köroğlu & Akıncı 2023 (0-100 = 5)
    (100,  250,  4.0),   # [U] Köroğlu & Akıncı / Koralay & Kara arası
    (250,  500,  3.0),   # [K] Kazakis 2015 (200-500 = 8/10)
    (500,  1000, 2.0),   # [K] Kazakis 2015 (500-1000 = 6/10)
    (1000, INF,  1.0),   # [K] Koralay & Kara 2024 (>1000 = 1)
]

# --- Eğim (derece) — SEL ---
# Bütün kaynaklar hemfikir: düz = yüksek duyarlılık.
#   Köroğlu & Akıncı (2023): 0-2 / 2-4 / 4-6 / 6-10 / >10 -> 5/4/3/2/1  (derece)
#   Kazakis (2015)         : <4 / 4-8 / 8-15 / 15-25 / >25 -> 10/8/6/4/2
# Köroğlu & Akıncı şeması doğrudan alıntılanabilir olduğu için o kullanıldı.
EGIM_SINIFLARI_SEL = [
    (0,  2,   5.0),   # [K] Köroğlu & Akıncı 2023
    (2,  4,   4.0),   # [K]
    (4,  6,   3.0),   # [K]
    (6,  10,  2.0),   # [K]
    (10, INF, 1.0),   # [K]
]

# --- Litoloji — SEL ---
#
# !!! LİTERATÜRDE İKİ ZITT GELENEK VAR — TEZDE İKİSİNİ DE ANLAT !!!
#
# A) GEÇİRİMLİLİK MANTIĞI: geçirimli = DÜŞÜK tehlike
#    Kazakis (2015)/Patrikaki (2018): alüvyon 2, taraça 4, neojen 6,
#    mermer 8, kristalin (geçirimsiz) 10.
#    Gerekçe: "geçirimsiz kayaçlar yüzey akışını artırır."
#
# B) TAŞKIN OVASI MANTIĞI: alüvyon = EN YÜKSEK
#    Köroğlu & Akıncı (2023): alüvyon 5, diğer kayaçlar 1
#    Tanış & Çelik (2024): alüvyon 5, kireçtaşı 4, kuvarsit 2, bazalt 1
#    Gerekçe: alüvyon zaten taşkının tarihsel kaydıdır — yani arazi biçimi
#    taşkın olayının kendi izidir. Corapci & Özdemir (2024) bu argümanı
#    kentleşmiş alüvyal yelpazeler için açıkça kurar.
#
# Burada B benimsendi ve gerekçesi jeomorfolojik (taşkın ovası göstergesi),
# hidrojeolojik (sızma) değil. Tezde bunu açıkça yaz, A'yı da kaynak göstererek
# anlat ve duyarlılık testi yap. İyi haber: litoloji ağırlığı neredeyse bütün
# taşkın çalışmalarında 0.02-0.05 — yani seçim haritayı çok az değiştiriyor,
# bu da rapor edilebilir bir sonuç.
LITOLOJI_SKORLARI_SEL = {
    "Akarsu alüvyonları":              5.0,  # [K] Köroğlu & Akıncı 2023, Tanış & Çelik 2024
    "Ayrılmamış kuvaterner çökelleri": 4.5,  # [U] genç çökel
    "Alüvyon yelpazesi, Taraça":       4.5,  # [K] Corapci & Özdemir 2024 (yelpaze)
    "Kırkağaç formasyonu":             4.0,  # [K] Tanış & Çelik 2024: kireçtaşı = 4
    "Soma formasyonu":                 3.0,  # [U] kireçtaşı-marn-kil karışık
    "Yeniköy formasyonu":              3.0,  # [U] kırıntılı
    "İzmir filişi":                    2.5,  # [E] yayın yok; geçirimsiz kırıntılı
    "Foça tüfleri":                    2.0,  # [E] yayın yok
    "Rahmanlar aglomerası":            1.5,  # [U] volkanik, Tanış & Çelik bazalt = 1
    "Peridotit":                       1.0,  # [K] Tanış & Çelik 2024: bazalt/masif = 1
}

# --- Arazi kullanımı — SEL ---
# Sıralama 6 kaynağın 6'sında da aynı: geçirimsiz yüzey en yüksek, orman en düşük.
#   Köroğlu & Akıncı (2023): sulak alan 5 / yapılaşmış 4 / çayır 3 / tarım 2 / orman 1
#   Tanış & Çelik (2024)   : şehir 5 / sürekli ürün 4 / ekilebilir-mera 3 / karışık 2 / orman 1
#   Koralay & Kara (2024)  : yapılaşmış 5 / tarım 4 / mera 3 / çalı-çıplak 2 / orman 1
# Nicel dayanak istersen SCS TR-55 eğri numaraları (CN) bu sıralamayı destekler:
#   asfalt/çatı 98, ticari 89-95, sanayi 81-93, konut 51-92, sıra ekim 72-91,
#   çalılık 48-83, mera 39-80, orman 36-79.
ARAZI_SKORLARI_SEL = {
    "Planı Olmayan Kentsel Yerleşik Alanlar": 5.0,  # [K] yapılaşmış en yüksek
    "Yapılaşmış Alanlar":                     5.0,  # [K]
    "Diğer Yapılaşmış Alanlar":               5.0,  # [K]
    "Sanayi Alanları":                        4.5,  # [K] TR-55 CN 81-93
    "Küçük Sanayi Siteleri":                  4.5,  # [K]
    "Plan İçi Yerleşim Alanları":             4.5,  # [K]
    "Köy Yerleşik Alanları":                  4.0,  # [U]
    "Turizm ve İkinci Konut Alanları":        4.0,  # [U]
    "Turizm Tesis Alanları":                  4.0,  # [U]
    "İdari ve Sosyal Tesis Alanları":         4.0,  # [U]
    "Arıtma Tesisleri":                       4.0,  # [U]
    "Kumsal ve Plajlar":                      3.5,  # [E] kıyı taşkını
    "Narenciye Bahçeleri":                    3.0,  # [K] Tanış & Çelik: sürekli ürün = 4
    "Diğer Meyve Bahçeleri ve Seralar":       3.0,  # [K]
    "Bağlık Alanlar":                         3.0,  # [K]
    "Zeytinlik Alanlar":                      3.0,  # [K]
    "Kuru Tarım Alanları":                    2.5,  # [K] tarım orta
    "Mera - Çayırlık Alanlar":                2.5,  # [K] mera/çayır orta
    "Arkeolojik Alanlar":                     2.0,  # [E]
    "Askeri Alanlar":                         2.0,  # [E]
    "Fundalık Makilik Alanlar":               2.0,  # [K] çalı, TR-55 CN 48-83
    "Orman Alanları":                         1.0,  # [K] orman en düşük, 6/6 kaynak
}

# --- Fay hattına uzaklık — SEL ---
# Taşkınla nedensel ilişkisi zayıf; ağırlığı çok düşük tutulmalı. [E]
FAY_MESAFE_SINIFLARI_SEL = [
    (0,    1000, 3.0),   # [E] taşkınla nedensel bağı zayıf
    (1000, 5000, 2.0),   # [E]
    (5000, INF,  1.0),   # [E]
]


# ===========================================================================
# TOPLU ERİŞİM
# ===========================================================================

VARSAYILANLAR = {"litoloji": 3.0, "arazi": 2.5}

TABLOLAR = {
    "DEPREM": {
        "Fay_Hattı_Uzaklığı": FAY_MESAFE_SINIFLARI,
        "Akarsu_Uzaklığı":    AKARSU_MESAFE_SINIFLARI_DEPREM,
        "Eğim":               EGIM_SINIFLARI_DEPREM,
        "Litoloji":           LITOLOJI_SKORLARI_DEPREM,
        "Arazi_Kullanımı":    ARAZI_SKORLARI_DEPREM,
    },
    "HEYELAN": {
        "Fay_Hattı_Uzaklığı": FAY_MESAFE_SINIFLARI_HEYELAN,
        "Akarsu_Uzaklığı":    AKARSU_MESAFE_SINIFLARI_HEYELAN,
        "Eğim":               EGIM_SINIFLARI_HEYELAN,
        "Litoloji":           LITOLOJI_SKORLARI_HEYELAN,
        "Arazi_Kullanımı":    ARAZI_SKORLARI_HEYELAN,
    },
    "SEL": {
        "Fay_Hattı_Uzaklığı": FAY_MESAFE_SINIFLARI_SEL,
        "Akarsu_Uzaklığı":    AKARSU_MESAFE_SINIFLARI_SEL,
        "Eğim":               EGIM_SINIFLARI_SEL,
        "Litoloji":           LITOLOJI_SKORLARI_SEL,
        "Arazi_Kullanımı":    ARAZI_SKORLARI_SEL,
    },
}


# ===========================================================================
# AĞIRLIKLAR
# ===========================================================================

# Koddaki mevcut ağırlıklar (değiştirilmedi — karşılaştırma için burada)
AGIRLIKLAR_MEVCUT = {
    "DEPREM":  {"Fay_Hattı_Uzaklığı": 0.50, "Litoloji": 0.30, "Eğim": 0.05,
                "Akarsu_Uzaklığı": 0.05, "Arazi_Kullanımı": 0.10},
    "HEYELAN": {"Fay_Hattı_Uzaklığı": 0.15, "Litoloji": 0.35, "Eğim": 0.40,
                "Akarsu_Uzaklığı": 0.05, "Arazi_Kullanımı": 0.05},
    "SEL":     {"Fay_Hattı_Uzaklığı": 0.05, "Litoloji": 0.15, "Eğim": 0.10,
                "Akarsu_Uzaklığı": 0.60, "Arazi_Kullanımı": 0.10},
}

# Literatürdeki yayımlanmış aralıkların ortasına oturan alternatif set.
# Beş faktöre indirgenmiş ve 1.0'a normalize edilmiştir.
#
# DEPREM  — Ocak & Bahadır (2022) CR 0.08; Demir & Altaş (2024) CR 0.023:
#   litoloji/zemin .31-.37 | fay .11-.15 | eğim .04-.05
#   (yer ivmesi ve yeraltı suyu katmanları elimizde yok, ağırlıkları dağıtıldı)
# HEYELAN — Berber & Ceryan (2023) CR 0.054; Öz (2025) CR 0.080:
#   litoloji .21-.25 | eğim .19-.20 | arazi .03-.17 | fay .08 | akarsu .05-.06
# SEL     — Yurteri (2024) CR 0.058; Tanış & Çelik (2024) CR 0.09:
#   akarsu mesafesi .31-.37 | eğim .18-.28 | arazi .08-.18 | litoloji .02-.05
AGIRLIKLAR_LITERATUR = {
    "DEPREM":  {"Litoloji": 0.45, "Fay_Hattı_Uzaklığı": 0.30, "Eğim": 0.08,
                "Arazi_Kullanımı": 0.12, "Akarsu_Uzaklığı": 0.05},
    "HEYELAN": {"Litoloji": 0.34, "Eğim": 0.30, "Arazi_Kullanımı": 0.14,
                "Fay_Hattı_Uzaklığı": 0.14, "Akarsu_Uzaklığı": 0.08},
    "SEL":     {"Akarsu_Uzaklığı": 0.45, "Eğim": 0.30, "Arazi_Kullanımı": 0.16,
                "Litoloji": 0.05, "Fay_Hattı_Uzaklığı": 0.04},
}


# ===========================================================================
# DAYANAK ETİKETLERİ
# ===========================================================================
#
# Her tablo satırının yanındaki [K]/[U]/[E] etiketi, o değerin nereden geldiğini
# söyler. Etiketler kod yorumunda durduğu için tek okuma noktası burasıdır;
# tools/tablo_uret.py de, /api/yontem ucu da aynı fonksiyonu kullanır ki
# rapordaki sayı ile arayüzdeki sayı ayrışmasın.


def etiketleri_oku() -> dict[str, str]:
    """Bu dosyanın kaynağından her tablo satırının [K]/[U]/[E] etiketini çıkarır.

    Anahtar, satırın içinde bulunduğu sabitin adıyla birlikte kurulur; aksi
    hâlde farklı afet tablolarındaki aynı sayısal aralık (örn. (0, 500, 5.0))
    birbirinin kaynak notunu çeker.
    """
    kaynak = Path(__file__).read_text(encoding="utf-8")
    etiketler: dict[str, str] = {}
    sabit = ""
    for satir in kaynak.splitlines():
        bas = re.match(r"([A-Z_][A-Z0-9_]*)\s*=", satir)
        if bas:
            sabit = bas.group(1)
        m = re.search(r"#\s*\[([KUE])\]\s*(.*)$", satir)
        if not m:
            continue
        kod = satir.split("#")[0]
        not_metni = f"[{m.group(1)}] {m.group(2).strip()}"
        # Sözlük satırı:  "Ad": deger,     (tırnak içi boşluklar korunmalı)
        d = re.match(r'\s*"([^"]+)"\s*:\s*([^,]+),?\s*$', kod)
        if d:
            etiketler[f'{sabit}|"{d.group(1)}":{d.group(2).strip()}'] = not_metni
            continue
        # Demet satırı:  (alt, ust, puan),
        u = re.match(r"\s*\(([^)]*)\)\s*,?\s*$", kod)
        if u:
            parcalar = ",".join(x.strip() for x in u.group(1).split(","))
            etiketler[f"{sabit}|({parcalar})"] = not_metni
    return etiketler


def etiket_sayilari() -> dict[str, int]:
    """Kaç satır kaynaklı [K], kaç satır uyarlama [U], kaç satır eksper [E]."""
    degerler = etiketleri_oku().values()
    return {kod: sum(1 for v in degerler if v.startswith(f"[{kod}]"))
            for kod in ("K", "U", "E")}


# ===========================================================================
# KAYNAKÇA
# ===========================================================================

KAYNAKLAR = [
    "Berber, S., & Ceryan, Ş. (2023). Güzelyalı-Lapseki (Çanakkale) arasındaki "
    "bölgenin heyelan duyarlılığının analitik hiyerarşi süreci yöntemiyle (AHP) "
    "değerlendirilmesi. Balıkesir Üniversitesi Fen Bilimleri Enstitüsü Dergisi, "
    "25(1), 305-316. https://doi.org/10.25092/baunfbed.1208462",

    "Çellek, S. (2020). Effect of the slope angle and its classification on "
    "landslide [Preprint]. Natural Hazards and Earth System Sciences Discussions. "
    "https://doi.org/10.5194/nhess-2020-87  [ÖN BASKI — hakem sürecinden geçtiği "
    "doğrulanamadı, tezde bu durumu belirt]",

    "Corapci, F., & Özdemir, H. (2024). A new approach to flood susceptibility "
    "analysis of urbanised alluvial fans: The case of Bursa City (Türkiye). "
    "Natural Hazards, 120(14), 12909-12932. https://doi.org/10.1007/s11069-024-06723-w",

    "Dağ, S., & Bulut, F. (2012). Coğrafi Bilgi Sistemleri tabanlı heyelan "
    "duyarlılık haritalarının hazırlanmasına bir örnek: Çayeli (Rize, KD Türkiye). "
    "Jeoloji Mühendisliği Dergisi, 36(1), 35-62.",

    "Danacıoğlu, Ş., & Öz, M. N. (2025). Tahtalı Barajı Havzasında bulanık mantık "
    "yöntemi ile taşkın risk analizi. Journal of Anatolian Geography, 2(1), 82-89. "
    "[TÜBİTAK 2209-A destekli, İzmir — en yakın kurumsal ve bölgesel emsal]",

    "Demir, M., & Altaş, N. T. (2024). Kars kentinde deprem hasar risk potansiyeli "
    "taşıyan alanların CBS tabanlı AHP analizlerine dayalı olarak belirlenmesi. "
    "Geomatik, 9(1), 123-140. https://doi.org/10.29128/geomatik.1375650",

    "Erden, T., & Karaman, H. (2012). Analysis of earthquake parameters to generate "
    "hazard maps by integrating AHP and GIS for Küçükçekmece region. Natural Hazards "
    "and Earth System Sciences, 12, 475-483. https://doi.org/10.5194/nhess-12-475-2012",

    "Kazakis, N., Kougias, I., & Patsialis, T. (2015). Assessment of flood hazard "
    "areas at a regional scale using an index-based approach and Analytical Hierarchy "
    "Process: Application in Rhodope-Evros region, Greece. Science of the Total "
    "Environment, 538, 555-563. https://doi.org/10.1016/j.scitotenv.2015.08.055",

    "Köroğlu, B., & Akıncı, H. (2023). Coğrafi Bilgi Sistemleri tabanlı çok kriterli "
    "karar analizi ile Giresun İli Dereli İlçesinin taşkın duyarlılık analizi. Artvin "
    "Çoruh Üniversitesi Mühendislik ve Fen Bilimleri Dergisi, 1(2), 62-81.",

    "Koralay, N., & Kara, Ö. (2024). Assessment of flood risk in Söğütlü stream "
    "watershed of Trabzon province in Turkey using geographic information systems and "
    "analytic hierarchy process approach. Natural Hazards. "
    "https://doi.org/10.1007/s11069-024-06594-1",

    "Ocak, F., & Bahadır, M. (2022). CBS teknikleri kullanılarak deprem duyarlılık "
    "analizi için Analitik Hiyerarşi Prosesi: Samsun Ladik Gölü Havzası örneği, "
    "Türkiye. Kesit Akademi Dergisi, (33).",

    "Öz, T. (2025). Heyelan duyarlılığının Analitik Hiyerarşi Süreci (AHS) ve Frekans "
    "Oranı (FR) ile belirlenmesi: Kürk Çayı Havzası (Elazığ) örneği. Fırat "
    "Üniversitesi Sosyal Bilimler Dergisi, 35(2), 467-485. "
    "https://doi.org/10.18069/firatsbed.1572408",

    "Partigöç, N. S., & Dinçer, C. (2024). Coğrafi bilgi sistemleri (CBS) tabanlı "
    "afet risk analizi: Denizli ili örneği. Geomatik, 9(1), 27-44. "
    "https://doi.org/10.29128/geomatik.1261051",

    "Patrikaki, O., Kazakis, N., Kougias, I., Patsialis, T., Theodossiou, N., & "
    "Voudouris, K. (2018). Assessing flood hazard at river basin scale with an "
    "index-based approach: The case of Mouriki, Greece. Geosciences, 8(2), 50. "
    "https://doi.org/10.3390/geosciences8020050",

    "Sayın, H., & Öztürk, Y. (2025). Akyayla Dağı'nın heyelan morfolojisi ve heyelan "
    "duyarlılığının CBS tabanlı Frekans Oranı (FO) yöntemi ile analizi "
    "(Doğubayazıt/Ağrı). Jeoloji Mühendisliği Dergisi, 49(2), 23-54. "
    "https://doi.org/10.24232/jmd.1704248",

    "Sözbilir, H., Sümer, Ö., Uzel, B., Tepe, Ç., Softa, M., Eski, S., Babayiğit, G., "
    "Turan, R., Karaş, M., & Koşum, S. (2015). İzmir kenti içinden geçen diri "
    "faylarda fay sakınım bandı / yüzey faylanması tehlikesi kuşağı oluşturma "
    "kriterleri. 3. Türkiye Deprem Mühendisliği ve Sismoloji Konferansı, DEÜ, İzmir. "
    "[SEFERİHİSAR FAYI İÇİN 40 m SAKINIM BANDI — çalışma alanına en özgü kaynak]",

    "Tanış, E., & Çelik, R. (2024). CBS tabanlı AHP çok kriterli karar verme yöntemi "
    "kullanılarak Van Gölü Güzelsu Alt Havzası taşkın risk haritalarının çıkarılması "
    "ve değerlendirilmesi. Dicle Üniversitesi Mühendislik Fakültesi Mühendislik "
    "Dergisi, 15(4), 941-950. https://doi.org/10.24012/dumf.1534940",

    "Türkiye Bina Deprem Yönetmeliği (TBDY). (2018). Resmî Gazete, 18 Mart 2018, "
    "Sayı 30364 (Mükerrer). Tablo 16.1 yerel zemin sınıfları (ZA-ZF). "
    "[RESMÎ METNİ KENDİN DOĞRULA — bu proje ikincil kaynaktan teyit etti]",

    "Yurteri, C. (2024). Coğrafi Bilgi Sistemleri (CBS) ortamında Analitik Hiyerarşi "
    "Yöntemi (AHY) kullanılarak taşkın risk analizi: Karabük İli örneği. Mühendislik "
    "Bilimleri ve Tasarım Dergisi, 12(2), 298-318. https://doi.org/10.21923/jesd.1438999 "
    "[Eğim şeması İÇ ÇELİŞKİLİ — eğim için ATIF VERME, sadece ağırlıklar için kullan]",
]

# Tezde ATIF VERİLMEMESİ gereken kaynaklar (iç çelişki tespit edildi)
ATIF_VERME = {
    "Güneş & Kömüşcü (2025)": "Eğim ve litoloji tabloları metindeki ifadeyle çelişiyor.",
    "Özşahin (2014)": "Alt sınıf tablolarının yönü metindeki ifadeyle ters. "
                      "Faktör ağırlıkları kullanılabilir.",
    "Şengür & Uncu (2025)": "Fay ve akarsu mesafesi tabloları birbirinin kopyası.",
    "Yurteri (2024) eğim tablosu": "0-3° en düşük, 30-76° en yüksek — metinle çelişiyor. "
                                   "Ağırlıkları kullanılabilir.",
}
