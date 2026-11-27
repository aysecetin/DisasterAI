"""
guc_analizi.py — Örneklem büyüklüğü ve istatistiksel güç analizi (İP4, iş #11)
==============================================================================

Deney tasarımı: üç kollu, katılımcılar arası (between-subjects).
  A) teknik_rapor (kontrol)  B) ham (ablasyon)  C) tonlu (deney)

Birincil hipotezler iki PLANLI KONTRAST olarak test edilir:
  H1:  A vs B   (doğal dilin etkisi)
  H2:  B vs C   (ton yönetiminin etkisi)

Birincil çıktılar: anlaşılırlık ve eylem niyeti (iki ölçek).
Analiz birimi KATILIMCIDIR — üç senaryonun ölçek puanları katılımcı başına
ortalanır; bu yüzden güç hesabı katılımcı sayısı üzerinden yapılır.

Çoklu karşılaştırma: iki birincil kontrast için Bonferroni ile
alfa = 0.05 / 2 = 0.025 (analizde Holm kullanılacak; Bonferroni planlama
aşamasında daha muhafazakâr olduğu için güç hesabında onu kullanıyoruz).

Etki büyüklüğü gerekçesi:
  Sade dil / kişiselleştirilmiş risk iletişimi müdahaleleri okuduğunu anlama ve
  davranış niyeti üzerinde tipik olarak orta-büyük etkiler raporlar. Planlama
  senaryosu olarak d = 0.65 (orta-büyük) alınmıştır; d = 0.50 ve d = 0.80
  duyarlılık senaryoları olarak tabloda verilir. Küçük etkiler (d < 0.5) bu
  örneklemle tespit edilemez — bu, tezde sınırlılık olarak belirtilmelidir.

Çalıştırma:
    python tools/guc_analizi.py
Çıktı:
    outputs/deney/guc_analizi.md   (tez + etik başvurusuna yapıştırılabilir)
"""

from __future__ import annotations

import math
from pathlib import Path

from statsmodels.stats.power import FTestAnovaPower, TTestIndPower

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CIKTI = PROJECT_ROOT / "outputs" / "deney" / "guc_analizi.md"

GUC_HEDEFI = 0.80
ALFA_KONTRAST = 0.025      # iki birincil kontrast, Bonferroni: 0.05 / 2
ALFA_OMNIBUS = 0.05
KAYIP_PAYI = 0.10          # eksik/geçersiz yanıt payı
ETKI_SENARYOLARI = (0.50, 0.65, 0.80)   # Cohen's d
PLANLAMA_D = 0.65


def d_den_f(d: float) -> float:
    """
    İki kol arasındaki d farkını üç kollu ANOVA'nın f'ine çevirir.
    Muhafazakâr desen: uçlardaki iki kol ±d/2, ortadaki kol 0 sapar
    (ortalamalar -d/2, 0, +d/2) -> f = d / sqrt(6) * sqrt(3)... açık yazalım:
    sigma_m = sqrt(((d/2)^2 + 0 + (d/2)^2) / 3) = d / sqrt(6);  f = sigma_m.
    """
    return d / math.sqrt(6.0)


def hesapla() -> dict:
    t_guc = TTestIndPower()
    f_guc = FTestAnovaPower()

    satirlar = []
    for d in ETKI_SENARYOLARI:
        n_kontrast = t_guc.solve_power(effect_size=d, alpha=ALFA_KONTRAST,
                                       power=GUC_HEDEFI, alternative="two-sided")
        n_kontrast = math.ceil(n_kontrast)              # kol başına
        f = d_den_f(d)
        n_anova_toplam = f_guc.solve_power(effect_size=f, alpha=ALFA_OMNIBUS,
                                           power=GUC_HEDEFI, k_groups=3)
        n_anova_kol = math.ceil(n_anova_toplam / 3)
        # Belirleyici olan (daha büyük) gereksinim
        n_kol = max(n_kontrast, n_anova_kol)
        n_toplam = 3 * n_kol
        n_toplam_kayipli = 3 * math.ceil(n_kol * (1 + KAYIP_PAYI))
        satirlar.append({
            "d": d, "f": round(f, 3),
            "n_kontrast_kol": n_kontrast,
            "n_anova_kol": n_anova_kol,
            "n_kol": n_kol, "n_toplam": n_toplam,
            "n_toplam_kayipli": n_toplam_kayipli,
        })

    # Duyarlılık: kol başına ulaşılabilir n için elde edilen güç
    duyarlilik = []
    for n_kol in (15, 20, 25, 30, 35):
        guc_d = {d: t_guc.solve_power(effect_size=d, alpha=ALFA_KONTRAST,
                                      nobs1=n_kol, alternative="two-sided")
                 for d in ETKI_SENARYOLARI}
        duyarlilik.append({"n_kol": n_kol,
                           **{f"guc_d{d}": round(g, 3) for d, g in guc_d.items()}})

    return {"tablo": satirlar, "duyarlilik": duyarlilik}


def rapor_yaz(sonuc: dict) -> None:
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    plan = next(s for s in sonuc["tablo"] if s["d"] == PLANLAMA_D)

    md = []
    md.append("# Örneklem Büyüklüğü ve Güç Analizi\n")
    md.append("> Bu dosya `tools/guc_analizi.py` ile üretilmiştir; elle düzenlemeyin.\n")
    md.append("## Tasarım özeti\n")
    md.append(
        "Üç kollu (teknik rapor / ham BDM / tonlu BDM), katılımcılar arası deney. "
        "Birincil hipotezler iki planlı kontrasttır: H1 (A vs B) ve H2 (B vs C). "
        "Birincil çıktılar anlaşılırlık ve eylem niyeti ölçek puanlarıdır; analiz "
        "birimi katılımcıdır (üç senaryonun puanları katılımcı başına ortalanır). "
        f"İki birincil kontrast için Bonferroni düzeltmesiyle kontrast başına "
        f"α = {ALFA_KONTRAST}, hedef güç = {GUC_HEDEFI:.2f} alınmıştır.\n")
    md.append("## Gerekli örneklem (güç = %80)\n")
    md.append("| Cohen's d | ANOVA f | Kontrast için n/kol | ANOVA için n/kol | "
              "Gerekli n/kol | Toplam N | %10 kayıp payıyla N |")
    md.append("|---|---|---|---|---|---|---|")
    for s in sonuc["tablo"]:
        isaret = " **(planlama senaryosu)**" if s["d"] == PLANLAMA_D else ""
        md.append(f"| {s['d']}{isaret} | {s['f']} | {s['n_kontrast_kol']} | "
                  f"{s['n_anova_kol']} | {s['n_kol']} | {s['n_toplam']} | "
                  f"{s['n_toplam_kayipli']} |")
    md.append("")
    md.append(
        f"**Karar:** Planlama senaryosu d = {PLANLAMA_D} için kol başına "
        f"**{plan['n_kol']}** katılımcı, toplam **{plan['n_toplam']}**; %10 kayıp "
        f"payıyla hedef **{plan['n_toplam_kayipli']}** katılımcıdır.\n")
    md.append("## Ulaşılabilir örnekleme göre güç (duyarlılık)\n")
    md.append("Hedef örnekleme ulaşılamazsa elde edilecek güç "
              f"(kontrast başına α = {ALFA_KONTRAST}):\n")
    md.append("| n/kol | Güç (d=0.50) | Güç (d=0.65) | Güç (d=0.80) |")
    md.append("|---|---|---|---|")
    for r in sonuc["duyarlilik"]:
        md.append(f"| {r['n_kol']} | {r['guc_d0.5']} | {r['guc_d0.65']} | "
                  f"{r['guc_d0.8']} |")
    md.append("")
    md.append("## Sınırlılıklar\n")
    md.append(
        "- Küçük etkiler (d < 0.5) bu örneklem aralığında güvenilir biçimde tespit "
        "edilemez; bulunamayan fark \"etki yok\" anlamına gelmez.\n"
        "- Hesap iki bağımsız örneklem t-testi varsayımıyla yapılmıştır; dağılım "
        "varsayımları bozulursa parametrik olmayan karşılıklar (Mann-Whitney U) "
        "bir miktar güç kaybettirir (ARE ≈ 0.95).\n"
        "- İki birincil çıktı (anlaşılırlık, eylem niyeti) için ayrıca düzeltme "
        "yapılmamıştır; analizde Holm yöntemi aile bazında uygulanacaktır.\n")

    CIKTI.write_text("\n".join(md), encoding="utf-8")
    print(f"Yazıldı: {CIKTI}")
    print(f"Öneri: kol başına {plan['n_kol']}, toplam {plan['n_toplam']} "
          f"(kayıp payıyla {plan['n_toplam_kayipli']}) katılımcı.")


if __name__ == "__main__":
    rapor_yaz(hesapla())
