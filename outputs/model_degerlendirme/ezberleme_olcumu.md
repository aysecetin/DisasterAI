# Ezberleme Denetimi — Ölçüm Sonuçları

> Bu dosya `tools/ezberleme_olcumu.py` ile üretilmiştir; elle düzenlemeyin.

## Yöntem

İnce ayarlı modelin ürettiği **40 test metni**, eğitim corpusundaki **2014 metinle** karşılaştırıldı. Eğitim corpusundan çıkarılan 8 sözcüklük benzersiz dizi sayısı: **213,161**. Karşılaştırma yalnızca sözcükler üzerinden yapıldı; noktalama ve markdown biçim karakterleri ölçüm dışında tutuldu.

## 1. Sözcük dizisi örtüşmesi

| Ölçüt (8 sözcüklük dizi) | Değer |
|---|---|
| Ortalama örtüşme | **%15.4** |
| Medyan | %15.5 |
| En düşük | %2.2 |
| En yüksek | %35.7 |

Bu düzeydeki örtüşme, alan diline özgü kalıp ifadelerden beklenen aralıktadır ("toplam risk skoru ... olarak hesaplanmıştır", "zemin/litoloji faktörü ... puan katkı sağlamıştır"). Ezberlemede bu oranın çok daha yüksek olması beklenir.

## 2. Birebir uzun dizi aktarımı

| Dizi uzunluğu | Eğitimde birebir bulunan metin sayısı |
|---|---|
| 10 sözcük | 32 / 40 |
| 15 sözcük | 8 / 40 |
| 20 sözcük | 3 / 40 |
| 30 sözcük | 0 / 40 |

Birebir örtüşen en uzun diziler 20 sözcüktür ve tamamı sayı taşıyan kalıp ifadelerdir. Örnek ([yatistirici] tonundan):

> en büyük etkiyi zemin litoloji puan 5 0 katkı 1 70 ve eğim puan 5 0 katkı 1 50 faktörleri

**30 sözcük ve üzeri uzunlukta birebir aktarılmış hiçbir dizi yoktur.** Ezberlemenin en doğrudan göstergesi olan uzun birebir aktarım gözlenmemiştir.

## 3. Kendi öğretmen referansına benzerlik

| Ölçüt | Değer |
|---|---|
| Ortalama karakter benzerliği | **%19.4** |
| Medyan | %20.3 |
| En yüksek | %40.4 |

Her üretilen metin, **aynı girdi için öğretmen modelin yazdığı** referans metinle karşılaştırıldı. Düşük benzerlik, modelin referansı kopyalamadığını; aynı olgu kümesinden kendi metnini kurduğunu göstermektedir.

## Rapordaki değerlerle karşılaştırma

| Rapor | Bu ölçüm |
|---|---|
| Örtüşme %15.4 | %15.4 |
| Referans benzerliği %19.4 | %19.4 |
