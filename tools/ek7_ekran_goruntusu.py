#!/usr/bin/env python3
"""Ek 7 ekran görüntülerini üretir — yerel model ve bulut API için ayrı ayrı.

Neden script: 30.08.2026'da elle alınan karelerin hiçbirinde modelin
tamamlanmış bir cevabı yoktu (biri analiz başlamadan, biri kartlar iskelet
hâldeyken, biri model hâlâ yazarken alınmıştı). Bu script kareyi almadan önce
üretimin GERÇEKTEN bittiğini yoklar: gönder düğmesindeki bekleme simgesi
kaybolana, "yazıyor" noktaları gidene ve metin uzamayı durdurana kadar bekler.
Sabit süre saymaz — yerel model yanıtı 50 saniyeyi bulabiliyor.

Aynı senaryo iki sağlayıcıda birebir aynı girdiyle koşturulur (aynı harita
noktası, aynı bina, aynı sorular), böylece karşılaştırma adil olur. Yanıt
süreleri ölçülüp JSON'a yazılır; rapordaki karşılaştırma tablosu bu sayılardan
beslenir.

Ön koşullar — script sunucu BAŞLATMAZ, ayakta olmalarını bekler:

    # Yerel model için (üç ayrı terminal)
    llama-server -m ~/Downloads/disasterai-Q4_K_M.gguf --host 127.0.0.1 \
        --port 11434 -c 3072 --jinja -ngl 0 -t 6
    MODEL_SAGLAYICI=yerel MPLCONFIGDIR=/private/tmp/matplotlib-cache \
        ayse-env/bin/python -m uvicorn backend.main:app --port 8514
    cd frontend && npm run dev

    # Sonra
    ayse-env/bin/python tools/ek7_ekran_goruntusu.py --saglayici yerel

    # Bulut karşılaştırması için backend'i MODEL_SAGLAYICI olmadan başlat
    ayse-env/bin/python tools/ek7_ekran_goruntusu.py --saglayici bulut

DİKKAT: `-ngl 0` şart — M2 8 GB'ta Metal "Compute error" veriyor.
"""

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

try:
    import websocket  # websocket-client
except ImportError:
    sys.exit("websocket-client gerekli:  ayse-env/bin/pip install websocket-client")

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Senaryo — iki sağlayıcıda da birebir aynı olmalı, yoksa karşılaştırma anlamsız.
BINA = {"Yapı Malzemesi": "Betonarme", "Toplam Kat": "5",
        "Oturulan Kat": "2", "Yapım Yılı": "2000"}
# Harita tıklaması: Leaflet kabının sol üstüne göre oran (0-1). Sabit oran +
# sabit başlangıç görünümü = her koşuda aynı koordinat.
HARITA_ORAN = (0.50, 0.55)
SORULAR = [
    "Risk skorum ne anlama geliyor?",
    "Şimdi ne yapmalıyım?",
    "Skoru nasıl düşürebilirim?",
    "Bu skor bina yaşından mı yoksa konumdan mı kaynaklanıyor?",
]

# Bir yanıtın bittiğine karar verme ölçütü: aşağıdakilerin HEPSİ doğru olmalı
# ve metin ÜST ÜSTE iki yoklamada aynı uzunlukta kalmalı.
BITTI_JS = """
(() => {
  const spin = document.querySelector('.chat-form button[type="submit"] .spin');
  const yaziyor = document.querySelector('.typing-dots');
  const balonlar = document.querySelectorAll('.chat-row.assistant .chat-message');
  const son = balonlar.length ? balonlar[balonlar.length - 1].textContent.trim() : '';
  return JSON.stringify({
    calisiyor: !!spin || !!yaziyor,
    uzunluk: son.length,
    metin: son,
  });
})()
"""


class Tarayici:
    """Chrome'u DevTools protokolü üzerinden süren ince bir sarmalayıcı."""

    def __init__(self, genislik=1600, yukseklik=1000):
        self.genislik, self.yukseklik = genislik, yukseklik
        self.profil = tempfile.mkdtemp(prefix="ek7-chrome-")
        self.surec = None
        self.ws = None
        self._id = 0

    def _bos_port(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def baslat(self):
        port = self._bos_port()
        self.surec = subprocess.Popen(
            [CHROME, "--headless=new", f"--remote-debugging-port={port}",
             f"--user-data-dir={self.profil}", "--remote-allow-origins=*",
             "--no-first-run", "--no-default-browser-check", "--disable-gpu",
             f"--window-size={self.genislik},{self.yukseklik}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        hedef = None
        for _ in range(60):
            time.sleep(0.5)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as y:
                    sekmeler = json.load(y)
                hedef = next((s for s in sekmeler if s.get("type") == "page"), None)
                if hedef:
                    break
            except Exception:
                continue
        if not hedef:
            raise RuntimeError("Chrome DevTools ucu açılmadı")
        # suppress_origin: websocket-client'ın gönderdiği Origin başlığını
        # Chrome 403'le reddediyor.
        self.ws = websocket.create_connection(
            hedef["webSocketDebuggerUrl"], suppress_origin=True, timeout=180)
        self.cmd("Page.enable")
        self.cmd("Runtime.enable")
        self.cmd("Emulation.setDeviceMetricsOverride", {
            "width": self.genislik, "height": self.yukseklik,
            "deviceScaleFactor": 2, "mobile": False})
        return self

    def cmd(self, yontem, parametre=None):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": yontem,
                                 "params": parametre or {}}))
        while True:
            yanit = json.loads(self.ws.recv())
            if yanit.get("id") == self._id:
                if "error" in yanit:
                    raise RuntimeError(f"{yontem}: {yanit['error']}")
                return yanit.get("result", {})

    def js(self, ifade):
        r = self.cmd("Runtime.evaluate", {"expression": ifade, "returnByValue": True,
                                          "awaitPromise": True})
        return r.get("result", {}).get("value")

    def bekle(self, ifade, sure=180, aralik=0.5, aciklama=""):
        son = time.time() + sure
        while time.time() < son:
            if self.js(ifade):
                return True
            time.sleep(aralik)
        raise TimeoutError(f"Koşul {sure} sn içinde sağlanmadı: {aciklama or ifade[:70]}")

    def git(self, url):
        self.cmd("Page.navigate", {"url": url})
        self.bekle("document.readyState === 'complete'", 60, aciklama="sayfa yüklenmesi")

    def tikla(self, x, y):
        for tur in ("mousePressed", "mouseReleased"):
            self.cmd("Input.dispatchMouseEvent", {
                "type": tur, "x": x, "y": y, "button": "left",
                "clickCount": 1, "buttons": 1 if tur == "mousePressed" else 0})
            time.sleep(0.05)

    def kare(self, yol):
        r = self.cmd("Page.captureScreenshot", {"format": "png"})
        with open(yol, "wb") as f:
            f.write(base64.b64decode(r["data"]))
        return os.path.getsize(yol)

    def kapat(self):
        try:
            if self.ws:
                self.ws.close()
        finally:
            if self.surec:
                self.surec.terminate()
                try:
                    self.surec.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.surec.kill()
            shutil.rmtree(self.profil, ignore_errors=True)


# --- Arayüzle konuşan yardımcılar ---

# React denetimli girdilerde `el.value = x` çalışmaz; React'in kendi
# izleyicisini atlatmak için yerel setter'ı çağırıp olayı elle yaymak gerekir.
ALAN_YAZ_JS = """
(function(etiket, deger) {
  const etiketler = [...document.querySelectorAll('label')];
  const l = etiketler.find(e => e.textContent.trim().startsWith(etiket));
  if (!l) return 'etiket bulunamadı: ' + etiket;
  let alan = l.control;
  if (!alan) {
    let k = l.parentElement;
    alan = k && (k.querySelector('input') || k.querySelector('select'));
  }
  if (!alan) return 'alan bulunamadı: ' + etiket;
  const proto = alan.tagName === 'SELECT'
    ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(alan, deger);
  alan.dispatchEvent(new Event('input', { bubbles: true }));
  alan.dispatchEvent(new Event('change', { bubbles: true }));
  return 'ok';
})(%s, %s)
"""


def alan_doldur(t, etiket, deger):
    sonuc = t.js(ALAN_YAZ_JS % (json.dumps(etiket), json.dumps(deger)))
    if sonuc != "ok":
        raise RuntimeError(f"Bina alanı doldurulamadı — {sonuc}")


def dugmeye_tikla(t, metin):
    """Metnine göre düğme bulup gerçek fare olayıyla tıklar."""
    kutu = t.js("""
      (() => {
        const d = [...document.querySelectorAll('button')]
          .find(b => b.textContent.trim().startsWith(%s) && !b.disabled);
        if (!d) return null;
        const r = d.getBoundingClientRect();
        return JSON.stringify([r.left + r.width / 2, r.top + r.height / 2]);
      })()
    """ % json.dumps(metin))
    if not kutu:
        raise RuntimeError(f"Düğme bulunamadı ya da pasif: {metin}")
    x, y = json.loads(kutu)
    t.tikla(x, y)


def yanit_bekle(t, onceki_sayi, azami=300):
    """Yeni asistan balonu tamamlanana kadar bekler; süreyi saniye döndürür.

    İki aşama: (1) yeni balon belirsin, (2) üretim bitsin. Bitiş ölçütü
    BITTI_JS ile okunur ve metin uzunluğunun üst üste iki yoklamada
    değişmemesi aranır — akış hâlinde yazan model yarıda yakalanmasın.
    """
    basla = time.time()
    t.bekle(
        "document.querySelectorAll('.chat-row.assistant .chat-message').length > %d" % onceki_sayi,
        60, aciklama="yeni asistan balonu")

    kararli, onceki_uzunluk = 0, -1
    while time.time() - basla < azami:
        durum = json.loads(t.js(BITTI_JS))
        if not durum["calisiyor"] and durum["uzunluk"] > 0:
            kararli = kararli + 1 if durum["uzunluk"] == onceki_uzunluk else 0
            if kararli >= 2:  # iki ardışık yoklamada aynı uzunluk
                return round(time.time() - basla, 1), durum["metin"]
        else:
            kararli = 0
        onceki_uzunluk = durum["uzunluk"]
        time.sleep(1.0)
    raise TimeoutError(f"Yanıt {azami} sn içinde tamamlanmadı")


def gonder(t):
    kutu = t.js("""
      (() => {
        const d = document.querySelector('.chat-form button[type="submit"]');
        if (!d || d.disabled) return null;
        const r = d.getBoundingClientRect();
        return JSON.stringify([r.left + r.width / 2, r.top + r.height / 2]);
      })()
    """)
    if not kutu:
        raise RuntimeError("Gönder düğmesi pasif — girdi boş olabilir")
    x, y = json.loads(kutu)
    t.tikla(x, y)


def senaryo(t, url, saglayici, cikti):
    """Tek sağlayıcı için bütün akışı koşturur, kareleri ve süreleri döndürür."""
    os.makedirs(cikti, exist_ok=True)
    ek = "yerel" if saglayici == "yerel" else "bulut"
    kayit = {"saglayici": saglayici, "kareler": [], "yanitlar": []}
    n = [0]

    def cek(ad):
        n[0] += 1
        yol = os.path.join(cikti, f"{n[0]:02d}_{ad}_{ek}.png")
        boyut = t.kare(yol)
        kayit["kareler"].append({"dosya": os.path.basename(yol), "bayt": boyut})
        print(f"    📸 {os.path.basename(yol)}  ({boyut // 1024} KB)")

    t.git(url)
    t.bekle("!!document.querySelector('.leaflet-container')", 60, aciklama="harita")
    t.bekle("!!document.querySelector('.model-rozeti')", 30, aciklama="model rozeti")
    time.sleep(2.0)  # karo yüklemesi otursun

    rozet = t.js("document.querySelector('.model-rozeti').textContent.trim()")
    beklenen = "Yerel model" if saglayici == "yerel" else "Bulut API"
    if beklenen not in rozet:
        raise RuntimeError(
            f"Rozet '{rozet}' diyor, '{beklenen}' bekleniyordu — backend yanlış "
            f"MODEL_SAGLAYICI ile çalışıyor olabilir.")
    kayit["rozet"] = rozet
    print(f"    rozet: {rozet}")

    for etiket, deger in BINA.items():
        alan_doldur(t, etiket, deger)
    cek("arayuz_bina_bilgileri")

    kutu = json.loads(t.js("""
      (() => { const r = document.querySelector('.leaflet-container').getBoundingClientRect();
               return JSON.stringify([r.left, r.top, r.width, r.height]); })()
    """))
    t.tikla(kutu[0] + kutu[2] * HARITA_ORAN[0], kutu[1] + kutu[3] * HARITA_ORAN[1])
    t.bekle("!!document.querySelector('.primary-button:not([disabled])')", 30,
            aciklama="nokta seçimi")
    kayit["koordinat"] = t.js(
        "(document.body.innerText.match(/\\d{2}\\.\\d{4,5},\\s*\\d{2}\\.\\d{4,5}/) || [''])[0]")
    print(f"    koordinat: {kayit['koordinat']}")

    dugmeye_tikla(t, "Analizi Başlat")
    # Analiz bitti = skor artık "--" değil VE hiçbir iskelet kart kalmadı.
    t.bekle("""
      (() => {
        const s = document.querySelector('.gauge-reading strong');
        return s && s.textContent.trim() !== '--'
               && document.querySelectorAll('.skeleton').length === 0;
      })()
    """, 240, aciklama="analiz sonucu")
    time.sleep(1.5)
    kayit["risk_skoru"] = t.js("document.querySelector('.gauge-reading strong').textContent.trim()")
    print(f"    risk skoru: {kayit['risk_skoru']}")
    cek("analiz_sonucu")

    # Asistan balonunun metni yok (ikon), o yüzden sınıfından bulup tıklıyoruz.
    kutu = json.loads(t.js("""
      (() => { const r = document.querySelector('.chat-fab').getBoundingClientRect();
               return JSON.stringify([r.left + r.width / 2, r.top + r.height / 2]); })()
    """))
    t.tikla(kutu[0], kutu[1])
    t.bekle("!!document.querySelector('.chat-panel')", 30, aciklama="sohbet paneli")
    time.sleep(1.0)
    cek("asistan_acildi")

    for i, soru in enumerate(SORULAR, start=1):
        print(f"    soru {i}/{len(SORULAR)}: {soru}")
        onceki = t.js("document.querySelectorAll('.chat-row.assistant .chat-message').length")
        t.js("""
          (() => {
            const g = document.querySelector('.chat-form input');
            Object.getOwnPropertyDescriptor(
              window.HTMLInputElement.prototype, 'value').set.call(g, %s);
            g.dispatchEvent(new Event('input', { bubbles: true }));
          })()
        """ % json.dumps(soru))
        time.sleep(0.4)
        gonder(t)
        sure, metin = yanit_bekle(t, onceki)
        print(f"      ✓ {sure} sn, {len(metin)} karakter")
        kayit["yanitlar"].append({"soru": soru, "saniye": sure,
                                  "karakter": len(metin), "metin": metin})
        time.sleep(0.8)
        cek(f"sohbet_{i}")

    return kayit


def main():
    global HARITA_ORAN
    a = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--saglayici", choices=["yerel", "bulut"], required=True)
    a.add_argument("--url", default="http://127.0.0.1:5173")
    a.add_argument("--cikti", default="outputs/ekran_goruntuleri_v2")
    a.add_argument("--api", default="http://127.0.0.1:8514/api/health")
    a.add_argument("--harita-oran", default=",".join(str(o) for o in HARITA_ORAN),
                   help="Haritaya tıklanacak nokta, kabın soluna/üstüne göre oran "
                        "(örn. 0.50,0.48). İki sağlayıcıda AYNI olmalı.")
    p = a.parse_args()
    HARITA_ORAN = tuple(float(x) for x in p.harita_oran.split(","))

    # Backend gerçekten istenen sağlayıcıda mı? Yanlışsa kare almanın anlamı yok.
    try:
        with urllib.request.urlopen(p.api, timeout=5) as y:
            saglik = json.load(y)
    except Exception as e:
        sys.exit(f"Backend'e ulaşılamadı ({p.api}): {e}")
    if saglik.get("model_saglayici") != p.saglayici.replace("bulut", "gemini"):
        sys.exit(f"Backend '{saglik.get('model_saglayici')}' sağlayıcısında çalışıyor, "
                 f"'{p.saglayici}' istendi. Backend'i doğru MODEL_SAGLAYICI ile yeniden başlat.")
    print(f"Backend: {saglik.get('model_saglayici')} / {saglik.get('model_adi')}")

    t = Tarayici().baslat()
    try:
        kayit = senaryo(t, p.url, p.saglayici, p.cikti)
    finally:
        t.kapat()

    kayit["model_adi"] = saglik.get("model_adi")
    sureler = [y["saniye"] for y in kayit["yanitlar"]]
    kayit["ortalama_saniye"] = round(sum(sureler) / len(sureler), 1) if sureler else None
    yol = os.path.join(p.cikti, f"olcum_{p.saglayici}.json")
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(kayit, f, ensure_ascii=False, indent=2)
    print(f"\n{len(kayit['kareler'])} kare + ölçüm dosyası → {p.cikti}")
    print(f"Ortalama yanıt süresi: {kayit['ortalama_saniye']} sn")


if __name__ == "__main__":
    main()
