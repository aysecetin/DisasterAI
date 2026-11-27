"""
risk_communication.py — Cog-S&C İletişim Modülü
================================================

Bu modül, araştırma önerisindeki H2 hipotezinin altyapısıdır:

  H2: Geliştirilen BDM Modülü, aynı mekânsal veriye dayalı olarak, kullanıcının
      profil ve sorgu bağlamına göre farklı iletişim tonları (Yatıştırıcı /
      Bilgilendirici / Eyleme Yönelik) arasında başarılı bir şekilde geçiş
      yapabilir.

Önceki durumda kodda tek bir sabit sistem mesajı vardı ve ton diye bir kavram
yoktu; yani H2 test edilemez durumdaydı. Bu modül dört çıktı modu tanımlar:

  1. "teknik_rapor"    -> KONTROL GRUBU. Deterministik, LLM kullanmaz.
                          A/B testinde geleneksel teknik rapor kolu budur.
  2. "bilgilendirici"  -> Nötr, açıklayıcı, veri odaklı.
  3. "eyleme_yonelik"  -> Emir kipi, numaralı ve zamanlanmış eylem adımları.
  4. "yatistirici"     -> Kontrol duygusu veren, panik azaltıcı çerçeveleme.

ÜÇÜNCÜ KOL (ablasyon) NEDEN ÖNEMLİ
-----------------------------------
Araştırma önerisinde A/B testi yalnızca "geleneksel rapor vs. BDM çıktısı"
olarak tanımlanmış. Bu tasarımla, gözlenen farkın *doğal dil kullanımından* mı
yoksa *ton yönetiminden* mi kaynaklandığı ayrıştırılamaz. `ton="ham"` modu bu
yüzden eklendi: ton yönergesi olmayan düz BDM çıktısı. Üç kollu tasarım
(teknik_rapor / ham / tonlu) H1'i ve H2'yi ayrı ayrı test etmeyi sağlar.

ETİK KISIT — TON DEĞİŞİR, OLGULAR DEĞİŞMEZ
-------------------------------------------
"Yatıştırıcı" ton, riski KÜÇÜMSEMEK demek değildir. Afet iletişiminde riski
olduğundan düşük göstermek doğrudan can güvenliği riskidir. Dört modun da aynı
sayısal olguları (risk skoru, fay mesafesi, bina yaşı) eksiksiz vermesi
gerekir; değişen yalnızca çerçeveleme ve dildir. `dogrula()` fonksiyonu bunu
otomatik denetler.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DENEY_KAYIT = PROJECT_ROOT / "outputs" / "deney_kayitlari.jsonl"

GECERLI_TONLAR = ("teknik_rapor", "ham", "bilgilendirici", "eyleme_yonelik", "yatistirici")

FAKTOR_ADLARI = {
    "Fay_Hattı_Uzaklığı": "fay hattına uzaklık",
    "Litoloji": "zemin/litoloji",
    "Akarsu_Uzaklığı": "akarsuya uzaklık",
    "Arazi_Kullanımı": "arazi kullanımı",
    "Eğim": "eğim",
}

MALZEME_ADLARI = {1: "betonarme", 2: "yığma", 3: "ahşap"}


# ---------------------------------------------------------------------------
# TON TANIMLARI
# ---------------------------------------------------------------------------

TON_TANIMLARI = {
    "bilgilendirici": {
        "etiket": "Bilgilendirici",
        "amac": "Kullanıcının riski DOĞRU ANLAMASINI sağlamak.",
        "yonerge": (
            "Nötr ve açıklayıcı bir dil kullan. Nedensellik kur: hangi mekânsal "
            "faktörün skora ne kadar katkı verdiğini açıkla. Emir kipi kullanma, "
            "tavsiye verme; sadece durumu betimle. Teknik terimi kullanırsan hemen "
            "yanında bir cümlelik gündelik karşılığını ver."
        ),
        "yasak": "Emir kipi, aciliyet ifadeleri, duygusal güvence cümleleri.",
        "ornek_acilis": "Seçtiğiniz konumun deprem risk skoru 3.3/5.0 olarak hesaplandı. Bu skorun en büyük bileşeni zemin yapısı:",
    },
    "eyleme_yonelik": {
        "etiket": "Eyleme Yönelik",
        "amac": "Kullanıcının SOMUT ADIM ATMASINI sağlamak.",
        "yonerge": (
            "Numaralı adımlar hâlinde yaz. Her adım tek bir eylem olsun ve zaman "
            "ufku belirt: 'Bugün', 'Bu hafta', 'Bu yıl içinde'. Her adım kullanıcının "
            "kendi başına yapabileceği bir şey olsun. Soyut tavsiye verme "
            "('önlem alın' değil, 'dolabı duvara sabitleyin')."
        ),
        "yasak": "Belirsiz tavsiyeler, uzun açıklama paragrafları, pasif cümleler.",
        "ornek_acilis": "Bu skor için bugünden başlayabileceğiniz üç adım var:",
    },
    "yatistirici": {
        "etiket": "Yatıştırıcı",
        "amac": "Kullanıcının KONTROL DUYGUSUNU korumak; paniği azaltmak.",
        "yonerge": (
            "Önce kullanıcının kontrolünde olan şeyi söyle, sonra riski tam olarak "
            "aktar. Riski asla küçümseme veya sayıları yumuşatma — aynı skoru ve "
            "aynı mesafeleri ver. Belirsizliği kabul et ('kesin tahmin edilemez'), "
            "ama hemen ardından belirli olanı söyle. Kişiselleştirilmiş ve sakin bir "
            "ton kullan."
        ),
        "yasak": (
            "Riski olduğundan düşük gösterme, 'endişelenecek bir şey yok' türü "
            "cümleler, sayıları yuvarlayıp hafifletme, boş güvence."
        ),
        "ornek_acilis": "Bu bilgiyi şimdi öğreniyor olmanız aslında en önemli avantajınız. Durum şu:",
    },
    "ham": {
        "etiket": "Ham (ablasyon kolu)",
        "amac": "Ton yönergesi OLMADAN düz BDM çıktısı — H2 için karşılaştırma kolu.",
        "yonerge": "Verilen risk analizini kullanıcıya açıkla.",
        "yasak": "",
        "ornek_acilis": "",
    },
}


# ---------------------------------------------------------------------------
# KONTROL GRUBU — GELENEKSEL TEKNİK RAPOR (deterministik, LLM yok)
# ---------------------------------------------------------------------------

def teknik_rapor(analiz: dict) -> str:
    """
    A/B testinin KONTROL kolu: geleneksel, teknik, kişiselleştirilmemiş rapor.

    Bilerek kuru ve teknik yazılmıştır — geleneksel CBS risk raporlarının
    tipik dilini temsil eder. LLM kullanmaz, dolayısıyla her katılımcıya
    tamamen aynı biçimde sunulur (kontrol kolunun standartlaştırılması).
    """
    c = analiz.get("coordinates", {}) or {}
    olgular = analiz.get("mekansal_olgular", {}) or {}
    dokum = analiz.get("faktor_dokumu", {}) or {}
    afet = str(analiz.get("afet_tipi", "DEPREM")).upper()

    satirlar = [
        f"{afet} TEHLİKE DEĞERLENDİRME RAPORU",
        "=" * 46,
        "",
        "1. ANALİZ PARAMETRELERİ",
        f"   Koordinat (EPSG:23035): X={c.get('x', 0):.1f}  Y={c.get('y', 0):.1f}",
        f"   Koordinat (WGS84): {c.get('lat', 0):.5f} N, {c.get('lon', 0):.5f} E",
        f"   Analiz yöntemi: Ağırlıklı çakıştırma (weighted overlay)",
        f"   Hücre boyutu: 30 m",
        "",
        "2. FAKTÖR DEĞERLERİ",
    ]
    for k, v in dokum.items():
        satirlar.append(
            f"   {k:<22} sınıf={v['puan']:.1f}/5.0  ağırlık={v['agirlik']:.3f}  "
            f"katkı={v['katki']:.3f}"
        )

    satirlar += [
        "",
        "3. SKORLAR",
        f"   Bölgesel tehlike indeksi : {analiz.get('hazard_score', 0):.4f}",
        f"   Yapısal hassasiyet indeksi: {analiz.get('vulnerability_score', 0):.4f}",
        f"   Bileşik risk indeksi      : {analiz.get('risk_score', 0):.4f}",
        "",
        "4. MEKÂNSAL ÖZNİTELİKLER",
    ]
    if "en_yakin_fay_m" in olgular:
        satirlar.append(f"   En yakın fay segmentine öklidyen uzaklık: {olgular['en_yakin_fay_m']:.1f} m")
    if "en_yakin_akarsu_m" in olgular:
        satirlar.append(f"   En yakın drenaj hattına uzaklık: {olgular['en_yakin_akarsu_m']:.1f} m")
    if "litoloji" in olgular:
        satirlar.append(f"   Litolojik birim: {olgular['litoloji']}")
    if "arazi_kullanimi" in olgular:
        satirlar.append(f"   Arazi kullanım sınıfı: {olgular['arazi_kullanimi']}")

    satirlar += [
        "",
        "5. SINIFLANDIRMA",
        f"   {_seviye_metni(analiz.get('risk_score', 0))}",
        "",
        "Not: Bu rapor 1:25.000 ölçekli veri setleri üzerinden üretilmiştir.",
        "Parsel ölçeğinde bağlayıcı değildir. Zemin etüdü yerine geçmez.",
    ]
    return "\n".join(satirlar)


def _seviye_metni(skor: float) -> str:
    if skor >= 4.0:
        return "Risk sınıfı: IV-V (YÜKSEK)"
    if skor >= 3.0:
        return "Risk sınıfı: III (ORTA)"
    return "Risk sınıfı: I-II (DÜŞÜK)"


# ---------------------------------------------------------------------------
# OTOMATİK TON SEÇİMİ (bağlamdan) — Cog-S&C'nin bağlam duyarlılığı
#
# H2 "kullanıcı BAĞLAMINA göre ton değiştirme" der. Deneyde bağlam, katılımcının
# bildirdiği endişe düzeyidir (kontrollü manipülasyon için şart). Gerçek
# kullanımda ise kullanıcıya ayrıca soru sormak yerine, YAZDIĞI METİNDEN
# ihtiyacını çıkarmak daha doğaldır.
#
# Neden önce KURAL, sonra model?
#   - Denetlenebilirlik: "sistem bu tonu neden seçti?" sorusuna, eşleşen
#     ifadeleri göstererek cevap verilebilir. Saf model kararı kara kutudur.
#   - Belirlenimcilik: aynı girdi her zaman aynı tonu verir; tezde ve deneyde
#     yeniden üretilebilirlik gerekir.
#   - Maliyet: ek BDM çağrısı gerekmez.
# Kural katmanı kararsız kalırsa (eşleşme yok / berabere) endişe düzeyine
# düşülür; ileride buraya model tabanlı ikinci katman eklenebilir.
# ---------------------------------------------------------------------------

# Ağırlık mantığı: çok kelimeli kalıplar tek kelimeden güçlüdür, çünkü
# "nasıl hesaplandı" ile "nasıl hazırlanırım" aynı kelimeyi paylaşır.
TON_IPUCLARI = {
    "yatistirici": {
        "kalip": [
            ("korkuyorum", 3), ("çok korkuyorum", 4), ("korkuyor", 2),
            ("panik", 3), ("panikliyorum", 4), ("kaygılıyım", 3), ("kaygı", 2),
            ("endişeliyim", 3), ("endişe ediyorum", 3), ("tedirginim", 3),
            ("uyuyamıyorum", 4), ("uykularım kaçıyor", 4), ("stres", 2),
            ("çok kötü hissediyorum", 4), ("dehşet", 3), ("ürküyorum", 3),
            ("huzursuzum", 3), ("gerginim", 2), ("travma", 3),
            ("ölecek miyiz", 4), ("yıkılacak mı", 3), ("çocuklarım için korkuyorum", 4),
            ("güvende miyim", 2), ("başıma bir şey gelir mi", 3),
        ],
    },
    "eyleme_yonelik": {
        "kalip": [
            ("ne yapmalıyım", 4), ("ne yapayım", 4), ("ne yapabilirim", 4),
            ("nereden başlamalıyım", 4), ("nereden başlayayım", 4),
            ("nasıl hazırlanırım", 4), ("nasıl hazırlanmalıyım", 4),
            ("hazırlık", 2), ("önlem", 3), ("tedbir", 3), ("adım adım", 3),
            ("yapmam gereken", 3), ("afet çantası", 3), ("sabitle", 2),
            ("güçlendirme", 2), ("taşınmalı mıyım", 3), ("plan", 2),
            ("liste", 2), ("tavsiye", 2), ("öneri", 2), ("acilen", 3),
            ("bugün ne", 3), ("nasıl korunurum", 4),
        ],
    },
    "bilgilendirici": {
        "kalip": [
            ("nasıl hesaplandı", 4), ("nasıl hesaplanıyor", 4), ("hesaplama", 3),
            ("ne anlama geliyor", 4), ("ne demek", 3), ("neden bu kadar", 3),
            ("niçin", 2), ("açıklar mısın", 3), ("açıkla", 2), ("anlamı", 3),
            ("hangi faktör", 4), ("faktör", 2), ("hangi veri", 4), ("veri", 2),
            ("yöntem", 3), ("skor nedir", 4), ("detay", 2), ("teknik", 2),
            ("nasıl bulundu", 4), ("kaynak", 2), ("güvenilir mi", 3),
        ],
    },
}

# Kural eşleşmesi yoksa: deneydeki eşleme (docs: H2 operasyonel tanımı)
ENDISE_TON_ESLESMESI = {
    "yüksek": "yatistirici",
    "orta": "bilgilendirici",
    "düşük": "eyleme_yonelik",
}


def ton_sec(kullanici_metni: str = "", endise_duzeyi: str = "orta") -> dict:
    """
    Kullanıcının yazdığı metinden uygun iletişim tonunu seçer.

    Dönüş:
      {
        "ton": "yatistirici" | "bilgilendirici" | "eyleme_yonelik",
        "gerekce": "metinde ... ifadeleri geçiyor" | "endişe düzeyi: yüksek",
        "kaynak": "kural" | "endise_duzeyi",
        "skorlar": {ton: puan},
        "eslesenler": {ton: [eşleşen kalıplar]},
      }

    Not: Deney akışı bu fonksiyonu KULLANMAZ; orada ton kola ve bildirilen
    endişe düzeyine göre belirlenir (kontrollü manipülasyon).
    """
    metin = (kullanici_metni or "").lower().strip()
    skorlar = {ton: 0 for ton in TON_IPUCLARI}
    eslesenler = {ton: [] for ton in TON_IPUCLARI}

    for ton, veri in TON_IPUCLARI.items():
        for kalip, agirlik in veri["kalip"]:
            if kalip in metin:
                skorlar[ton] += agirlik
                eslesenler[ton].append(kalip)

    en_yuksek = max(skorlar.values())
    kazananlar = [t for t, s in skorlar.items() if s == en_yuksek]

    # Kararsızlık: hiç eşleşme yok ya da beraberlik -> endişe düzeyine düş
    if en_yuksek == 0 or len(kazananlar) > 1:
        duzey = (endise_duzeyi or "orta").strip().lower()
        ton = ENDISE_TON_ESLESMESI.get(duzey, "bilgilendirici")
        return {
            "ton": ton,
            "gerekce": (f"Metinde belirgin ipucu yok; bildirilen endişe düzeyi "
                        f"'{duzey}' kullanıldı."),
            "kaynak": "endise_duzeyi",
            "skorlar": skorlar,
            "eslesenler": {k: v for k, v in eslesenler.items() if v},
        }

    ton = kazananlar[0]
    return {
        "ton": ton,
        "gerekce": ("Metinde şu ifadeler geçiyor: "
                    + ", ".join(f"'{e}'" for e in eslesenler[ton][:4])),
        "kaynak": "kural",
        "skorlar": skorlar,
        "eslesenler": {k: v for k, v in eslesenler.items() if v},
    }


# ---------------------------------------------------------------------------
# CHAIN-OF-THOUGHT PROMPT ÜRETİMİ
# ---------------------------------------------------------------------------

def cot_prompt(analiz: dict, ton: str, kullanici_sorusu: str = "", endise_duzeyi: str = "orta") -> str:
    """
    Araştırma önerisindeki "Chain-of-Thought yapısıyla optimize edilmiş prompt".

    CBS çıktısı (nicel veri) + kullanıcının duygusal durumu + hedeflenen iletişim
    tonu, modele adımlanmış bir akıl yürütme yapısı içinde verilir.
    """
    if ton not in TON_TANIMLARI:
        ton = "bilgilendirici"
    t = TON_TANIMLARI[ton]

    olgular = analiz.get("mekansal_olgular", {}) or {}
    dokum = analiz.get("faktor_dokumu", {}) or {}
    meta = analiz.get("katman_meta", {}) or {}

    # Baskın faktör — modelin "hangi faktör baskın" adımını doğrulamak için
    baskin = max(dokum.items(), key=lambda kv: kv[1]["katki"])[0] if dokum else None

    olgu_satirlari = []
    if "en_yakin_fay_m" in olgular:
        olgu_satirlari.append(f"- En yakın fay hattı: {olgular['en_yakin_fay_m']:.0f} metre")
    if "en_yakin_akarsu_m" in olgular:
        ad = olgular.get("en_yakin_akarsu_adi", "")
        olgu_satirlari.append(f"- En yakın akarsu ({ad}): {olgular['en_yakin_akarsu_m']:.0f} metre")
    if "litoloji" in olgular:
        ek = f" ({olgular['litoloji_aciklama']})" if olgular.get("litoloji_aciklama") else ""
        olgu_satirlari.append(f"- Zemin/litoloji: {olgular['litoloji']}{ek}")
    if "arazi_kullanimi" in olgular:
        olgu_satirlari.append(f"- Arazi kullanımı: {olgular['arazi_kullanimi']}")
    if "mahalle" in olgular:
        olgu_satirlari.append(f"- Yerleşim: {olgular['mahalle']}")

    faktor_satirlari = [
        f"- {FAKTOR_ADLARI.get(k, k)}: {v['puan']:.1f}/5.0 "
        f"(ağırlık {v['agirlik']:.2f}, toplam skora katkı {v['katki']:.2f})"
        for k, v in sorted(dokum.items(), key=lambda kv: -kv[1]["katki"])
    ]

    bina = []
    if analiz.get("yapim_yili"):
        bina.append(f"yapım yılı {analiz['yapim_yili']}")
    if analiz.get("malzeme_secim"):
        bina.append(MALZEME_ADLARI.get(analiz["malzeme_secim"], "bilinmiyor"))
    if analiz.get("bina_kat_sayisi"):
        bina.append(f"{analiz['bina_kat_sayisi']} katlı")
    if analiz.get("oturulan_kat"):
        bina.append(f"kullanıcı {analiz['oturulan_kat']}. katta")

    eksik_notu = ""
    if meta.get("eksik_katmanlar"):
        eksik_notu = (
            f"\nVERİ SINIRI: Şu katman(lar) analize dahil edilemedi: "
            f"{', '.join(meta['eksik_katmanlar'])}. Kullanıcıya kesin konuşurken "
            f"bu sınırı bir cümleyle belirt."
        )

    ton_blogu = ""
    if ton != "ham":
        ton_blogu = f"""
HEDEF İLETİŞİM TONU: {t['etiket']}
Amaç: {t['amac']}
Yönerge: {t['yonerge']}
Kaçınılacaklar: {t['yasak']}
"""

    return f"""Aşağıda Seferihisar (İzmir) için CBS tabanlı ağırlıklı çakıştırma analiziyle
üretilmiş nicel afet risk verisi var. Bu veriyi kullanıcıya doğal dilde aktaracaksın.

=== NİCEL CBS ÇIKTISI ===
Afet tipi: {analiz.get('afet_tipi', 'DEPREM')}
Bölgesel tehlike skoru: {analiz.get('hazard_score', 0):.2f}/5.0
Bina hassasiyet skoru: {analiz.get('vulnerability_score', 0):.2f}/5.0
TOPLAM RİSK SKORU: {analiz.get('risk_score', 0):.2f}/5.0

Faktör katkıları:
{chr(10).join(faktor_satirlari) if faktor_satirlari else '- (faktör dökümü yok)'}

Mekânsal olgular:
{chr(10).join(olgu_satirlari) if olgu_satirlari else '- (mekânsal olgu yok)'}

Bina bilgisi: {', '.join(bina) if bina else 'belirtilmemiş'}
Kullanıcının endişe düzeyi: {endise_duzeyi}{eksik_notu}
{ton_blogu}
=== AKIL YÜRÜTME ADIMLARI (bunları YAZMA, sadece uygula) ===
ADIM 1 — Yukarıdaki sayıları oku. Hiçbirini değiştirme, yuvarlama, uydurma.
ADIM 2 — Toplam skora en çok katkı veren faktörü belirle. (Hesaba göre: {FAKTOR_ADLARI.get(baskin, baskin) if baskin else 'belirsiz'})
ADIM 3 — Skoru seviyeye çevir: 1.0-2.9 düşük, 3.0-3.9 orta, 4.0-5.0 yüksek.
ADIM 4 — Bina bilgisiyle bölgesel tehlikeyi ilişkilendir: hangisi skoru yukarı çekiyor?
ADIM 5 — Yanıtı hedef tona göre yaz.

=== KATI KURALLAR ===
- Yukarıda VERİLMEYEN hiçbir sayıyı kullanma. Sayı uydurmak bu sistemde en ciddi hatadır.
- Toplam risk skorunu ({analiz.get('risk_score', 0):.2f}) mutlaka yanıtta belirt.
- Deprem davranış tavsiyesi verirsen güncel kılavuza uy: ÇÖK-KAPAN-TUTUN.
  Kapı çerçevesine/kirişine sığınmayı ASLA önerme (güncelliğini yitirmiş bilgidir).
- Ton ne olursa olsun olgular aynı kalır; riski hafifletme veya abartma.
- En fazla 6 cümle veya 5 numaralı adım.
- Yanıt Türkçe olacak.

{"KULLANICININ SORUSU: " + kullanici_sorusu if kullanici_sorusu else "Kullanıcı genel bir risk açıklaması istiyor."}
"""


# ---------------------------------------------------------------------------
# SAYISAL DOĞRULAMA (halüsinasyon denetimi)
# ---------------------------------------------------------------------------

_SAYI = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)(?![\w])")

# "1 132 metre" gibi boşluklu binlik ayırıcı (normal/ince/bölünmez boşluk):
# tek sayıdır, "1" + "132" diye bölünürse 132 uydurma sanılır
_BINLIK = re.compile("(?<=\\d)[ \u00a0\u2009\u202f](?=\\d{3}(?!\\d))")

# Yanıtta serbestçe geçebilecek, uydurma sayılmayan kalıplar
_MASUM_BAGLAM = re.compile(
    r"(1\s*[-–:]\s*[\d.]+|/\s*5|5\s*üzerinden|EPSG:\s*\d+|"
    r"^\s*\d+[\.\)]|adım\s*\d+|\d+\s*(saniye|dakika|birinci|ikinci|üçüncü))",
    re.IGNORECASE | re.MULTILINE,
)


def _tum_sayilar(nesne, cikti=None):
    """analiz sözlüğündeki TÜM sayısal değerleri özyinelemeli toplar.

    Mantık: modele verilen her sayı yanıtta serbestçe kullanılabilir;
    verilmeyen bir sayı ise uydurulmuş demektir.
    """
    if cikti is None:
        cikti = set()
    if isinstance(nesne, bool):
        return cikti
    if isinstance(nesne, (int, float)):
        try:
            f = float(nesne)
        except (TypeError, ValueError):
            return cikti
        cikti.add(round(f, 2))
        cikti.add(round(f, 1))
        cikti.add(float(round(f)))
        if abs(f) >= 100:
            # metre -> km olarak da yazılabilir
            cikti.add(round(f / 1000.0, 2))
            cikti.add(round(f / 1000.0, 1))
            # modelin yuvarlama ihtimalleri (2250.4 -> 2250 / 2300 / 2000)
            cikti.add(float(round(f / 10.0) * 10))
            cikti.add(float(round(f / 100.0) * 100))
    elif isinstance(nesne, dict):
        for v in nesne.values():
            _tum_sayilar(v, cikti)
    elif isinstance(nesne, (list, tuple)):
        for v in nesne:
            _tum_sayilar(v, cikti)
    return cikti


def dogrula(yanit: str, analiz: dict, tolerans: float = 0.05) -> dict:
    """
    BDM yanıtındaki sayıların CBS çıktısıyla tutarlılığını denetler.

    Afet iletişiminde uydurulmuş bir mesafe veya skor doğrudan can güvenliği
    riskidir. Bu fonksiyon, araştırma önerisindeki "Nicel CBS çıktısının BDM
    tarafından üretilen yanıttaki sayısal verinin doğru aktarımı kontrol
    edilecektir" taahhüdünün karşılığıdır.

    Dönüş:
      {
        "risk_skoru_gecti": bool,   # toplam skor yanıtta doğru geçiyor mu
        "uydurma_sayilar": [...],   # CBS çıktısında karşılığı olmayan sayılar
        "sayisal_dogruluk": 0.0-1.0,
        "kontrol_edilen_sayi_adedi": int
      }
    """
    izinli = _tum_sayilar(analiz)
    izinli.update({1.0, 2.0, 3.0, 4.0, 5.0})       # 1-5 risk ölçeği
    izinli.update({30.0, 25.0, 25000.0, 0.0})      # hücre boyutu, ölçek, sıfır
    # cot_prompt ADIM 3'te modele verilen seviye sınırları ("1.0-2.9 düşük,
    # 3.0-3.9 orta, 4.0-5.0 yüksek") — model bunları aktarırsa uydurma değildir
    izinli.update({2.9, 3.9})

    temiz = _MASUM_BAGLAM.sub(" ", _BINLIK.sub("", yanit))
    bulunan, uydurma = [], []
    for m in _SAYI.finditer(temiz):
        ham = m.group(1).replace(",", ".")
        try:
            f = float(ham)
        except ValueError:
            continue
        bulunan.append(f)
        # Bağıl tolerans üst sınırlandı: aksi hâlde büyük sayılarda
        # (örn. yapım yılı 1995) tamamen uydurma bir değer (1978) de
        # "yakın" sayılıp kaçırılıyordu.
        if any(abs(f - iz) <= max(tolerans, min(abs(iz) * 0.01, 10.0)) for iz in izinli):
            continue
        uydurma.append(f)

    risk = float(analiz.get("risk_score", 0))
    risk_gecti = any(abs(b - risk) <= 0.06 for b in bulunan)
    dogruluk = 1.0 if not bulunan else (len(bulunan) - len(uydurma)) / len(bulunan)

    # SEVİYE TUTARLILIĞI — ince ayarlı küçük model değerlendirmesinde (30.08)
    # 40 üretimin 7'sinde skor doğru aktarılıp seviye yanlış adlandırıldı; hepsi
    # eşik civarı vakalardı (2.70-2.94 için "orta" denmişti). Sayı denetimi bunu
    # yakalayamaz, çünkü uydurma sayı yok — ayrı bir kontrol gerekiyor.
    beklenen_seviye = ("yüksek" if risk >= 4.0 else "orta" if risk >= 3.0 else "düşük")
    kucuk = yanit.lower()
    seviye_tutarli = True
    if beklenen_seviye not in kucuk:
        for yanlis in {"düşük", "orta", "yüksek"} - {beklenen_seviye}:
            if (f"{yanlis} risk" in kucuk or f"{yanlis} seviye" in kucuk
                    or f"{yanlis} düzey" in kucuk or f"\u201c{yanlis}\u201d" in kucuk):
                seviye_tutarli = False
                break

    return {
        "risk_skoru_gecti": risk_gecti,
        "uydurma_sayilar": sorted(set(uydurma)),
        "sayisal_dogruluk": round(dogruluk, 3),
        "kontrol_edilen_sayi_adedi": len(bulunan),
        "seviye_tutarli": seviye_tutarli,
        "beklenen_seviye": beklenen_seviye,
    }


# ---------------------------------------------------------------------------
# DENEY KAYDI (İP4 için veri toplama)
# ---------------------------------------------------------------------------

def deney_kaydet(kayit: dict) -> None:
    """
    Her üretilen çıktıyı JSONL olarak kaydeder. Kontrollü kullanıcı
    deneylerinde (A/B testi) analiz edilecek ham veri budur.
    """
    try:
        DENEY_KAYIT.parent.mkdir(parents=True, exist_ok=True)
        kayit = dict(kayit)
        kayit["zaman"] = datetime.now(timezone.utc).isoformat()
        with DENEY_KAYIT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
    except Exception as e:  # kayıt hatası kullanıcı akışını bozmasın
        print(f"deney_kaydet uyarı: {e}")
