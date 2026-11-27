"""
deney.py — Kontrollü kullanıcı deneyi altyapısı (İP4)
======================================================

Yüz yüze prototip deneyi için: kol atama, senaryo yönetimi, yanıt kaydı.

DENEY TASARIMI
--------------
Üç kollu, KATILIMCILAR ARASI (between-subjects) tasarım. Her katılımcı tek bir
kola atanır ve o kolda birden fazla senaryo görür.

  A) teknik_rapor  — geleneksel teknik rapor (KONTROL)
  B) ham           — ton yönergesiz düz BDM çıktısı (ABLASYON)
  C) tonlu         — kişiselleştirilmiş, tona göre ayarlanmış BDM çıktısı

Neden üç kol:
  A vs B  -> H1'in "doğal dil" bileşenini test eder
  B vs C  -> H2'nin "ton yönetimi" bileşenini test eder
  A vs C  -> sistemin bütününün etkisi

İki kollu tasarımda (sadece A vs C) gözlenen farkın doğal dilden mi ton
yönetiminden mi geldiği AYRIŞTIRILAMAZ. Başvurudaki tasarım iki kolluydu;
üçüncü kol bu nedenle eklendi.

KİŞİSELLEŞTİRME KURALI (C kolu)
--------------------------------
Projenin özgünlük iddiası "kullanıcının bağlamına göre ton değiştirme". C
kolunda ton, katılımcının bildirdiği endişe düzeyine göre seçilir:

  yüksek endişe -> yatistirici    (önce kontrol duygusu)
  orta endişe   -> bilgilendirici (nötr açıklama)
  düşük endişe  -> eyleme_yonelik (doğrudan adımlar)

Bu kuralın kendisi test edilen şeydir; keyfî değil, H2'nin operasyonel tanımıdır.

KÖRLEME
-------
Katılımcı hangi kolda olduğunu bilmez ve diğer kolların çıktısını görmez.
Uygulayıcı (sen) kolu görebilirsin — çift körleme tek kişilik bir projede
mümkün değil, bunu tezde sınırlılık olarak yaz.

ÖLÇEK MADDELERİNİN DURUMU
-------------------------
Maddeler doğrulanmış ölçeklerden UYARLANDI (kaynak eşlemesi:
docs/deney/olcek_kaynak_eslemesi.md). Her ölçekteki "kaynak" alanı dayanağı
belirtir; etiketleme reclass_tables ile aynı ([K] kaynaklı / [U] uyarlama /
[E] eksper ataması). Kesinleşme için hâlâ gereken iki adım:
  1. Kapsam geçerliliği: en az 3 uzmanla Davis tekniği (form aynı dokümanda).
  2. Pilot (n≈10-15) ve Cronbach alfa >= 0.70 kontrolü
     (tools/istatistik_analiz.py --pilot bunu hesaplar).
Bu iki adım tamamlanmadan toplanan veri tezde ana analiz olarak kullanılamaz.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DENEY_DIR = PROJECT_ROOT / "outputs" / "deney"
KATILIMCI_KAYIT = DENEY_DIR / "katilimcilar.jsonl"
YANIT_KAYIT = DENEY_DIR / "yanitlar.jsonl"

KOLLAR = ("teknik_rapor", "ham", "tonlu")

ENDISE_TON_ESLESMESI = {
    "yüksek": "yatistirici",
    "orta": "bilgilendirici",
    "düşük": "eyleme_yonelik",
}


# ---------------------------------------------------------------------------
# SENARYOLAR
#
# Tüm katılımcılara AYNI konumlar gösterilir — deneysel kontrol için şart.
# Katılımcının haritada serbestçe tıklaması, her katılımcının farklı bir uyarana
# maruz kalması demek olurdu ve kollar karşılaştırılamazdı.
#
# Üç senaryo düşük / orta / yüksek risk bandını kapsayacak şekilde seçildi.
# Koordinatlar EPSG:4326 (WGS84).
# ---------------------------------------------------------------------------

SENARYOLAR = [
    {
        "kod": "S1",
        "ad": "Sahil yerleşimi",
        "lat": 38.1940, "lon": 26.7890,
        "afet_tipi": "DEPREM",
        "bina": {"yapim_yili": 1992, "malzeme_secim": 1, "bina_kat_sayisi": 6,
                 "oturulan_kat": 4, "asansor_var": 1},
        "aciklama": "Alüvyon zemin üzerinde, 1998 yönetmeliği öncesi betonarme bina.",
    },
    {
        "kod": "S2",
        "ad": "İç kesim, yamaç",
        "lat": 38.2900, "lon": 26.9200,
        "afet_tipi": "HEYELAN",
        "bina": {"yapim_yili": 2010, "malzeme_secim": 1, "bina_kat_sayisi": 3,
                 "oturulan_kat": 2, "asansor_var": 0},
        "aciklama": "Eğimli arazide, güncel yönetmeliğe göre yapılmış bina.",
    },
    {
        "kod": "S3",
        "ad": "Dere yatağı yakını",
        "lat": 38.2300, "lon": 26.9000,
        "afet_tipi": "SEL",
        "bina": {"yapim_yili": 1985, "malzeme_secim": 2, "bina_kat_sayisi": 2,
                 "oturulan_kat": 1, "asansor_var": 0},
        "aciklama": "Akarsuya yakın, zemin katta oturulan yığma yapı.",
    },
]


# ---------------------------------------------------------------------------
# ÖLÇEKLER
#
# Kaynak eşlemesi ve madde-madde dayanak: docs/deney/olcek_kaynak_eslemesi.md
# "kaynak" alanı arayüzde gösterilmez; tez ve etik başvurusu için metadata.
# Uzman görüşü + pilot tamamlanmadan NİHAİ sayılmaz (üstteki docstring).
# ---------------------------------------------------------------------------

OLCEKLER = {
    "anlasilirlik": {
        "baslik": "Anlaşılırlık",
        "aciklama": "Okuduğunuz metin hakkında ne ölçüde katılıyorsunuz?",
        "kaynak": "[U] PEMAT anlaşılabilirlik boyutundan öz-bildirime uyarlandı "
                  "(Shoemaker, Wolf & Brach, 2014); madde 4 teach-back "
                  "yaklaşımından.",
        "maddeler": [
            "Metinde anlatılanları kolayca anladım.",
            "Riskimin ne düzeyde olduğunu net biçimde kavradım.",
            "Metinde anlamadığım teknik terim veya ifadeler vardı.",   # TERS KODLANIR
            "Bu bilgiyi bir başkasına kendi cümlelerimle anlatabilirim.",
        ],
        "ters_kodlanan": [2],   # 0-tabanlı indeks
    },
    "eylem_niyeti": {
        "baslik": "Harekete geçme niyeti",
        "aciklama": "Bu bilgiyi okuduktan sonra, önümüzdeki bir ay için "
                    "aşağıdakilere ne ölçüde katılıyorsunuz?",
        "kaynak": "[U] Niyet kalıbı Planlı Davranış Teorisi'nden (Ajzen, 2002); "
                  "madde içerikleri Genel Afete Hazırlıklı Olma İnanç "
                  "Ölçeği'nin davranış alanından (İnal, Altıntaş & Doğan, 2018) "
                  "uyarlandı.",
        "maddeler": [
            "Evimde afete hazırlık (afet çantası, eşya sabitleme, su/gıda "
            "stoğu) yapmaya niyetliyim.",
            "Binamın güvenlik durumu hakkında bilgi almak için harekete "
            "geçmeye niyetliyim.",
            "Bu bilgiyi ailemle veya komşularımla paylaşmayı planlıyorum.",
            "En yakın toplanma alanının yerini öğrenmeye/teyit etmeye "
            "niyetliyim.",
        ],
        "ters_kodlanan": [],
    },
    "duygusal_tepki": {
        "baslik": "Duygusal tepki",
        "aciklama": "Metni okurken kendinizi nasıl hissettiniz?",
        "kaynak": "[U] Kaygı/sakinlik maddeleri STAI-6 kısa formundan (Marteau "
                  "& Bekker, 1992; Türkçe STAI: Öner & Le Compte, 1983); "
                  "kontrol hissi EPPM öz-yeterlik kavramından (Witte, 1996). "
                  "Madde 3 [E].",
        "maddeler": [
            "Metni okurken kendimi endişeli hissettim.",               # TERS KODLANIR
            "Metni okuduktan sonra durumu kontrol edebileceğimi hissettim.",
            "Metin beni gereksiz yere korkuttu.",                      # TERS KODLANIR
            "Metni okurken kendimi sakin hissettim.",
        ],
        "ters_kodlanan": [0, 2],
    },
}

LIKERT = [
    (1, "Kesinlikle katılmıyorum"),
    (2, "Katılmıyorum"),
    (3, "Kararsızım"),
    (4, "Katılıyorum"),
    (5, "Kesinlikle katılıyorum"),
]


# ---------------------------------------------------------------------------
# KOL ATAMA
# ---------------------------------------------------------------------------

def _kayitlari_oku(dosya: Path) -> list[dict]:
    if not dosya.exists():
        return []
    kayitlar = []
    with dosya.open(encoding="utf-8") as f:
        for satir in f:
            satir = satir.strip()
            if satir:
                try:
                    kayitlar.append(json.loads(satir))
                except json.JSONDecodeError:
                    continue
    return kayitlar


def kol_ata(katilimci_kodu: str) -> dict:
    """
    Katılımcıyı bir kola atar. Aynı kod tekrar sorulursa AYNI kolu döndürür.

    Denge: her yeni katılımcı, o ana kadar EN AZ kullanılmış kola atanır.
    Basit rastgele atamaya göre küçük örneklemlerde çok daha dengeli sonuç verir
    (n=30'da rastgele atama 14/8/8 gibi dağılabilir; bu yöntem 10/10/10 verir).
    Eşitlik durumunda katılımcı kodunun hash'i belirler — yani sıradaki kol
    tahmin edilebilir değildir ama dağılım dengeli kalır.
    """
    katilimci_kodu = (katilimci_kodu or "").strip()
    if not katilimci_kodu:
        raise ValueError("Katılımcı kodu boş olamaz.")

    mevcut = _kayitlari_oku(KATILIMCI_KAYIT)
    for k in mevcut:
        if k.get("katilimci_kodu") == katilimci_kodu:
            return {"kol": k["kol"], "yeni": False,
                    "endise_duzeyi": k.get("endise_duzeyi", "orta")}

    sayim = {kol: sum(1 for k in mevcut if k.get("kol") == kol) for kol in KOLLAR}
    en_az = min(sayim.values())
    adaylar = sorted(kol for kol, s in sayim.items() if s == en_az)
    h = int(hashlib.sha256(katilimci_kodu.encode("utf-8")).hexdigest(), 16)
    kol = adaylar[h % len(adaylar)]

    return {"kol": kol, "yeni": True, "kol_dagilimi": sayim}


def katilimci_kaydet(katilimci_kodu: str, kol: str, endise_duzeyi: str,
                     demografik: dict | None = None) -> None:
    DENEY_DIR.mkdir(parents=True, exist_ok=True)
    kayit = {
        "katilimci_kodu": katilimci_kodu,
        "kol": kol,
        "endise_duzeyi": endise_duzeyi,
        "demografik": demografik or {},
        "zaman": datetime.now(timezone.utc).isoformat(),
    }
    with KATILIMCI_KAYIT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(kayit, ensure_ascii=False) + "\n")


def ton_sec(kol: str, endise_duzeyi: str) -> str:
    """Kola ve katılımcı bağlamına göre hangi ton üretilecek."""
    if kol == "teknik_rapor":
        return "teknik_rapor"
    if kol == "ham":
        return "ham"
    return ENDISE_TON_ESLESMESI.get((endise_duzeyi or "orta").strip().lower(),
                                    "bilgilendirici")


# ---------------------------------------------------------------------------
# YANIT KAYDI
# ---------------------------------------------------------------------------

def _puanla(olcek_adi: str, yanitlar: list[int]) -> float | None:
    """Ters kodlanan maddeleri çevirip ölçek ortalamasını döndürür."""
    olcek = OLCEKLER.get(olcek_adi)
    if not olcek or not yanitlar:
        return None
    ters = set(olcek.get("ters_kodlanan", []))
    puanlar = []
    for i, y in enumerate(yanitlar):
        if y is None:
            continue
        y = int(y)
        puanlar.append(6 - y if i in ters else y)
    return round(sum(puanlar) / len(puanlar), 3) if puanlar else None


def yanit_kaydet(kayit: dict) -> dict:
    """
    Bir senaryo için katılımcı yanıtını kaydeder ve ölçek puanlarını hesaplar.

    Beklenen kayit:
      katilimci_kodu, kol, ton, senaryo_kodu, gosterilen_metin,
      olcek_yanitlari: {"anlasilirlik": [4,5,2,4], "eylem_niyeti": [...], ...},
      okuma_suresi_sn (opsiyonel)
    """
    DENEY_DIR.mkdir(parents=True, exist_ok=True)
    yanitlar = kayit.get("olcek_yanitlari", {}) or {}
    puanlar = {ad: _puanla(ad, yanitlar.get(ad, [])) for ad in OLCEKLER}

    tam = dict(kayit)
    tam["olcek_puanlari"] = puanlar
    tam["zaman"] = datetime.now(timezone.utc).isoformat()

    with YANIT_KAYIT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(tam, ensure_ascii=False) + "\n")

    return {"kaydedildi": True, "olcek_puanlari": puanlar}


def durum() -> dict:
    """Deneyin o anki durumu — kaç katılımcı, kollara dağılım, kaç yanıt."""
    katilimcilar = _kayitlari_oku(KATILIMCI_KAYIT)
    yanitlar = _kayitlari_oku(YANIT_KAYIT)
    dagilim = {kol: sum(1 for k in katilimcilar if k.get("kol") == kol) for kol in KOLLAR}
    return {
        "katilimci_sayisi": len(katilimcilar),
        "kol_dagilimi": dagilim,
        "yanit_sayisi": len(yanitlar),
        "senaryo_sayisi": len(SENARYOLAR),
        "beklenen_yanit": len(katilimcilar) * len(SENARYOLAR),
    }
