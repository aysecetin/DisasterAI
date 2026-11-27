"""
istatistik_analiz.py — Deney verisinin istatistiksel analizi (İP4, iş #11)
==========================================================================

outputs/deney/katilimcilar.jsonl ve yanitlar.jsonl dosyalarını okur,
analiz planını uygular, Markdown rapor üretir.

ANALİZ PLANI (etik başvurusu ve tezle tutarlı — değiştirme)
-----------------------------------------------------------
- Analiz birimi KATILIMCI: üç senaryonun ölçek puanları katılımcı başına
  ortalanır (senaryolar bağımsız gözlem değildir).
- Birincil çıktılar: anlaşılırlık, eylem niyeti. İkincil: duygusal tepki.
- Birincil kontrastlar: H1 = teknik_rapor vs ham, H2 = ham vs tonlu.
  İkincil kontrast: teknik_rapor vs tonlu.
- Her ölçek içinde iki birincil kontrasta Holm düzeltmesi uygulanır.
- Varsayım denetimi: Shapiro-Wilk (kol başına), Levene. Karşılaştırmalar
  Welch t-testi ile yapılır (varyans homojenliği varsaymaz); dağılım ciddi
  bozuksa Mann-Whitney U sonucu da raporlanır — ikisi birden verilir, karar
  metnin okuyucusuna bırakılmaz: birincil test Welch'tir, MWU duyarlılıktır.
- Omnibus: klasik ANOVA + Welch ANOVA + Kruskal-Wallis (tam tablo için).
- Etki büyüklükleri: Hedges g (kontrastlar), eta-kare (ANOVA).

ÇALIŞTIRMA
----------
    python tools/istatistik_analiz.py            # ana analiz
    python tools/istatistik_analiz.py --pilot    # pilot: güvenilirlik analizi
    python tools/istatistik_analiz.py --girdi outputs/deney_pilot

Çıktılar: outputs/deney/istatistik_raporu.md (+ katilimci_duzeyi_veri.csv)
          --pilot ile outputs/deney/pilot_guvenilirlik.md
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
import deney as dny  # noqa: E402  (OLCEKLER ve ters kodlama tek kaynaktan)

KOLLAR = list(dny.KOLLAR)                     # teknik_rapor, ham, tonlu
OLCEKLER = list(dny.OLCEKLER)                 # anlasilirlik, eylem_niyeti, duygusal_tepki
BIRINCIL_OLCEKLER = ["anlasilirlik", "eylem_niyeti"]
KONTRASTLAR = [
    ("H1 (doğal dil)", "teknik_rapor", "ham", True),
    ("H2 (ton yönetimi)", "ham", "tonlu", True),
    ("Bütün sistem", "teknik_rapor", "tonlu", False),   # ikincil
]


# ---------------------------------------------------------------------------
# VERİ OKUMA
# ---------------------------------------------------------------------------

def jsonl_oku(dosya: Path) -> list[dict]:
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


def veri_yukle(girdi: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Döndürür:
      yanit_df    — satır = katılımcı×senaryo; ölçek puanları + madde yanıtları
      katilimci_df— satır = katılımcı; ölçek puanları senaryolar üzerinden ortalanmış
    """
    yanitlar = jsonl_oku(girdi / "yanitlar.jsonl")
    if not yanitlar:
        raise SystemExit(f"Veri yok: {girdi/'yanitlar.jsonl'} boş veya eksik.")

    satirlar = []
    for y in yanitlar:
        satir = {
            "katilimci_kodu": y.get("katilimci_kodu"),
            "kol": y.get("kol"),
            "ton": y.get("ton"),
            "senaryo": y.get("senaryo_kodu"),
            "okuma_suresi_sn": y.get("okuma_suresi_sn"),
        }
        puanlar = y.get("olcek_puanlari") or {}
        for ad in OLCEKLER:
            satir[ad] = puanlar.get(ad)
        # madde düzeyi (güvenilirlik analizi için, ters kodlama UYGULANMIŞ)
        ham_yanitlar = y.get("olcek_yanitlari") or {}
        for ad in OLCEKLER:
            ters = set(dny.OLCEKLER[ad].get("ters_kodlanan", []))
            maddeler = ham_yanitlar.get(ad) or []
            for i, deger in enumerate(maddeler):
                if deger is None:
                    continue
                deger = int(deger)
                satir[f"{ad}_m{i+1}"] = 6 - deger if i in ters else deger
        satirlar.append(satir)
    yanit_df = pd.DataFrame(satirlar)
    yanit_df = yanit_df[yanit_df["kol"].isin(KOLLAR)]

    # Aynı katılımcı×senaryo mükerrer kaydedildiyse SONUNCUSU geçerli
    yanit_df = yanit_df.drop_duplicates(subset=["katilimci_kodu", "senaryo"],
                                        keep="last")

    katilimci_df = (yanit_df
                    .groupby(["katilimci_kodu", "kol"], as_index=False)[OLCEKLER]
                    .mean())
    return yanit_df, katilimci_df


# ---------------------------------------------------------------------------
# İSTATİSTİK YARDIMCILARI
# ---------------------------------------------------------------------------

def cronbach_alfa(madde_df: pd.DataFrame) -> float | None:
    """Satır = gözlem, sütun = madde. Eksiksiz satırlar üzerinden alfa."""
    m = madde_df.dropna()
    if m.shape[0] < 3 or m.shape[1] < 2:
        return None
    k = m.shape[1]
    madde_var = m.var(axis=0, ddof=1).sum()
    toplam_var = m.sum(axis=1).var(ddof=1)
    if toplam_var == 0:
        return None
    return (k / (k - 1)) * (1 - madde_var / toplam_var)


def madde_toplam_korelasyon(madde_df: pd.DataFrame) -> dict[str, float]:
    """Düzeltilmiş madde-toplam korelasyonu (madde kendi toplamından çıkarılır)."""
    m = madde_df.dropna()
    sonuc = {}
    for kolon in m.columns:
        digerleri = m.drop(columns=[kolon]).sum(axis=1)
        if m[kolon].std(ddof=1) == 0 or digerleri.std(ddof=1) == 0:
            sonuc[kolon] = float("nan")
        else:
            sonuc[kolon] = float(np.corrcoef(m[kolon], digerleri)[0, 1])
    return sonuc


def hedges_g(x: np.ndarray, y: np.ndarray) -> float | None:
    n1, n2 = len(x), len(y)
    if n1 < 2 or n2 < 2:
        return None
    s_havuz = math.sqrt(((n1 - 1) * np.var(x, ddof=1) +
                         (n2 - 1) * np.var(y, ddof=1)) / (n1 + n2 - 2))
    if s_havuz == 0:
        return None
    d = (np.mean(x) - np.mean(y)) / s_havuz
    duzeltme = 1 - 3 / (4 * (n1 + n2) - 9)
    return d * duzeltme


def welch_anova(gruplar: list[np.ndarray]) -> tuple[float, float, float] | None:
    """Welch ANOVA. Döndürür (F, df2, p) — df1 = k-1."""
    gruplar = [g for g in gruplar if len(g) >= 2 and np.var(g, ddof=1) > 0]
    k = len(gruplar)
    if k < 2:
        return None
    n = np.array([len(g) for g in gruplar], dtype=float)
    m = np.array([np.mean(g) for g in gruplar])
    v = np.array([np.var(g, ddof=1) for g in gruplar])
    w = n / v
    W = w.sum()
    genel = (w * m).sum() / W
    A = (w * (m - genel) ** 2).sum() / (k - 1)
    payda_terimi = ((1 - w / W) ** 2 / (n - 1)).sum()
    B = 1 + 2 * (k - 2) / (k ** 2 - 1) * payda_terimi
    F = A / B
    df2 = (k ** 2 - 1) / (3 * payda_terimi)
    p = stats.f.sf(F, k - 1, df2)
    return float(F), float(df2), float(p)


def holm_duzelt(p_listesi: list[float]) -> list[float]:
    """Holm-Bonferroni düzeltilmiş p değerleri (sıra korunur)."""
    m = len(p_listesi)
    sirali = sorted(range(m), key=lambda i: p_listesi[i])
    duzeltilmis = [0.0] * m
    onceki = 0.0
    for rütbe, i in enumerate(sirali):
        p = min(1.0, (m - rütbe) * p_listesi[i])
        p = max(p, onceki)          # monotonluk
        duzeltilmis[i] = p
        onceki = p
    return duzeltilmis


def p_bicim(p: float | None) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "—"
    return "< .001" if p < 0.001 else f"{p:.3f}"


# ---------------------------------------------------------------------------
# PİLOT RAPORU (güvenilirlik)
# ---------------------------------------------------------------------------

def pilot_raporu(yanit_df: pd.DataFrame, cikti: Path) -> None:
    md = ["# Pilot Güvenilirlik Raporu\n",
          "> `tools/istatistik_analiz.py --pilot` çıktısı; elle düzenlemeyin.\n",
          f"Gözlem sayısı (katılımcı×senaryo): **{len(yanit_df)}**, "
          f"katılımcı: **{yanit_df['katilimci_kodu'].nunique()}**\n",
          "Not: Alfa, katılımcı×senaryo gözlemleri üzerinden hesaplanmıştır; "
          "gözlemler tam bağımsız olmadığı için pilot değerlendirmesinde "
          "yaklaşık göstergedir.\n"]

    for ad in OLCEKLER:
        kolonlar = [c for c in yanit_df.columns if c.startswith(f"{ad}_m")]
        baslik = dny.OLCEKLER[ad]["baslik"]
        md.append(f"## {baslik} (`{ad}`)\n")
        if not kolonlar:
            md.append("Madde düzeyi veri yok (olcek_yanitlari kaydedilmemiş).\n")
            continue
        madde_df = yanit_df[kolonlar]
        alfa = cronbach_alfa(madde_df)
        alfa_metin = f"{alfa:.3f}" if alfa is not None else "hesaplanamadı (veri az)"
        karar = ""
        if alfa is not None:
            karar = " ✅ (≥ 0.70)" if alfa >= 0.70 else " ⚠️ **(< 0.70 — maddeleri gözden geçir)**"
        md.append(f"**Cronbach alfa = {alfa_metin}**{karar}\n")
        md.append("| Madde | Ort. | SS | Düzeltilmiş madde-toplam r | Madde silinirse alfa |")
        md.append("|---|---|---|---|---|")
        korelasyonlar = madde_toplam_korelasyon(madde_df)
        for kolon in kolonlar:
            digerleri = [c for c in kolonlar if c != kolon]
            alfa_silinirse = cronbach_alfa(madde_df[digerleri]) if len(digerleri) >= 2 else None
            alfa_s = f"{alfa_silinirse:.3f}" if alfa_silinirse is not None else "—"
            r = korelasyonlar.get(kolon, float("nan"))
            r_metin = "—" if math.isnan(r) else f"{r:.3f}"
            uyari = " ⚠️" if (not math.isnan(r) and r < 0.30) else ""
            md.append(f"| {kolon} | {madde_df[kolon].mean():.2f} | "
                      f"{madde_df[kolon].std(ddof=1):.2f} | {r_metin}{uyari} | "
                      f"{alfa_s} |")
        md.append("")
    md.append("**Karar kuralları:** alfa ≥ 0.70; madde-toplam r < 0.30 olan "
              "madde gözden geçirilir (`docs/deney/olcek_kaynak_eslemesi.md`).\n")
    cikti.write_text("\n".join(md), encoding="utf-8")
    print(f"Yazıldı: {cikti}")


# ---------------------------------------------------------------------------
# ANA ANALİZ RAPORU
# ---------------------------------------------------------------------------

def ana_rapor(yanit_df: pd.DataFrame, katilimci_df: pd.DataFrame,
              cikti: Path) -> None:
    md = ["# Deney İstatistik Raporu\n",
          "> `tools/istatistik_analiz.py` çıktısı; elle düzenlemeyin.\n"]

    # --- örneklem özeti
    dagilim = katilimci_df["kol"].value_counts().to_dict()
    md.append("## Örneklem\n")
    md.append(f"Toplam katılımcı: **{len(katilimci_df)}** — " +
              ", ".join(f"{k}: {dagilim.get(k, 0)}" for k in KOLLAR) + "\n")
    md.append("Analiz birimi katılımcıdır; senaryo puanları katılımcı başına "
              "ortalanmıştır.\n")

    kucuk_orneklem = any(dagilim.get(k, 0) < 2 for k in KOLLAR)
    if kucuk_orneklem:
        md.append("> ⚠️ En az bir kolda 2'den az katılımcı var — çıkarımsal "
                  "testler atlandı, yalnızca betimleyiciler raporlandı.\n")

    # --- güvenilirlik özeti (ana raporda da kısaca)
    md.append("## Güvenilirlik (Cronbach alfa)\n")
    md.append("| Ölçek | Alfa |")
    md.append("|---|---|")
    for ad in OLCEKLER:
        kolonlar = [c for c in yanit_df.columns if c.startswith(f"{ad}_m")]
        alfa = cronbach_alfa(yanit_df[kolonlar]) if kolonlar else None
        alfa_metin = f"{alfa:.3f}" if alfa is not None else "—"
        md.append(f"| {dny.OLCEKLER[ad]['baslik']} | {alfa_metin} |")
    md.append("")

    # --- ölçek bazında analiz
    for ad in OLCEKLER:
        baslik = dny.OLCEKLER[ad]["baslik"]
        birincil = ad in BIRINCIL_OLCEKLER
        md.append(f"## {baslik} (`{ad}`)"
                  f"{' — BİRİNCİL ÇIKTI' if birincil else ' — ikincil çıktı'}\n")

        gruplar = {k: katilimci_df.loc[katilimci_df["kol"] == k, ad]
                                  .dropna().to_numpy() for k in KOLLAR}

        # Betimleyiciler
        md.append("| Kol | n | Ort. | SS | Medyan |")
        md.append("|---|---|---|---|---|")
        for k in KOLLAR:
            g = gruplar[k]
            if len(g) == 0:
                md.append(f"| {k} | 0 | — | — | — |")
            else:
                ss = f"{np.std(g, ddof=1):.2f}" if len(g) > 1 else "—"
                md.append(f"| {k} | {len(g)} | {np.mean(g):.2f} | {ss} | "
                          f"{np.median(g):.2f} |")
        md.append("")

        if kucuk_orneklem:
            continue

        # Varsayımlar
        md.append("**Varsayım denetimi:** ")
        varsayim = []
        for k in KOLLAR:
            g = gruplar[k]
            if len(g) >= 3 and np.std(g) > 0:
                _, p = stats.shapiro(g)
                varsayim.append(f"Shapiro {k}: p = {p_bicim(p)}")
        try:
            _, p_lev = stats.levene(*[gruplar[k] for k in KOLLAR])
            varsayim.append(f"Levene: p = {p_bicim(p_lev)}")
        except ValueError:
            pass
        md.append("; ".join(varsayim) + "\n" if varsayim else "hesaplanamadı\n")

        # Omnibus
        try:
            F, p_anova = stats.f_oneway(*[gruplar[k] for k in KOLLAR])
            genel = np.concatenate([gruplar[k] for k in KOLLAR])
            ss_toplam = ((genel - genel.mean()) ** 2).sum()
            ss_gruplar = sum(len(gruplar[k]) * (gruplar[k].mean() - genel.mean()) ** 2
                             for k in KOLLAR)
            eta_kare = ss_gruplar / ss_toplam if ss_toplam > 0 else float("nan")
            df1 = len(KOLLAR) - 1
            df2 = len(genel) - len(KOLLAR)
            md.append(f"**Omnibus:** ANOVA F({df1}, {df2}) = {F:.2f}, "
                      f"p = {p_bicim(p_anova)}, η² = {eta_kare:.3f}. ")
        except Exception:
            md.append("**Omnibus:** ANOVA hesaplanamadı. ")
        w = welch_anova([gruplar[k] for k in KOLLAR])
        if w:
            md.append(f"Welch F(2, {w[1]:.1f}) = {w[0]:.2f}, p = {p_bicim(w[2])}. ")
        try:
            H, p_kw = stats.kruskal(*[gruplar[k] for k in KOLLAR])
            md.append(f"Kruskal-Wallis H = {H:.2f}, p = {p_bicim(p_kw)}.\n")
        except ValueError:
            md.append("\n")

        # Planlı kontrastlar
        md.append("**Planlı kontrastlar** (birincil test: Welch t; "
                  "Mann-Whitney U duyarlılık; Holm iki birincil kontrasta):\n")
        md.append("| Kontrast | Fark (Ort.) | Welch t | p (ham) | p (Holm) | "
                  "Hedges g | MWU p |")
        md.append("|---|---|---|---|---|---|---|")

        satirlar = []
        for etiket, k1, k2, birincil_kontrast in KONTRASTLAR:
            g1, g2 = gruplar[k1], gruplar[k2]
            if len(g1) < 2 or len(g2) < 2:
                satirlar.append((etiket, None, None, None, None, birincil_kontrast))
                continue
            # t işareti fark ve Hedges g ile aynı yönde olsun diye (g2, g1)
            t, p_t = stats.ttest_ind(g2, g1, equal_var=False)
            try:
                _, p_u = stats.mannwhitneyu(g1, g2, alternative="two-sided")
            except ValueError:
                p_u = float("nan")
            g_etki = hedges_g(g2, g1)   # pozitif = ikinci kol (deney yönü) yüksek
            fark = np.mean(g2) - np.mean(g1)
            satirlar.append((etiket, fark, (t, p_t), p_u, g_etki, birincil_kontrast))

        birincil_pler = [s[2][1] for s in satirlar if s[5] and s[2] is not None]
        holm = holm_duzelt(birincil_pler) if birincil_pler else []
        holm_iter = iter(holm)
        for etiket, fark, t_sonuc, p_u, g_etki, birincil_kontrast in satirlar:
            if t_sonuc is None:
                md.append(f"| {etiket} | — | — | — | — | — | — |")
                continue
            t, p_t = t_sonuc
            p_holm = next(holm_iter) if birincil_kontrast else None
            holm_metin = p_bicim(p_holm) if birincil_kontrast else "(ikincil)"
            g_metin = f"{g_etki:+.2f}" if g_etki is not None else "—"
            md.append(f"| {etiket} | {fark:+.2f} | {t:.2f} | {p_bicim(p_t)} | "
                      f"{holm_metin} | {g_metin} | {p_bicim(p_u)} |")
        md.append("")

    md.append("## Yorumlama notları\n")
    md.append("- Fark sütunu (ikinci kol − birinci kol): pozitif değer, deney "
              "yönündeki kolun daha yüksek puan aldığını gösterir.\n"
              "- Holm sütunundaki p < .05 birincil hipotez için anlamlılık "
              "ölçütüdür; ham p tek başına kullanılmaz.\n"
              "- Duygusal tepkide yüksek puan sakin/kontrollü hissetmek demektir "
              "(kaygı maddeleri ters kodlanır).\n"
              "- Anlamlı çıkmayan fark \"fark yok\" demek değildir; güç için "
              "`outputs/deney/guc_analizi.md` duyarlılık tablosuna bakın.\n")

    cikti.write_text("\n".join(md), encoding="utf-8")
    print(f"Yazıldı: {cikti}")


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Deney verisi istatistik analizi")
    ap.add_argument("--girdi", default=str(PROJECT_ROOT / "outputs" / "deney"),
                    help="katilimcilar.jsonl ve yanitlar.jsonl dizini")
    ap.add_argument("--pilot", action="store_true",
                    help="Pilot modu: yalnızca güvenilirlik analizi")
    ap.add_argument("--cikti", default=None, help="Rapor dosyası (md)")
    args = ap.parse_args()

    girdi = Path(args.girdi)
    yanit_df, katilimci_df = veri_yukle(girdi)

    if args.pilot:
        cikti = Path(args.cikti) if args.cikti else girdi / "pilot_guvenilirlik.md"
        cikti.parent.mkdir(parents=True, exist_ok=True)
        pilot_raporu(yanit_df, cikti)
    else:
        cikti = Path(args.cikti) if args.cikti else girdi / "istatistik_raporu.md"
        cikti.parent.mkdir(parents=True, exist_ok=True)
        csv_yolu = cikti.parent / "katilimci_duzeyi_veri.csv"
        katilimci_df.to_csv(csv_yolu, index=False)
        print(f"Yazıldı: {csv_yolu}")
        ana_rapor(yanit_df, katilimci_df, cikti)


if __name__ == "__main__":
    main()
