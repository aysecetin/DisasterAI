import functools
import concurrent.futures as _cf
import math
import geopandas as gpd
import pyproj
import rasterio
from rasterio.plot import show
from rasterio.transform import Affine
from rasterio.mask import mask 
import numpy as np
import matplotlib.pyplot as plt
import os
import requests
from PIL import Image
from pathlib import Path
from matplotlib.colors import ListedColormap, BoundaryNorm
from shapely.geometry import mapping, shape, Point
from shapely.ops import nearest_points
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv() # .env dosyasından GOOGLE_API_KEY yüklenecek

# --- GERÇEK CBS MOTORU ---
# Eski simulate_spatial_risk() sahte veri üretiyordu; artık tüm faktörler
# data/ altındaki gerçek .gdb katmanlarından hesaplanıyor.
try:
    from . import gis_engine as ge          # paket olarak import edilirse
except ImportError:
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import gis_engine as ge
try:
    from . import risk_communication as rc
except ImportError:
    import risk_communication as rc
try:
    from . import reclass_tables as rt
except ImportError:
    import reclass_tables as rt
try:
    from . import deney as dny
except ImportError:
    import deney as dny

# --- API İÇİN GEREKLİ EKLENTİLER ---
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


def _resolve_seferihisar_data_dir() -> Path:
    if DATA_ROOT.exists():
        for candidate in DATA_ROOT.iterdir():
            if candidate.is_dir() and "SEFER" in candidate.name.upper():
                return candidate
    return DATA_ROOT / "İZMİR SEFERİHİSAR"


app = FastAPI(
    title="DisasterAI Risk Analysis API",
    description="CBS tabanlı afet risk analizi, rota ve AI danışman uçları.",
    version="0.2.0",
)

# Tarayıcı ve Flutter erişimi için CORS ayarı
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Çıktıları dışarı açıyoruz
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

# --- MAKALE HAFIZASI (KALICI ÖNBELLEK İLE) ---
retriever = None
llm = None
# --- AI SOHBET MODELI ---
llm = None
memory_initialized = False

# Sohbet geçmişi: session_id -> mesaj listesi
_conversation_history: dict = {}
# Cevap önbelleği: (mesaj_hash) -> cevap metni
_response_cache: dict = {}

# Sistemin sabit tanımı — her sohbette bir kez gönderilir
SYSTEM_MESSAGE = (
    "Sen Türkiye afet risk yönetimi alanında uzmanlaşmış bir analiz asistanısın. "
    "Görevin, CBS tabanlı afet risk analizi sonuçlarını kullanıcıya net ve anlaşılır şekilde açıklamaktır.\n"
    "TON KURALLARI (kesinlikle uy):\n"
    "- Samimi ve anlaşılır ol, ama profesyonel kal.\n"
    "- 'kanka', 'abi', 'canım', 'tatlım', 'be', 'ya', 'ha' gibi argo veya samimi hitap ifadesi KULLANMA.\n"
    "- 'Umarım yardımcı oldu', 'güvenli kalın', 'uzman görüşü alın' gibi dolgu cümleler yazma.\n"
    "- Risk skorunu ilk yorumda veya kullanıcı özellikle skor sorarsa belirt; aynı analizde sonraki sorularda tekrar etme.\n"
    "- Maksimum 4 kısa cümle yaz, 4. cümleden sonra dur.\n"
    "- Her cümle eyleme geçirilebilir, somut bilgi içersin.\n"
    "- 'uygun güçlendirme yöntemleri', 'kentsel dönüşüm seçenekleri', 'uzman görüşü alın' gibi genel kalıp cümleleri tek başına KULLANMA.\n"
    "- Güçlendirme sorularında şu formatı kullan: 'Önce kontrol', 'Olası teknik müdahaleler', 'Kullanıcının bugün yapacağı iş'.\n"
    "- Teknik örnekleri somut ver: kolon-kiriş birleşimi, perde duvar ihtiyacı, mantolama, karbon elyaf, çelik çapraz, temel/zemin iyileştirme, yumuşak kat ve düzensizlik kontrolü.\n"
    "- Kentsel dönüşümden sadece risk yüksekse veya kullanıcı özellikle sorarsa bahset.\n"
    "- Eğer soru afet, bina güvenliği veya risk analizi ile ilgili değilse: "
    "'Bu sistem yalnızca afet risk analizi için tasarlanmıştır.' de ve dur."
)

# BDM sağlayıcı seçimi (İP2):
#   MODEL_SAGLAYICI=gemini  -> Gemini 2.5 Flash API (varsayılan)
#   MODEL_SAGLAYICI=yerel   -> Yerelde çalışan kendi ince ayarlı modelimiz
#                              (Ollama/vLLM; OpenAI-uyumlu uç)
# Yerel mod, projenin çevrimdışı çalışabilirlik iddiasının kanıtıdır:
# internet ve üçüncü taraf servis olmadan da aynı beş metin türü üretilir.
MODEL_SAGLAYICI = os.environ.get("MODEL_SAGLAYICI", "gemini").strip().lower()
YEREL_URL = os.environ.get("YEREL_LLM_URL", "http://127.0.0.1:11434/v1")
YEREL_MODEL = os.environ.get("YEREL_LLM_MODEL", "disasterai")


def initialize_memory():
    global llm, memory_initialized
    if memory_initialized:
        return

    if MODEL_SAGLAYICI == "yerel":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            print("❌ HATA: yerel mod için langchain-openai gerekli "
                  "(pip install langchain-openai).")
            memory_initialized = True
            return
        print(f"🤖 Sistem Başlatılıyor: YEREL model ({YEREL_MODEL} @ {YEREL_URL})")
        llm = ChatOpenAI(
            model=YEREL_MODEL,
            temperature=0.4,
            base_url=YEREL_URL,
            api_key="yerel",          # Ollama anahtar istemez, dolgu değer
            timeout=180,
        )
        memory_initialized = True
        print("✅ Yerel model hazır!")
        return

    print("🤖 Sistem Başlatılıyor: Google Gemini AI")
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("❌ HATA: GOOGLE_API_KEY bulunamadı! Lütfen bir .env dosyası oluşturup anahtarı ekleyin.")
        memory_initialized = True
        return

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.4,
        google_api_key=api_key
    )
    memory_initialized = True
    print("✅ Gemini AI hazır!")


# --- AYARLAR VE GLOBAL SABİTLER ---
# DİKKAT: Katmanların gerçek CRS'i EPSG:23035 (ED50 / UTM zone 35N).
# Eski kodda EPSG:32635 (WGS84 / UTM 35N) varsayılıyordu — Türkiye'de iki
# datum arasında ~90-100 m yatay fark var, 30 m pikselde ~3 piksel kayma.
ANALYSIS_CRS = ge.TARGET_CRS
BASE_DIR = _resolve_seferihisar_data_dir()
LAYER_NAMES = {
    "Akarsu": "Akarsu", "Arazi_Kullanım": "Arazi_Kullanım", "Eğim": "Eğim_Raster_Data", 
    "Fay_Hattı": "Fay_Hattı", "Litoloji": "Formasyon", "Sınır": "Seferihisar_Sınır"
}

# --- AĞIRLIK SETİ ---
# Bir TEZ KARARI. İki set var (ikisi de reclass_tables.py'de tanımlı):
#
#   "literatur" (VARSAYILAN) — yayımlanmış Türkiye AHP çalışmalarının bildirdiği
#       aralıkların ortasına oturur. Deprem için litoloji/zemin en ağır faktör
#       (0.24-0.37), fay mesafesi orta (0.07-0.15), eğim en hafif (0.04-0.06).
#       Kaynaklar: Ocak & Bahadır (2022) CR 0.08; Demir & Altaş (2024) CR 0.023;
#       Berber & Ceryan (2023) CR 0.054; Öz (2025) CR 0.080; Yurteri (2024) CR 0.058.
#
#   "mevcut" — projenin ilk sürümündeki ağırlıklar (deprem: fay 0.50, litoloji 0.30).
#       Fay ağırlığı literatür aralığının belirgin şekilde dışındaydı.
#       Duyarlılık analizi için korundu.
#
# Set değiştirmek için:  AGIRLIK_SETI=mevcut python -m uvicorn backend.main:app ...
# Karşılaştırma için  :  python tools/agirlik_karsilastir.py
AGIRLIK_SETI = os.environ.get("AGIRLIK_SETI", "literatur").strip().lower()
WEIGHTS = rt.AGIRLIKLAR_MEVCUT if AGIRLIK_SETI == "mevcut" else rt.AGIRLIKLAR_LITERATUR

# --- API VERİ MODELİ ---
class AnalizSorgu(BaseModel):
    x: float | None = None
    y: float | None = None
    lat: float | None = None
    lon: float | None = None
    bina_kat_sayisi: int
    oturulan_kat: int
    yapim_yili: int
    malzeme_secim: int
    asansor_var: int
    afet_tipi: str 


class AciklamaSorgu(AnalizSorgu):
    """/api/aciklama için: analiz parametreleri + iletişim tonu.

    ton: teknik_rapor (kontrol) | ham (ablasyon) | bilgilendirici |
         eyleme_yonelik | yatistirici
    """
    ton: str = "bilgilendirici"
    soru: str | None = None
    endise_duzeyi: str = "orta"
    katilimci_kodu: str | None = None   # A/B testinde anonim katılımcı kimliği


class RotaSorgu(BaseModel):
    lat: float
    lon: float

# --- ANALİZ FONKSİYONLARI ---

@functools.lru_cache(maxsize=16)
def cached_gpd_read(path, layer):
    return gpd.read_file(path, layer=layer)

def get_full_gdb_path(gdb_name):
    return str(BASE_DIR / gdb_name)

def get_base_raster_info():
    """Analiz gridi — ilçe sınırından, gis_engine üzerinden üretilir."""
    width, height, transform, bounds = ge.grid_info()
    return width, height, transform, list(bounds)


def simulate_spatial_risk(width, height, factor_key):
    """KALDIRILDI.

    Bu fonksiyon katman adından türetilen bir seed ile rastgele sayı + doğrusal
    gradyan üretiyordu; yani CBS katmanları hiç okunmuyordu. Gerçek analiz artık
    gis_engine.py içinde. Yanlışlıkla çağrılırsa sessizce sahte veri dönmesin diye
    hata veriyor.
    """
    raise RuntimeError(
        "simulate_spatial_risk() artık kullanılmıyor. Gerçek CBS analizi için "
        "gis_engine.weighted_overlay() kullanılmalıdır."
    )


def process_factor(gdb_name, layer_name, factor_type, width, height, transform):
    """Geriye dönük uyumluluk sarmalayıcısı — gerçek katmandan üretir."""
    raise RuntimeError(
        "process_factor() artık kullanılmıyor; gis_engine faktör üreticilerine bakın."
    )


def perform_weighted_overlay(weights, width=None, height=None, transform=None, map_type="DEPREM"):
    """
    Gerçek CBS katmanlarından ağırlıklı çakıştırma.

    Dönüş: (risk_matrisi, meta)
      meta: hangi katmanın hangi kaynaktan geldiği, eksik katmanlar,
            ağırlıkların yeniden normalize edilip edilmediği.
    """
    return ge.weighted_overlay(weights, map_type)


def calculate_vulnerability_score(user_data):
    score = 1.0
    yili = user_data['yapim_yili']
    malzeme = user_data['malzeme_secim']
    kat = user_data['bina_kat_sayisi']
    
    if yili < 2000: score += 1.5
    elif yili < 2007: score += 0.8
    
    if malzeme == 2: score += 1.5 
    elif malzeme == 3: score += 1.2 
    elif malzeme == 1: score += 0.5
    
    # Mevzuat ve Kat Sınırlamaları Kontrolü
    if malzeme in [2, 3] and kat > 3:
        score += 1.5 # Yığma ve Ahşap için 3 kat sınırı ihlali
    if malzeme == 1 and yili < 1998 and kat > 5:
        score += 1.0 # Eski ve çok katlı betonarme riski (1998 öncesi)
        
    if kat >= 7: score += 1.0
    elif kat >= 4: score += 0.5
    if user_data['oturulan_kat'] >= 5: score += 0.4 
    if user_data['asansor_var'] == 1: score += 0.2
    return np.clip(score, 1.0, 5.0)

def finalize_and_advise(risk_matrix, transform, map_type, user_data):
    """
    Bölgesel tehlike skorunu KULLANICININ SEÇTİĞİ NOKTADAN örnekler.

    Eski davranış: risk_matrix[H*0.5, W*0.5] — yani matrisin ortası. Kullanıcı
    haritada nereye tıklarsa tıklasın bölgesel skor aynı çıkıyordu ve toplam
    skor yalnızca bina girdilerine göre değişiyordu. Konuma özgü risk iddiası
    bu yüzden fiilen karşılanmıyordu.
    """
    x, y = user_data.get("x"), user_data.get("y")
    regional_hazard_score = None
    if x is not None and y is not None:
        regional_hazard_score = ge.sample_at(risk_matrix, float(x), float(y))
    if regional_hazard_score is None:
        raise HTTPException(
            status_code=422,
            detail="Seçilen nokta Seferihisar çalışma alanının dışında. "
                   "Lütfen ilçe sınırları içinden bir konum seçin."
        )

    vulnerability_score = calculate_vulnerability_score(user_data)
    if map_type == "DEPREM":
        final_risk = (regional_hazard_score * 0.60) + (vulnerability_score * 0.40)
    else:
        final_risk = (regional_hazard_score * 0.80) + (vulnerability_score * 0.20)
    final_risk = float(np.clip(final_risk, 1.0, 5.0))

    if final_risk >= 4.0:
        tavsiye = f"🔴 YÜKSEK RİSK BÖLGESİ ({final_risk:.2f}/5.0)"
    elif final_risk >= 3.0:
        tavsiye = f"🟠 ORTA RİSK BÖLGESİ ({final_risk:.2f}/5.0)"
    else:
        tavsiye = f"🟢 DÜŞÜK RİSK BÖLGESİ ({final_risk:.2f}/5.0)"
    return tavsiye, float(regional_hazard_score), float(vulnerability_score), final_risk


def _harita_aciklamasi_ekle(ax, renkler, sinirlar, konum_var):
    """Haritaya lejant, ölçek çubuğu ve kuzey oku ekler.

    Bu haritalar sonuç raporuna Şekil 1–3 olarak giriyor. Lejantsız bir risk
    haritası uzman olmayan okuyucu için yorumlanamaz: turuncunun "orta" mı
    "yüksek" mi olduğu, macenta çizgilerin ne olduğu görünmez. Renk sınırları
    da rapordaki risk sınıflarıyla (Düşük <3,0 · Orta 3,0–4,0 · Yüksek ≥4,0)
    hizalıdır; böylece metindeki "%71,1'i orta" gibi oranlar haritadan
    gözle doğrulanabilir.
    """
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D

    SINIF_ADI = ("Çok düşük", "Düşük", "Orta", "Yüksek", "Çok yüksek")

    def tr(sayi):
        return f"{sayi:.1f}".replace(".", ",")

    ogeler = [
        Patch(facecolor=renk, edgecolor="black", linewidth=0.4,
              label=f"{SINIF_ADI[i]}  ({tr(sinirlar[i])}–{tr(sinirlar[i + 1])})")
        for i, renk in enumerate(renkler)
    ]
    ogeler.append(Line2D([0], [0], color="blue", linewidth=1.5, label="Akarsu"))
    ogeler.append(Line2D([0], [0], color="#FF00FF", linewidth=1.2, linestyle="--",
                         label="Fay hattı"))
    ogeler.append(Line2D([0], [0], color="black", linewidth=1.5, label="İlçe sınırı"))
    if konum_var:
        ogeler.append(Line2D([0], [0], marker="o", linestyle="none", markerfacecolor="cyan",
                             markeredgecolor="black", markersize=9, label="Seçilen konum"))

    lejant = ax.legend(handles=ogeler, loc="lower left", fontsize=8, framealpha=0.93,
                       title="Risk skoru (1–5)", title_fontsize=9, borderpad=0.6,
                       labelspacing=0.45)
    lejant.set_zorder(40)

    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    genislik, yukseklik = x1 - x0, y1 - y0

    # Ölçek çubuğu — sağ altta, harita genişliğine göre yuvarlak bir uzunluk
    uzunluk = 5000 if genislik > 14000 else 2000
    bx = x1 - 0.05 * genislik - uzunluk
    by = y0 + 0.030 * yukseklik
    ax.plot([bx, bx + uzunluk], [by, by], color="black", linewidth=4,
            solid_capstyle="butt", zorder=40)
    ax.text(bx + uzunluk / 2, by + 0.010 * yukseklik, f"{uzunluk // 1000} km",
            ha="center", va="bottom", fontsize=9, fontweight="bold", zorder=41,
            bbox=dict(boxstyle="square,pad=0.15", facecolor="white",
                      edgecolor="none", alpha=0.85))

    # Kuzey oku — sağ üstte
    nx = x0 + 0.94 * genislik
    ny = y1 - 0.10 * yukseklik
    ax.annotate("K", xy=(nx, ny), xytext=(nx, ny - 0.055 * yukseklik),
                arrowprops=dict(facecolor="black", edgecolor="black", width=2.5,
                                headwidth=9, headlength=8),
                ha="center", va="center", fontsize=11, fontweight="bold", zorder=41)

    ax.set_xlabel("Doğu (m) — EPSG:23035", fontsize=9)
    ax.set_ylabel("Kuzey (m) — EPSG:23035", fontsize=9)
    ax.ticklabel_format(style="plain", useOffset=False)
    ax.tick_params(labelsize=8)


def create_risk_map_plot(risk_matrix, transform, map_type, bounds, output_dir=OUTPUT_DIR, user_coords=None, dpi=96):
    title = f"{map_type.upper()} RİSK HARİTASI (Seferihisar Bölgesi)"
    img_filename = f"{map_type.lower()}_risk_haritasi.png"
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    output_filename = output_dir / img_filename
    
    overlay_filename = f"{map_type.lower()}_overlay.png"
    overlay_filepath = output_dir / overlay_filename
    
    colors = ['#00FF00', '#FFFF00', '#FFA500', '#FF4500', '#FF0000']
    cmap = ListedColormap(colors)
    # Renk sınırları rapordaki üç risk sınıfıyla hizalı: 3,0 ve 4,0 eşikleri
    # renk değiştirdiği için "hücrelerin %71,1'i orta" gibi oranlar haritadan
    # gözle doğrulanabiliyor. (Eskiden eşit aralıklıydı — 1,8 / 2,6 / 3,4 —
    # ve hiçbir renk sınırı rapordaki sınıf sınırına denk gelmiyordu.)
    bounds_norm = np.array([1.0, 2.0, 3.0, 4.0, 4.5, 5.0])
    norm = BoundaryNorm(bounds_norm, cmap.N)

    minx, miny, maxx, maxy = bounds[0], bounds[1], bounds[2], bounds[3]
    # Gerçek coğrafi boyutlardan aspect ratio hesapla
    geo_width  = maxx - minx
    geo_height = maxy - miny
    fig_w = 8.0
    fig_h = max(4.0, min(12.0, fig_w * (geo_height / geo_width)))
    fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h))

    try:
        boundary_gpd = ge._read_layer("akarsu", "sinir")
        minx, miny, maxx, maxy = boundary_gpd.total_bounds
        geometries = [mapping(geom) for geom in boundary_gpd.geometry]

        memfile = rasterio.io.MemoryFile().open(
            driver='GTiff', height=risk_matrix.shape[0], width=risk_matrix.shape[1],
            count=1, dtype=risk_matrix.dtype, crs=ANALYSIS_CRS, transform=transform
        )
        memfile.write(risk_matrix.astype(risk_matrix.dtype), 1)
        out_image, out_transform = mask(memfile, geometries, crop=False, filled=False, nodata=np.nan)
        
        show(out_image, transform=out_transform, ax=ax, cmap=cmap, norm=norm, alpha=1.0, zorder=5) 

        # NOT: gis_engine._read_layer katmanları ANALYSIS_CRS'e dönüştürür.
        # Fay katmanı kaynakta EPSG:4022 (derece) olduğu için doğrudan
        # çizildiğinde harita dışına düşüyordu — bu yüzden buradan okunuyor.
        akarsu_gpd = ge._read_layer("akarsu", "akarsu")
        akarsu_gpd.plot(ax=ax, color='blue', linewidth=1.5, zorder=12)

        fay_gpd = ge._read_layer("fay", "fay")
        fay_gpd.plot(ax=ax, color='#FF00FF', linewidth=1.2, linestyle='--', zorder=12)

        boundary_gpd.plot(ax=ax, facecolor='none', edgecolor='black', linewidth=1.5, zorder=15)
    except Exception as e:
        ax.imshow(risk_matrix, cmap=cmap, norm=norm, origin='upper', extent=[minx, maxx, miny, maxy])

    if user_coords:
        ax.plot(user_coords[0], user_coords[1], marker='o', color='cyan', markersize=15, zorder=30, markeredgecolor='black')

    ax.set_title(title, fontsize=16, fontweight='bold')
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    _harita_aciklamasi_ekle(ax, colors, bounds_norm, user_coords is not None)


    # Uygulama 96 dpi kullanır (hız); rapor şekilleri için dpi=200 ile çağrılır,
    # yoksa lejant yazısı baskıda okunmuyor.
    plt.savefig(output_filename, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    
    # 2. AYRICA FOLIUM İÇİN TRANSPARAN OVERLAY OLUŞTUR
    try:
        # out_image varsa onu kullan (sınırlarla kesilmiş)
        data = out_image[0]
        # Maskelenmiş (sınır dışı) veya NaN olan yerleri bul
        if hasattr(data, 'mask'):
            valid_mask = ~data.mask
            data_values = data.data
        else:
            valid_mask = ~np.isnan(data)
            data_values = data
            
        # Değerleri RGBA renklere çevir
        rgba_img = cmap(norm(data_values))
        # Sınır dışı kalan tüm pikselleri %100 transparan yap (Alpha = 0)
        rgba_img[~valid_mask, 3] = 0.0 
        
        # Overlay'i 400px'e küçülterek kaydet — base64 çok daha küçük olur
        rgba_uint8 = (rgba_img * 255).astype(np.uint8)
        pil_img = Image.fromarray(rgba_uint8, 'RGBA')
        _h, _w = rgba_uint8.shape[0], rgba_uint8.shape[1]
        _scale = 600.0 / max(_h, _w)
        pil_img = pil_img.resize((max(1, int(_w * _scale)), max(1, int(_h * _scale))), Image.LANCZOS)
        pil_img.save(overlay_filepath, format='PNG', optimize=True)
    except Exception as e:
        # Eğer out_image yoksa risk_matrix'i kullan
        print(f"Overlay creation warning: {e}")
        rgba_img = cmap(norm(risk_matrix))
        rgba_img[np.isnan(risk_matrix), 3] = 0.0
        rgba_uint8 = (rgba_img * 255).astype(np.uint8)
        pil_img = Image.fromarray(rgba_uint8, 'RGBA')
        pil_img = pil_img.resize((400, 400), Image.LANCZOS)
        pil_img.save(overlay_filepath, format='PNG', optimize=True)
        
    return img_filename, overlay_filename # İkisini birden döndür


def _resolve_analysis_coordinates(sorgu: AnalizSorgu):
    if sorgu.x is not None and sorgu.y is not None:
        return float(sorgu.x), float(sorgu.y)
    if sorgu.lat is not None and sorgu.lon is not None:
        transformer = pyproj.Transformer.from_crs("epsg:4326", ANALYSIS_CRS, always_xy=True)
        x, y = transformer.transform(float(sorgu.lon), float(sorgu.lat))
        return float(x), float(y)
    raise HTTPException(status_code=422, detail="Analiz için x/y veya lat/lon koordinatı gerekli.")


def _bounds_to_wgs84(bounds):
    transformer = pyproj.Transformer.from_crs(ANALYSIS_CRS, "epsg:4326", always_xy=True)
    lon_min, lat_min = transformer.transform(float(bounds[0]), float(bounds[1]))
    lon_max, lat_max = transformer.transform(float(bounds[2]), float(bounds[3]))
    return [[lat_min, lon_min], [lat_max, lon_max]]


def _distance_km(lat1, lon1, lat2, lon2):
    radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_evacuation_route(lat, lon):
    max_direct_candidate_km = 3.0
    max_walking_route_km = 3.5
    max_walking_duration_min = 47.0

    osm_tags = [
        '["emergency"="assembly_point"]',
        '["amenity"="shelter"]',
        '["leisure"="park"]',
        '["leisure"="pitch"]',
        '["leisure"="playground"]',
        '["leisure"="garden"]',
        '["leisure"="common"]',
        '["leisure"="sports_centre"]',
        '["leisure"="stadium"]',
        '["amenity"="school"]',
        '["amenity"="university"]',
        '["amenity"="hospital"]',
        '["amenity"="community_centre"]',
        '["amenity"="marketplace"]',
        '["amenity"="parking"]',
        '["amenity"="place_of_worship"]',
        '["landuse"="recreation_ground"]',
        '["landuse"="grass"]',
        '["landuse"="meadow"]',
        '["landuse"="village_green"]',
        '["natural"="beach"]',
        '["natural"="grassland"]',
        '["tourism"="camp_site"]',
        '["place"="square"]',
    ]

    def _candidate_meta(tags):
        tags = tags or {}
        if tags.get("emergency") == "assembly_point":
            return "Toplanma Alanı", 0
        if tags.get("amenity") == "shelter":
            return "Barınma Alanı", 1
        if tags.get("place") == "square":
            return "Meydan", 2
        if tags.get("leisure") in {"park", "playground", "pitch", "sports_centre", "stadium", "common"}:
            return "Açık Spor/Park Alanı", 3
        if tags.get("landuse") in {"recreation_ground", "grass", "meadow", "village_green"}:
            return "Açık Alan", 4
        if tags.get("natural") in {"beach", "grassland"}:
            return "Doğal Açık Alan", 5
        if tags.get("amenity") in {"school", "university"}:
            return "Okul/Kampüs Alanı", 6
        if tags.get("amenity") in {"community_centre", "marketplace"}:
            return "Kamusal Açık Alan", 7
        if tags.get("amenity") == "parking":
            return "Otopark/Açık Alan", 10
        if tags.get("amenity") in {"hospital", "place_of_worship"}:
            return "Kamusal Alan", 8
        if tags.get("tourism") == "camp_site":
            return "Kamp/Açık Alan", 6
        return "Yakın Kamusal Alan", 9

    overpass_urls = [
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass-api.de/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ]

    def _build_query(radius):
        tag_blocks = "\n  ".join(
            f"node{tag}(around:{radius},{lat},{lon});\n  way{tag}(around:{radius},{lat},{lon});\n  relation{tag}(around:{radius},{lat},{lon});"
            for tag in osm_tags
        )
        return f"[out:json][timeout:14];\n(\n  {tag_blocks}\n);\nout center geom;"

    def _fetch(url, query):
        try:
            response = requests.post(url, data={"data": query}, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("elements"):
                    return data["elements"]
        except Exception:
            pass
        return None

    elements = []
    for radius in [5000, 15000, 30000]:
        query = _build_query(radius)
        with _cf.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_fetch, url, query): url for url in overpass_urls}
            try:
                for future in _cf.as_completed(futures, timeout=12):
                    result = future.result()
                    if result:
                        elements.extend(result)
                        break
            except _cf.TimeoutError:
                pass
        if len(elements) >= 30:
            break

    if not elements:
        raise HTTPException(
            status_code=404,
            detail="Yakında doğrulanabilir toplanma/açık alan verisi bulunamadı."
        )

    candidates_by_key = {}
    user_point = Point(float(lon), float(lat))
    for element in elements:
        plat = element.get("lat") or (element.get("center") or {}).get("lat")
        plon = element.get("lon") or (element.get("center") or {}).get("lon")
        if element.get("geometry"):
            try:
                geom = shape(element["geometry"])
                nearest = nearest_points(user_point, geom)[1]
                plat = nearest.y
                plon = nearest.x
            except Exception:
                pass
        if plat and plon:
            plat = float(plat)
            plon = float(plon)
            tags = element.get("tags", {})
            category, priority = _candidate_meta(tags)
            name = tags.get("name") or category
            key = (round(plat, 5), round(plon, 5))
            candidates_by_key[key] = {
                "lat": plat,
                "lon": plon,
                "name": name,
                "category": category,
                "priority": priority,
                "direct_distance_km": _distance_km(lat, lon, plat, plon),
            }

    nearby_candidates = [
        candidate for candidate in candidates_by_key.values()
        if candidate["direct_distance_km"] <= max_direct_candidate_km
    ]

    candidates = sorted(
        nearby_candidates,
        key=lambda item: (item["direct_distance_km"] + (item["priority"] * 0.18), item["direct_distance_km"])
    )[:40]

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail="Yakın çevrede afet anı için makul yürüme mesafesinde toplanma/açık alan bulunamadı."
        )

    def _fetch_walking_route(point):
        osrm_url = (
            "http://router.project-osrm.org/route/v1/foot/"
            f"{lon},{lat};{point['lon']},{point['lat']}"
            "?overview=full&geometries=geojson&steps=false&radiuses=1000;1000"
        )
        try:
            osrm_res = requests.get(osrm_url, timeout=8)
            osrm_data = osrm_res.json()
            if osrm_data.get("code") != "Ok" or not osrm_data.get("routes"):
                return None
            route = osrm_data["routes"][0]
            walking_km = route.get("distance", 0) / 1000.0
            direct_km = point["direct_distance_km"]
            duration_min = (walking_km / 4.5) * 60.0
            if walking_km > max_walking_route_km or duration_min > max_walking_duration_min:
                return None
            route_ratio = walking_km / max(direct_km, 0.03)
            route_note = "Yaya yol ağına göre en kısa bulunan rota; haritadaki çizgiyi takip edin."
            if route_ratio > 1.9 and walking_km - direct_km > 0.35:
                route_note = (
                    "Kuş uçuşuna göre daha uzun görünüyor; çünkü rota evlerin/kapalı alanların üzerinden değil, "
                    "yürünebilir yol ağı üzerinden çizildi."
                )
            return {
                "safe_point": {
                    "lat": point["lat"],
                    "lon": point["lon"],
                    "name": point["name"],
                    "category": point["category"],
                },
                "route_geojson": route["geometry"],
                "distance_km": walking_km,
                "direct_distance_km": direct_km,
                "duration_min": duration_min,
                "priority": point["priority"],
                "source": "osrm",
                "route_type": "walking",
                "route_note": route_note,
            }
        except Exception:
            return None

    walking_routes = []
    reasonable_routes = []
    with _cf.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(_fetch_walking_route, point) for point in candidates]
        try:
            for future in _cf.as_completed(futures, timeout=15):
                route = future.result()
                if route:
                    walking_routes.append(route)
                    direct_km = max(route["direct_distance_km"], 0.03)
                    max_reasonable_km = min(
                        max_walking_route_km,
                        max(direct_km * 2.6, direct_km + 1.0, 1.8)
                    )
                    if route["distance_km"] <= max_reasonable_km:
                        reasonable_routes.append(route)
        except _cf.TimeoutError:
            pass

    def _route_rank(route):
        return (
            route["distance_km"] + (route.get("priority", 9) * 0.25),
            route["distance_km"],
            route["direct_distance_km"],
        )

    if reasonable_routes:
        return sorted(reasonable_routes, key=_route_rank)[0]

    if walking_routes:
        return sorted(walking_routes, key=_route_rank)[0]

    def _fetch_nearby_park_candidates():
        park_query = f"""
        [out:json][timeout:10];
        (
          node["leisure"="park"](around:1500,{lat},{lon});
          way["leisure"="park"](around:1500,{lat},{lon});
          relation["leisure"="park"](around:1500,{lat},{lon});
          node["leisure"="playground"](around:1500,{lat},{lon});
          way["leisure"="playground"](around:1500,{lat},{lon});
          node["landuse"="recreation_ground"](around:1500,{lat},{lon});
          way["landuse"="recreation_ground"](around:1500,{lat},{lon});
        );
        out center geom tags;
        """
        park_elements = []
        with _cf.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_fetch, url, park_query): url for url in overpass_urls}
            try:
                for future in _cf.as_completed(futures, timeout=10):
                    result = future.result()
                    if result:
                        park_elements = result
                        break
            except _cf.TimeoutError:
                pass

        park_candidates = {}
        for element in park_elements:
            tags = element.get("tags", {})
            category, priority = _candidate_meta(tags)
            name = tags.get("name") or "Yakın Park/Açık Alan"
            points = []
            if element.get("lat") and element.get("lon"):
                points.append((float(element["lat"]), float(element["lon"])))
            if (element.get("center") or {}).get("lat") and (element.get("center") or {}).get("lon"):
                center = element["center"]
                points.append((float(center["lat"]), float(center["lon"])))
            for point in (element.get("geometry") or []):
                if point.get("lat") and point.get("lon"):
                    points.append((float(point["lat"]), float(point["lon"])))

            for plat, plon in sorted(points, key=lambda item: _distance_km(lat, lon, item[0], item[1]))[:4]:
                direct_km = _distance_km(lat, lon, plat, plon)
                if direct_km > max_direct_candidate_km:
                    continue
                key = (round(plat, 5), round(plon, 5), name)
                park_candidates[key] = {
                    "lat": plat,
                    "lon": plon,
                    "name": name,
                    "category": category,
                    "priority": min(priority, 3),
                    "direct_distance_km": direct_km,
                }
        return sorted(park_candidates.values(), key=lambda item: item["direct_distance_km"])[:12]

    nearby_park_candidates = _fetch_nearby_park_candidates()
    if nearby_park_candidates:
        with _cf.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_fetch_walking_route, point) for point in nearby_park_candidates]
            nearby_park_routes = []
            try:
                for future in _cf.as_completed(futures, timeout=12):
                    route = future.result()
                    if route:
                        nearby_park_routes.append(route)
            except _cf.TimeoutError:
                pass
        if nearby_park_routes:
            return sorted(nearby_park_routes, key=_route_rank)[0]

    raise HTTPException(
        status_code=404,
        detail="Yakında yürüyerek ulaşılabilir güvenli açık alan bulunamadı; uzak ve afet anı için pratik olmayan rota gösterilmedi."
    )


# --- API ENDPOINT ---

@app.post("/api/analysis")
@app.post("/analiz")
async def api_analiz(sorgu: AnalizSorgu, request: Request):
    x, y = _resolve_analysis_coordinates(sorgu)
    width, height, transform, bounds = get_base_raster_info()
    map_type = sorgu.afet_tipi.upper()
    weights = WEIGHTS.get(map_type, WEIGHTS["DEPREM"])

    # Gerçek CBS katmanlarından ağırlıklı çakıştırma
    final_risk_map, katman_meta = perform_weighted_overlay(weights, map_type=map_type)

    user_data = sorgu.model_dump()
    user_data["x"] = x
    user_data["y"] = y

    tavsiye, regional_hazard, vulnerability, final_skor = finalize_and_advise(
        final_risk_map, transform, map_type, user_data
    )

    img_name, overlay_name = create_risk_map_plot(
        final_risk_map, transform, map_type, bounds, user_coords=(x, y)
    )
    map_url = str(request.url_for("get_image", file_name=img_name))
    overlay_url = str(request.url_for("get_image", file_name=overlay_name))

    # "Skor Neden Böyle?" ve LLM için yapılandırılmış mekânsal olgular
    faktor_dokumu = ge.factor_breakdown(x, y, weights, map_type)
    mekansal_olgular = ge.mesafe_bilgisi(x, y)

    return {
        "tavsiye": str(tavsiye),
        "risk_score": float(final_skor),
        "hazard_score": float(regional_hazard),
        "vulnerability_score": float(vulnerability),
        "map_url": map_url,
        "overlay_url": overlay_url,
        "overlay_bounds_wgs84": _bounds_to_wgs84(bounds),
        "bounds_utm": [float(v) for v in bounds],
        "coordinates": {"x": x, "y": y, "lat": sorgu.lat, "lon": sorgu.lon},
        # --- YENİ: şeffaflık ve doğrulanabilirlik alanları ---
        "faktor_dokumu": faktor_dokumu,
        "mekansal_olgular": mekansal_olgular,
        "katman_meta": katman_meta,
        "veri_kaynagi": "gercek_cbs",
        "analiz_crs": ANALYSIS_CRS,
        "agirlik_seti": AGIRLIK_SETI,
    }

def _analiz_hesapla(sorgu: AnalizSorgu):
    """api_analiz ve api_aciklama'nın ortak hesap çekirdeği."""
    x, y = _resolve_analysis_coordinates(sorgu)
    map_type = sorgu.afet_tipi.upper()
    weights = WEIGHTS.get(map_type, WEIGHTS["DEPREM"])
    risk_map, katman_meta = perform_weighted_overlay(weights, map_type=map_type)

    user_data = sorgu.model_dump()
    user_data["x"], user_data["y"] = x, y
    tavsiye, hazard, vuln, skor = finalize_and_advise(risk_map, None, map_type, user_data)

    return {
        "afet_tipi": map_type,
        "tavsiye": tavsiye,
        "risk_score": float(skor),
        "hazard_score": float(hazard),
        "vulnerability_score": float(vuln),
        "faktor_dokumu": ge.factor_breakdown(x, y, weights, map_type),
        "mekansal_olgular": ge.mesafe_bilgisi(x, y),
        "katman_meta": katman_meta,
        "coordinates": {"x": x, "y": y, "lat": sorgu.lat, "lon": sorgu.lon},
        "yapim_yili": sorgu.yapim_yili,
        "malzeme_secim": sorgu.malzeme_secim,
        "bina_kat_sayisi": sorgu.bina_kat_sayisi,
        "oturulan_kat": sorgu.oturulan_kat,
    }


@app.post("/api/aciklama")
async def api_aciklama(sorgu: AciklamaSorgu):
    """
    Cog-S&C iletişim modülü: CBS çıktısını seçilen tonda doğal dile çevirir.

    Bu uç nokta, araştırma önerisindeki H2 hipotezinin test edilebilmesi için
    eklendi. Aynı mekânsal veriden, yalnızca `ton` parametresi değiştirilerek
    farklı iletişim çıktıları üretilir. `ton="teknik_rapor"` A/B testinin
    kontrol kolunu (LLM kullanmayan, deterministik geleneksel rapor),
    `ton="ham"` ise ablasyon kolunu (ton yönergesi olmayan düz BDM çıktısı)
    verir.
    """
    ton = (sorgu.ton or "bilgilendirici").strip().lower()

    # ton="otomatik": tonu kullanıcının yazdığı metinden çıkar (Cog-S&C bağlam
    # duyarlılığı). Deney akışı bunu KULLANMAZ — orada ton kola göre sabittir.
    ton_secimi = None
    if ton == "otomatik":
        ton_secimi = rc.ton_sec(sorgu.soru or "", sorgu.endise_duzeyi)
        ton = ton_secimi["ton"]

    if ton not in rc.GECERLI_TONLAR:
        raise HTTPException(
            status_code=422,
            detail=f"Geçersiz ton: {ton}. Geçerli değerler: "
                   f"{', '.join(rc.GECERLI_TONLAR)}, otomatik"
        )

    analiz = _analiz_hesapla(sorgu)

    # --- KONTROL KOLU: LLM kullanılmaz ---
    if ton == "teknik_rapor":
        metin = rc.teknik_rapor(analiz)
        sonuc = {
            "ton": ton, "metin": metin, "llm_kullanildi": False,
            "dogrulama": rc.dogrula(metin, analiz), "analiz": analiz,
            "ton_secimi": ton_secimi,
        }
        rc.deney_kaydet({
            "ton": ton, "katilimci_kodu": sorgu.katilimci_kodu,
            "koordinat": analiz["coordinates"], "afet_tipi": analiz["afet_tipi"],
            "risk_score": analiz["risk_score"], "metin": metin,
            "dogrulama": sonuc["dogrulama"], "llm_kullanildi": False,
        })
        return sonuc

    # --- BDM KOLLARI ---
    initialize_memory()
    if llm is None:
        raise HTTPException(
            status_code=503,
            detail="BDM kullanılamıyor (GOOGLE_API_KEY eksik olabilir). "
                   "Kontrol kolu için ton='teknik_rapor' kullanılabilir."
        )

    prompt = rc.cot_prompt(
        analiz, ton,
        kullanici_sorusu=sorgu.soru or "",
        endise_duzeyi=sorgu.endise_duzeyi,
    )
    try:
        metin = llm.invoke(prompt).content.strip()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"BDM çağrısı başarısız: {e}")

    dogrulama = rc.dogrula(metin, analiz)
    sonuc = {
        "ton": ton, "metin": metin, "llm_kullanildi": True,
        "dogrulama": dogrulama, "analiz": analiz, "prompt": prompt,
        "ton_secimi": ton_secimi,
    }
    rc.deney_kaydet({
        "ton": ton, "katilimci_kodu": sorgu.katilimci_kodu,
        "koordinat": analiz["coordinates"], "afet_tipi": analiz["afet_tipi"],
        "risk_score": analiz["risk_score"], "metin": metin,
        "dogrulama": dogrulama, "llm_kullanildi": True,
        "endise_duzeyi": sorgu.endise_duzeyi, "soru": sorgu.soru,
    })
    return sonuc


@app.post("/api/tonlari-karsilastir")
async def api_tonlari_karsilastir(sorgu: AciklamaSorgu):
    """
    H2 için tek çağrıda dört kolu birden üretir: teknik_rapor, ham,
    bilgilendirici, eyleme_yonelik, yatistirici.

    Ton doğruluğu etiketlemesi ve deney materyali hazırlığı için kullanılır:
    aynı mekânsal veriden üretilen çıktılar yan yana konularak
    değerlendiricilere sunulabilir.
    """
    analiz = _analiz_hesapla(sorgu)
    ciktilar = {"teknik_rapor": {
        "metin": rc.teknik_rapor(analiz), "llm_kullanildi": False,
    }}
    ciktilar["teknik_rapor"]["dogrulama"] = rc.dogrula(
        ciktilar["teknik_rapor"]["metin"], analiz)

    initialize_memory()
    for ton in ("ham", "bilgilendirici", "eyleme_yonelik", "yatistirici"):
        if llm is None:
            ciktilar[ton] = {"hata": "BDM kullanılamıyor (GOOGLE_API_KEY?)"}
            continue
        try:
            prompt = rc.cot_prompt(analiz, ton, sorgu.soru or "", sorgu.endise_duzeyi)
            metin = llm.invoke(prompt).content.strip()
            ciktilar[ton] = {
                "metin": metin, "llm_kullanildi": True,
                "dogrulama": rc.dogrula(metin, analiz),
            }
        except Exception as e:
            ciktilar[ton] = {"hata": str(e)}

    rc.deney_kaydet({
        "tip": "ton_karsilastirma", "katilimci_kodu": sorgu.katilimci_kodu,
        "koordinat": analiz["coordinates"], "afet_tipi": analiz["afet_tipi"],
        "risk_score": analiz["risk_score"],
        "ciktilar": {k: v.get("metin", v.get("hata")) for k, v in ciktilar.items()},
        "dogrulamalar": {k: v.get("dogrulama") for k, v in ciktilar.items()},
    })
    return {"analiz": analiz, "ciktilar": ciktilar}


# ===========================================================================
# DENEY UÇLARI (İP4 — kontrollü kullanıcı deneyi)
# ===========================================================================

@app.get("/api/deney/yapilandirma")
def api_deney_yapilandirma():
    """Arayüzün deney ekranını kurmak için gereken her şey."""
    return {
        "senaryolar": dny.SENARYOLAR,
        "olcekler": dny.OLCEKLER,
        "likert": [{"deger": d, "etiket": e} for d, e in dny.LIKERT],
        "kollar": list(dny.KOLLAR),
        "durum": dny.durum(),
    }


@app.post("/api/deney/kol-ata")
async def api_deney_kol_ata(istek: dict):
    """
    Katılımcıyı dengeli biçimde bir kola atar ve kaydeder.

    Aynı katılımcı kodu tekrar gönderilirse aynı kol döner (yeniden atama yok).
    """
    kod = (istek.get("katilimci_kodu") or "").strip()
    endise = (istek.get("endise_duzeyi") or "orta").strip().lower()
    if not kod:
        raise HTTPException(status_code=422, detail="Katılımcı kodu gerekli.")
    try:
        atama = dny.kol_ata(kod)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if atama.get("yeni"):
        dny.katilimci_kaydet(kod, atama["kol"], endise,
                             istek.get("demografik"))
    else:
        endise = atama.get("endise_duzeyi", endise)

    return {
        "katilimci_kodu": kod,
        "kol": atama["kol"],
        "ton": dny.ton_sec(atama["kol"], endise),
        "endise_duzeyi": endise,
        "yeni_katilimci": atama.get("yeni", False),
        "durum": dny.durum(),
    }


@app.post("/api/deney/senaryo-metni")
async def api_deney_senaryo_metni(istek: dict):
    """
    Bir senaryo için katılımcıya gösterilecek metni üretir.

    Katılımcı yalnızca kendi koluna ait metni görür (körleme).
    """
    kod = (istek.get("katilimci_kodu") or "").strip()
    senaryo_kodu = (istek.get("senaryo_kodu") or "").strip()
    if not kod:
        raise HTTPException(status_code=422, detail="Katılımcı kodu gerekli.")

    senaryo = next((s for s in dny.SENARYOLAR if s["kod"] == senaryo_kodu), None)
    if senaryo is None:
        raise HTTPException(status_code=404, detail=f"Senaryo bulunamadı: {senaryo_kodu}")

    atama = dny.kol_ata(kod)
    endise = atama.get("endise_duzeyi", (istek.get("endise_duzeyi") or "orta"))
    ton = dny.ton_sec(atama["kol"], endise)

    sorgu = AciklamaSorgu(
        lat=senaryo["lat"], lon=senaryo["lon"], afet_tipi=senaryo["afet_tipi"],
        ton=ton, endise_duzeyi=endise, katilimci_kodu=kod, **senaryo["bina"],
    )
    sonuc = await api_aciklama(sorgu)

    return {
        "senaryo": senaryo,
        "kol": atama["kol"],
        "ton": ton,
        "metin": sonuc["metin"],
        "dogrulama": sonuc["dogrulama"],
        # Katılımcıya gösterilmez; uygulayıcının kontrolü için
        "_analiz": sonuc["analiz"],
    }


@app.post("/api/deney/yanit")
async def api_deney_yanit(istek: dict):
    """Katılımcının ölçek yanıtlarını kaydeder ve puanları hesaplar."""
    if not (istek.get("katilimci_kodu") or "").strip():
        raise HTTPException(status_code=422, detail="Katılımcı kodu gerekli.")
    return dny.yanit_kaydet(istek)


@app.get("/api/deney/durum")
def api_deney_durum():
    return dny.durum()


@app.get("/api/health")
@app.get("/health")
def health_check():
    return {"status": "ok", "data_dir": str(BASE_DIR), "outputs_dir": str(OUTPUT_DIR),
            "agirlik_seti": AGIRLIK_SETI, "analiz_crs": ANALYSIS_CRS,
            "model_saglayici": MODEL_SAGLAYICI,
            "model_adi": (YEREL_MODEL if MODEL_SAGLAYICI == "yerel" else "gemini-2.5-flash")}

# Yöntem sayfası, sayıları elle yazmak yerine bu uçtan okur: ağırlık seti,
# dayanak etiketi sayıları ve duyarlılık analizi tek kaynaktan gelir, böylece
# arayüzdeki değer raporla ayrışamaz.
FAKTOR_ADLARI = {
    "Fay_Hattı_Uzaklığı": "Fay hattına uzaklık",
    "Litoloji": "Zemin / litoloji",
    "Eğim": "Eğim",
    "Akarsu_Uzaklığı": "Akarsuya uzaklık",
    "Arazi_Kullanımı": "Arazi kullanımı",
}

AFET_ADLARI = {"DEPREM": "Deprem", "HEYELAN": "Heyelan", "SEL": "Sel"}


def _duyarlilik_ozeti() -> list[dict]:
    """tools/agirlik_karsilastir.py çıktısındaki özet tablosunu okur.

    Kappa'yı istek anında yeniden hesaplamak bütün rasterleri yeniden üretmek
    demek; onun yerine üretilmiş rapor okunur. Rapor yoksa bölüm gösterilmez.
    """
    yol = OUTPUT_DIR / "agirlik_duyarlilik_analizi.md"
    if not yol.exists():
        return []
    satirlar = []
    ozet = False
    for satir in yol.read_text(encoding="utf-8").splitlines():
        if satir.startswith("## Özet"):
            ozet = True
            continue
        if ozet:
            if satir.startswith("#"):
                break
            hucreler = [h.strip() for h in satir.strip().strip("|").split("|")]
            if len(hucreler) != 6 or hucreler[0] in ("Afet", "---"):
                continue
            try:
                satirlar.append({
                    "afet": hucreler[0],
                    "ort_skor_eski": float(hucreler[1]),
                    "ort_skor_literatur": float(hucreler[2]),
                    "ort_mutlak_fark": float(hucreler[3]),
                    "sinif_degisimi": hucreler[4],
                    "kappa": float(hucreler[5]),
                })
            except ValueError:
                continue
    return satirlar


@app.get("/api/yontem")
def api_yontem():
    """Yöntem sayfasının izlenebilirlik verisi (ağırlıklar, dayanaklar, duyarlılık)."""
    sayilar = rt.etiket_sayilari()
    toplam = sum(sayilar.values())
    return {
        "agirlik_seti": AGIRLIK_SETI,
        "analiz_crs": ANALYSIS_CRS,
        "piksel_m": ge.PIXEL_SIZE,
        "faktor_adlari": FAKTOR_ADLARI,
        "afet_adlari": AFET_ADLARI,
        "agirliklar": WEIGHTS,
        "dayanak": {
            "sayilar": sayilar,
            "toplam": toplam,
            "aciklama": {
                "K": "Kaynaklı — yayımlanmış bir çalışmadan alınmış ya da ölçeklenmiş",
                "U": "Uyarlama — yayımlanmış şemalardan uyarlanmış, birebir alıntı değil",
                "E": "Eksper ataması — literatürde karşılığı bulunamadı, tarafımızca atanmıştır",
            },
        },
        "kaynak_sayisi": len(rt.KAYNAKLAR),
        "duyarlilik": _duyarlilik_ozeti(),
        "katmanlar": sorted(ge.LAYER.values()),
        "dem": "Copernicus GLO-30 (ESA, 2024) — eğim Horn (1981) yöntemiyle üretildi",
        "bina_agirliklari": {"DEPREM": {"bolgesel": 0.60, "bina": 0.40},
                             "DIGER": {"bolgesel": 0.80, "bina": 0.20}},
    }


@app.get("/outputs/{file_name}")
async def get_image(file_name: str):
    file_path = OUTPUT_DIR / Path(file_name).name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
    return FileResponse(file_path)


@app.post("/api/evacuation-route")
async def api_evacuation_route(sorgu: RotaSorgu):
    return find_evacuation_route(float(sorgu.lat), float(sorgu.lon))

def ask_aiChatbot(user_message: str, context_data: dict, session_id: str = "default"):
    try:
        if is_strengthening_question(user_message):
            yield build_local_chat_response(user_message, context_data, session_id=session_id)
            return

        initialize_memory()

        if llm is None:
            yield build_local_chat_response(user_message, context_data, session_id=session_id)
            return

        # --- CEVAP ÖNBELLEĞİ: Aynı soru + bağlamda Gemini'ye gitme ---
        cache_key = hash((
            user_message.strip().lower(),
            str(context_data.get("afet_tipi", "") if context_data else ""),
            str(context_data.get("toplam_risk_skoru", "") if context_data else "")
        ))
        if cache_key in _response_cache:
            yield _response_cache[cache_key]
            return

        # --- ANALİZ BAĞLAMINI HAZIRLA ---
        ctx = context_data or {}
        afet_tipi   = ctx.get("afet_tipi", "Belirtilmemiş")
        toplam_skor = ctx.get("toplam_risk_skoru", None)
        bolgesel    = ctx.get("bolgesel_tehlike_skoru", None)
        bina_skor   = ctx.get("bina_hassasiyet_skoru", None)
        tavsiye     = ctx.get("tavsiye", "")
        yapi_yili = ctx.get("yapim_yili", "belirtilmemiş")
        kat_sayisi = ctx.get("bina_kat_sayisi", "belirtilmemiş")
        oturulan_kat = ctx.get("oturulan_kat", "belirtilmemiş")
        malzeme = ctx.get("malzeme", "belirtilmemiş")

        def seviye(skor):
            if skor is None: return "bilinmiyor"
            if skor >= 4.0: return "yüksek"
            if skor >= 3.0: return "orta"
            return "düşük"

        def fmt(skor):
            return f"{skor:.1f}/5.0" if skor is not None else "?/5.0"

        if toplam_skor is not None:
            context_block = (
                f"Afet türü: {afet_tipi} | "
                f"Genel risk skoru: {fmt(toplam_skor)} ({seviye(toplam_skor)}) | "
                f"Bölgesel tehlike skoru: {fmt(bolgesel)} ({seviye(bolgesel)}) | "
                f"Bina hassasiyeti skoru: {fmt(bina_skor)} ({seviye(bina_skor)}) | "
                f"Bina bilgileri: malzeme={malzeme}, toplam kat={kat_sayisi}, oturulan kat={oturulan_kat}, yapım yılı={yapi_yili} | "
                f"Sistem değerlendirmesi: {tavsiye}"
            )
        else:
            context_block = "Henüz analiz yapılmamış."

        # --- SOHBET GEÇMİŞİ: Session bazlı, son 6 mesaj ---
        if session_id not in _conversation_history:
            _conversation_history[session_id] = [
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "assistant", "content": "Anlaşıldı. Afet risk analizi sonuçlarını net ve profesyonel şekilde açıklayacağım."}
            ]

        history = _conversation_history[session_id]
        user_turn = f"[{context_block}]\nSoru: {user_message}"
        history.append({"role": "human", "content": user_turn})

        # Sistem mesajı + son 3 gidiş-geliş (6 mesaj)
        trimmed = history[:2] + history[max(2, len(history) - 6):]

        # --- LLM'E GÖNDER (streaming) ---
        full_reply = ""
        for chunk in llm.stream(trimmed):
            text_val = chunk.content if hasattr(chunk, "content") else str(chunk)
            full_reply += text_val
            yield text_val

        # Cevabı geçmişe ekle, max 20 mesaj tut
        history.append({"role": "assistant", "content": full_reply})

        if len(history) > 20:
            _conversation_history[session_id] = history[:2] + history[-14:]

        # Önbelleğe kaydet
        _response_cache[cache_key] = full_reply

    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            yield (
                "⏳ Gemini API günlük ücretsiz kota doldu. "
                "Kota gece yarısında (UTC 00:00) sıfırlanır. "
                "Acil ihtiyaç varsa https://aistudio.google.com adresinden yeni API anahtarı oluşturabilirsiniz."
            )
        else:
            yield f"Sistem hatası: {err_str}"


def is_strengthening_question(user_message: str) -> bool:
    message = (user_message or "").strip().lower()
    terms = ["güç", "gucl", "güçlendirme", "guclendirme", "kolon", "kiriş", "kiris", "perde", "zemin"]
    return any(term in message for term in terms)


def build_local_chat_response(user_message: str, context_data: dict, session_id: str = "default") -> str:
    message = (user_message or "").strip().lower()
    ctx = context_data or {}
    total = ctx.get("toplam_risk_skoru")
    hazard = ctx.get("bolgesel_tehlike_skoru")
    vulnerability = ctx.get("bina_hassasiyet_skoru")
    disaster_type = ctx.get("afet_tipi", "afet")
    material = ctx.get("malzeme", "belirtilmemiş")
    year = ctx.get("yapim_yili")
    floors = ctx.get("bina_kat_sayisi")
    lived_floor = ctx.get("oturulan_kat")

    local_key = f"local:{session_id}"
    history = _conversation_history.setdefault(local_key, [])
    prior_text = " ".join(item.get("content", "") for item in history[-8:]).lower()
    already_explained_score = "genel risk skoru" in prior_text

    relevant_terms = [
        "risk", "afet", "deprem", "sel", "heyelan", "bina", "skor", "yorum",
        "toplanma", "rota", "güvenli", "guvenli", "kaçış", "kacis",
        "güç", "gucl", "güçlendirme", "guclendirme", "kolon", "kiriş", "kiris",
        "zemin", "perde", "donatı", "donati", "kat", "tahliye"
    ]
    if message and not any(term in message for term in relevant_terms):
        return "Bu sistem yalnızca afet risk analizi için tasarlanmıştır."

    if total is None:
        return (
            "Henüz analiz sonucu yok; haritadan konum seçip analiz başlatırsanız skoru yorumlayabilirim. "
            "Toplanma alanını analizden bağımsız olarak da bulabilirsiniz."
        )

    def level(score):
        if score >= 4.0:
            return "yüksek"
        if score >= 3.0:
            return "orta"
        return "düşük"

    driver = "bölgesel tehlike"
    if vulnerability is not None and hazard is not None and vulnerability > hazard:
        driver = "bina hassasiyeti"

    def score_text(score):
        return f"{score:.1f}/5.0" if isinstance(score, (int, float)) else "?/5.0"

    wants_strengthening = any(term in message for term in ["güç", "gucl", "kolon", "kiriş", "kiris", "perde", "zemin"])
    wants_route = any(term in message for term in ["toplanma", "rota", "kaçış", "kacis", "tahliye"])

    if wants_strengthening:
        year_note = "2000 ve sonrası için proje/uygulama kalitesi yine kontrol edilmeli"
        if isinstance(year, (int, float)) and year < 2000:
            year_note = "2000 öncesi olduğu için deprem performans analizi öncelikli"
        elif isinstance(year, (int, float)) and year < 2007:
            year_note = "2007 öncesi olduğu için yönetmelik farkı ayrıca incelenmeli"

        reply = (
            f"Önce kontrol: {material}, {floors} kat, yapım yılı {year}; {year_note}. "
            "Mühendisten kolon-kiriş birleşimi, perde duvar ihtiyacı, yumuşak kat/düzensizlik ve zemin etüdü kontrolü istenmeli. "
            "Olası teknik müdahaleler rapora göre mantolama, perde ekleme, karbon elyaf, çelik çapraz veya temel/zemin iyileştirmedir; bugün proje/ruhsat bilgilerini ve varsa eski statik projeyi hazırlayın."
        )
    elif wants_route:
        reply = (
            "Toplanma alanı için haritadaki yürüyüş rotasını kullan; süre ve mesafe panelde gösteriliyor. "
            "Rota uzun görünüyorsa bunun nedeni kapalı parsellerin üstünden değil, yürünebilir yol ağı üzerinden çizilmesidir."
        )
    elif already_explained_score:
        reply = (
            f"Bu soruda tekrar skoru açmadan odak noktasını söyleyeyim: baskın etken {driver}. "
            f"{disaster_type} için bina bilgilerini ve yürüyüş rotasını birlikte değerlendir; kırılganlık yüksekse taşıyıcı sistem kontrolünü öne al."
        )
    else:
        reply = (
            f"Genel risk skoru {total:.1f}/5.0 ve bu {level(total)} risk seviyesine denk geliyor. "
            f"Bu sonuçta en baskın etken {driver}; bölgesel tehlike {score_text(hazard)}, bina hassasiyeti {score_text(vulnerability)}. "
            "Sonraki adım olarak toplanma rotasını netleştirip bina tarafında hangi unsurun skoru yükselttiğini kontrol etmelisin."
        )

    history.append({"role": "human", "content": user_message or ""})
    history.append({"role": "assistant", "content": reply})
    if len(history) > 16:
        _conversation_history[local_key] = history[-16:]
    return reply


@app.post("/api/chat")
@app.post("/chat")
async def chat_with_ai(prompt_data: dict):
    user_message = prompt_data.get("message")
    context_data = prompt_data.get("context")
    session_id = prompt_data.get("session_id", "default")
    return StreamingResponse(
        ask_aiChatbot(user_message, context_data, session_id=session_id),
        media_type="text/plain"
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8504)
