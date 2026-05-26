# DisasterAI

DisasterAI, İzmir Seferihisar bölgesi için CBS tabanlı afet risk analizi yapan ve sonucu kullanıcı dostu bir web arayüzünde gösteren karar destek uygulamasıdır. Kullanıcı harita üzerinden konum seçer, bina bilgilerini girer ve deprem, heyelan veya sel/taşkın için risk skorunu görüntüler.

Uygulama ayrıca risk katmanını harita üzerinde gösterir, skorun neden oluştuğunu açıklar, yakın açık/toplanma alanı için yürüyüş rotası üretir ve analiz sonucunu yapay zeka destekli asistan ile yorumlar.

## Özellikler

- Deprem, heyelan ve sel/taşkın için afet risk analizi
- CBS katmanlarına dayalı ağırlıklı çakıştırma yaklaşımı
- Bina bilgilerine göre bina hassasiyeti skoru
- Toplam risk skoru ve risk seviyesi gösterimi
- Harita üzerinde risk katmanı ve şeffaflık kontrolü
- Haritadan analiz noktası seçme ve adres/koordinat gösterimi
- Yakın açık/toplanma alanı bulma
- Yol ağına göre yürüyüş rotası, mesafe ve süre hesabı
- "Skor Neden Böyle?" açıklama bölümü
- Senaryo karşılaştırması
- Analiz geçmişi
- PDF raporu alma
- Google Gemini 2.5 Flash destekli analiz asistanı
- Açık/koyu tema

## Kullanılan Teknolojiler

### Backend

- Python
- FastAPI
- GeoPandas
- Rasterio
- Shapely
- PyProj
- NumPy / Pandas
- Matplotlib
- Requests
- LangChain Google GenAI
- Google Gemini 2.5 Flash

### Frontend

- React
- Vite
- Leaflet / React Leaflet
- Lucide React
- CSS

### Harita ve Rota

- OpenStreetMap
- OSRM yürüyüş rotası servisi
- CBS veri katmanları: fay hattı, eğim, litoloji, akarsu, arazi kullanımı ve sınır verileri

## Proje Yapısı

```text
disaster-risk-turkey-master/
├── backend/
│   └── main.py                 # FastAPI giriş noktası
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Ana React uygulaması
│   │   ├── main.jsx
│   │   └── styles.css
│   ├── package.json
│   └── package-lock.json
├── src/
│   ├── disaster_risk_v4.py     # Ana analiz motoru ve API uçları
├── data/
│   └── İZMİR SEFERİHİSAR/    # CBS veri katmanları
├── outputs/                    # Analiz sırasında üretilen harita çıktıları
├── requirements.txt            # Python bağımlılıkları
└── README.md
```

## Gereksinimler

- Python 3.10 veya üzeri
- Node.js 18 veya üzeri
- npm
- İnternet bağlantısı

İnternet bağlantısı özellikle OpenStreetMap, OSRM rota servisi ve Gemini API için gereklidir.

## İlk Kurulum

Projeyi yeni bir bilgisayarda ilk kez çalıştırmak için aşağıdaki adımları izle.

### 1. Proje klasörüne gir

```bash
cd "path/to/DisasterAI"
```

Başka bilgisayarda klasör yolu farklıysa kendi proje klasörünün yolunu kullan.

### 2. Python sanal ortamı oluştur

macOS / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

### 3. Python paketlerini kur

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Frontend paketlerini kur

```bash
cd frontend
npm install
cd ..
```

### 5. Gemini API anahtarı ekle

Proje kök dizininde `.env` dosyası oluştur:

```bash
GOOGLE_API_KEY=buraya_api_anahtarini_yaz
```

Bu anahtar sadece analiz asistanı için gereklidir. Risk analizi, harita ve rota özellikleri Gemini olmadan da çalışabilir; ancak asistan yanıtları sınırlı olur.

`.env` dosyasını GitHub'a yükleme.

## Projeyi Çalıştırma

Uygulamayı çalıştırmak için iki ayrı terminal aç.

### Terminal 1: Backend

Proje kök dizininde:

```bash
source venv/bin/activate
MPLCONFIGDIR=/private/tmp/matplotlib-cache python -m uvicorn backend.main:app --host 127.0.0.1 --port 8514
```

Windows kullanıyorsan:

```powershell
venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8514
```

Backend adresi:

```text
http://127.0.0.1:8514
```

Sağlık kontrolü:

```text
http://127.0.0.1:8514/api/health
```

### Terminal 2: Frontend

```bash
cd frontend
npm run dev
```

Web arayüzü:

```text
http://127.0.0.1:5173
```

Tarayıcıda bu adresi aç:

```text
http://127.0.0.1:5173
```

## Bu Bilgisayarda Mevcut Ortam

Bu bilgisayarda `venv` klasörü silinmiş görünüyor; ancak `ayse-env` adlı bir Python sanal ortamı mevcut. Şu an projeyi bu ortamla da çalıştırabilirsin:

```bash
MPLCONFIGDIR=/private/tmp/matplotlib-cache ayse-env/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8514
```

Frontend için:

```bash
cd frontend
npm run dev
```

Yeni bilgisayarda `ayse-env` taşımak zorunda değilsin. En temiz yol, yeni bir `venv` oluşturup `requirements.txt` ile paketleri yeniden kurmaktır.

## venv Silinirse Ne Olur?

`venv` veya `ayse-env` silinirse proje kodları silinmez. Sadece Python paketlerinin kurulu olduğu sanal ortam silinmiş olur.

Yeniden oluşturmak için:

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Sonra backend'i tekrar çalıştır:

```bash
MPLCONFIGDIR=/private/tmp/matplotlib-cache python -m uvicorn backend.main:app --host 127.0.0.1 --port 8514
```

Kısaca: `venv` silinirse korkulacak bir şey yok; `requirements.txt` dosyası durduğu sürece ortam yeniden kurulabilir.

## Başka Bilgisayarda Nasıl Kullanılır?

Başka bilgisayara taşırken şu dosya ve klasörler yeterlidir:

- `backend/`
- `frontend/`
- `src/`
- `data/İZMİR SEFERİHİSAR/`
- `outputs/` isteğe bağlıdır; yoksa uygulama yeniden çıktı üretir
- `requirements.txt`
- `README.md`
- `.env.example` veya kendi `.env` dosyan

Taşımana gerek olmayan klasörler:

- `venv/`
- `ayse-env/`
- `frontend/node_modules/`
- `frontend/dist/`
- `__pycache__/`
- `.DS_Store`

Bu klasörler başka bilgisayarda yeniden oluşturulabilir.

Yeni bilgisayarda sırayla:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

```bash
cd frontend
npm install
npm run dev
```

Ayrı terminalde:

```bash
source venv/bin/activate
MPLCONFIGDIR=/private/tmp/matplotlib-cache python -m uvicorn backend.main:app --host 127.0.0.1 --port 8514
```

## Portlar

Varsayılan portlar:

- Frontend: `5173`
- Backend: `8514`

Frontend farklı bir backend adresine bağlanacaksa `frontend/.env` dosyasına şunu yaz:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8514
```

## Sık Karşılaşılan Sorunlar

### localhost:5173 açılmıyor

Frontend çalışmıyordur. Şunu başlat:

```bash
cd frontend
npm run dev
```

### Analiz çalışmıyor ama sayfa açılıyor

Backend kapalı olabilir. Şunu başlat:

```bash
source venv/bin/activate
MPLCONFIGDIR=/private/tmp/matplotlib-cache python -m uvicorn backend.main:app --host 127.0.0.1 --port 8514
```

### Gemini / Analiz Asistanı hata veriyor

`.env` içinde `GOOGLE_API_KEY` eksik olabilir veya Gemini servisi yoğunluk yaşıyor olabilir. Bu durum risk analiz motorunu bozmaz; sadece asistan yanıtını etkiler.

### ModuleNotFoundError hatası

Sanal ortam aktif değildir veya paketler kurulmamıştır:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### npm: command not found

Node.js kurulu değildir. Node.js 18 veya üzeri kurulmalıdır.

## Akademik Not

Risk skoru, CBS tabanlı ağırlıklı çakıştırma yaklaşımıyla hesaplanır. Bölgesel tehlike skoru; fay hattı, eğim, litoloji, akarsuya yakınlık ve arazi kullanımı gibi katmanlardan üretilir. Bina hassasiyeti ise kullanıcının girdiği yapı malzemesi, yapım yılı, kat sayısı, oturulan kat ve asansör bilgisiyle hesaplanır.

Yapay zeka modeli risk skorunu hesaplamak için değil, hesaplanan sonucu doğal dilde açıklamak için kullanılır.

## Geliştirici

Ayşe Çetin  
Yönetim Bilişim Sistemleri  
Pamukkale Üniversitesi
