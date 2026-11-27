/**
 * ExperimentPanel.jsx — Kontrollü kullanıcı deneyi ekranı (İP4)
 *
 * Yüz yüze prototip deneyi için ayrı bir ekran. Analiz ekranına dokunmaz;
 * böylece deney akışı normal kullanımdan tamamen yalıtılmış olur.
 *
 * AKIŞ
 *   1. Kurulum   — katılımcı kodu, endişe düzeyi, isteğe bağlı demografik
 *   2. Hazırlık  — üç senaryonun metni birlikte üretilir
 *   3. Senaryo   — metin, ardından ölçekler (bölüm başlıklı, sayaçlı)
 *   4. Onay      — "Yanıtlarınız kaydedildi", birkaç saniye sonra sıradaki senaryo
 *   5. Bitiş     — teşekkür ekranı
 *
 * KÖRLEME
 *   Katılımcı hangi kolda olduğunu görmez. Kol bilgisi yalnızca "Uygulayıcı
 *   paneli" içinde durur ve her aşama değişiminde kendiliğinden kapanır.
 *   Metinler senaryolar arasında değil baştan üretilir: teknik rapor kolu
 *   anında, BDM kolları saniyeler sonra geldiği için bekleme süresi katılımcıya
 *   kolunu sezdirebilirdi.
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  CircleCheck,
  ClipboardList,
  Loader2,
  Lock,
  RotateCcw,
} from "lucide-react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8514";
const api = (path) => `${API_BASE_URL}${path}`;

const ENDISE_SECENEKLERI = [
  { value: "düşük", label: "Düşük", aciklama: "Afetler beni pek kaygılandırmaz" },
  { value: "orta", label: "Orta", aciklama: "Zaman zaman düşünürüm" },
  { value: "yüksek", label: "Yüksek", aciklama: "Sık sık endişelenirim" },
];

const YAS_ARALIKLARI = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"];
const EGITIM = ["İlköğretim", "Lise", "Ön lisans", "Lisans", "Lisansüstü"];

// Onay ekranından sıradaki senaryoya geçmeden önceki bekleme (saniye)
const ONAY_SURESI = 3;

function yeniKatilimciKodu() {
  // Kimliksizleştirilmiş kod: tarih + rastgele son ek.
  const d = new Date();
  const gun = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
  const ek = Math.random().toString(36).slice(2, 6).toUpperCase();
  return `K-${gun}-${ek}`;
}

async function hataMetni(r, varsayilan) {
  try {
    return (await r.json()).detail || varsayilan;
  } catch {
    return varsayilan;
  }
}

export default function ExperimentPanel() {
  const [yapilandirma, setYapilandirma] = useState(null);
  const [asama, setAsama] = useState("kurulum"); // kurulum | hazirlik | senaryo | onay | bitis
  const [hata, setHata] = useState("");
  const [yukleniyor, setYukleniyor] = useState(false);

  const [katilimciKodu, setKatilimciKodu] = useState(yeniKatilimciKodu);
  const [endise, setEndise] = useState("orta");
  const [demografik, setDemografik] = useState({ yas: "", egitim: "", cinsiyet: "" });
  const [atama, setAtama] = useState(null);

  const [metinler, setMetinler] = useState([]); // senaryo sırasına göre; null = henüz yok
  const [senaryoIndex, setSenaryoIndex] = useState(0);
  const [yanitlar, setYanitlar] = useState({});
  const [vurgulanan, setVurgulanan] = useState(null);
  const [geriSayim, setGeriSayim] = useState(ONAY_SURESI);
  const [uygulayiciAcik, setUygulayiciAcik] = useState(false);

  const okumaBaslangic = useRef(null);
  const baslikRef = useRef(null);
  const oturum = useRef(0); // yeni katılımcıya geçilince eski isteklerin yanıtı yok sayılır

  useEffect(() => {
    fetch(api("/api/deney/yapilandirma"))
      .then((r) => r.json())
      .then(setYapilandirma)
      .catch(() => setHata("Deney yapılandırması alınamadı. Backend çalışıyor mu?"));
  }, []);

  const senaryolar = yapilandirma?.senaryolar || [];
  const olcekler = yapilandirma?.olcekler || {};
  const likert = yapilandirma?.likert || [];
  const aktifSenaryo = senaryolar[senaryoIndex];
  const aktifMetin = metinler[senaryoIndex];

  const maddeler = useMemo(
    () =>
      Object.entries(olcekler).flatMap(([ad, olcek]) =>
        (olcek.maddeler || []).map((_, i) => ({ ad, i, anahtar: `${ad}-${i}` }))
      ),
    [olcekler]
  );
  const yanitlananSayisi = maddeler.filter(({ ad, i }) => yanitlar?.[ad]?.[i] != null).length;
  const tumMaddelerYanitlandi = maddeler.length > 0 && yanitlananSayisi === maddeler.length;
  const hazirMetinSayisi = metinler.filter(Boolean).length;

  // Her aşama değişiminde: panel kapanır, sayfa başa döner, odak başlığa gider
  useEffect(() => {
    setUygulayiciAcik(false);
    window.scrollTo({ top: 0 });
    baslikRef.current?.focus({ preventScroll: true });
    if (asama === "senaryo") okumaBaslangic.current = Date.now();
  }, [asama, senaryoIndex]);

  // Onay ekranı: geri sayım bitince sıradaki senaryo
  useEffect(() => {
    if (asama !== "onay") return;
    if (geriSayim <= 0) {
      sonrakiSenaryo();
      return;
    }
    const t = setTimeout(() => setGeriSayim((s) => s - 1), 1000);
    return () => clearTimeout(t);
    // sonrakiSenaryo her render'da yeniden tanımlanır; tetikleyici sayaçtır
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asama, geriSayim]);

  async function metinGetir(index) {
    const r = await fetch(api("/api/deney/senaryo-metni"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        katilimci_kodu: katilimciKodu.trim(),
        senaryo_kodu: senaryolar[index].kod,
        endise_duzeyi: endise,
      }),
    });
    if (!r.ok) throw new Error(await hataMetni(r, "Metin üretilemedi"));
    return r.json();
  }

  async function metinleriHazirla(eksikler) {
    const buOturum = oturum.current;
    setHata("");
    const sonuclar = await Promise.allSettled(
      eksikler.map(async (index) => {
        const veri = await metinGetir(index);
        if (oturum.current !== buOturum) return;
        setMetinler((onceki) => {
          const yeni = [...onceki];
          yeni[index] = veri;
          return yeni;
        });
      })
    );
    if (oturum.current !== buOturum) return;
    const basarisiz = sonuclar.find((s) => s.status === "rejected");
    if (basarisiz) setHata(`Senaryo metni hazırlanamadı: ${basarisiz.reason?.message || basarisiz.reason}`);
  }

  async function deneyiBaslat() {
    if (!katilimciKodu.trim()) return setHata("Katılımcı kodu boş olamaz.");
    setYukleniyor(true);
    setHata("");
    try {
      const r = await fetch(api("/api/deney/kol-ata"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          katilimci_kodu: katilimciKodu.trim(),
          endise_duzeyi: endise,
          demografik,
        }),
      });
      if (!r.ok) throw new Error(await hataMetni(r, "Kol atanamadı"));
      setAtama(await r.json());
      setMetinler(senaryolar.map(() => null));
      setSenaryoIndex(0);
      setYanitlar({});
      setAsama("hazirlik");
      metinleriHazirla(senaryolar.map((_, i) => i));
    } catch (e) {
      setHata(String(e.message || e));
    } finally {
      setYukleniyor(false);
    }
  }

  function yanitSec(ad, i, deger) {
    setYanitlar((o) => {
      const dizi = [...(o[ad] || [])];
      dizi[i] = deger;
      return { ...o, [ad]: dizi };
    });
    if (vurgulanan === `${ad}-${i}`) setVurgulanan(null);
  }

  function yanitlanmamisaGit() {
    const ilk = maddeler.find(({ ad, i }) => yanitlar?.[ad]?.[i] == null);
    if (!ilk) return;
    const el = document.getElementById(`madde-${ilk.anahtar}`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    el?.querySelector("[role=radio]")?.focus({ preventScroll: true });
    setVurgulanan(ilk.anahtar);
  }

  async function yanitiGonder() {
    if (!tumMaddelerYanitlandi) return yanitlanmamisaGit();
    setYukleniyor(true);
    setHata("");
    try {
      const sure = okumaBaslangic.current
        ? Math.round((Date.now() - okumaBaslangic.current) / 1000)
        : null;
      const r = await fetch(api("/api/deney/yanit"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          katilimci_kodu: katilimciKodu,
          kol: aktifMetin?.kol,
          ton: aktifMetin?.ton,
          senaryo_kodu: aktifSenaryo?.kod,
          gosterilen_metin: aktifMetin?.metin,
          risk_score: aktifMetin?._analiz?.risk_score,
          olcek_yanitlari: yanitlar,
          okuma_suresi_sn: sure,
        }),
      });
      if (!r.ok) throw new Error(await hataMetni(r, "Yanıt kaydedilemedi"));
      await r.json();
      if (senaryoIndex + 1 < senaryolar.length) {
        setGeriSayim(ONAY_SURESI);
        setAsama("onay");
      } else {
        setAsama("bitis");
      }
    } catch (e) {
      setHata(String(e.message || e));
    } finally {
      setYukleniyor(false);
    }
  }

  function sonrakiSenaryo() {
    setYanitlar({});
    setVurgulanan(null);
    setSenaryoIndex((i) => i + 1);
    setAsama("senaryo");
  }

  function yeniKatilimci() {
    oturum.current += 1;
    setKatilimciKodu(yeniKatilimciKodu());
    setEndise("orta");
    setDemografik({ yas: "", egitim: "", cinsiyet: "" });
    setAtama(null);
    setMetinler([]);
    setYanitlar({});
    setVurgulanan(null);
    setSenaryoIndex(0);
    setHata("");
    setAsama("kurulum");
  }

  if (!yapilandirma && !hata) {
    return (
      <div className="deney-sayfa">
        <DeneyStilleri />
        <div className="deney-yukleniyor">
          <Loader2 className="donuyor" size={22} /> Deney yapılandırması yükleniyor…
        </div>
      </div>
    );
  }

  const panel = (
    <UygulayiciPaneli
      acik={uygulayiciAcik}
      setAcik={setUygulayiciAcik}
      durum={yapilandirma?.durum}
      atama={asama === "kurulum" ? null : atama}
      senaryoVerisi={asama === "senaryo" ? aktifMetin : null}
    />
  );

  return (
    <div className="deney-sayfa">
      <DeneyStilleri />

      <header className="deney-baslik">
        <ClipboardList size={20} />
        <div>
          <h1>Afet Riski Bilgilendirme Çalışması</h1>
          <p>TÜBİTAK 2209-A · Pamukkale Üniversitesi</p>
        </div>
      </header>

      {hata && asama !== "senaryo" && <div className="deney-hata" role="alert">{hata}</div>}

      {asama === "kurulum" && (
        <section className="deney-kart">
          <h2 ref={baslikRef} tabIndex={-1} className="deney-odak">Katılımcı kaydı</h2>

          <div className="deney-onam">
            <strong>Uygulayıcı:</strong> Ad, telefon, e-posta girmeyin; katılımcı kodu yeterli.
          </div>

          <label className="deney-alan">
            <span>Katılımcı kodu</span>
            <div className="deney-satir">
              <input
                value={katilimciKodu}
                onChange={(e) => setKatilimciKodu(e.target.value)}
                spellCheck={false}
              />
              <button type="button" className="deney-ikincil" onClick={() => setKatilimciKodu(yeniKatilimciKodu())}>
                <RotateCcw size={15} /> Yeni kod
              </button>
            </div>
          </label>

          <fieldset className="deney-alan">
            <legend>Afet riski konusunda genel endişe düzeyiniz</legend>
            <div className="deney-secenekler" role="radiogroup" aria-label="Endişe düzeyi">
              {ENDISE_SECENEKLERI.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  role="radio"
                  aria-checked={endise === s.value}
                  className={endise === s.value ? "deney-secenek aktif" : "deney-secenek"}
                  onClick={() => setEndise(s.value)}
                >
                  <strong>{s.label}</strong>
                  <span>{s.aciklama}</span>
                </button>
              ))}
            </div>
          </fieldset>

          <div className="deney-izgara">
            <label className="deney-alan">
              <span>Yaş aralığı</span>
              <select value={demografik.yas} onChange={(e) => setDemografik({ ...demografik, yas: e.target.value })}>
                <option value="">Belirtmek istemiyorum</option>
                {YAS_ARALIKLARI.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </label>
            <label className="deney-alan">
              <span>Eğitim durumu</span>
              <select value={demografik.egitim} onChange={(e) => setDemografik({ ...demografik, egitim: e.target.value })}>
                <option value="">Belirtmek istemiyorum</option>
                {EGITIM.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </label>
            <label className="deney-alan">
              <span>Cinsiyet</span>
              <select value={demografik.cinsiyet} onChange={(e) => setDemografik({ ...demografik, cinsiyet: e.target.value })}>
                <option value="">Belirtmek istemiyorum</option>
                <option value="kadın">Kadın</option>
                <option value="erkek">Erkek</option>
                <option value="diğer">Diğer</option>
              </select>
            </label>
          </div>

          <button className="deney-birincil" type="button" onClick={deneyiBaslat} disabled={yukleniyor || !yapilandirma}>
            {yukleniyor ? <Loader2 className="donuyor" size={16} /> : null} Deneyi başlat
          </button>

          {panel}
        </section>
      )}

      {asama === "hazirlik" && (
        <section className="deney-kart deney-orta">
          <h2 ref={baslikRef} tabIndex={-1} className="deney-odak">
            {hazirMetinSayisi === senaryolar.length ? "Hazır" : "Metinler hazırlanıyor"}
          </h2>
          <p className="deney-soluk" aria-live="polite">
            {hazirMetinSayisi} / {senaryolar.length} senaryo
          </p>
          <div className="deney-cubuk deney-cubuk-genis">
            <div style={{ width: `${(hazirMetinSayisi / Math.max(senaryolar.length, 1)) * 100}%` }} />
          </div>

          {hazirMetinSayisi === senaryolar.length ? (
            <button className="deney-birincil" type="button" onClick={() => setAsama("senaryo")}>
              Başla
            </button>
          ) : hata ? (
            <button
              className="deney-birincil"
              type="button"
              onClick={() => metinleriHazirla(metinler.map((m, i) => (m ? null : i)).filter((i) => i != null))}
            >
              <RotateCcw size={16} /> Tekrar dene
            </button>
          ) : (
            <div className="deney-yukleniyor"><Loader2 className="donuyor" size={20} /> Lütfen bekleyin</div>
          )}

          {panel}
        </section>
      )}

      {asama === "senaryo" && aktifMetin && (
        <section className="deney-kart">
          <Adimlar toplam={senaryolar.length} aktif={senaryoIndex} tamamlanan={senaryoIndex} />

          <div className="deney-senaryo-basi">
            <h2 ref={baslikRef} tabIndex={-1} className="deney-odak">{aktifSenaryo?.ad}</h2>
            <p>{aktifSenaryo?.aciklama}</p>
          </div>

          <div className="deney-metin">{aktifMetin.metin}</div>

          <p className="deney-yonerge">
            Metni okuduktan sonra aşağıdaki ifadeleri değerlendirin. Doğru ya da yanlış yanıt yoktur.
          </p>

          {Object.entries(olcekler).map(([ad, olcek], bolumNo, tum) => {
            const adet = (olcek.maddeler || []).length;
            const yanitlanan = (olcek.maddeler || []).filter((_, i) => yanitlar?.[ad]?.[i] != null).length;
            return (
              <fieldset key={ad} className="deney-olcek">
                <legend className="deney-olcek-basi">
                  <span className="deney-olcek-no">Bölüm {bolumNo + 1} / {tum.length}</span>
                  <span className="deney-olcek-ad">{olcek.baslik}</span>
                  <span className={yanitlanan === adet ? "deney-olcek-sayac tamam" : "deney-olcek-sayac"}>
                    {yanitlanan === adet ? <Check size={14} aria-label="Tamamlandı" /> : `${yanitlanan}/${adet}`}
                  </span>
                </legend>
                <p className="deney-olcek-aciklama">{olcek.aciklama}</p>
                {(olcek.maddeler || []).map((madde, i) => (
                  <LikertMaddesi
                    key={i}
                    kimlik={`${ad}-${i}`}
                    metin={madde}
                    secenekler={likert}
                    deger={yanitlar?.[ad]?.[i]}
                    vurgulu={vurgulanan === `${ad}-${i}`}
                    onSec={(deger) => yanitSec(ad, i, deger)}
                  />
                ))}
              </fieldset>
            );
          })}

          <div className="deney-gonder">
            {hata && <p className="deney-hata" role="alert">{hata}</p>}
            <div className="deney-gonder-satir">
              <div className="deney-gonder-durum">
                <span aria-live="polite">
                  <strong>{yanitlananSayisi}</strong> / {maddeler.length} yanıtlandı
                </span>
                <div className="deney-cubuk">
                  <div style={{ width: `${(yanitlananSayisi / Math.max(maddeler.length, 1)) * 100}%` }} />
                </div>
                {!tumMaddelerYanitlandi && (
                  <button type="button" className="deney-baglanti" onClick={yanitlanmamisaGit}>
                    Yanıtlanmamış maddeye git
                  </button>
                )}
              </div>
              <button
                className="deney-birincil"
                type="button"
                onClick={yanitiGonder}
                disabled={yukleniyor || !tumMaddelerYanitlandi}
              >
                {yukleniyor ? <Loader2 className="donuyor" size={16} /> : null}
                {senaryoIndex + 1 < senaryolar.length ? "Kaydet ve devam et" : "Kaydet ve bitir"}
              </button>
            </div>
          </div>

          {panel}
        </section>
      )}

      {asama === "onay" && (
        <section className="deney-kart deney-orta">
          <Adimlar toplam={senaryolar.length} aktif={senaryoIndex + 1} tamamlanan={senaryoIndex + 1} />
          <CircleCheck className="deney-onay-ikon" size={52} aria-hidden="true" />
          <h2 ref={baslikRef} tabIndex={-1} className="deney-odak">Yanıtlarınız kaydedildi</h2>
          <p className="deney-soluk" aria-live="polite">
            Senaryo {senaryoIndex + 2} birazdan açılıyor ({Math.max(geriSayim, 0)})
          </p>
          <button className="deney-birincil" type="button" onClick={sonrakiSenaryo}>
            Hemen devam et
          </button>
        </section>
      )}

      {asama === "bitis" && (
        <section className="deney-kart deney-orta">
          <Adimlar toplam={senaryolar.length} aktif={senaryolar.length} tamamlanan={senaryolar.length} />
          <CircleCheck className="deney-onay-ikon" size={52} aria-hidden="true" />
          <h2 ref={baslikRef} tabIndex={-1} className="deney-odak">Katılımınız için teşekkürler</h2>
          <p className="deney-soluk">Tüm yanıtlarınız kaydedildi.</p>
          <button className="deney-ikincil" type="button" onClick={yeniKatilimci}>
            <RotateCcw size={15} /> Yeni katılımcı
          </button>
          {panel}
        </section>
      )}
    </div>
  );
}

function Adimlar({ toplam, aktif, tamamlanan }) {
  return (
    <ol className="deney-adimlar" aria-label={`Senaryo ${Math.min(aktif + 1, toplam)} / ${toplam}`}>
      {Array.from({ length: toplam }, (_, i) => {
        const durum = i < tamamlanan ? "tamam" : i === aktif ? "aktif" : "bekliyor";
        return (
          <li key={i} className={`deney-adim ${durum}`} aria-current={durum === "aktif" ? "step" : undefined}>
            <span className="deney-adim-nokta">{durum === "tamam" ? <Check size={14} /> : i + 1}</span>
            <span className="deney-adim-ad">Senaryo {i + 1}</span>
          </li>
        );
      })}
    </ol>
  );
}

function LikertMaddesi({ kimlik, metin, secenekler, deger, vurgulu, onSec }) {
  const dugmeler = useRef([]);
  const odakIndex = Math.max(0, secenekler.findIndex((s) => s.deger === deger));

  // Radyo grubu klavye davranışı: oklar seçimi komşuya taşır
  function tusla(e, index) {
    const yon = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (!yon) return;
    e.preventDefault();
    const yeni = (index + yon + secenekler.length) % secenekler.length;
    onSec(secenekler[yeni].deger);
    dugmeler.current[yeni]?.focus();
  }

  const uclar = secenekler.length
    ? [secenekler[0], secenekler[Math.floor(secenekler.length / 2)], secenekler[secenekler.length - 1]]
    : [];

  return (
    <div id={`madde-${kimlik}`} className={vurgulu ? "deney-madde vurgulu" : "deney-madde"}>
      <p id={`madde-metin-${kimlik}`}>{metin}</p>
      <div className="deney-likert" role="radiogroup" aria-labelledby={`madde-metin-${kimlik}`}>
        {secenekler.map((l, index) => (
          <button
            key={l.deger}
            ref={(el) => (dugmeler.current[index] = el)}
            type="button"
            role="radio"
            aria-checked={deger === l.deger}
            aria-label={`${l.deger} — ${l.etiket}`}
            tabIndex={index === odakIndex ? 0 : -1}
            className={deger === l.deger ? "deney-likert-dugme aktif" : "deney-likert-dugme"}
            onClick={() => onSec(l.deger)}
            onKeyDown={(e) => tusla(e, index)}
          >
            <span className="deney-likert-sayi">{l.deger}</span>
            <span className="deney-likert-etiket">{l.etiket}</span>
          </button>
        ))}
      </div>
      {/* Dar ekranda düğme içi etiketler gizlenir; uç ve orta etiketler altta */}
      <div className="deney-likert-uclar" aria-hidden="true">
        {uclar.map((l) => <span key={l.deger}>{l.etiket}</span>)}
      </div>
    </div>
  );
}

function UygulayiciPaneli({ acik, setAcik, durum, atama, senaryoVerisi }) {
  const [canliDurum, setCanliDurum] = useState(durum);
  useEffect(() => {
    if (!acik) return;
    fetch(api("/api/deney/durum")).then((r) => r.json()).then(setCanliDurum).catch(() => {});
  }, [acik, senaryoVerisi]);

  const d = canliDurum || durum;

  return (
    <div className="deney-uygulayici">
      <button
        type="button"
        className="deney-uygulayici-basi"
        onClick={() => setAcik(!acik)}
        aria-expanded={acik}
      >
        {acik ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        <Lock size={14} />
        Uygulayıcı paneli
      </button>
      {acik && (
        <div className="deney-uygulayici-govde">
          <p>Üç kollu, katılımcılar arası tasarım. Endişe düzeyi, tonlu kolda tonu seçer.</p>
          {atama && (
            <p>
              Bu katılımcı: kol <strong>{atama.kol}</strong> · ton <strong>{atama.ton}</strong> ·
              endişe <strong>{atama.endise_duzeyi}</strong>
            </p>
          )}
          {senaryoVerisi?.dogrulama && (
            <p>
              Sayısal doğruluk: <strong>{senaryoVerisi.dogrulama.sayisal_dogruluk}</strong>
              {senaryoVerisi.dogrulama.uydurma_sayilar?.length > 0 && (
                <span className="deney-uyari">
                  {" "}⚠ Uydurma sayı: {senaryoVerisi.dogrulama.uydurma_sayilar.join(", ")}
                </span>
              )}
              {" · "}Risk skoru metinde geçiyor mu:{" "}
              <strong>{senaryoVerisi.dogrulama.risk_skoru_gecti ? "evet" : "HAYIR"}</strong>
            </p>
          )}
          {d && (
            <p>
              Toplam katılımcı: <strong>{d.katilimci_sayisi}</strong> · kol dağılımı{" "}
              {Object.entries(d.kol_dagilimi || {}).map(([k, v]) => `${k}: ${v}`).join(" · ")} ·
              kayıtlı yanıt: <strong>{d.yanit_sayisi}</strong> / {d.beklenen_yanit}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function DeneyStilleri() {
  return (
    <style>{`
.deney-sayfa { max-width: 820px; margin: 0 auto; padding: 24px 20px 64px; color: var(--text); }
.deney-baslik { display:flex; gap:12px; align-items:flex-start; margin-bottom:20px; color: var(--heading); }
.deney-baslik h1 { font-size:1.35rem; margin:0 0 4px; }
.deney-baslik p { margin:0; font-size:.82rem; color: var(--muted); }
.deney-kart { background: var(--panel); border:1px solid var(--line); border-radius:14px; padding:22px; margin-bottom:16px; }
.deney-kart h2 { margin:0 0 14px; font-size:1.1rem; color: var(--heading); }
.deney-odak:focus { outline: none; }
.deney-orta { text-align:center; display:flex; flex-direction:column; align-items:center; }
.deney-orta .deney-uygulayici { align-self: stretch; text-align:left; }
.deney-soluk { color: var(--muted); margin: 0 0 18px; font-size: .92rem; }
.deney-hata { border:1px solid var(--error-line); background: var(--error-bg); color: var(--error-text);
  padding:10px 14px; border-radius:10px; margin:0 0 14px; font-size:.86rem; }
.deney-onam { border-left:3px solid var(--amber); background: color-mix(in srgb, var(--amber) 10%, transparent);
  padding:10px 14px; border-radius:8px; margin-bottom:18px; font-size:.84rem; line-height:1.5; }
.deney-alan { display:block; margin-bottom:16px; border:0; padding:0; min-width:0; }
.deney-alan > span, .deney-alan > legend { display:block; font-size:.85rem; font-weight:600; margin-bottom:6px; color: var(--label); }
.deney-alan input, .deney-alan select { width:100%; padding:9px 11px; border-radius:9px;
  border:1px solid var(--line); background: var(--field-bg); color:inherit; font-size:.9rem; font-family:inherit; }
.deney-satir { display:flex; gap:8px; }
.deney-satir input { flex:1; min-width:0; }
.deney-izgara { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; }
.deney-secenekler { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:8px; }
.deney-secenek { display:flex; flex-direction:column; gap:3px; padding:12px 14px; text-align:left; min-height:56px;
  border:1px solid var(--line); border-radius:10px; background:transparent; color:inherit; font-family:inherit;
  transition: border-color .15s ease, background-color .15s ease; }
.deney-secenek span { font-size:.78rem; color: var(--muted); }
.deney-secenek:hover { border-color: var(--blue); }
.deney-secenek.aktif { border-color: var(--blue); box-shadow: inset 0 0 0 1px var(--blue);
  background: color-mix(in srgb, var(--blue) 12%, transparent); }
.deney-birincil { display:inline-flex; align-items:center; justify-content:center; gap:8px; padding:12px 22px; min-height:46px;
  border-radius:10px; border:0; background: var(--dolgu-mavi); color:#fff; font-weight:600; font-size:.95rem; font-family:inherit;
  transition: filter .15s ease; }
.deney-birincil:not(:disabled):hover { filter: brightness(1.1); }
.deney-birincil:disabled { opacity:.45; }
.deney-ikincil { display:inline-flex; align-items:center; gap:6px; padding:9px 14px; border-radius:9px;
  border:1px solid var(--line); background:transparent; color:inherit; font-size:.84rem; font-family:inherit; }
.deney-baglanti { background:none; border:0; padding:0; color: var(--blue); font:inherit; font-size:.8rem;
  text-decoration: underline; text-underline-offset: 2px; }
.deney-cubuk { height:6px; border-radius:3px; background: var(--control-bg); overflow:hidden; }
.deney-cubuk div { height:100%; background: var(--blue); transition:width .3s; }
.deney-cubuk-genis { width:min(320px, 100%); margin-bottom:22px; }

.deney-adimlar { list-style:none; display:flex; margin:0 0 22px; padding:0; width:100%; }
.deney-adim { flex:1; display:flex; flex-direction:column; align-items:center; gap:6px; position:relative;
  font-size:.78rem; color: var(--muted); }
.deney-adim:not(:first-child)::before { content:""; position:absolute; top:14px; right:50%; width:100%; height:2px;
  background: var(--line); z-index:0; }
.deney-adim.tamam:not(:first-child)::before, .deney-adim.aktif:not(:first-child)::before { background: var(--blue); }
.deney-adim-nokta { position:relative; z-index:1; width:30px; height:30px; border-radius:50%; display:grid; place-items:center;
  font-weight:700; font-size:.85rem; background: var(--panel); border:2px solid var(--line); color: var(--muted); }
.deney-adim.aktif .deney-adim-nokta { border-color: var(--blue); color: var(--blue); }
.deney-adim.aktif { color: var(--heading); font-weight:600; }
.deney-adim.tamam .deney-adim-nokta { background: var(--dolgu-mavi); border-color: var(--dolgu-mavi); color:#fff; }

.deney-senaryo-basi { margin-bottom:14px; }
.deney-senaryo-basi h2 { margin:0 0 4px; }
.deney-senaryo-basi p { margin:0; font-size:.85rem; color: var(--muted); }
.deney-metin { white-space:pre-wrap; font-size:1rem; line-height:1.7; padding:18px 20px;
  border-radius:12px; background: var(--panel-soft); border:1px solid var(--line); margin-bottom:18px; }
.deney-yonerge { font-size:.86rem; color: var(--muted); margin:0 0 20px; }

.deney-olcek { border:1px solid var(--line); border-radius:12px; padding:0 18px 4px; margin:0 0 16px; min-width:0; }
.deney-olcek-basi { display:flex; align-items:center; gap:10px; width:calc(100% + 36px); margin:0 -18px 12px;
  padding:12px 18px; float:left; border-bottom:1px solid var(--line); background: var(--panel-soft);
  border-radius:12px 12px 0 0; }
.deney-olcek-basi + * { clear:both; }
.deney-olcek-no { font-size:.72rem; font-weight:700; text-transform:uppercase; letter-spacing:.04em; color: var(--blue); }
.deney-olcek-ad { font-weight:700; font-size:1rem; color: var(--heading); }
.deney-olcek-sayac { margin-left:auto; font-size:.8rem; color: var(--muted); font-variant-numeric: tabular-nums;
  display:inline-flex; align-items:center; }
.deney-olcek-sayac.tamam { color: var(--green); }
.deney-olcek-aciklama { font-size:.84rem; color: var(--muted); margin:0 0 14px; }

.deney-madde { margin:0 -10px 14px; padding:8px 10px; border-radius:10px; transition: background-color .3s ease; }
.deney-madde.vurgulu { background: color-mix(in srgb, var(--amber) 14%, transparent); box-shadow: inset 3px 0 0 var(--amber); }
.deney-madde p { margin:0 0 8px; font-size:.93rem; line-height:1.5; }
.deney-likert { display:grid; grid-template-columns:repeat(5,1fr); gap:6px; }
.deney-likert-dugme { display:flex; flex-direction:column; align-items:center; justify-content:center; gap:4px;
  min-height:64px; padding:8px 4px; border:1px solid var(--line); border-radius:10px; background: var(--field-bg);
  color:inherit; font-family:inherit; transition: border-color .15s ease, background-color .15s ease; }
.deney-likert-dugme:hover { border-color: var(--blue); }
.deney-likert-sayi { font-weight:700; font-size:1.05rem; }
.deney-likert-etiket { font-size:.72rem; line-height:1.25; text-align:center; color: var(--muted); }
.deney-likert-dugme.aktif { background: var(--dolgu-mavi); border-color: var(--dolgu-mavi); color:#fff; }
.deney-likert-dugme.aktif .deney-likert-etiket { color:#fff; }
.deney-likert-uclar { display:none; }

.deney-gonder { position:sticky; bottom:0; z-index:5; margin:8px -22px -22px; padding:14px 22px;
  background: var(--panel); border-top:1px solid var(--line); border-radius:0 0 14px 14px; }
.deney-gonder-satir { display:flex; align-items:center; gap:16px; }
.deney-gonder-durum { flex:1; display:flex; flex-direction:column; gap:6px; font-size:.85rem; min-width:0; }
.deney-gonder-durum .deney-baglanti { align-self:flex-start; }

.deney-onay-ikon { color: var(--green); margin: 4px 0 10px; }

.deney-yukleniyor { display:flex; align-items:center; gap:9px; padding:18px 0; font-size:.9rem; color: var(--muted); }
.donuyor { animation:deney-don 1s linear infinite; }
@keyframes deney-don { to { transform:rotate(360deg); } }
.deney-uygulayici { margin-top:22px; border-top:1px dashed var(--line); padding-top:12px; }
.deney-gonder + .deney-uygulayici { margin-top:34px; }
.deney-uygulayici-basi { display:flex; align-items:center; gap:7px; background:transparent; border:0;
  color: var(--muted); font-size:.76rem; padding:0; font-family:inherit; }
.deney-uygulayici-govde { margin-top:10px; font-size:.79rem; line-height:1.7; }
.deney-uygulayici-govde p { margin:0 0 4px; }
.deney-uyari { color: var(--red); font-weight:600; }

@media (max-width: 560px) {
  .deney-sayfa { padding: 16px 12px 48px; }
  .deney-kart { padding: 16px; }
  .deney-olcek { padding: 0 12px 4px; }
  .deney-olcek-basi { width:calc(100% + 24px); margin:0 -12px 12px; padding:10px 12px; flex-wrap:wrap; gap:4px 10px; }
  .deney-olcek-no { width:100%; }
  .deney-likert { gap:5px; }
  .deney-likert-dugme { min-height:52px; }
  .deney-likert-etiket { display:none; }
  .deney-likert-uclar { display:flex; justify-content:space-between; gap:6px; margin-top:5px;
    font-size:.7rem; color: var(--muted); }
  .deney-likert-uclar span { flex:1; }
  .deney-likert-uclar span:nth-child(2) { text-align:center; }
  .deney-likert-uclar span:last-child { text-align:right; }
  .deney-gonder { margin:8px -16px -16px; padding:12px 16px; }
  .deney-gonder-satir { flex-direction:column; align-items:stretch; gap:10px; }
  .deney-gonder .deney-birincil { width:100%; }
  .deney-metin { padding:14px; font-size:.97rem; }
}
    `}</style>
  );
}
