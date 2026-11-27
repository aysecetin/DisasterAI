import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import {
  Activity,
  AlertTriangle,
  BookOpen,
  Bot,
  Building2,
  Clock,
  Cpu,
  Database,
  Download,
  FileText,
  GripHorizontal,
  History,
  Info,
  Layers,
  Loader2,
  MapPinned,
  MessageCircle,
  Moon,
  Navigation,
  RotateCcw,
  Search,
  Send,
  ShieldCheck,
  Sun,
  X,
} from "lucide-react";
import {
  Circle,
  ImageOverlay,
  LayersControl,
  MapContainer,
  Marker,
  Pane,
  Polyline,
  Popup,
  ScaleControl,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";
import ExperimentPanel from "./ExperimentPanel";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8514";
const SEFERIHISAR_CENTER = [38.196, 26.84];

const disasterOptions = [
  { label: "Deprem", value: "DEPREM" },
  { label: "Heyelan", value: "HEYELAN" },
  { label: "Sel/Taşkın", value: "SEL" },
];

const materialOptions = [
  { label: "Betonarme", value: 1 },
  { label: "Yığma", value: 2 },
  { label: "Ahşap", value: 3 },
];

function getMaterialLabel(value) {
  return materialOptions.find((option) => option.value === Number(value))?.label || "Belirtilmemiş";
}

const selectedIcon = L.divIcon({
  className: "map-pin",
  html: "<span></span>",
  iconSize: [34, 34],
  iconAnchor: [17, 17],
});

const safeIcon = L.divIcon({
  className: "safe-pin",
  html: "<span></span>",
  iconSize: [32, 32],
  iconAnchor: [16, 16],
});

function apiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

// PDF raporu HTML dizesi olarak yazılıyor; adres gibi dışarıdan gelen metin
// (Nominatim) işaretleme olarak yorumlanmasın
function htmlKacis(deger) {
  return String(deger ?? "").replace(/[&<>"']/g, (karakter) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[karakter]
  ));
}

function formatAddressLine(place) {
  if (!place) return "";
  const address = place.address || {};
  const road = address.road || address.pedestrian || address.footway || address.path || address.cycleway;
  const neighbourhood =
    address.neighbourhood ||
    address.suburb ||
    address.quarter ||
    address.village ||
    address.hamlet ||
    address.city_district;
  const district = address.town || address.county || address.city || address.province;
  const parts = [road, neighbourhood, district].filter(Boolean);
  const uniqueParts = parts.filter((part, index) => parts.indexOf(part) === index);

  if (uniqueParts.length) return uniqueParts.slice(0, 2).join(", ");
  return (place.display_name || "").split(",").slice(0, 2).join(", ").trim();
}

// Backend faktor_dokumu anahtarları -> okunur Türkçe etiket
const FAKTOR_ETIKETLERI = {
  "Fay_Hattı_Uzaklığı": "Fay hattına uzaklık",
  "Litoloji": "Zemin / litoloji",
  "Eğim": "Eğim",
  "Akarsu_Uzaklığı": "Akarsuya uzaklık",
  "Arazi_Kullanımı": "Arazi kullanımı",
};

// Risk katmanı renk skalası — backend'in çizdiği raster paletiyle birebir aynı
const RISK_RENKLERI = ["#00FF00", "#FFFF00", "#FFA500", "#FF4500", "#FF0000"];

function riskTone(score) {
  if (!score) return "neutral";
  if (score >= 4) return "high";
  if (score >= 3) return "medium";
  return "low";
}

function riskLabel(score) {
  if (!score) return "Analiz bekleniyor";
  if (score >= 4) return "Yüksek Risk";
  if (score >= 3) return "Orta Risk";
  return "Düşük Risk";
}

function calculateVulnerabilityScore(data) {
  let score = 1.0;
  const year = Number(data.yapim_yili);
  const material = Number(data.malzeme_secim);
  const floors = Number(data.bina_kat_sayisi);
  const livedFloor = Number(data.oturulan_kat);

  if (year < 2000) score += 1.5;
  else if (year < 2007) score += 0.8;

  if (material === 2) score += 1.5;
  else if (material === 3) score += 1.2;
  else if (material === 1) score += 0.5;

  if ([2, 3].includes(material) && floors > 3) score += 1.5;
  if (material === 1 && year < 1998 && floors > 5) score += 1.0;
  if (floors >= 7) score += 1.0;
  else if (floors >= 4) score += 0.5;
  if (livedFloor >= 5) score += 0.4;
  if (Number(data.asansor_var) === 1) score += 0.2;

  return Math.min(5, Math.max(1, score));
}

function combineRiskScore(hazardScore, vulnerabilityScore, disasterType) {
  if (!hazardScore || !vulnerabilityScore) return null;
  const hazardWeight = disasterType === "DEPREM" ? 0.6 : 0.8;
  return Math.min(5, Math.max(1, (hazardScore * hazardWeight) + (vulnerabilityScore * (1 - hazardWeight))));
}

function buildRiskExplanation(result, form) {
  if (!result) return [];
  const points = [];
  const material = getMaterialLabel(form.malzeme_secim);
  const driver = result.vulnerability_score > result.hazard_score ? "bina hassasiyeti" : "bölgesel tehlike";

  points.push(`Skoru en çok etkileyen taraf: ${driver}.`);
  points.push(`${material}, ${form.bina_kat_sayisi} kat ve ${form.yapim_yili} yapım yılı bina hassasiyetine yansıtıldı.`);

  if (form.yapim_yili < 2000) points.push("2000 öncesi yapı yılı deprem açısından kırılganlığı belirgin artırır.");
  else if (form.yapim_yili < 2007) points.push("2007 öncesi yapı yılı yönetmelik farkı nedeniyle ayrıca kontrol ister.");
  else points.push("Yapı yılı yeni olsa bile kat sayısı, taşıyıcı sistem ve uygulama kalitesi kontrol edilmelidir.");

  if (form.bina_kat_sayisi >= 7) points.push("7 ve üzeri kat sayısı tahliye ve taşıyıcı sistem hassasiyetini yükseltir.");
  return points;
}

function buildScenarioComparison(result, form) {
  if (!result) return [];
  const currentVulnerability = result.vulnerability_score;
  const strengthenedVulnerability = Math.max(1, currentVulnerability - 0.7);
  const updatedYearVulnerability = calculateVulnerabilityScore({ ...form, yapim_yili: 2026 });
  const lowerFloorVulnerability = calculateVulnerabilityScore({
    ...form,
    bina_kat_sayisi: Math.max(1, Number(form.bina_kat_sayisi) - 2),
    oturulan_kat: Math.min(Number(form.oturulan_kat), Math.max(1, Number(form.bina_kat_sayisi) - 2)),
  });

  return [
    { label: "Mevcut", score: result.risk_score, detail: "Girilen bina bilgileriyle hesaplandı." },
    {
      label: "Güçlendirme",
      score: combineRiskScore(result.hazard_score, strengthenedVulnerability, form.afet_tipi),
      detail: "Bina hassasiyetinin yaklaşık 0.7 puan düşmesi varsayımı.",
    },
    {
      label: "Yeni Yapı",
      score: combineRiskScore(result.hazard_score, updatedYearVulnerability, form.afet_tipi),
      detail: "Yapım yılı 2026 kabul edilerek tahmini karşılaştırma.",
    },
    {
      label: "Daha Az Kat",
      score: combineRiskScore(result.hazard_score, lowerFloorVulnerability, form.afet_tipi),
      detail: "Toplam kat sayısı 2 azaltılmış senaryo.",
    },
  ];
}

function getHistoryItems() {
  try {
    return JSON.parse(window.localStorage.getItem("disasterai-history") || "[]");
  } catch {
    return [];
  }
}

const IPUCU_ANAHTARI = "disasterai.ipucu.goruldu";

function ipucuGorulduMu() {
  try {
    return window.localStorage.getItem(IPUCU_ANAHTARI) === "1";
  } catch {
    return false;
  }
}

function getInitialTheme() {
  if (typeof window === "undefined") return "light";
  return window.localStorage.getItem("disasterai-theme") || "light";
}

function MapClickHandler({ onSelect }) {
  useMapEvents({
    click(event) {
      onSelect({
        lat: event.latlng.lat,
        lon: event.latlng.lng,
      });
    },
  });
  return null;
}

function FitMap({ selectedLocation, route }) {
  const map = useMap();

  useEffect(() => {
    if (route?.safe_point && selectedLocation) {
      map.fitBounds(
        [
          [selectedLocation.lat, selectedLocation.lon],
          [route.safe_point.lat, route.safe_point.lon],
        ],
        { padding: [48, 48] }
      );
      return;
    }

    if (selectedLocation) {
      map.flyTo([selectedLocation.lat, selectedLocation.lon], 14, { duration: 0.45 });
    }
  }, [map, route, selectedLocation]);

  return null;
}

function RouteLayer({ route }) {
  if (!route?.route_geojson?.coordinates) return null;

  const positions = route.route_geojson.coordinates.map(([lon, lat]) => [lat, lon]);
  const routeHalo = {
    color: "#ffffff",
    weight: 10,
    opacity: 0.88,
    lineCap: "round",
    lineJoin: "round",
  };
  const routeLine = {
    color: "#0f766e",
    weight: 5,
    opacity: 1,
    dashArray: "10 12",
    lineCap: "round",
    lineJoin: "round",
  };

  return (
    <>
      <Pane name="route-pane" style={{ zIndex: 560 }}>
        <Polyline positions={positions} pathOptions={routeHalo} />
        <Polyline positions={positions} pathOptions={routeLine} />
      </Pane>
      <Marker position={[route.safe_point.lat, route.safe_point.lon]} icon={safeIcon}>
        <Popup>
          <strong>{route.safe_point.name}</strong>
          <br />
          Yaya rotası: {route.distance_km.toFixed(2)} km, {route.duration_min.toFixed(1)} dk
        </Popup>
      </Marker>
    </>
  );
}

function MapLegend({ disasterType }) {
  const disasterLabel = disasterOptions.find((option) => option.value === disasterType)?.label || disasterType;
  return (
    <div className="map-legend" aria-label="Risk katmanı lejantı">
      <strong>{disasterLabel} risk katmanı</strong>
      <div className="legend-swatches">
        {RISK_RENKLERI.map((color) => (
          <span key={color} style={{ background: color }} />
        ))}
      </div>
      {/* Etiketler rapordaki üç risk sınıfıyla aynı eşikleri kullanır
          (Düşük <3 · Orta 3–4 · Yüksek ≥4); renk basamakları da bu
          eşiklerde değişiyor, yoksa arayüzle rapor ayrışıyor */}
      <div className="legend-labels">
        <span>Düşük &lt;3</span>
        <span>Orta 3–4</span>
        <span>Yüksek ≥4</span>
      </div>
    </div>
  );
}

function RiskMap({
  selectedLocation,
  onSelect,
  result,
  route,
  overlayOpacity,
  setOverlayOpacity,
  theme,
  ipucuGoster,
  onIpucuKapat,
}) {
  return (
    <div className="map-shell">
      <MapContainer center={SEFERIHISAR_CENTER} zoom={13} zoomControl={false} className="map-canvas">
        <LayersControl position="topright">
          <LayersControl.BaseLayer checked={theme !== "dark"} name="Sokak">
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer checked={theme === "dark"} name="Okunur Koyu">
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              className="readable-dark-tiles"
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name="Uydu">
            <TileLayer
              attribution="Tiles &copy; Esri"
              url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name="Topoğrafya">
            <TileLayer
              attribution="Map data &copy; OpenStreetMap contributors, SRTM | Map style &copy; OpenTopoMap"
              url="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png"
            />
          </LayersControl.BaseLayer>
        </LayersControl>

        <TileLayer
          attribution=""
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}"
          opacity={0.5}
        />

        {result?.overlay_url && result?.overlay_bounds_wgs84 && (
          <ImageOverlay
            url={result.overlay_url}
            bounds={result.overlay_bounds_wgs84}
            opacity={overlayOpacity}
            zIndex={320}
          />
        )}

        {selectedLocation && (
          <>
            <Marker position={[selectedLocation.lat, selectedLocation.lon]} icon={selectedIcon}>
              <Popup>
                <strong>Seçilen Konum</strong>
                <br />
                {selectedLocation.address && (
                  <>
                    {selectedLocation.address}
                    <br />
                  </>
                )}
                {selectedLocation.lat.toFixed(5)}, {selectedLocation.lon.toFixed(5)}
                {result && (
                  <div className="popup-skor">
                    <span>
                      Toplam risk: <b>{result.risk_score.toFixed(2)} / 5</b> · {riskLabel(result.risk_score)}
                    </span>
                    <span>Bölgesel tehlike: {result.hazard_score.toFixed(2)} / 5</span>
                  </div>
                )}
              </Popup>
              <Tooltip>{result ? `Risk ${result.risk_score.toFixed(2)} / 5` : "Analiz noktası"}</Tooltip>
            </Marker>
            <Circle
              center={[selectedLocation.lat, selectedLocation.lon]}
              radius={300}
              pathOptions={{ color: "#d83a3a", fillColor: "#d83a3a", fillOpacity: 0.08, weight: 2 }}
            />
          </>
        )}

        <RouteLayer route={route} />
        <ScaleControl position="bottomright" imperial={false} maxWidth={140} />
        <MapClickHandler onSelect={onSelect} />
        <FitMap selectedLocation={selectedLocation} route={route} />
      </MapContainer>

      {/* İlk ziyaret ipucu: ilk nokta seçilince kalıcı olarak kaybolur */}
      {ipucuGoster && (
        <div className="map-ipucu" role="note" aria-label="Nasıl kullanılır">
          <ol>
            <li>Afet tipini seç</li>
            <li>Bina bilgilerini gir</li>
            <li>Haritada binanın yerini seç</li>
          </ol>
          <button type="button" className="map-ipucu-kapat" onClick={onIpucuKapat} aria-label="İpucunu kapat">
            <X size={15} />
          </button>
        </div>
      )}

      {result?.overlay_url && (
        <div className="map-opacity-control">
          <div className="map-opacity-label">
            <Layers size={15} />
            {/* Değer opaklıktır: sağa çekince renkler koyulaşır. Eski etiket
                "Saydamlık" diyordu, yani kaydırıcının yönünü ters anlatıyordu */}
            <span>Risk katmanı</span>
            <output>%{Math.round(overlayOpacity * 100)}</output>
          </div>
          <input
            aria-label="Risk katmanı görünürlüğü"
            title="Sola: altlık harita netleşir · Sağa: risk renkleri belirginleşir"
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={overlayOpacity}
            onChange={(event) => setOverlayOpacity(Number(event.target.value))}
          />
        </div>
      )}

      {result?.overlay_url && <MapLegend disasterType={result.coordinates?.afet_tipi || "DEPREM"} />}
    </div>
  );
}

function MetricCard({ label, value, suffix }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>
        {value}
        {suffix && <small>{suffix}</small>}
      </strong>
    </div>
  );
}

function AnalysisForm({
  form,
  setForm,
  selectedLocation,
  onAnalyze,
  onReset,
  onSearchPlace,
  loading,
  error,
  result,
  onRoute,
  routeLoading,
  history,
  onUseHistory,
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);

  async function submitSearch(event) {
    event.preventDefault();
    const query = searchQuery.trim();
    if (!query) return;
    setSearching(true);
    await onSearchPlace(query);
    setSearching(false);
  }

  return (
    <aside className="control-panel">
      <section className="panel-section">
        <div className="section-title">
          <Activity size={18} />
          <span>Afet Tipi</span>
        </div>
        <div className="segmented">
          {disasterOptions.map((option) => (
            <button
              key={option.value}
              className={form.afet_tipi === option.value ? "active" : ""}
              onClick={() => setForm((current) => ({ ...current, afet_tipi: option.value }))}
              type="button"
            >
              {option.label}
            </button>
          ))}
        </div>
      </section>

      <section className="panel-section">
        <div className="section-title">
          <Building2 size={18} />
          <span>Bina Bilgileri</span>
        </div>

        <label>
          Yapı Malzemesi
          <select
            value={form.malzeme_secim}
            onChange={(event) => setForm((current) => ({ ...current, malzeme_secim: Number(event.target.value) }))}
          >
            {materialOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <div className="field-grid">
          <label>
            Toplam Kat
            <input
              type="number"
              min="1"
              max="50"
              value={form.bina_kat_sayisi}
              onChange={(event) => setForm((current) => ({ ...current, bina_kat_sayisi: Number(event.target.value) }))}
            />
          </label>
          <label>
            Oturulan Kat
            <input
              type="number"
              min="0"
              max="50"
              value={form.oturulan_kat}
              onChange={(event) => setForm((current) => ({ ...current, oturulan_kat: Number(event.target.value) }))}
            />
          </label>
        </div>

        <label>
          Yapım Yılı
          <input
            type="number"
            min="1800"
            max="2026"
            value={form.yapim_yili}
            onChange={(event) => setForm((current) => ({ ...current, yapim_yili: Number(event.target.value) }))}
          />
        </label>

        <label className="check-row">
          <input
            type="checkbox"
            checked={form.asansor_var === 1}
            onChange={(event) => setForm((current) => ({ ...current, asansor_var: event.target.checked ? 1 : 0 }))}
          />
          <span>Asansör var</span>
        </label>
      </section>

      <section className="panel-section">
        <div className="section-title">
          <MapPinned size={18} />
          <span>Konum</span>
        </div>
        <form className="search-row" onSubmit={submitSearch}>
          <input
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Mahalle veya yer ara"
            aria-label="Mahalle veya yer ara"
          />
          <button type="submit" aria-label="Ara" disabled={searching || !searchQuery.trim()}>
            {searching ? <Loader2 size={16} className="spin" /> : <Search size={16} />}
          </button>
        </form>
        <div className="location-box">
          {selectedLocation ? (
            <>
              <div className="location-details">
                <strong>{selectedLocation.lat.toFixed(5)}, {selectedLocation.lon.toFixed(5)}</strong>
                <span className={selectedLocation.addressLoading ? "muted-status" : ""}>
                  {selectedLocation.addressLoading
                    ? "Adres alınıyor..."
                    : selectedLocation.address || "Mahalle/cadde bilgisi bulunamadı"}
                </span>
              </div>
              <button type="button" className="ghost-button" onClick={onReset}>
                <RotateCcw size={16} />
                Yeni nokta
              </button>
            </>
          ) : (
            <span>Haritadan bir nokta seçin.</span>
          )}
        </div>
      </section>

      {error && (
        <div className="alert error" role="alert">
          <AlertTriangle size={17} />
          <span>{error}</span>
        </div>
      )}

      {/* Dar ekranda bunun yerine alttaki sabit çubuk görünür (.mobil-eylem) */}
      <button className="primary-button panel-analiz-dugmesi" type="button" onClick={onAnalyze} disabled={loading}>
        {loading ? <Loader2 size={18} className="spin" /> : <Activity size={18} />}
        Analizi Başlat
      </button>

      {selectedLocation && (
        <button className="secondary-button" type="button" onClick={onRoute} disabled={routeLoading}>
          {routeLoading ? <Loader2 size={18} className="spin" /> : <Navigation size={18} />}
          Toplanma Alanını Bul
        </button>
      )}

      {history.length > 0 && (
        <section className="panel-section history-section">
          <div className="section-title">
            <History size={18} />
            <span>Analiz Geçmişi</span>
          </div>
          <div className="history-list">
            {history.slice(0, 3).map((item) => (
              <button key={item.id} type="button" onClick={() => onUseHistory(item)}>
                <span>{item.disasterLabel}</span>
                <strong>{item.score.toFixed(2)} / 5</strong>
                <small>{item.lat.toFixed(4)}, {item.lon.toFixed(4)}</small>
              </button>
            ))}
          </div>
        </section>
      )}
    </aside>
  );
}

function RiskGauge({ score, tone }) {
  // Yarım halka: r=52, yarım çevre = PI * 52
  const yarimCevre = Math.PI * 52;
  const oran = score ? Math.min(1, Math.max(0, (score - 1) / 4)) : 0;
  return (
    <div className={`risk-gauge ${tone}`}>
      <svg viewBox="0 0 120 68" role="img" aria-label={`Risk skoru ${score ? score.toFixed(2) : "-"} / 5`}>
        <path
          d="M 8 60 A 52 52 0 0 1 112 60"
          fill="none"
          className="gauge-track"
          strokeWidth="11"
          strokeLinecap="round"
        />
        {score ? (
          <path
            d="M 8 60 A 52 52 0 0 1 112 60"
            fill="none"
            className="gauge-value"
            strokeWidth="11"
            strokeLinecap="round"
            strokeDasharray={`${yarimCevre * oran} ${yarimCevre}`}
          />
        ) : null}
      </svg>
      <div className="gauge-reading">
        <strong>{score ? score.toFixed(2) : "--"}</strong>
        <span>/ 5.0</span>
      </div>
    </div>
  );
}

function FactorBars({ dokum }) {
  const entries = Object.entries(dokum || {}).sort((a, b) => b[1].katki - a[1].katki);
  if (!entries.length) return null;
  const maxKatki = Math.max(...entries.map(([, v]) => v.katki), 0.001);

  return (
    <section className="panel-section compact">
      <div className="section-title">
        <Layers size={18} />
        <span>Faktör Katkıları</span>
      </div>
      <div className="factor-bars">
        {entries.map(([key, value]) => (
          <div className="factor-row" key={key}>
            <div className="factor-meta">
              <span>{FAKTOR_ETIKETLERI[key] || key.replaceAll("_", " ")}</span>
              <small>
                {value.puan.toFixed(1)}/5 × ağırlık {value.agirlik.toFixed(2)}
              </small>
            </div>
            <div className="factor-track">
              <span style={{ width: `${(value.katki / maxKatki) * 100}%` }} />
            </div>
            <strong>{value.katki.toFixed(2)}</strong>
          </div>
        ))}
      </div>
      <p className="factor-footnote">Çubuklar bölgesel tehlike skoruna katkıyı gösterir (puan × ağırlık).</p>
    </section>
  );
}

function ResultsSkeleton() {
  return (
    <aside className="result-panel" aria-busy="true" aria-label="Analiz hesaplanıyor">
      <div className="skeleton skeleton-summary" />
      <div className="metrics-grid">
        <div className="skeleton skeleton-metric" />
        <div className="skeleton skeleton-metric" />
      </div>
      <div className="skeleton skeleton-block" />
      <div className="skeleton skeleton-block tall" />
    </aside>
  );
}

function ResultsPanel({ result, form, selectedLocation, route, onPrintReport, loading }) {
  const tone = riskTone(result?.risk_score);
  const explanation = buildRiskExplanation(result, form);
  const scenarios = buildScenarioComparison(result, form);

  if (loading) return <ResultsSkeleton />;

  return (
    <aside className="result-panel">
      <section className={`risk-summary ${tone}`}>
        <div className="risk-summary-head">
          <span>Toplam Risk</span>
          <b>{riskLabel(result?.risk_score)}</b>
        </div>
        <RiskGauge score={result?.risk_score} tone={tone} />
      </section>

      <div className="metrics-grid">
        <MetricCard label="Bölgesel Tehlike" value={result ? result.hazard_score.toFixed(2) : "--"} suffix="/5" />
        <MetricCard label="Bina Hassasiyeti" value={result ? result.vulnerability_score.toFixed(2) : "--"} suffix="/5" />
      </div>

      <section className="panel-section compact">
        <div className="section-title">
          <ShieldCheck size={18} />
          <span>Değerlendirme</span>
        </div>
        <p className="advice-text">{result?.tavsiye || "Analiz sonucu burada görünecek."}</p>
      </section>

      {result && <FactorBars dokum={result.faktor_dokumu} />}

      {result && (
        <section className="panel-section compact">
          <div className="section-title">
            <Info size={18} />
            <span>Skor Neden Böyle?</span>
          </div>
          <ul className="explain-list">
            {explanation.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </section>
      )}

      {result && (
        <section className="panel-section compact">
          <div className="section-title">
            <Activity size={18} />
            <span>Senaryo Karşılaştırma</span>
          </div>
          <div className="scenario-grid">
            {scenarios.map((scenario) => (
              <div className="scenario-card" key={scenario.label}>
                <span>{scenario.label}</span>
                <strong>{scenario.score?.toFixed(2)} / 5</strong>
                <small>{scenario.detail}</small>
              </div>
            ))}
          </div>
        </section>
      )}

      {route && (
        <section className="panel-section compact">
          <div className="section-title">
            <Navigation size={18} />
            <span>Yürüyüş Rotası</span>
          </div>
          <p className="route-name">{route.safe_point.name}</p>
          <div className="route-stats">
            <span>Yürüyüş: {route.distance_km.toFixed(2)} km</span>
            <span>Süre: {route.duration_min.toFixed(1)} dk</span>
            {route.direct_distance_km && <span>Kuş uçuşu: {route.direct_distance_km.toFixed(2)} km</span>}
          </div>
          {route.route_note && <p className="route-note">{route.route_note}</p>}
        </section>
      )}

      {selectedLocation && (
        <section className="panel-section compact">
          <div className="section-title">
            <Clock size={18} />
            <span>Acil Plan Kartı</span>
          </div>
          <div className="plan-card">
            <p>Konum: {selectedLocation.lat.toFixed(5)}, {selectedLocation.lon.toFixed(5)}</p>
            <p>Toplanma: {route?.safe_point?.name || "Henüz rota seçilmedi"}</p>
            <p>Yürüme: {route ? `${route.distance_km.toFixed(2)} km / ${route.duration_min.toFixed(1)} dk` : "Toplanma alanı butonuyla hesaplanır"}</p>
          </div>
        </section>
      )}

      {result && (
        <button className="report-button" type="button" onClick={onPrintReport}>
          <Download size={18} />
          Raporu PDF Olarak Al
        </button>
      )}
    </aside>
  );
}

const CHAT_ONERILERI = [
  "Risk skorum ne anlama geliyor?",
  "Şimdi ne yapmalıyım?",
  "Skoru nasıl düşürebilirim?",
];

function ChatPanel({ result, form, onClose, surukleProps }) {
  const sessionId = useMemo(() => {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    return String(Date.now());
  }, []);
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Analizden sonra risk skorunu birlikte yorumlayabiliriz." },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  function submitMessage(event) {
    event.preventDefault();
    sendMessage(input);
  }

  async function sendMessage(rawText) {
    const text = (rawText || "").trim();
    if (!text || loading) return;

    const context = result
      ? {
          afet_tipi: result.coordinates?.afet_tipi || "Belirtilmemiş",
          toplam_risk_skoru: result.risk_score,
          bolgesel_tehlike_skoru: result.hazard_score,
          bina_hassasiyet_skoru: result.vulnerability_score,
          tavsiye: result.tavsiye,
          malzeme: materialOptions.find((option) => option.value === form.malzeme_secim)?.label || "Belirtilmemiş",
          bina_kat_sayisi: form.bina_kat_sayisi,
          oturulan_kat: form.oturulan_kat,
          yapim_yili: form.yapim_yili,
          asansor_var: form.asansor_var,
        }
      : {};

    setMessages((current) => [...current, { role: "user", text }, { role: "assistant", text: "" }]);
    setInput("");
    setLoading(true);

    try {
      const response = await fetch(apiUrl("/api/chat"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, context, session_id: sessionId }),
      });

      if (!response.ok) throw new Error("Asistan yanıtı alınamadı.");

      const reader = response.body?.getReader();
      if (!reader) {
        const fallback = await response.text();
        setMessages((current) => current.map((message, index) => (
          index === current.length - 1 ? { ...message, text: fallback } : message
        )));
        return;
      }

      const decoder = new TextDecoder();
      let reply = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        reply += decoder.decode(value, { stream: true });
        setMessages((current) => current.map((message, index) => (
          index === current.length - 1 ? { ...message, text: reply } : message
        )));
      }
    } catch (error) {
      setMessages((current) => current.map((message, index) => (
        index === current.length - 1 ? { ...message, text: error.message } : message
      )));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="chat-panel">
      <div
        className={`section-title${surukleProps ? " chat-drag-handle" : ""}`}
        {...(surukleProps || {})}
      >
        <MessageCircle size={18} />
        <span>Analiz Asistanı</span>
        {result && <span className="chat-context-badge">Analiz bağlamı aktif</span>}
        {/* Tutamağın görünür işareti: başlığın sürüklenebildiği ancak
            böyle anlaşılıyor (12.09 — Ayşe "taşınmıyor" dedi, meğer
            başlığın ortasını kapatma düğmesi kaplıyormuş) */}
        {surukleProps && (
          <span className="chat-grip" aria-hidden="true">
            <GripHorizontal size={15} />
          </span>
        )}
        {onClose && (
          <button type="button" className="chat-close" onClick={onClose} aria-label="Asistanı kapat">
            <X size={17} />
          </button>
        )}
      </div>
      <div className="chat-messages">
        {messages.map((message, index) => (
          <div className={`chat-row ${message.role}`} key={`${message.role}-${index}`}>
            {message.role === "assistant" && (
              <span className="chat-avatar" aria-hidden="true">
                <Bot size={15} />
              </span>
            )}
            <div className={`chat-message ${message.role}`}>
              {message.text ? (
                message.text
              ) : (
                <span className="typing-dots" aria-label="Asistan yazıyor">
                  <i /><i /><i />
                </span>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      {messages.length <= 1 && (
        <div className="chat-suggestions">
          {CHAT_ONERILERI.map((oneri) => (
            <button key={oneri} type="button" onClick={() => sendMessage(oneri)} disabled={loading}>
              {oneri}
            </button>
          ))}
        </div>
      )}
      <form onSubmit={submitMessage} className="chat-form">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Sorunu yaz..."
          aria-label="Asistana mesaj"
        />
        <button type="submit" disabled={loading || !input.trim()} aria-label="Gönder">
          {loading ? <Loader2 size={17} className="spin" /> : <Send size={17} />}
        </button>
      </form>
    </section>
  );
}

// Asistan balonunun taşınan konumu tarayıcıda saklanır; kullanıcı balonu
// haritanın önünden çekip bıraktıysa her analizde aynı yeri bulmalı.
// Saklanan şey BALONUN (yuvarlak düğmenin) sol üst köşesi — sohbet paneli
// konumunu balondan türetir, yani ikisi hiç ayrılmaz.
const ASISTAN_KONUM_ANAHTARI = "disasterai.asistan.konum";
const BALON_KENAR_BOSLUGU = 8;
const BALON_PANEL_ARASI = 12;
const SURUKLEME_ESIGI = 4;   // bu kadar piksel altındaki hareket tıklama sayılır

function asistanKonumuOku() {
  try {
    const ham = window.localStorage.getItem(ASISTAN_KONUM_ANAHTARI);
    if (!ham) return null;
    const veri = JSON.parse(ham);
    if (Number.isFinite(veri?.x) && Number.isFinite(veri?.y)) {
      return { x: veri.x, y: veri.y };
    }
  } catch {
    // Gizli sekmede veya depolama kapalıyken varsayılan köşeye düşeriz
  }
  return null;
}

// Balon pencere dışına taşmasın: küçültülen pencerede kaybolmaması için
// her taşımada ve pencere boyutu değişince yeniden sınırlanır.
function balonKonumunuSinirla(konum, balon) {
  const bosluk = BALON_KENAR_BOSLUGU;
  const genislik = balon?.offsetWidth || 56;
  const yukseklik = balon?.offsetHeight || 56;
  const enBuyukX = Math.max(bosluk, window.innerWidth - genislik - bosluk);
  const enBuyukY = Math.max(bosluk, window.innerHeight - yukseklik - bosluk);
  return {
    x: Math.round(Math.min(Math.max(bosluk, konum.x), enBuyukX)),
    y: Math.round(Math.min(Math.max(bosluk, konum.y), enBuyukY)),
  };
}

// Panel balona kenetli: sağ kenarları hizalı, panel balonun üstünde durur.
// Yukarıda yer kalmadıysa altına geçer, o da olmazsa ekrana sığdırılır.
function panelKonumunuHesapla(balonKonumu, balon, panel) {
  const bosluk = BALON_KENAR_BOSLUGU;
  const balonGenislik = balon?.offsetWidth || 56;
  const balonYukseklik = balon?.offsetHeight || 56;
  const panelGenislik = panel?.offsetWidth || 384;
  const panelYukseklik = panel?.offsetHeight || 540;

  let x = balonKonumu.x + balonGenislik - panelGenislik;
  let y = balonKonumu.y - panelYukseklik - BALON_PANEL_ARASI;
  if (y < bosluk) {
    const altta = balonKonumu.y + balonYukseklik + BALON_PANEL_ARASI;
    if (altta + panelYukseklik + bosluk <= window.innerHeight) {
      y = altta;
    } else {
      // Balon ekranın ortasındaysa ne üstte ne altta yer var; panel balonun
      // üstüne binmesin diye yanına geçer, dikeyde balonla ortalanır.
      const solda = balonKonumu.x - BALON_PANEL_ARASI - panelGenislik;
      const sagda = balonKonumu.x + balonGenislik + BALON_PANEL_ARASI;
      if (solda >= bosluk) {
        x = solda;
      } else if (sagda + panelGenislik + bosluk <= window.innerWidth) {
        x = sagda;
      }
      y = balonKonumu.y + balonYukseklik / 2 - panelYukseklik / 2;
    }
  }
  const enBuyukX = Math.max(bosluk, window.innerWidth - panelGenislik - bosluk);
  const enBuyukY = Math.max(bosluk, window.innerHeight - panelYukseklik - bosluk);
  return {
    x: Math.min(Math.max(bosluk, x), enBuyukX),
    y: Math.min(Math.max(bosluk, y), enBuyukY),
  };
}

function ChatWidget({ result, form, sifirlaAnahtari }) {
  const [open, setOpen] = useState(false);
  const [konum, setKonum] = useState(asistanKonumuOku);        // balonun konumu
  const [panelKonum, setPanelKonum] = useState(null);          // balondan türetilir
  const [surukleniyor, setSurukleniyor] = useState(false);
  const balonRef = useRef(null);
  const panelRef = useRef(null);
  const kavramaRef = useRef(null);   // imleç ile balonun sol üst köşesi arasındaki fark
  const sonKonumRef = useRef(konum);
  const tasindiRef = useRef(false);  // sürükleme oldu mu — tıklamadan ayırmak için

  // Panel her zaman balonun bulunduğu yere yapışsın: balon kıpırdayınca,
  // panel açılınca ve pencere boyutu değişince yeniden hesaplanır.
  useLayoutEffect(() => {
    if (!konum) {
      setPanelKonum(null);
      return;
    }
    setPanelKonum(panelKonumunuHesapla(konum, balonRef.current, panelRef.current));
  }, [konum, open]);

  useEffect(() => {
    function pencereDegisti() {
      setKonum((mevcut) => {
        if (!mevcut) return mevcut;
        const sinirli = balonKonumunuSinirla(mevcut, balonRef.current);
        sonKonumRef.current = sinirli;
        return sinirli;
      });
    }
    window.addEventListener("resize", pencereDegisti);
    return () => window.removeEventListener("resize", pencereDegisti);
  }, []);

  function konumuKaydet() {
    try {
      if (sonKonumRef.current) {
        window.localStorage.setItem(
          ASISTAN_KONUM_ANAHTARI,
          JSON.stringify(sonKonumRef.current),
        );
      }
    } catch {
      // depolama yoksa konum yalnızca bu oturumda yaşar
    }
  }

  // Hem balondan hem panelin başlık çubuğundan aynı sürükleme çalışır:
  // imleçle balon arasındaki fark korunduğu için panelden tutunca balon
  // imlecin altına zıplamaz, ikisi birlikte kayar.
  function surukleBaslat(olay) {
    if (olay.button !== 0) return;                 // yalnızca sol tuş
    if (olay.target.closest("button") && olay.currentTarget.tagName !== "BUTTON") {
      return;                                      // kapat düğmesi taşımayı tetiklemesin
    }
    const kutu = balonRef.current?.getBoundingClientRect();
    if (!kutu) return;
    kavramaRef.current = {
      dx: olay.clientX - kutu.left,
      dy: olay.clientY - kutu.top,
      baslangicX: olay.clientX,
      baslangicY: olay.clientY,
    };
    tasindiRef.current = false;
    olay.currentTarget.setPointerCapture(olay.pointerId);
  }

  function surukleHareket(olay) {
    const kavrama = kavramaRef.current;
    if (!kavrama) return;
    if (!tasindiRef.current) {
      const yatay = Math.abs(olay.clientX - kavrama.baslangicX);
      const dikey = Math.abs(olay.clientY - kavrama.baslangicY);
      if (yatay < SURUKLEME_ESIGI && dikey < SURUKLEME_ESIGI) return;
      tasindiRef.current = true;
      setSurukleniyor(true);
    }
    const yeni = balonKonumunuSinirla(
      { x: olay.clientX - kavrama.dx, y: olay.clientY - kavrama.dy },
      balonRef.current,
    );
    sonKonumRef.current = yeni;
    setKonum(yeni);
    olay.preventDefault();
  }

  function surukleBitir(olay) {
    if (!kavramaRef.current) return;
    kavramaRef.current = null;
    try {
      olay.currentTarget.releasePointerCapture(olay.pointerId);
    } catch {
      // yakalama zaten bırakılmışsa önemli değil
    }
    if (tasindiRef.current) {
      setSurukleniyor(false);
      konumuKaydet();
    }
  }

  // Çift tıklama ikisini birden sağ alt köşedeki varsayılan yerine gönderir
  function konumuSifirla() {
    kavramaRef.current = null;
    sonKonumRef.current = null;
    tasindiRef.current = false;
    setSurukleniyor(false);
    setKonum(null);
    try {
      window.localStorage.removeItem(ASISTAN_KONUM_ANAHTARI);
    } catch {
      // yoksay
    }
  }

  // Balonu sürükledikten sonra gelen click paneli açıp kapatmasın.
  // Klavyeyle (Enter/Space) gelen click'te sürükleme olmadığı için bu
  // koruma devreye girmez.
  function balonaTiklandi() {
    if (tasindiRef.current) {
      tasindiRef.current = false;
      return;
    }
    setOpen((current) => !current);
  }

  const surukleProps = {
    onPointerDown: surukleBaslat,
    onPointerMove: surukleHareket,
    onPointerUp: surukleBitir,
    onPointerCancel: surukleBitir,
  };

  const panelStil = panelKonum
    ? { left: `${panelKonum.x}px`, top: `${panelKonum.y}px`, right: "auto", bottom: "auto",
        transformOrigin: "center" }
    : undefined;
  const balonStil = konum
    ? { left: `${konum.x}px`, top: `${konum.y}px`, right: "auto", bottom: "auto" }
    : undefined;

  return (
    <>
      <div
        ref={panelRef}
        className={`chat-popup ${open ? "open" : ""} ${surukleniyor ? "surukleniyor" : ""}`}
        style={panelStil}
        aria-hidden={!open}
        // Kapalı panel görünmüyor ama Tab tuşu içindeki düğmelere gidiyordu
        inert={!open}
      >
        {/* key değişince ChatPanel yeniden kurulur => sohbet temizlenir.
            Yeni analiz eski sohbetin bağlamını geçersiz kılıyor. */}
        <ChatPanel key={sifirlaAnahtari} result={result} form={form}
                   onClose={() => setOpen(false)}
                   surukleProps={{
                     ...surukleProps,
                     onDoubleClick: konumuSifirla,
                     title: "Sürükleyerek taşıyın — balon da birlikte gelir, çift tıklama köşeye geri alır",
                   }} />
      </div>
      <button
        ref={balonRef}
        className={`chat-fab${surukleniyor ? " surukleniyor" : ""}`}
        type="button"
        style={balonStil}
        {...surukleProps}
        onClick={balonaTiklandi}
        aria-label={open ? "Asistanı kapat" : "Analiz asistanını aç"}
        aria-expanded={open}
        title="Tıkla: asistanı aç/kapat — sürükle: balonu ve paneli birlikte taşı"
      >
        {open ? <X size={23} /> : <MessageCircle size={23} />}
        {!open && result && <span className="chat-fab-dot" aria-hidden="true" />}
      </button>
    </>
  );
}

function InfoPage({ type }) {
  const isMethod = type === "method";
  const [yontem, setYontem] = useState(null);
  const [yontemHata, setYontemHata] = useState(false);

  useEffect(() => {
    if (!isMethod) return undefined;
    let iptal = false;
    fetch(apiUrl("/api/yontem"))
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((veri) => {
        if (!iptal) setYontem(veri);
      })
      .catch(() => {
        if (!iptal) setYontemHata(true);
      });
    return () => {
      iptal = true;
    };
  }, [isMethod]);

  const faktorSirasi = useMemo(() => {
    if (!yontem) return [];
    const toplam = {};
    Object.values(yontem.agirliklar).forEach((set) => {
      Object.entries(set).forEach(([f, a]) => {
        toplam[f] = (toplam[f] || 0) + a;
      });
    });
    return Object.keys(toplam).sort((a, b) => toplam[b] - toplam[a]);
  }, [yontem]);

  const yuzde = (deger) => `%${Math.round(deger * 100)}`;

  return (
    <main className="content-page">
      <section>
        <div className="section-title">
          {isMethod ? <FileText size={20} /> : <Info size={20} />}
          <span>{isMethod ? "Yöntem" : "Hakkımızda"}</span>
        </div>
        {isMethod ? (
          <>
            <h1>CBS Tabanlı Çok Kriterli Risk Analizi</h1>
            <p>
              Sistem; fay hattı uzaklığı, litoloji, eğim, akarsu uzaklığı ve arazi kullanımı katmanlarını afet türüne
              göre ağırlıklandırır. Bina yaşı, taşıyıcı sistem ve kat bilgisi yapısal hassasiyet skoruna dönüşür.
              Aşağıdaki değerler, arayüzde yazılı sabitler değil; analizi yapan sunucudan o an okunan gerçek
              parametrelerdir.
            </p>

            {yontemHata && (
              <p className="method-note">
                Sunucudan yöntem verisi okunamadı. Sayısal döküm için sunucunun çalışıyor olması gerekir.
              </p>
            )}

            {yontem && (
              <>
                <h2 className="method-heading">
                  <Layers size={17} /> Faktör ağırlıkları
                </h2>
                <p className="method-sub">
                  Etkin ağırlık seti: <strong>{yontem.agirlik_seti}</strong> — literatürdeki yayımlanmış AHP
                  çalışmalarının bildirdiği aralıkların ortasına oturtulmuş, beş faktöre normalize edilmiş settir.
                  Aynı faktör afet tipine göre farklı ağırlık alır.
                </p>
                <div className="method-table-wrap">
                  <table className="method-table">
                    <thead>
                      <tr>
                        <th>Faktör</th>
                        {Object.keys(yontem.agirliklar).map((afet) => (
                          <th key={afet}>{yontem.afet_adlari[afet] || afet}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {faktorSirasi.map((faktor) => (
                        <tr key={faktor}>
                          <td>{yontem.faktor_adlari[faktor] || faktor}</td>
                          {Object.keys(yontem.agirliklar).map((afet) => (
                            <td key={afet} className="method-num">
                              {yuzde(yontem.agirliklar[afet][faktor] || 0)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="method-sub">
                  Bölgesel tehlike skoru ile bina hassasiyet skoru, deprem için{" "}
                  {yuzde(yontem.bina_agirliklari.DEPREM.bolgesel)} / {yuzde(yontem.bina_agirliklari.DEPREM.bina)},
                  diğer afetler için {yuzde(yontem.bina_agirliklari.DIGER.bolgesel)} /{" "}
                  {yuzde(yontem.bina_agirliklari.DIGER.bina)} oranıyla birleştirilir.
                </p>

                <h2 className="method-heading">
                  <BookOpen size={17} /> Her değerin dayanağı
                </h2>
                <p className="method-sub">
                  Yeniden sınıflandırma tablolarındaki {yontem.dayanak.toplam} satırın her biri güven etiketi taşır;
                  kaynakça {yontem.kaynak_sayisi} kayıttan oluşur.
                </p>
                <div className="method-badges">
                  {Object.entries(yontem.dayanak.sayilar).map(([kod, adet]) => (
                    <div key={kod} className={`method-badge badge-${kod}`}>
                      <span className="badge-kod">[{kod}]</span>
                      <span className="badge-adet">{adet} satır</span>
                      <span className="badge-aciklama">{yontem.dayanak.aciklama[kod]}</span>
                    </div>
                  ))}
                </div>

                {yontem.duyarlilik.length > 0 && (
                  <>
                    <h2 className="method-heading">
                      <Activity size={17} /> Ağırlık seçimi sonucu ne kadar değiştiriyor?
                    </h2>
                    <p className="method-sub">
                      Projenin ilk sürümündeki ağırlıklarla literatür tabanlı ağırlıkların ürettiği haritalar üç risk
                      sınıfı üzerinden Cohen&apos;s kappa ile karşılaştırıldı. Üç afette de &quot;iyi uyum&quot; bandı:
                      harita, ağırlık seçimine görece dayanıklıdır.
                    </p>
                    <div className="method-table-wrap">
                      <table className="method-table">
                        <thead>
                          <tr>
                            <th>Afet</th>
                            <th>Ort. mutlak fark</th>
                            <th>Sınıf değişimi</th>
                            <th>Cohen&apos;s kappa</th>
                          </tr>
                        </thead>
                        <tbody>
                          {yontem.duyarlilik.map((s) => (
                            <tr key={s.afet}>
                              <td>{s.afet}</td>
                              <td className="method-num">{s.ort_mutlak_fark.toFixed(3)}</td>
                              <td className="method-num">{s.sinif_degisimi}</td>
                              <td className="method-num">{s.kappa.toFixed(3)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}

                <h2 className="method-heading">
                  <Database size={17} /> Veri ve koordinat sistemi
                </h2>
                <ul className="method-list">
                  <li>
                    Vektör katmanlar: {yontem.katmanlar.join(", ")} — coğrafi veri tabanından okunur, simüle edilmez.
                  </li>
                  <li>Sayısal yükseklik modeli: {yontem.dem}</li>
                  <li>
                    Analiz koordinat sistemi: {yontem.analiz_crs} (ED50 / UTM 35N), hücre boyutu {yontem.piksel_m} m.
                  </li>
                  <li>Risk skoru, haritada seçtiğiniz koordinattan örneklenir; çalışma alanı dışı istekler reddedilir.</li>
                </ul>
              </>
            )}

            <div className="method-limit">
              <AlertTriangle size={17} />
              <div>
                <strong>Sınırlılıklar.</strong> Sonuçlar karar destek amaçlıdır; resmî hasar tespiti, zemin etüdü veya
                mühendislik raporu yerine geçmez. Yer ivmesi (PGA) ve yeraltı su seviyesi katmanları temin
                edilemediğinden ağırlıklar kalan beş faktöre dağıtılmıştır. Bina bilgisi kullanıcı beyanına dayanır.
              </div>
            </div>
          </>
        ) : (
          <>
            <h1>DisasterAI Risk Analizi</h1>
            <p className="about-support">
              Bu çalışma <strong>TÜBİTAK 2209-A Üniversite Öğrencileri Araştırma Projeleri Destekleme Programı</strong>{" "}
              kapsamında desteklenmektedir.
            </p>
            <p>
              <strong>Proje başlığı:</strong> Coğrafi Bilgi Sistemleri ve Büyük Dil Modelleri ile Kişiselleştirilmiş
              Afet Risk İletişiminin Geliştirilmesi. Pilot bölge: İzmir / Seferihisar.
            </p>
            <p>
              DisasterAI, CBS&apos;nin ürettiği nicel afet risk verisini vatandaşın anlayabileceği, eyleme yönelik ve
              panik yaratmayan doğal dile çeviren akademik bir karar destek uygulamasıdır. Aynı mekânsal veriden
              bilgilendirici, eyleme yönelik ve yatıştırıcı tonlarda açıklama üretebilir; üretilen her metindeki sayı,
              CBS çıktısıyla otomatik karşılaştırılır.
            </p>
            <div className="method-grid">
              <div>
                <h3>Proje yürütücüsü</h3>
                <p>Ayşe Çetin — Pamukkale Üniversitesi, Yönetim Bilişim Sistemleri</p>
              </div>
              <div>
                <h3>Akademik danışman</h3>
                <p>Mehmet Ulaş Koyuncuoğlu — Pamukkale Üniversitesi</p>
              </div>
              <div>
                <h3>Teknoloji</h3>
                <p>Python, FastAPI, GeoPandas/Fiona/Shapely, Leaflet, React ve ince ayarlı Türkçe dil modeli.</p>
              </div>
              <div>
                <h3>Kullanım amacı</h3>
                <p>Akademik araştırma ve farkındalık. Resmî afet yönlendirmesi için AFAD kaynaklarını esas alın.</p>
              </div>
            </div>
          </>
        )}
      </section>
    </main>
  );
}

export default function App() {
  const [theme, setTheme] = useState(getInitialTheme);
  const [view, setView] = useState("analysis");
  const [selectedLocation, setSelectedLocation] = useState(null);
  const [result, setResult] = useState(null);
  const [route, setRoute] = useState(null);
  const [history, setHistory] = useState(getHistoryItems);
  const [overlayOpacity, setOverlayOpacity] = useState(0.65);
  const [loading, setLoading] = useState(false);
  const [routeLoading, setRouteLoading] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    afet_tipi: "DEPREM",
    malzeme_secim: 1,
    bina_kat_sayisi: 5,
    oturulan_kat: 2,
    yapim_yili: 2000,
    asansor_var: 0,
  });
  const addressRequestId = useRef(0);
  const [modelBilgisi, setModelBilgisi] = useState(null);
  // Her yeni analizde artar; sohbet balonunu sıfırlamak için kullanılır
  const [analizSayaci, setAnalizSayaci] = useState(0);
  const [ipucuAcik, setIpucuAcik] = useState(() => !ipucuGorulduMu());
  const sonucaKaydirRef = useRef(false);

  // Dar ekranda sonuç haritanın altında kalıp fark edilmiyordu. Kaydırma
  // render bittikten sonra yapılır: geçmiş listesine eklenen satır formu
  // uzatıyor, önceden hesaplanan hedef yarım kalıyordu.
  useEffect(() => {
    if (!result || !sonucaKaydirRef.current) return;
    sonucaKaydirRef.current = false;
    if (window.matchMedia("(max-width: 820px)").matches) {
      document.querySelector(".result-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [result]);

  function ipucuKapat() {
    setIpucuAcik(false);
    try {
      window.localStorage.setItem(IPUCU_ANAHTARI, "1");
    } catch {
      // depolama yoksa ipucu bir sonraki ziyarette yeniden görünür
    }
  }

  // Aktif BDM sağlayıcısını göster: İP2'de eğitilen yerel model mi, API mi?
  useEffect(() => {
    fetch(apiUrl("/api/health"))
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setModelBilgisi({ saglayici: d.model_saglayici, ad: d.model_adi }))
      .catch(() => setModelBilgisi(null));
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem("disasterai-theme", theme);
  }, [theme]);

  function toggleTheme() {
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  }

  function resetLocation() {
    addressRequestId.current += 1;
    setSelectedLocation(null);
    setResult(null);
    setRoute(null);
    setError("");
    setAnalizSayaci((n) => n + 1);
  }

  async function enrichLocationAddress(location, requestId) {
    try {
      const reverseUrl = new URL("https://nominatim.openstreetmap.org/reverse");
      reverseUrl.searchParams.set("format", "jsonv2");
      reverseUrl.searchParams.set("lat", String(location.lat));
      reverseUrl.searchParams.set("lon", String(location.lon));
      reverseUrl.searchParams.set("zoom", "18");
      reverseUrl.searchParams.set("addressdetails", "1");
      reverseUrl.searchParams.set("accept-language", "tr");

      const response = await fetch(reverseUrl.toString(), { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("Adres alınamadı.");
      const data = await response.json();
      const address = formatAddressLine(data);

      if (addressRequestId.current !== requestId) return;
      setSelectedLocation((current) => {
        if (!current || current.lat !== location.lat || current.lon !== location.lon) return current;
        return { ...current, address, addressLoading: false };
      });
    } catch {
      if (addressRequestId.current !== requestId) return;
      setSelectedLocation((current) => {
        if (!current || current.lat !== location.lat || current.lon !== location.lon) return current;
        return { ...current, address: "", addressLoading: false };
      });
    }
  }

  function handleMapSelect(location, address = "") {
    const normalizedLocation = {
      lat: Number(location.lat),
      lon: Number(location.lon),
      address,
      addressLoading: !address,
    };
    const requestId = addressRequestId.current + 1;
    addressRequestId.current = requestId;
    if (ipucuAcik) ipucuKapat();
    setSelectedLocation(normalizedLocation);
    setResult(null);
    setRoute(null);
    setError("");
    if (!address) enrichLocationAddress(normalizedLocation, requestId);
  }

  async function searchPlace(query) {
    setError("");
    try {
      const searchUrl = new URL("https://nominatim.openstreetmap.org/search");
      searchUrl.searchParams.set("format", "json");
      searchUrl.searchParams.set("limit", "1");
      searchUrl.searchParams.set("countrycodes", "tr");
      searchUrl.searchParams.set("q", `${query} İzmir Türkiye`);
      const response = await fetch(searchUrl.toString(), { headers: { Accept: "application/json" } });
      const data = await response.json();
      if (!data.length) throw new Error("Aranan yer bulunamadı.");
      handleMapSelect(
        { lat: Number(data[0].lat), lon: Number(data[0].lon) },
        formatAddressLine(data[0])
      );
    } catch (searchError) {
      setError(searchError.message || "Yer araması yapılamadı.");
    }
  }

  function saveHistoryItem(analysisResult, location) {
    const item = {
      id: String(Date.now()),
      createdAt: new Date().toLocaleString("tr-TR"),
      disasterLabel: disasterOptions.find((option) => option.value === form.afet_tipi)?.label || form.afet_tipi,
      score: analysisResult.risk_score,
      lat: location.lat,
      lon: location.lon,
      address: location.address || "",
      form,
      result: analysisResult,
    };
    const nextHistory = [item, ...history.filter((entry) => entry.id !== item.id)].slice(0, 8);
    setHistory(nextHistory);
    window.localStorage.setItem("disasterai-history", JSON.stringify(nextHistory));
  }

  function useHistoryItem(item) {
    setForm(item.form);
    handleMapSelect({ lat: item.lat, lon: item.lon }, item.address || "");
    setResult(item.result);
    setAnalizSayaci((n) => n + 1);
    setRoute(null);
    setError("");
  }

  function validate() {
    if (!selectedLocation) return "Lütfen haritadan bir konum seçin.";
    if (form.oturulan_kat > form.bina_kat_sayisi) return "Oturulan kat toplam kat sayısından büyük olamaz.";
    if (form.malzeme_secim === 2 && form.bina_kat_sayisi > 3) return "Yığma binalar için kat sayısı 3'ü aşmamalı.";
    return "";
  }

  async function runAnalysis() {
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);
    setError("");
    setRoute(null);

    try {
      const response = await fetch(apiUrl("/api/analysis"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          lat: selectedLocation.lat,
          lon: selectedLocation.lon,
        }),
      });

      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || "Analiz sırasında hata oluştu.");
      }

      const data = await response.json();
      const analysisResult = { ...data, coordinates: { ...data.coordinates, afet_tipi: form.afet_tipi } };
      setResult(analysisResult);
      setAnalizSayaci((n) => n + 1);   // sohbeti temizle: bağlam değişti
      saveHistoryItem(analysisResult, selectedLocation);
      sonucaKaydirRef.current = true;
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function requestRoute() {
    if (!selectedLocation) return;

    setRouteLoading(true);
    setError("");

    try {
      const response = await fetch(apiUrl("/api/evacuation-route"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(selectedLocation),
      });

      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || "Toplanma alanı bulunamadı.");
      }

      setRoute(await response.json());
    } catch (routeError) {
      setError(routeError.message);
    } finally {
      setRouteLoading(false);
    }
  }

  function printReport() {
    if (!result || !selectedLocation) return;
    const e = htmlKacis;
    const afetAdi = disasterOptions.find((option) => option.value === form.afet_tipi)?.label || form.afet_tipi;
    const tarih = new Date();
    const tarihMetni = tarih.toLocaleString("tr-TR", { dateStyle: "long", timeStyle: "short" });
    // Tarayıcının "PDF olarak kaydet" penceresi dosya adını <title>'dan alır
    const dosyaAdi = `DisasterAI Risk Raporu - ${afetAdi} - ${tarih.toISOString().slice(0, 10)}`;
    const seviyeRengi = { high: "#c93636", medium: "#c2410c", low: "#15803d" }[riskTone(result.risk_score)] || "#475569";
    const bolgeselPay = form.afet_tipi === "DEPREM" ? 60 : 80;
    const km = (metre) => `${(metre / 1000).toFixed(2)} km`;

    const binaSatirlari = [
      ["Yapı malzemesi", getMaterialLabel(form.malzeme_secim)],
      ["Toplam kat", form.bina_kat_sayisi],
      ["Oturulan kat", Number(form.oturulan_kat) === 0 ? "Zemin" : form.oturulan_kat],
      ["Yapım yılı", form.yapim_yili],
      ["Asansör", Number(form.asansor_var) === 1 ? "Var" : "Yok"],
    ];

    const olgular = result.mekansal_olgular || {};
    const konumSatirlari = [
      selectedLocation.address && ["Adres", selectedLocation.address],
      ["Koordinat (WGS84)", `${selectedLocation.lat.toFixed(5)}, ${selectedLocation.lon.toFixed(5)}`],
      olgular.en_yakin_fay_m != null && ["En yakın fay hattı", km(olgular.en_yakin_fay_m)],
      olgular.en_yakin_akarsu_m != null && [
        "En yakın akarsu",
        `${km(olgular.en_yakin_akarsu_m)}${olgular.en_yakin_akarsu_adi ? ` (${olgular.en_yakin_akarsu_adi})` : ""}`,
      ],
      olgular.litoloji && ["Zemin / litoloji", olgular.litoloji],
      olgular.arazi_kullanimi && ["Arazi kullanımı", olgular.arazi_kullanimi],
    ].filter(Boolean);

    const tabloSatirlari = (satirlar) => satirlar
      .map(([etiket, deger]) => `<tr><th>${e(etiket)}</th><td>${e(deger)}</td></tr>`)
      .join("");

    const faktorler = Object.entries(result.faktor_dokumu || {}).sort((a, b) => b[1].katki - a[1].katki);
    const enBuyukKatki = Math.max(...faktorler.map(([, v]) => v.katki), 0.001);
    const faktorTablosu = faktorler.length
      ? `<section>
          <h2>Bölgesel tehlikeyi oluşturan faktörler</h2>
          <table>
            <thead><tr><th>Faktör</th><th class="sayi">Puan (1–5)</th><th class="sayi">Ağırlık</th><th class="sayi">Katkı</th><th></th></tr></thead>
            <tbody>${faktorler.map(([anahtar, v]) => `
              <tr>
                <td>${e(FAKTOR_ETIKETLERI[anahtar] || anahtar.replaceAll("_", " "))}</td>
                <td class="sayi">${v.puan.toFixed(1)}</td>
                <td class="sayi">%${Math.round(v.agirlik * 100)}</td>
                <td class="sayi"><b>${v.katki.toFixed(2)}</b></td>
                <td class="cubuk-hucre"><span class="cubuk" style="width:${((v.katki / enBuyukKatki) * 100).toFixed(0)}%"></span></td>
              </tr>`).join("")}
            </tbody>
          </table>
          <p class="dipnot">Katkı = faktörün bu noktadaki puanı × afet tipine göre ağırlığı.</p>
        </section>`
      : "";

    const senaryolar = buildScenarioComparison(result, form);
    const aciklamalar = buildRiskExplanation(result, form);
    const eksikKatmanlar = Array.isArray(result.katman_meta?.eksik_katmanlar) ? result.katman_meta.eksik_katmanlar : [];
    const yontemNotu = [
      result.analiz_crs && `Analiz koordinat sistemi ${result.analiz_crs}`,
      result.agirlik_seti && `ağırlık seti "${result.agirlik_seti}"`,
      eksikKatmanlar.length && `eksik katman: ${eksikKatmanlar.join(", ")}`,
    ].filter(Boolean).join(" · ");

    const reportWindow = window.open("", "_blank", "width=920,height=1100");
    if (!reportWindow) {
      setError("Rapor penceresi açılamadı. Tarayıcının açılır pencere engelini bu site için kaldırın.");
      return;
    }
    reportWindow.document.write(`<!doctype html>
<html lang="tr">
  <head>
    <meta charset="utf-8" />
    <title>${e(dosyaAdi)}</title>
    <style>
      @page { size: A4; margin: 15mm 14mm 16mm; }
      * { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      body { margin: 0; padding: 20px; background: #e9eef3; color: #16202a;
             font: 10pt/1.5 Inter, "Segoe UI", Helvetica, Arial, sans-serif; }
      .arac-cubugu { max-width: 182mm; margin: 0 auto 12px; display: flex; flex-wrap: wrap; gap: 8px 16px;
                     align-items: center; justify-content: space-between; color: #475569; font-size: 9.5pt; }
      .arac-cubugu button { font: inherit; font-weight: 700; padding: 8px 16px; border: 0; border-radius: 6px;
                            background: #0f172a; color: #fff; cursor: pointer; }
      .sayfa { max-width: 182mm; margin: 0 auto; padding: 13mm 13mm 9mm; background: #fff;
               box-shadow: 0 2px 18px rgba(15, 23, 42, 0.14); }
      header { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px;
               padding-bottom: 9px; border-bottom: 2px solid #0f172a; }
      .marka { font-size: 8pt; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: #64748b; }
      h1 { margin: 1px 0 0; font-size: 18pt; line-height: 1.2; }
      .proje { margin: 3px 0 0; font-size: 8.5pt; color: #475569; }
      .tarih { flex: none; text-align: right; font-size: 8.5pt; color: #64748b; }
      .tarih strong { display: block; color: #16202a; font-size: 9.5pt; }
      h2 { margin: 16px 0 6px; padding-bottom: 3px; border-bottom: 1px solid #d8e0e8; font-size: 11pt; }
      section { break-inside: avoid; }
      .ozet { display: grid; grid-template-columns: 1.25fr 1fr 1fr; gap: 9px; margin-top: 13px; }
      .kutu { padding: 9px 11px; border: 1px solid #d8e0e8; border-radius: 6px; }
      .kutu small { display: block; color: #64748b; font-size: 8pt; font-weight: 700; }
      .kutu b { font-size: 15pt; font-variant-numeric: tabular-nums; }
      .kutu b span { font-size: 9pt; color: #64748b; font-weight: 600; }
      .toplam { border-left: 5px solid ${seviyeRengi}; }
      .toplam b { color: ${seviyeRengi}; font-size: 21pt; }
      .rozet { display: inline-block; margin-left: 6px; padding: 1px 8px; border-radius: 999px;
               background: ${seviyeRengi}; color: #fff; font-size: 8pt; font-weight: 700; vertical-align: 4px; }
      .kutu p { margin: 3px 0 0; font-size: 8pt; color: #64748b; }
      .iki-sutun { display: grid; grid-template-columns: 1fr 1fr; gap: 0 18px; }
      table { width: 100%; border-collapse: collapse; font-size: 9pt; }
      th, td { padding: 4px 6px; border-bottom: 1px solid #e6ebf0; text-align: left; vertical-align: top; }
      thead th { color: #64748b; font-size: 8pt; border-bottom-color: #cbd5e1; }
      tbody th { width: 40%; color: #475569; font-weight: 600; }
      .sayi { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
      .cubuk-hucre { width: 28%; vertical-align: middle; }
      .cubuk { display: block; height: 7px; border-radius: 4px; background: #0f766e; }
      .dipnot { margin: 4px 0 0; color: #64748b; font-size: 8pt; }
      ul { margin: 0; padding-left: 17px; }
      li { margin: 2px 0; }
      figure { margin: 0; break-inside: avoid; }
      /* Harita tam genişlikte bir sayfayı tek başına dolduruyordu; yükseklik
         sınırı toplanma alanı, harita ve uyarı notunu ikinci sayfaya sığdırır */
      figure img { display: block; max-width: 100%; max-height: 168mm; margin: 0 auto;
                   border: 1px solid #d8e0e8; border-radius: 6px; }
      figcaption { text-align: center; }
      figcaption { margin-top: 4px; color: #64748b; font-size: 8pt; }
      .uyari { margin-top: 14px; padding: 8px 11px; border: 1px solid #f3c9a6; border-radius: 6px;
               background: #fff7ed; font-size: 8.5pt; break-inside: avoid; }
      footer { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 12px; margin-top: 10px;
               padding-top: 6px; border-top: 1px solid #d8e0e8; color: #64748b; font-size: 7.5pt; }
      @media print {
        body { padding: 0; background: #fff; }
        .arac-cubugu { display: none; }
        .sayfa { max-width: none; padding: 0; box-shadow: none; }
      }
    </style>
  </head>
  <body>
    <div class="arac-cubugu">
      <span>Yazdırma penceresinde hedef olarak <b>PDF olarak kaydet</b>'i seçin.</span>
      <button type="button" onclick="window.print()">PDF olarak kaydet / yazdır</button>
    </div>
    <main class="sayfa">
      <header>
        <div>
          <div class="marka">DisasterAI · Kişiselleştirilmiş afet risk analizi</div>
          <h1>${e(afetAdi)} Risk Raporu</h1>
          <p class="proje">İzmir / Seferihisar pilot bölgesi · TÜBİTAK 2209-A destekli araştırma projesi, Pamukkale Üniversitesi</p>
        </div>
        <div class="tarih"><strong>${e(tarihMetni)}</strong>Rapor tarihi</div>
      </header>

      <div class="ozet">
        <div class="kutu toplam">
          <small>Toplam risk</small>
          <b>${result.risk_score.toFixed(2)} <span>/ 5</span></b><span class="rozet">${e(riskLabel(result.risk_score))}</span>
          <p>Bölgesel tehlike %${bolgeselPay} + bina hassasiyeti %${100 - bolgeselPay}</p>
        </div>
        <div class="kutu">
          <small>Bölgesel tehlike</small>
          <b>${result.hazard_score.toFixed(2)} <span>/ 5</span></b>
          <p>Seçilen koordinattaki CBS katmanlarından</p>
        </div>
        <div class="kutu">
          <small>Bina hassasiyeti</small>
          <b>${result.vulnerability_score.toFixed(2)} <span>/ 5</span></b>
          <p>Girilen bina bilgilerinden</p>
        </div>
      </div>

      <div class="iki-sutun">
        <section>
          <h2>Konum</h2>
          <table><tbody>${tabloSatirlari(konumSatirlari)}</tbody></table>
        </section>
        <section>
          <h2>Bina</h2>
          <table><tbody>${tabloSatirlari(binaSatirlari)}</tbody></table>
        </section>
      </div>

      ${faktorTablosu}

      <div class="iki-sutun">
        <section>
          <h2>Skor neden böyle?</h2>
          <ul>${aciklamalar.map((madde) => `<li>${e(madde)}</li>`).join("")}</ul>
        </section>
        <section>
          <h2>Senaryo karşılaştırması</h2>
          <table>
            <tbody>${senaryolar.map((s) => `
              <tr><th>${e(s.label)}</th><td class="sayi"><b>${s.score != null ? s.score.toFixed(2) : "–"}</b> / 5</td><td>${e(s.detail)}</td></tr>`).join("")}
            </tbody>
          </table>
        </section>
      </div>

      <section>
        <h2>Toplanma alanı</h2>
        ${route
          ? `<table><tbody>${tabloSatirlari([
              ["En yakın toplanma alanı", route.safe_point.name],
              ["Yürüyüş", `${route.distance_km.toFixed(2)} km · yaklaşık ${route.duration_min.toFixed(0)} dk`],
              ...(route.direct_distance_km ? [["Kuş uçuşu", `${route.direct_distance_km.toFixed(2)} km`]] : []),
            ])}</tbody></table>`
          : `<p class="dipnot">Bu rapor için toplanma rotası hesaplanmadı. Uygulamadaki "Toplanma Alanını Bul" düğmesiyle eklenebilir.</p>`}
      </section>

      <section>
        <h2>Risk haritası</h2>
        <figure>
          <img src="${e(result.map_url)}" alt="${e(afetAdi)} risk haritası" />
          <figcaption>Seferihisar ${e(afetAdi.toLocaleLowerCase("tr-TR"))} bölgesel tehlike haritası; analiz noktası işaretlidir. Risk sınıfları: Düşük &lt;3 · Orta 3–4 · Yüksek ≥4.</figcaption>
        </figure>
      </section>

      <div class="uyari">
        <b>Bu rapor karar destek amaçlıdır.</b> Resmî hasar tespiti, zemin etüdü veya mühendislik raporu yerine geçmez;
        bina bilgileri kullanıcı beyanına dayanır. Resmî afet yönlendirmesi için AFAD kaynaklarını esas alın.
      </div>

      <footer>
        <span>DisasterAI · CBS ve büyük dil modelleriyle afet risk iletişimi</span>
        ${yontemNotu ? `<span>${e(yontemNotu)}</span>` : ""}
      </footer>
    </main>
  </body>
</html>`);
    reportWindow.document.close();
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <ShieldCheck size={24} />
          <span>DisasterAI</span>
        </div>
        <div className="topbar-actions">
          {modelBilgisi && (
            <span className={`model-rozeti ${modelBilgisi.saglayici === "yerel" ? "yerel" : "api"}`}
                  title={`Aktif dil modeli: ${modelBilgisi.ad}`}>
              <Cpu size={13} />
              {modelBilgisi.saglayici === "yerel" ? "Yerel model" : "Bulut API"}
              <small>{modelBilgisi.ad}</small>
            </span>
          )}
          <nav>
            <button className={view === "analysis" ? "active" : ""} onClick={() => setView("analysis")} type="button">
              Analiz
            </button>
            <button className={view === "method" ? "active" : ""} onClick={() => setView("method")} type="button">
              Yöntem
            </button>
            <button className={view === "about" ? "active" : ""} onClick={() => setView("about")} type="button">
              Hakkımızda
            </button>
            <button className={view === "deney" ? "active" : ""} onClick={() => setView("deney")} type="button">
              Deney
            </button>
          </nav>
          <button
            className="theme-toggle"
            type="button"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "Açık temaya geç" : "Koyu temaya geç"}
            aria-pressed={theme === "dark"}
            title={theme === "dark" ? "Açık tema" : "Koyu tema"}
          >
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </header>

      {view === "analysis" ? (
        <main className="workspace">
          <AnalysisForm
            form={form}
            setForm={setForm}
            selectedLocation={selectedLocation}
            onAnalyze={runAnalysis}
            onReset={resetLocation}
            onSearchPlace={searchPlace}
            loading={loading}
            error={error}
            result={result}
            onRoute={requestRoute}
            routeLoading={routeLoading}
            history={history}
            onUseHistory={useHistoryItem}
          />

          <section className="map-panel">
            <RiskMap
              selectedLocation={selectedLocation}
              onSelect={handleMapSelect}
              result={result}
              route={route}
              overlayOpacity={overlayOpacity}
              setOverlayOpacity={setOverlayOpacity}
              theme={theme}
              ipucuGoster={ipucuAcik && !selectedLocation}
              onIpucuKapat={ipucuKapat}
            />
          </section>

          <div className="side-stack">
            <ResultsPanel
              result={result}
              form={form}
              selectedLocation={selectedLocation}
              route={route}
              onPrintReport={printReport}
              loading={loading}
            />
          </div>

          <ChatWidget result={result} form={form} sifirlaAnahtari={analizSayaci} />

          {/* Dar ekranda form haritanın üstünde kalıyor: noktayı seçen kullanıcı
              analizi başlatmak için yukarı kaydırmasın diye sabit alt çubuk */}
          <div className="mobil-eylem">
            {error && <p className="mobil-eylem-hata">{error}</p>}
            <button
              className={`primary-button${selectedLocation ? "" : " bekliyor"}`}
              type="button"
              onClick={runAnalysis}
              disabled={loading || !selectedLocation}
            >
              {loading ? <Loader2 size={18} className="spin" /> : <Activity size={18} />}
              {loading ? "Hesaplanıyor…" : selectedLocation ? "Analizi Başlat" : "Haritadan bir nokta seçin"}
            </button>
          </div>
        </main>
      ) : view === "deney" ? (
        <ExperimentPanel />
      ) : (
        <InfoPage type={view} />
      )}
    </div>
  );
}
