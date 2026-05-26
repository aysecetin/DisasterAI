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

def initialize_memory():
    global llm, memory_initialized
    if memory_initialized:
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
BASE_DIR = _resolve_seferihisar_data_dir()
LAYER_NAMES = {
    "Akarsu": "Akarsu", "Arazi_Kullanım": "Arazi_Kullanım", "Eğim": "Eğim_Raster_Data", 
    "Fay_Hattı": "Fay_Hattı", "Litoloji": "Formasyon", "Sınır": "Seferihisar_Sınır"
}

WEIGHTS = {
    "DEPREM": {"Fay_Hattı_Uzaklığı": 0.50, "Litoloji": 0.30, "Eğim": 0.05, "Akarsu_Uzaklığı": 0.05, "Arazi_Kullanımı": 0.10}, 
    "HEYELAN": {"Fay_Hattı_Uzaklığı": 0.15, "Litoloji": 0.35, "Eğim": 0.40, "Akarsu_Uzaklığı": 0.05, "Arazi_Kullanımı": 0.05},
    "SEL": {"Fay_Hattı_Uzaklığı": 0.05, "Litoloji": 0.15, "Eğim": 0.10, "Akarsu_Uzaklığı": 0.60, "Arazi_Kullanımı": 0.10}
}

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
    bounds = [481000, 4210000, 497000, 4229000] # Default UTM bounds (Seferihisar area approx)
    pixel_size = 30
    try:
        boundary_gdb_path = get_full_gdb_path("Akarsu Analizi.gdb")
        boundary_gpd = cached_gpd_read(boundary_gdb_path, layer=LAYER_NAMES["Sınır"])
        bounds = boundary_gpd.total_bounds
    except Exception: pass 
    width = int(np.ceil((bounds[2] - bounds[0]) / pixel_size))
    height = int(np.ceil((bounds[3] - bounds[1]) / pixel_size))
    transform = Affine(pixel_size, 0, bounds[0], 0, -pixel_size, bounds[3])
    return width, height, transform, bounds

def simulate_spatial_risk(width, height, factor_key):
    np.random.seed(sum(ord(c) for c in factor_key) % 100 + 1)
    risk_base = np.random.uniform(1.0, 5.0, size=(height, width))
    block_size = 50 
    block_scores = np.random.uniform(1, 5, size=(height // block_size + 1, width // block_size + 1))
    risk_matrix = np.kron(block_scores, np.ones((block_size, block_size)))[:height, :width]
    if "DEPREM" in factor_key or "Fay" in factor_key:
        gradient = np.linspace(5.0, 1.0, width)[None, :] 
    elif "SEL" in factor_key or "Akarsu" in factor_key:
        gradient = np.linspace(1.0, 5.0, height)[:, None] 
    elif "HEYELAN" in factor_key or "Eğim" in factor_key:
        grad_x = np.linspace(1.0, 5.0, width)[None, :]
        grad_y = np.linspace(1.0, 5.0, height)[:, None]
        gradient = (grad_x + grad_y) / 2
    else:
        gradient = np.full((height, width), 2.5)
    gradient = np.interp(gradient, (gradient.min(), gradient.max()), (1.0, 5.0))
    risk_matrix = (risk_base * 0.1) + (gradient * 0.9) 
    return np.clip(risk_matrix, 1.0, 5.0)

def process_factor(gdb_name, layer_name, factor_type, width, height, transform):
    key_for_sim = layer_name if layer_name else gdb_name 
    return simulate_spatial_risk(width, height, key_for_sim)

def perform_weighted_overlay(weights, width, height, transform):
    total_risk_matrix = np.zeros((height, width), dtype=np.float32)
    gdb_mapping = {"Eğim": "Eğim Analizi.gdb", "Litoloji": "Litoloji Analizi.gdb", "Akarsu_Uzaklığı": "Akarsu Analizi.gdb", "Fay_Hattı_Uzaklığı": "Fay Hattı Analizi.gdb", "Arazi_Kullanımı": "Arazi Kullanım Analizi.gdb"}
    for factor_key, weight in weights.items():
        if weight == 0: continue
        gdb_name = gdb_mapping.get(factor_key)
        base_key = factor_key.replace('_Uzaklığı', '')
        layer_name = LAYER_NAMES.get(base_key) 
        factor_type = 'Raster' if 'Eğim' in factor_key else 'Vector'
        risk_scores_1_to_5 = process_factor(gdb_name, layer_name, factor_type, width, height, transform)
        total_risk_matrix += risk_scores_1_to_5 * weight
    return total_risk_matrix

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
    regional_hazard_score = np.interp(risk_matrix[int(risk_matrix.shape[0]*0.5), int(risk_matrix.shape[1]*0.5)], 
                                     (risk_matrix.min(), risk_matrix.max()), (1.0, 5.0))
    vulnerability_score = calculate_vulnerability_score(user_data)
    if map_type == "DEPREM": final_risk = (regional_hazard_score * 0.60) + (vulnerability_score * 0.40)
    else: final_risk = (regional_hazard_score * 0.80) + (vulnerability_score * 0.20)
    final_risk = np.clip(final_risk, 1.0, 5.0)
    if final_risk >= 4.0: tavsiye = f"🔴 YÜKSEK RİSK BÖLGESİ ({final_risk:.2f}/5.0)"
    elif final_risk >= 3.0: tavsiye = f"🟠 ORTA RİSK BÖLGESİ ({final_risk:.2f}/5.0)"
    else: tavsiye = f"🟢 DÜŞÜK RİSK BÖLGESİ ({final_risk:.2f}/5.0)"
    return tavsiye, float(regional_hazard_score), float(vulnerability_score), float(final_risk)

def create_risk_map_plot(risk_matrix, transform, map_type, bounds, output_dir=OUTPUT_DIR, user_coords=None):
    title = f"{map_type.upper()} RİSK HARİTASI (Seferihisar Bölgesi)"
    img_filename = f"{map_type.lower()}_risk_haritasi.png"
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    output_filename = output_dir / img_filename
    
    overlay_filename = f"{map_type.lower()}_overlay.png"
    overlay_filepath = output_dir / overlay_filename
    
    colors = ['#00FF00', '#FFFF00', '#FFA500', '#FF4500', '#FF0000'] 
    cmap = ListedColormap(colors)
    vmin, vmax = 1.0, 5.0
    bounds_norm = np.linspace(vmin, vmax, 6)
    norm = BoundaryNorm(bounds_norm, cmap.N)

    minx, miny, maxx, maxy = bounds[0], bounds[1], bounds[2], bounds[3]
    # Gerçek coğrafi boyutlardan aspect ratio hesapla
    geo_width  = maxx - minx
    geo_height = maxy - miny
    fig_w = 8.0
    fig_h = max(4.0, min(12.0, fig_w * (geo_height / geo_width)))
    fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h))

    try:
        boundary_gdb_path = get_full_gdb_path("Akarsu Analizi.gdb")
        boundary_gpd = cached_gpd_read(boundary_gdb_path, layer=LAYER_NAMES["Sınır"])
        minx, miny, maxx, maxy = boundary_gpd.total_bounds
        geometries = [mapping(geom) for geom in boundary_gpd.geometry]

        memfile = rasterio.io.MemoryFile().open(
            driver='GTiff', height=risk_matrix.shape[0], width=risk_matrix.shape[1],
            count=1, dtype=risk_matrix.dtype, crs='EPSG:32635', transform=transform
        )
        memfile.write(risk_matrix.astype(risk_matrix.dtype), 1)
        out_image, out_transform = mask(memfile, geometries, crop=False, filled=False, nodata=np.nan)
        
        show(out_image, transform=out_transform, ax=ax, cmap=cmap, norm=norm, alpha=1.0, zorder=5) 

        akarsu_gpd = cached_gpd_read(get_full_gdb_path("Akarsu Analizi.gdb"), layer=LAYER_NAMES["Akarsu"])
        akarsu_gpd.plot(ax=ax, color='blue', linewidth=1.5, zorder=12)
        
        fay_gpd = cached_gpd_read(get_full_gdb_path("Fay Hattı Analizi.gdb"), layer=LAYER_NAMES["Fay_Hattı"])
        fay_gpd.plot(ax=ax, color='#FF00FF', linewidth=2.5, linestyle='--', zorder=12)

        boundary_gpd.plot(ax=ax, facecolor='none', edgecolor='black', linewidth=1.5, zorder=15)
    except Exception as e:
        ax.imshow(risk_matrix, cmap=cmap, norm=norm, origin='upper', extent=[minx, maxx, miny, maxy])

    if user_coords:
        ax.plot(user_coords[0], user_coords[1], marker='o', color='cyan', markersize=15, zorder=30, markeredgecolor='black')

    ax.set_title(title, fontsize=16, fontweight='bold')
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    
    plt.savefig(output_filename, dpi=96, bbox_inches='tight')  # 300→96 dpi: çok daha hızlı kayıt
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
        pil_img = pil_img.resize((400, 400), Image.LANCZOS)
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
        transformer = pyproj.Transformer.from_crs("epsg:4326", "epsg:32635", always_xy=True)
        x, y = transformer.transform(float(sorgu.lon), float(sorgu.lat))
        return float(x), float(y)
    raise HTTPException(status_code=422, detail="Analiz için x/y veya lat/lon koordinatı gerekli.")


def _bounds_to_wgs84(bounds):
    transformer = pyproj.Transformer.from_crs("epsg:32635", "epsg:4326", always_xy=True)
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
    final_risk_map = perform_weighted_overlay(weights, width, height, transform)

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
    
    return {
        "tavsiye": str(tavsiye),
        "risk_score": float(final_skor),
        "hazard_score": float(regional_hazard),
        "vulnerability_score": float(vulnerability),
        "map_url": map_url,
        "overlay_url": overlay_url,
        "overlay_bounds_wgs84": _bounds_to_wgs84(bounds),
        "bounds_utm": [float(value) for value in bounds],
        "coordinates": {"x": x, "y": y, "lat": sorgu.lat, "lon": sorgu.lon},
    }

@app.get("/api/health")
@app.get("/health")
def health_check():
    return {"status": "ok", "data_dir": str(BASE_DIR), "outputs_dir": str(OUTPUT_DIR)}

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
