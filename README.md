# DisasterAI

**GIS-based multi-hazard disaster risk analysis, explained in plain language by a fine-tuned local LLM.**

A resident picks a point on the map and describes their building. DisasterAI computes an earthquake, landslide or flood risk score from GIS layers, shows why the score is what it is, routes them on foot to the nearest assembly area, and lets them ask follow-up questions to an assistant. The assistant can run on Gemini or fully offline on a Turkish Llama 8B model I fine-tuned with QLoRA.

Graduation project, Management Information Systems, Pamukkale University (2026). **Supported by TÜBİTAK 2209-A** (Undergraduate Research Projects Support Programme). Study area: Seferihisar, İzmir.

*[Türkçe açıklama aşağıda](#türkçe)*

![Analysis result: risk layer on the map, total score, factor contributions and explanation](assets/readme/02_analiz_sonucu_yerel.jpg)

## How it works

The risk score is calculated, not generated. The language model only explains a result that the GIS engine has already produced.

```
location + building info
        │
        ▼
 GIS engine (weighted overlay)          building vulnerability
 fault distance · lithology · slope  +  material · year · floors ·
 land use · distance to rivers          floor lived on · elevator
        │                                       │
        └──────────────► total risk score ◄─────┘
                               │
              ┌────────────────┼─────────────────┐
              ▼                ▼                 ▼
        "Why this score?"  walking route to   assistant (Gemini or
        factor breakdown   assembly area      local fine-tuned model)
```

**Weighted overlay with literature-based weights.** Each hazard combines reclassified GIS layers (1–5) with factor weights. The first version gave fault distance a weight of 0.50 for earthquakes; published Turkish AHP studies put it at 0.07–0.15. I replaced the weights with values in the middle of the ranges reported by five studies (consistency ratios 0.023–0.080) and measured how much the risk map changed using Cohen's kappa across the three risk classes. See [`outputs/agirlik_duyarlilik_analizi.md`](outputs/agirlik_duyarlilik_analizi.md).

| Earthquake factor | Weight |
| --- | --- |
| Lithology | 0.45 |
| Distance to fault | 0.30 |
| Land use | 0.12 |
| Slope | 0.08 |
| Distance to rivers | 0.05 |

## The fine-tuned model

| | |
| --- | --- |
| Base model | `ytu-ce-cosmos/Turkish-Llama-8b-Instruct-v0.1` |
| Method | QLoRA (r=16, α=32), 1 epoch, trained on Kaggle |
| Training data | ~2,500 examples generated from the GIS engine's own outputs |
| Serving | Quantised to GGUF Q4_K_M and served locally with Ollama |

Evaluated on 40 held-out cases ([`outputs/model_degerlendirme`](outputs/model_degerlendirme)):

| Metric | Result |
| --- | --- |
| Answers with no invented numbers | **97.5%** (39/40) |
| Invented numbers among all numbers produced | **0.3%** (1/390) |
| Answers that state the composite risk score | 87.5% (35/40) |
| Outdated safety advice | 0/40 |
| Memorisation check: 30+ word sequences copied from training data | **none** |

The memorisation check compares every generated text with the 2,014 training texts using 8-word sequence overlap (mean 15.4%, which is in line with fixed domain phrasing) and with the teacher model's reference answer for the same input (mean similarity 19.4%).

![The assistant answering with the local model](assets/readme/04_sohbet_1_yerel.jpg)

## Tone of risk communication

The same result can be told in different ways. [`src/risk_communication.py`](src/risk_communication.py) defines communication tones (for example a calming tone that does not downplay the risk) and picks one from the user's context. [`src/deney.py`](src/deney.py) and the **Experiment** tab run a three-arm, between-subjects user study: a deterministic technical report with no LLM, the raw LLM output, and the tone-managed output.

## Features

- Earthquake, landslide and flood/inundation risk for any point in the study area
- Building vulnerability from material, construction year, number of floors, floor lived on and elevator
- Risk layer on the map with adjustable opacity
- "Why this score?" factor breakdown
- Scenario comparison (for example, the score after retrofitting)
- Nearest assembly area and walking route with distance and time (OSRM)
- Analysis history, PDF report, light and dark theme
- Assistant on Gemini 2.5 Flash or a local model, switched with one environment variable

## Tech stack

**Backend:** Python, FastAPI, GeoPandas, Rasterio, Shapely, PyProj, NumPy, pandas, LangChain
**Frontend:** React, Vite, Leaflet / React Leaflet
**ML:** Hugging Face Transformers, PEFT (QLoRA), bitsandbytes, llama.cpp (GGUF), Ollama
**Data:** OpenStreetMap, OSRM, Copernicus DEM (slope), GIS layers for faults, lithology, rivers and land use

## Project structure

```text
backend/main.py              FastAPI entry point
src/
  disaster_risk_v4.py        analysis engine and API endpoints
  gis_engine.py              raster/vector sampling and weighted overlay
  reclass_tables.py          reclassification tables (1–5) per factor
  risk_communication.py      communication tones and tone selection
  deney.py                   user-study infrastructure
frontend/src/                React app (App.jsx, ExperimentPanel.jsx)
data/                        GIS layers for Seferihisar, slope raster
tools/                       QLoRA training notebooks, evaluation and analysis scripts
outputs/                     risk maps, weight sensitivity analysis, model evaluation
```

## Run it locally

Requirements: Python 3.10+, Node.js 18+.

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

Backend (terminal 1):

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8514
```

Frontend (terminal 2):

```bash
cd frontend && npm run dev
```

Open `http://127.0.0.1:5173`.

**Assistant provider.** By default the assistant uses Gemini: put `GOOGLE_API_KEY=...` in a `.env` file at the project root. To run it offline on the fine-tuned model, build it with Ollama (`ollama create disasterai -f tools/Modelfile.disasterai`, after pointing `FROM` at your GGUF file) and start the backend with `MODEL_SAGLAYICI=yerel`. Risk analysis, the map and routing work without any LLM.

**Slope raster.** `data/raster/egim.tif` is included. To regenerate it, download the Copernicus DEM tiles N38 E026 and N38 E027 into `data/raster/` and run `tools/egim_uret.py`.

## Author

**Ayşe Çetin** · Management Information Systems, Pamukkale University
[Portfolio](https://aysecetin.github.io) · [LinkedIn](https://www.linkedin.com/in/ayseecetin/)

---

## Türkçe

# DisasterAI

**CBS tabanlı çoklu afet riski analizi; sonucu, ince ayar yapılmış yerel bir dil modeli sade bir dille açıklıyor.**

Kullanıcı haritadan bir nokta seçer ve binasını tanımlar. DisasterAI, CBS katmanlarından deprem, heyelan veya sel riski puanını hesaplar, puanın neden o çıktığını gösterir, kişiyi yürüyerek en yakın toplanma alanına yönlendirir ve bir asistana takip soruları sormasını sağlar. Asistan Gemini ile ya da QLoRA ile ince ayar yaptığım Türkçe Llama 8B modeliyle tamamen çevrimdışı çalışabiliyor.

Pamukkale Üniversitesi Yönetim Bilişim Sistemleri bitirme projesi (2026). **TÜBİTAK 2209-A** (Üniversite Öğrencileri Araştırma Projeleri Destekleme Programı) kapsamında desteklendi. Çalışma alanı: Seferihisar, İzmir.

### Nasıl çalışıyor

Risk puanı **hesaplanır, üretilmez.** Dil modeli yalnızca CBS motorunun zaten ürettiği sonucu açıklar.

- **CBS motoru (ağırlıklı çakıştırma):** fay uzaklığı, litoloji, eğim, arazi kullanımı ve akarsuya uzaklık katmanları
- **Bina kırılganlığı:** malzeme, yapım yılı, kat sayısı, oturulan kat, asansör
- Bu ikisi birleşerek **toplam risk puanını** verir; ardından "Bu puan neden çıktı?" faktör dökümü, toplanma alanına yürüme rotası ve asistan devreye girer.

**Literatüre dayalı ağırlıklar.** Her afet türü, 1–5 arasında yeniden sınıflandırılmış CBS katmanlarını faktör ağırlıklarıyla birleştirir. İlk sürümde depremde fay uzaklığının ağırlığı 0,50'ydi; Türkiye'de yayımlanmış AHP çalışmaları bu değeri 0,07–0,15 aralığında veriyor. Ağırlıkları beş çalışmanın raporladığı aralıkların ortasındaki değerlerle değiştirdim (tutarlılık oranları 0,023–0,080) ve risk haritasının ne kadar değiştiğini üç risk sınıfı üzerinden Cohen'in kappa katsayısıyla ölçtüm. Ayrıntılar: [`outputs/agirlik_duyarlilik_analizi.md`](outputs/agirlik_duyarlilik_analizi.md).

| Deprem faktörü | Ağırlık |
| --- | --- |
| Litoloji | 0,45 |
| Faya uzaklık | 0,30 |
| Arazi kullanımı | 0,12 |
| Eğim | 0,08 |
| Akarsuya uzaklık | 0,05 |

### İnce ayarlı model

| | |
| --- | --- |
| Temel model | `ytu-ce-cosmos/Turkish-Llama-8b-Instruct-v0.1` |
| Yöntem | QLoRA (r=16, α=32), 1 epoch, Kaggle'da eğitildi |
| Eğitim verisi | CBS motorunun kendi çıktılarından üretilen ~2.500 örnek |
| Sunum | GGUF Q4_K_M olarak nicemlendi, Ollama ile yerelde çalışıyor |

Eğitimde kullanılmayan 40 vaka üzerinde değerlendirme ([`outputs/model_degerlendirme`](outputs/model_degerlendirme)):

| Ölçüt | Sonuç |
| --- | --- |
| Uydurma sayı içermeyen yanıtlar | **%97,5** (39/40) |
| Üretilen tüm sayılar içinde uydurma sayı oranı | **%0,3** (1/390) |
| Toplam risk puanını belirten yanıtlar | %87,5 (35/40) |
| Güncelliğini yitirmiş güvenlik tavsiyesi | 0/40 |
| Ezber kontrolü: eğitim verisinden kopyalanmış 30+ kelimelik dizi | **yok** |

Ezber kontrolü, üretilen her metni 2.014 eğitim metniyle 8 kelimelik dizi örtüşmesi üzerinden (ortalama %15,4; alana özgü kalıp ifadelerle uyumlu) ve aynı girdi için öğretmen modelin referans yanıtıyla (ortalama benzerlik %19,4) karşılaştırıyor.

### Risk iletişiminde üslup

Aynı sonuç farklı biçimlerde anlatılabilir. [`src/risk_communication.py`](src/risk_communication.py), iletişim üsluplarını tanımlar (örneğin riski küçümsemeden sakinleştiren bir üslup) ve kullanıcının bağlamına göre birini seçer. [`src/deney.py`](src/deney.py) ve **Deney** sekmesi, üç kollu, katılımcılar arası (between-subjects) bir kullanıcı çalışması yürütür: LLM içermeyen deterministik teknik rapor, ham LLM çıktısı ve üslubu yönetilen çıktı.

### Özellikler

- Çalışma alanındaki herhangi bir nokta için deprem, heyelan ve sel/su baskını riski
- Malzeme, yapım yılı, kat sayısı, oturulan kat ve asansörden bina kırılganlığı
- Haritada saydamlığı ayarlanabilen risk katmanı
- "Bu puan neden çıktı?" faktör dökümü
- Senaryo karşılaştırma (örneğin güçlendirme sonrası puan)
- En yakın toplanma alanı ve mesafe/süreli yürüme rotası (OSRM)
- Analiz geçmişi, PDF rapor, açık ve koyu tema
- Tek ortam değişkeniyle Gemini 2.5 Flash veya yerel model arasında geçiş yapılan asistan

### Teknolojiler

**Backend:** Python, FastAPI, GeoPandas, Rasterio, Shapely, PyProj, NumPy, pandas, LangChain
**Frontend:** React, Vite, Leaflet / React Leaflet
**ML:** Hugging Face Transformers, PEFT (QLoRA), bitsandbytes, llama.cpp (GGUF), Ollama
**Veri:** OpenStreetMap, OSRM, Copernicus DEM (eğim), fay, litoloji, akarsu ve arazi kullanımı CBS katmanları

### Yerelde çalıştırma

Gereksinimler: Python 3.10+, Node.js 18+.

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

Backend (1. terminal):

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8514
```

Frontend (2. terminal):

```bash
cd frontend && npm run dev
```

Tarayıcıda `http://127.0.0.1:5173` adresini açın.

**Asistan sağlayıcısı.** Varsayılan olarak asistan Gemini kullanır: proje kökündeki `.env` dosyasına `GOOGLE_API_KEY=...` yazın. İnce ayarlı modelle çevrimdışı çalıştırmak için modeli Ollama ile oluşturun (`FROM` satırını GGUF dosyanıza yönlendirdikten sonra `ollama create disasterai -f tools/Modelfile.disasterai`) ve backend'i `MODEL_SAGLAYICI=yerel` ile başlatın. Risk analizi, harita ve rota hiçbir LLM olmadan da çalışır.

**Eğim rasterı.** `data/raster/egim.tif` repoda bulunuyor. Yeniden üretmek için Copernicus DEM N38 E026 ve N38 E027 paftalarını `data/raster/` klasörüne indirip `tools/egim_uret.py` dosyasını çalıştırın.

### Yazar

**Ayşe Çetin** · Yönetim Bilişim Sistemleri, Pamukkale Üniversitesi
[Portfolyo](https://aysecetin.github.io) · [LinkedIn](https://www.linkedin.com/in/ayseecetin/)
