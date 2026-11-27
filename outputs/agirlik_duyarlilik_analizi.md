# Ağırlık Seti Duyarlılık Analizi

Seferihisar (İzmir) — ağırlıklı çakıştırmada kullanılan faktör ağırlıklarının
sonuç haritası üzerindeki etkisi.

İki set karşılaştırıldı:

- **Eski (mevcut):** projenin ilk sürümündeki ağırlıklar. Deprem için fay
  mesafesine 0.50 ağırlık veriyordu; yayımlanmış Türkiye çalışmalarında bu
  faktör 0.07–0.15 aralığında.
- **Literatür tabanlı (kullanılan):** Ocak & Bahadır (2022, CR 0.08),
  Demir & Altaş (2024, CR 0.023), Berber & Ceryan (2023, CR 0.054),
  Öz (2025, CR 0.080) ve Yurteri (2024, CR 0.058) çalışmalarının bildirdiği
  aralıkların ortasına oturur.

Uyum ölçütü olarak üç risk sınıfı (Düşük / Orta / Yüksek) üzerinden
**Cohen's kappa** hesaplanmıştır.

## Deprem

### Ağırlıklar

| Faktör | Eski | Literatür | Değişim |
|---|---|---|---|
| Litoloji | 0.30 | **0.45** | +0.15 |
| Fay_Hattı_Uzaklığı | 0.50 | **0.30** | -0.20 |
| Arazi_Kullanımı | 0.10 | **0.12** | +0.02 |
| Eğim | 0.05 | **0.08** | +0.03 |
| Akarsu_Uzaklığı | 0.05 | **0.05** | +0.00 |

### Sonuç haritası üzerindeki etki

| Ölçüt | Değer |
|---|---|
| Ortalama risk skoru (eski) | 3.465 |
| Ortalama risk skoru (literatür) | 3.220 |
| Ortalama mutlak fark | 0.314 |
| En büyük fark | 0.780 |
| Risk sınıfı değişen hücre oranı | %17.4 |
| Cohen's kappa | 0.605 (iyi uyum) |

Eski set sınıf dağılımı — Düşük %19.7 · Orta %71.3 · Yüksek %9.1

Literatür set sınıf dağılımı — Düşük %26.0 · Orta %71.1 · Yüksek %2.9

![DEPREM karşılaştırma](agirlik_karsilastirma_deprem.png)

## Heyelan

### Ağırlıklar

| Faktör | Eski | Literatür | Değişim |
|---|---|---|---|
| Litoloji | 0.35 | **0.34** | -0.01 |
| Eğim | 0.40 | **0.30** | -0.10 |
| Fay_Hattı_Uzaklığı | 0.15 | **0.14** | -0.01 |
| Arazi_Kullanımı | 0.05 | **0.14** | +0.09 |
| Akarsu_Uzaklığı | 0.05 | **0.08** | +0.03 |

### Sonuç haritası üzerindeki etki

| Ölçüt | Değer |
|---|---|
| Ortalama risk skoru (eski) | 3.428 |
| Ortalama risk skoru (literatür) | 3.265 |
| Ortalama mutlak fark | 0.241 |
| En büyük fark | 0.480 |
| Risk sınıfı değişen hücre oranı | %24.7 |
| Cohen's kappa | 0.628 (iyi uyum) |

Eski set sınıf dağılımı — Düşük %28.9 · Orta %35.6 · Yüksek %35.5

Literatür set sınıf dağılımı — Düşük %30.0 · Orta %54.8 · Yüksek %15.3

![HEYELAN karşılaştırma](agirlik_karsilastirma_heyelan.png)

## Sel

### Ağırlıklar

| Faktör | Eski | Literatür | Değişim |
|---|---|---|---|
| Akarsu_Uzaklığı | 0.60 | **0.45** | -0.15 |
| Eğim | 0.10 | **0.30** | +0.20 |
| Arazi_Kullanımı | 0.10 | **0.16** | +0.06 |
| Litoloji | 0.15 | **0.05** | -0.10 |
| Fay_Hattı_Uzaklığı | 0.05 | **0.04** | -0.01 |

### Sonuç haritası üzerindeki etki

| Ölçüt | Değer |
|---|---|
| Ortalama risk skoru (eski) | 1.872 |
| Ortalama risk skoru (literatür) | 1.868 |
| Ortalama mutlak fark | 0.228 |
| En büyük fark | 1.020 |
| Risk sınıfı değişen hücre oranı | %5.5 |
| Cohen's kappa | 0.686 (iyi uyum) |

Eski set sınıf dağılımı — Düşük %90.7 · Orta %6.2 · Yüksek %3.1

Literatür set sınıf dağılımı — Düşük %90.3 · Orta %6.9 · Yüksek %2.7

![SEL karşılaştırma](agirlik_karsilastirma_sel.png)

## Özet

| Afet | Ort. skor (eski) | Ort. skor (lit.) | Ort. mutlak fark | Sınıf değişimi | Kappa |
|---|---|---|---|---|---|
| Deprem | 3.465 | 3.220 | 0.314 | %17.4 | 0.605 |
| Heyelan | 3.428 | 3.265 | 0.241 | %24.7 | 0.628 |
| Sel | 1.872 | 1.868 | 0.228 | %5.5 | 0.686 |

### Tezde nasıl yorumlanır

Kappa değeri yüksekse (>0.60) sonuç haritasının ağırlık seçimine görece
**dayanıklı** olduğu söylenebilir — bu, yönteminin güçlü yanıdır ve rapor
edilmelidir. Kappa düşükse ağırlık seçimi sonucu belirleyen kritik bir karar
demektir; o zaman literatür tabanlı seti tercih etme gerekçesini (yayımlanmış
aralıklara ve bildirilen CR değerlerine uygunluk) açıkça yazmalısın.

Her iki durumda da bu analizin kendisi tezde bir katkıdır: AHP çalışmalarının
en sık eleştirilen yanı ağırlıkların keyfîliğidir ve çoğu çalışma duyarlılık
analizi sunmaz.
