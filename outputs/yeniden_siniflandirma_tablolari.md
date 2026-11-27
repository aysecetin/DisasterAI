# Yeniden Sınıflandırma Tabloları

Seferihisar (İzmir) afet risk analizi — ağırlıklı çakıştırmada kullanılan
faktörlerin 1–5 risk puanına dönüştürülme kuralları.

Bu dosya `src/reclass_tables.py` dosyasından otomatik üretilmiştir.
Elle düzenleme; kodu değiştir ve `tools/tablo_uret.py` scriptini yeniden çalıştır.

## Güven seviyeleri

| Etiket | Anlamı |
|---|---|
| **[K]** | Kaynaklı — yayımlanmış bir çalışmadan alınmış/ölçeklenmiş |
| **[U]** | Uyarlama — yayımlanmış şemalardan uyarlanmış, birebir alıntı değil |
| **[E]** | Eksper ataması — literatürde karşılığı bulunamadı |

> **[E]** etiketli değerler tezde *"tarafımızca atanmıştır"* diye belirtilmeli.
> Bunları kaynaklı gibi sunmak akademik hata olur.

## Deprem

### Fay hattına uzaklık (m)

| Sınıf | Risk puanı | Dayanak |
|---|---|---|
| 0 – 500 | 5 | [U] Sözbilir vd. 2015 sakınım bandı mantığıyla eklendi |
| 500 – 1.000 | 4.5 | [K] Ocak & Bahadır 2022 en yüksek sınıfın devamı |
| 1.000 – 2.000 | 3.5 | [K] Ocak & Bahadır 2022 orta sınıf |
| 2.000 – 5.000 | 2 | [K] Demir & Altaş 2024 "az riskli" |
| > 5.000 | 1 | [K] Demir & Altaş 2024 "risksiz" |

### Akarsuya uzaklık (m)

| Sınıf | Risk puanı | Dayanak |
|---|---|---|
| 0 – 250 | 4 | [E] sıvılaşma için dolaylı gösterge |
| 250 – 500 | 3 | [E]  |
| 500 – 1.000 | 2 | [E]  |
| > 1.000 | 1 | [E]  |

### Eğim (derece)

| Sınıf | Risk puanı | Dayanak |
|---|---|---|
| 0 – 2 | 1 | [K] Ocak & Bahadır 2022 (0.035) |
| 2 – 5 | 1.5 | [K] Ocak & Bahadır 2022 (0.068) |
| 5 – 15 | 2.5 | [K] Ocak & Bahadır 2022 (0.134) |
| 15 – 35 | 3.5 | [K] Ocak & Bahadır 2022 (0.260) |
| > 35 | 5 | [K] Ocak & Bahadır 2022 (0.503) |

### Litoloji (Formasyon)

| Sınıf | Risk puanı | Dayanak |
|---|---|---|
| Akarsu alüvyonları | 5 | [K] Demir & Altaş 2024: QAL = ZF |
| Ayrılmamış kuvaterner çökelleri | 4.5 | [K] Ocak & Bahadır 2022: alüvyon = ZE |
| Alüvyon yelpazesi, Taraça | 4 | [U] daha iri/sıkı çökel |
| Yeniköy formasyonu | 4 | [K] kumtaşı+konglomera ~ ZC-ZD |
| Soma formasyonu | 3 | [K] marn/kil içerikli |
| İzmir filişi | 3 | [E] zayıf, çatlaklı kaya -> ZC tanımı |
| Rahmanlar aglomerası | 2 | [K] Demir & Altaş 2024: aglomera/andezit = ZB |
| Foça tüfleri | 2 | [K] Demir & Altaş 2024: tüf = ZB |
| Kırkağaç formasyonu | 2 | [K] Ocak & Bahadır 2022: kireçtaşı = ZA |
| Peridotit | 1 | [E] sağlam sert kaya -> ZA tanımı |

### Arazi kullanımı

| Sınıf | Risk puanı | Dayanak |
|---|---|---|
| Planı Olmayan Kentsel Yerleşik Alanlar | 5 | [E]  |
| Köy Yerleşik Alanları | 4.5 | [E]  |
| Yapılaşmış Alanlar | 4 | [K] yerleşim en yüksek |
| Diğer Yapılaşmış Alanlar | 4 | [K]  |
| Sanayi Alanları | 4 | [K] sanayi orta-üst |
| Küçük Sanayi Siteleri | 4 | [K]  |
| Plan İçi Yerleşim Alanları | 3.5 | [E]  |
| Turizm ve İkinci Konut Alanları | 3 | [E]  |
| Turizm Tesis Alanları | 3 | [E]  |
| İdari ve Sosyal Tesis Alanları | 3 | [E]  |
| Arıtma Tesisleri | 3 | [E]  |
| Kumsal ve Plajlar | 3 | [E] sıvılaşma/tsunami |
| Askeri Alanlar | 2 | [E]  |
| Arkeolojik Alanlar | 2 | [E]  |
| Orman Alanları | 2 | [K] orman orta (Partigöç 2) |
| Kuru Tarım Alanları | 1 | [K] tarım en düşük |
| Bağlık Alanlar | 1 | [K]  |
| Zeytinlik Alanlar | 1 | [K]  |
| Narenciye Bahçeleri | 1 | [K]  |
| Diğer Meyve Bahçeleri ve Seralar | 1 | [K]  |
| Mera - Çayırlık Alanlar | 1 | [K] mera en düşük |
| Fundalık Makilik Alanlar | 1 | [E]  |

## Heyelan

### Fay hattına uzaklık (m)

| Sınıf | Risk puanı | Dayanak |
|---|---|---|
| 0 – 500 | 5 | [K] Öz 2025 (FR 2.16) |
| 500 – 1.000 | 4.5 | [K] Öz 2025 (FR 2.00) |
| 1.000 – 5.000 | 3.5 | [K] Öz 2025 (FR 1.75) |
| > 5.000 | 1 | [K] Öz 2025 (FR 0.17) |

### Akarsuya uzaklık (m)

| Sınıf | Risk puanı | Dayanak |
|---|---|---|
| 0 – 50 | 5 | [K] Öz 2025 (FR 1.31), Dağ & Bulut 2012 |
| 50 – 100 | 4 | [K] Öz 2025 (FR 1.27) |
| 100 – 150 | 3 | [K] Öz 2025 (FR 0.94) |
| 150 – 250 | 2 | [K] Öz 2025 (FR 0.58) |
| > 250 | 1 | [K] Güneş & Kömüşcü 2025 |

### Eğim (derece)

| Sınıf | Risk puanı | Dayanak |
|---|---|---|
| 0 – 5 | 1 | [K] Berber & Ceryan 2023 (0.035) |
| 5 – 10 | 2.5 | [K] Berber & Ceryan 2023 (0.146) |
| 10 – 15 | 5 | [K] Berber & Ceryan 2023 (0.418) — TEPE |
| 15 – 25 | 4 | [K] Berber & Ceryan 2023 (0.255) |
| 25 – 35 | 2.5 | [U] Berber & Ceryan >25° (0.146) ile Öz 25-35 (1.54) arası |
| > 35 | 1.5 | [K] Öz 2025: 35-45° FR 0.20, >45° FR 0.10 |

### Litoloji (Formasyon)

| Sınıf | Risk puanı | Dayanak |
|---|---|---|
| Yeniköy formasyonu | 5 | [K] kumtaşı-çamurtaşı (0.460, en yüksek) |
| İzmir filişi | 4.5 | [E] fliş = zayıf kırıntılı; yayın yok |
| Soma formasyonu | 3 | [K] kireçtaşı-marn-kil (0.254) |
| Kırkağaç formasyonu | 3 | [K] neritik kireçtaşı (FO 1.268) |
| Peridotit | 3 | [K] ofiyolitik melanj (FO 1.200) |
| Rahmanlar aglomerası | 2.5 | [K] volkanik (0.201) |
| Foça tüfleri | 2.5 | [E] volkanik grubuna atandı |
| Alüvyon yelpazesi, Taraça | 1.5 | [K] kuvaterner birikim (0.054) |
| Akarsu alüvyonları | 1 | [K] alüvyon (0.032) |
| Ayrılmamış kuvaterner çökelleri | 1 | [K] "Ayrılmamış Kuvaterner" FO 0.000 |

### Arazi kullanımı

| Sınıf | Risk puanı | Dayanak |
|---|---|---|
| Planı Olmayan Kentsel Yerleşik Alanlar | 4.5 | [E]  |
| Bağlık Alanlar | 4.5 | [K] Öz 2025 bağ-bahçe FR 2.85 |
| Kuru Tarım Alanları | 4 | [K] Öz 2025 bağ-bahçe/tarım yüksek |
| Narenciye Bahçeleri | 4 | [K] bağ-bahçe grubu |
| Diğer Meyve Bahçeleri ve Seralar | 4 | [K] bağ-bahçe grubu |
| Zeytinlik Alanlar | 3.5 | [U] kalıcı ürün |
| Mera - Çayırlık Alanlar | 3 | [K] Öz 2025 mera FR 1.41 |
| Diğer Yapılaşmış Alanlar | 3 | [E]  |
| Yapılaşmış Alanlar | 3 | [E]  |
| Köy Yerleşik Alanları | 3 | [E]  |
| Küçük Sanayi Siteleri | 2.5 | [E]  |
| Sanayi Alanları | 2.5 | [E]  |
| Plan İçi Yerleşim Alanları | 2 | [K] yerleşim düşük (Öz 2025: 0) |
| Turizm ve İkinci Konut Alanları | 2 | [E]  |
| Turizm Tesis Alanları | 2 | [E]  |
| İdari ve Sosyal Tesis Alanları | 2 | [E]  |
| Arıtma Tesisleri | 2 | [E]  |
| Arkeolojik Alanlar | 2 | [E]  |
| Askeri Alanlar | 2 | [E]  |
| Fundalık Makilik Alanlar | 2 | [U] seyrek bitki örtüsü |
| Kumsal ve Plajlar | 1 | [E]  |
| Orman Alanları | 1 | [K] Öz 2025 FR 0.00 |

## Sel

### Fay hattına uzaklık (m)

| Sınıf | Risk puanı | Dayanak |
|---|---|---|
| 0 – 1.000 | 3 | [E] taşkınla nedensel bağı zayıf |
| 1.000 – 5.000 | 2 | [E]  |
| > 5.000 | 1 | [E]  |

### Akarsuya uzaklık (m)

| Sınıf | Risk puanı | Dayanak |
|---|---|---|
| 0 – 100 | 5 | [U] Köroğlu & Akıncı 2023 (0-100 = 5) |
| 100 – 250 | 4 | [U] Köroğlu & Akıncı / Koralay & Kara arası |
| 250 – 500 | 3 | [K] Kazakis 2015 (200-500 = 8/10) |
| 500 – 1.000 | 2 | [K] Kazakis 2015 (500-1000 = 6/10) |
| > 1.000 | 1 | [K] Koralay & Kara 2024 (>1000 = 1) |

### Eğim (derece)

| Sınıf | Risk puanı | Dayanak |
|---|---|---|
| 0 – 2 | 5 | [K] Köroğlu & Akıncı 2023 |
| 2 – 4 | 4 | [K]  |
| 4 – 6 | 3 | [K]  |
| 6 – 10 | 2 | [K]  |
| > 10 | 1 | [K]  |

### Litoloji (Formasyon)

| Sınıf | Risk puanı | Dayanak |
|---|---|---|
| Akarsu alüvyonları | 5 | [K] Köroğlu & Akıncı 2023, Tanış & Çelik 2024 |
| Ayrılmamış kuvaterner çökelleri | 4.5 | [U] genç çökel |
| Alüvyon yelpazesi, Taraça | 4.5 | [K] Corapci & Özdemir 2024 (yelpaze) |
| Kırkağaç formasyonu | 4 | [K] Tanış & Çelik 2024: kireçtaşı = 4 |
| Soma formasyonu | 3 | [U] kireçtaşı-marn-kil karışık |
| Yeniköy formasyonu | 3 | [U] kırıntılı |
| İzmir filişi | 2.5 | [E] yayın yok; geçirimsiz kırıntılı |
| Foça tüfleri | 2 | [E] yayın yok |
| Rahmanlar aglomerası | 1.5 | [U] volkanik, Tanış & Çelik bazalt = 1 |
| Peridotit | 1 | [K] Tanış & Çelik 2024: bazalt/masif = 1 |

### Arazi kullanımı

| Sınıf | Risk puanı | Dayanak |
|---|---|---|
| Planı Olmayan Kentsel Yerleşik Alanlar | 5 | [K] yapılaşmış en yüksek |
| Yapılaşmış Alanlar | 5 | [K]  |
| Diğer Yapılaşmış Alanlar | 5 | [K]  |
| Sanayi Alanları | 4.5 | [K] TR-55 CN 81-93 |
| Küçük Sanayi Siteleri | 4.5 | [K]  |
| Plan İçi Yerleşim Alanları | 4.5 | [K]  |
| Köy Yerleşik Alanları | 4 | [U]  |
| Turizm ve İkinci Konut Alanları | 4 | [U]  |
| Turizm Tesis Alanları | 4 | [U]  |
| İdari ve Sosyal Tesis Alanları | 4 | [U]  |
| Arıtma Tesisleri | 4 | [U]  |
| Kumsal ve Plajlar | 3.5 | [E] kıyı taşkını |
| Narenciye Bahçeleri | 3 | [K] Tanış & Çelik: sürekli ürün = 4 |
| Diğer Meyve Bahçeleri ve Seralar | 3 | [K]  |
| Bağlık Alanlar | 3 | [K]  |
| Zeytinlik Alanlar | 3 | [K]  |
| Kuru Tarım Alanları | 2.5 | [K] tarım orta |
| Mera - Çayırlık Alanlar | 2.5 | [K] mera/çayır orta |
| Arkeolojik Alanlar | 2 | [E]  |
| Askeri Alanlar | 2 | [E]  |
| Fundalık Makilik Alanlar | 2 | [K] çalı, TR-55 CN 48-83 |
| Orman Alanları | 1 | [K] orman en düşük, 6/6 kaynak |

## Ağırlıklar

Analizde **literatür tabanlı** set kullanılıyor (varsayılan). Projenin ilk
sürümündeki ağırlıklar duyarlılık analizi için korundu; `AGIRLIK_SETI=mevcut`
ortam değişkeniyle o sete geçilebilir. Karşılaştırma için:
`python tools/agirlik_karsilastir.py`

### Deprem

| Faktör | Eski (mevcut) | **Literatür tabanlı (kullanılan)** |
|---|---|---|
| Litoloji (Formasyon) | 0.30 | 0.45 |
| Fay hattına uzaklık (m) | 0.50 | 0.30 |
| Arazi kullanımı | 0.10 | 0.12 |
| Eğim (derece) | 0.05 | 0.08 |
| Akarsuya uzaklık (m) | 0.05 | 0.05 |

### Heyelan

| Faktör | Eski (mevcut) | **Literatür tabanlı (kullanılan)** |
|---|---|---|
| Litoloji (Formasyon) | 0.35 | 0.34 |
| Eğim (derece) | 0.40 | 0.30 |
| Arazi kullanımı | 0.05 | 0.14 |
| Fay hattına uzaklık (m) | 0.15 | 0.14 |
| Akarsuya uzaklık (m) | 0.05 | 0.08 |

### Sel

| Faktör | Eski (mevcut) | **Literatür tabanlı (kullanılan)** |
|---|---|---|
| Akarsuya uzaklık (m) | 0.60 | 0.45 |
| Eğim (derece) | 0.10 | 0.30 |
| Arazi kullanımı | 0.10 | 0.16 |
| Litoloji (Formasyon) | 0.15 | 0.05 |
| Fay hattına uzaklık (m) | 0.05 | 0.04 |

## Atıf verilmemesi gereken kaynaklar

Literatür taramasında iç çelişki tespit edilen çalışmalar. Tabloları
metinlerindeki ifadeyle uyuşmuyor; bu haliyle atıf verilmesi risklidir.

| Kaynak | Sorun |
|---|---|
| Güneş & Kömüşcü (2025) | Eğim ve litoloji tabloları metindeki ifadeyle çelişiyor. |
| Özşahin (2014) | Alt sınıf tablolarının yönü metindeki ifadeyle ters. Faktör ağırlıkları kullanılabilir. |
| Şengür & Uncu (2025) | Fay ve akarsu mesafesi tabloları birbirinin kopyası. |
| Yurteri (2024) eğim tablosu | 0-3° en düşük, 30-76° en yüksek — metinle çelişiyor. Ağırlıkları kullanılabilir. |

## Kaynakça

- Berber, S., & Ceryan, Ş. (2023). Güzelyalı-Lapseki (Çanakkale) arasındaki bölgenin heyelan duyarlılığının analitik hiyerarşi süreci yöntemiyle (AHP) değerlendirilmesi. Balıkesir Üniversitesi Fen Bilimleri Enstitüsü Dergisi, 25(1), 305-316. https://doi.org/10.25092/baunfbed.1208462

- Çellek, S. (2020). Effect of the slope angle and its classification on landslide [Preprint]. Natural Hazards and Earth System Sciences Discussions. https://doi.org/10.5194/nhess-2020-87  [ÖN BASKI — hakem sürecinden geçtiği doğrulanamadı, tezde bu durumu belirt]

- Corapci, F., & Özdemir, H. (2024). A new approach to flood susceptibility analysis of urbanised alluvial fans: The case of Bursa City (Türkiye). Natural Hazards, 120(14), 12909-12932. https://doi.org/10.1007/s11069-024-06723-w

- Dağ, S., & Bulut, F. (2012). Coğrafi Bilgi Sistemleri tabanlı heyelan duyarlılık haritalarının hazırlanmasına bir örnek: Çayeli (Rize, KD Türkiye). Jeoloji Mühendisliği Dergisi, 36(1), 35-62.

- Danacıoğlu, Ş., & Öz, M. N. (2025). Tahtalı Barajı Havzasında bulanık mantık yöntemi ile taşkın risk analizi. Journal of Anatolian Geography, 2(1), 82-89. [TÜBİTAK 2209-A destekli, İzmir — en yakın kurumsal ve bölgesel emsal]

- Demir, M., & Altaş, N. T. (2024). Kars kentinde deprem hasar risk potansiyeli taşıyan alanların CBS tabanlı AHP analizlerine dayalı olarak belirlenmesi. Geomatik, 9(1), 123-140. https://doi.org/10.29128/geomatik.1375650

- Erden, T., & Karaman, H. (2012). Analysis of earthquake parameters to generate hazard maps by integrating AHP and GIS for Küçükçekmece region. Natural Hazards and Earth System Sciences, 12, 475-483. https://doi.org/10.5194/nhess-12-475-2012

- Kazakis, N., Kougias, I., & Patsialis, T. (2015). Assessment of flood hazard areas at a regional scale using an index-based approach and Analytical Hierarchy Process: Application in Rhodope-Evros region, Greece. Science of the Total Environment, 538, 555-563. https://doi.org/10.1016/j.scitotenv.2015.08.055

- Köroğlu, B., & Akıncı, H. (2023). Coğrafi Bilgi Sistemleri tabanlı çok kriterli karar analizi ile Giresun İli Dereli İlçesinin taşkın duyarlılık analizi. Artvin Çoruh Üniversitesi Mühendislik ve Fen Bilimleri Dergisi, 1(2), 62-81.

- Koralay, N., & Kara, Ö. (2024). Assessment of flood risk in Söğütlü stream watershed of Trabzon province in Turkey using geographic information systems and analytic hierarchy process approach. Natural Hazards. https://doi.org/10.1007/s11069-024-06594-1

- Ocak, F., & Bahadır, M. (2022). CBS teknikleri kullanılarak deprem duyarlılık analizi için Analitik Hiyerarşi Prosesi: Samsun Ladik Gölü Havzası örneği, Türkiye. Kesit Akademi Dergisi, (33).

- Öz, T. (2025). Heyelan duyarlılığının Analitik Hiyerarşi Süreci (AHS) ve Frekans Oranı (FR) ile belirlenmesi: Kürk Çayı Havzası (Elazığ) örneği. Fırat Üniversitesi Sosyal Bilimler Dergisi, 35(2), 467-485. https://doi.org/10.18069/firatsbed.1572408

- Partigöç, N. S., & Dinçer, C. (2024). Coğrafi bilgi sistemleri (CBS) tabanlı afet risk analizi: Denizli ili örneği. Geomatik, 9(1), 27-44. https://doi.org/10.29128/geomatik.1261051

- Patrikaki, O., Kazakis, N., Kougias, I., Patsialis, T., Theodossiou, N., & Voudouris, K. (2018). Assessing flood hazard at river basin scale with an index-based approach: The case of Mouriki, Greece. Geosciences, 8(2), 50. https://doi.org/10.3390/geosciences8020050

- Sayın, H., & Öztürk, Y. (2025). Akyayla Dağı'nın heyelan morfolojisi ve heyelan duyarlılığının CBS tabanlı Frekans Oranı (FO) yöntemi ile analizi (Doğubayazıt/Ağrı). Jeoloji Mühendisliği Dergisi, 49(2), 23-54. https://doi.org/10.24232/jmd.1704248

- Sözbilir, H., Sümer, Ö., Uzel, B., Tepe, Ç., Softa, M., Eski, S., Babayiğit, G., Turan, R., Karaş, M., & Koşum, S. (2015). İzmir kenti içinden geçen diri faylarda fay sakınım bandı / yüzey faylanması tehlikesi kuşağı oluşturma kriterleri. 3. Türkiye Deprem Mühendisliği ve Sismoloji Konferansı, DEÜ, İzmir. [SEFERİHİSAR FAYI İÇİN 40 m SAKINIM BANDI — çalışma alanına en özgü kaynak]

- Tanış, E., & Çelik, R. (2024). CBS tabanlı AHP çok kriterli karar verme yöntemi kullanılarak Van Gölü Güzelsu Alt Havzası taşkın risk haritalarının çıkarılması ve değerlendirilmesi. Dicle Üniversitesi Mühendislik Fakültesi Mühendislik Dergisi, 15(4), 941-950. https://doi.org/10.24012/dumf.1534940

- Türkiye Bina Deprem Yönetmeliği (TBDY). (2018). Resmî Gazete, 18 Mart 2018, Sayı 30364 (Mükerrer). Tablo 16.1 yerel zemin sınıfları (ZA-ZF). [RESMÎ METNİ KENDİN DOĞRULA — bu proje ikincil kaynaktan teyit etti]

- Yurteri, C. (2024). Coğrafi Bilgi Sistemleri (CBS) ortamında Analitik Hiyerarşi Yöntemi (AHY) kullanılarak taşkın risk analizi: Karabük İli örneği. Mühendislik Bilimleri ve Tasarım Dergisi, 12(2), 298-318. https://doi.org/10.21923/jesd.1438999 [Eğim şeması İÇ ÇELİŞKİLİ — eğim için ATIF VERME, sadece ağırlıklar için kullan]
