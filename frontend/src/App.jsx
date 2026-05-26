import React, { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import {
  Activity,
  Building2,
  Clock,
  Download,
  FileText,
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
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";

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

function RiskMap({ selectedLocation, onSelect, result, route, overlayOpacity, setOverlayOpacity, theme }) {
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
              </Popup>
              <Tooltip>Analiz noktası</Tooltip>
            </Marker>
            <Circle
              center={[selectedLocation.lat, selectedLocation.lon]}
              radius={300}
              pathOptions={{ color: "#d83a3a", fillColor: "#d83a3a", fillOpacity: 0.08, weight: 2 }}
            />
          </>
        )}

        <RouteLayer route={route} />
        <MapClickHandler onSelect={onSelect} />
        <FitMap selectedLocation={selectedLocation} route={route} />
      </MapContainer>

      {result?.overlay_url && (
        <div className="map-opacity-control">
          <div className="map-opacity-label">
            <Layers size={15} />
            <span>Risk</span>
          </div>
          <input
            aria-label="Risk katmanı şeffaflığı"
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={overlayOpacity}
            onChange={(event) => setOverlayOpacity(Number(event.target.value))}
          />
        </div>
      )}
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

      {error && <div className="alert error">{error}</div>}

      <button className="primary-button" type="button" onClick={onAnalyze} disabled={loading}>
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

function ResultsPanel({ result, form, selectedLocation, route, onPrintReport }) {
  const tone = riskTone(result?.risk_score);
  const scorePercent = result ? `${Math.min(100, (result.risk_score / 5) * 100)}%` : "0%";
  const explanation = buildRiskExplanation(result, form);
  const scenarios = buildScenarioComparison(result, form);

  return (
    <aside className="result-panel">
      <section className={`risk-summary ${tone}`}>
        <div>
          <span>Toplam Risk</span>
          <strong>{result ? result.risk_score.toFixed(2) : "--"} / 5.0</strong>
        </div>
        <b>{riskLabel(result?.risk_score)}</b>
        <div className="risk-bar">
          <span style={{ width: scorePercent }} />
        </div>
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

function ChatPanel({ result, form }) {
  const sessionId = useMemo(() => {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    return String(Date.now());
  }, []);
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Analizden sonra risk skorunu birlikte yorumlayabiliriz." },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function sendMessage(event) {
    event.preventDefault();
    const text = input.trim();
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
      <div className="section-title">
        <MessageCircle size={18} />
        <span>Analiz Asistanı</span>
      </div>
      <div className="chat-messages">
        {messages.map((message, index) => (
          <div className={`chat-message ${message.role}`} key={`${message.role}-${index}`}>
            {message.text || "Yazıyor..."}
          </div>
        ))}
      </div>
      <form onSubmit={sendMessage} className="chat-form">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Risk skorum ne anlama geliyor?"
        />
        <button type="submit" disabled={loading || !input.trim()} aria-label="Gönder">
          {loading ? <Loader2 size={17} className="spin" /> : <Send size={17} />}
        </button>
      </form>
    </section>
  );
}

function InfoPage({ type }) {
  const isMethod = type === "method";

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
              Sistem; fay hattı, akarsu uzaklığı, litoloji, eğim ve arazi kullanımı katmanlarını afet türüne göre
              ağırlıklandırır. Bina yaşı, malzeme ve kat bilgisi yapısal hassasiyet skoruna dönüştürülür.
            </p>
            <div className="method-grid">
              <div>
                <h3>Deprem</h3>
                <p>Fay hattı uzaklığı, litoloji, eğim, akarsu uzaklığı ve arazi kullanımı birlikte değerlendirilir.</p>
              </div>
              <div>
                <h3>Sel/Taşkın</h3>
                <p>Akarsu yakınlığı daha yüksek ağırlık alır; bölgesel tehlike bina hassasiyetiyle birleştirilir.</p>
              </div>
              <div>
                <h3>Heyelan</h3>
                <p>Eğim ve litoloji baskın faktörlerdir; sonuçlar kullanıcı konumu için okunabilir skora çevrilir.</p>
              </div>
              <div>
                <h3>Sınırlılıklar</h3>
                <p>Sonuçlar karar destek amaçlıdır; resmi hasar tespiti, zemin etüdü veya mühendislik raporu yerine geçmez.</p>
              </div>
            </div>
          </>
        ) : (
          <>
            <h1>DisasterAI Risk Analizi</h1>
            <p>
              DisasterAI, afet risklerini harita ve yapı bilgileriyle birlikte yorumlayan, kullanıcıların konum bazlı
              farkındalık kazanmasını hedefleyen akademik bir karar destek uygulamasıdır.
            </p>
            <p>
              Proje; Python, FastAPI, GeoPandas, Leaflet ve yapay zeka destekli açıklama katmanını bir araya getirir.
            </p>
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
      saveHistoryItem(analysisResult, selectedLocation);
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
    const material = getMaterialLabel(form.malzeme_secim);
    const explanation = buildRiskExplanation(result, form);
    const routeText = route
      ? `${route.safe_point.name} - ${route.distance_km.toFixed(2)} km / ${route.duration_min.toFixed(1)} dk`
      : "Toplanma rotası hesaplanmadı";
    const reportWindow = window.open("", "_blank", "width=920,height=1100");
    if (!reportWindow) return;
    reportWindow.document.write(`
      <!doctype html>
      <html lang="tr">
        <head>
          <meta charset="utf-8" />
          <title>DisasterAI Risk Raporu</title>
          <style>
            body { font-family: Arial, sans-serif; color: #16202a; margin: 32px; line-height: 1.5; }
            h1 { margin: 0 0 8px; }
            h2 { margin-top: 24px; border-bottom: 1px solid #d8e0e8; padding-bottom: 6px; }
            .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
            .box { border: 1px solid #d8e0e8; border-radius: 8px; padding: 12px; }
            .score { font-size: 32px; font-weight: 800; color: #c93636; }
            img { max-width: 100%; border: 1px solid #d8e0e8; border-radius: 8px; }
            @media print { button { display: none; } body { margin: 18mm; } }
          </style>
        </head>
        <body>
          <button onclick="window.print()">PDF olarak kaydet / yazdır</button>
          <h1>DisasterAI Risk Raporu</h1>
          <p>${new Date().toLocaleString("tr-TR")}</p>
          <div class="grid">
            <div class="box"><strong>Afet Tipi</strong><br/>${form.afet_tipi}</div>
            <div class="box"><strong>Konum</strong><br/>${selectedLocation.address ? `${selectedLocation.address}<br/>` : ""}${selectedLocation.lat.toFixed(5)}, ${selectedLocation.lon.toFixed(5)}</div>
            <div class="box"><strong>Bina</strong><br/>${material}, ${form.bina_kat_sayisi} kat, ${form.yapim_yili}</div>
            <div class="box"><strong>Toplanma</strong><br/>${routeText}</div>
          </div>
          <h2>Risk Özeti</h2>
          <p class="score">${result.risk_score.toFixed(2)} / 5.0 - ${riskLabel(result.risk_score)}</p>
          <p>Bölgesel tehlike: ${result.hazard_score.toFixed(2)} / 5.0</p>
          <p>Bina hassasiyeti: ${result.vulnerability_score.toFixed(2)} / 5.0</p>
          <p>${result.tavsiye}</p>
          <h2>Skor Açıklaması</h2>
          <ul>${explanation.map((item) => `<li>${item}</li>`).join("")}</ul>
          <h2>Harita Çıktısı</h2>
          <img src="${result.map_url}" alt="Risk haritası" />
        </body>
      </html>
    `);
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
            />
          </section>

          <div className="side-stack">
            <ResultsPanel
              result={result}
              form={form}
              selectedLocation={selectedLocation}
              route={route}
              onPrintReport={printReport}
            />
            <ChatPanel result={result} form={form} />
          </div>
        </main>
      ) : (
        <InfoPage type={view} />
      )}
    </div>
  );
}
