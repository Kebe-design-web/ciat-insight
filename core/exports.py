"""Exports : Excel (données filtrées + indicateurs) et PDF (fiche de synthèse)."""
import io
import datetime as dt

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether

from core.kpi import pct, fcfa

BROWN = colors.HexColor("#4A2C1D")
BEIGE = colors.HexColor("#C9976B")
LIGHT = colors.HexColor("#F5EDE4")

KPI_LABELS = [
    ("K1", "Idées reçues", lambda v: str(v)),
    ("K2", "Projets sélectionnés", lambda v: str(v)),
    ("K3", "Taux de sélection", pct),
    ("K4", "Prototypes réalisés", lambda v: str(v)),
    ("K5", "Taux de transformation", pct),
    ("K6", "Projets en retard", lambda v: str(v)),
    ("K7", "Taux de retard", pct),
    ("K8", "Avancement moyen des actifs", pct),
    ("K9", "Part des projets portés par des femmes", pct),
    ("K10", "Financements obtenus", fcfa),
    ("K11", "Partenariats actifs", lambda v: str(v)),
]


def kpi_table(k):
    return pd.DataFrame([{"Code": c, "Indicateur": l, "Valeur": f(k[c])} for c, l, f in KPI_LABELS])


def excel_bytes(k, p, coh):
    buf = io.BytesIO()
    cols = {"id_projet": "ID", "titre": "Titre", "domaine": "Domaine", "annee": "Cohorte", "statut": "Statut",
            "selectionne": "Sélectionné", "genre": "Genre porteur", "mentor": "Mentor", "avancement": "Avancement",
            "prototype": "Prototype validé", "en_retard": "En retard", "jours_retard": "Jours de retard",
            "financement": "Financement (FCFA)"}
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        kpi_table(k).to_excel(w, sheet_name="Indicateurs", index=False)
        coh.to_excel(w, sheet_name="Cohortes", index=False)
        p[list(cols)].rename(columns=cols).to_excel(w, sheet_name="Projets filtrés", index=False)
        for ws in w.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(45, max(12, max(len(str(c.value or "")) for c in col) + 2))
    return buf.getvalue()


def _bar_png(series, title):
    fig, ax = plt.subplots(figsize=(7, 3))
    series.sort_values().plot.barh(ax=ax, color="#C9976B")
    ax.set_ylabel("")
    ax.set_title(title, fontsize=10, color="#4A2C1D")
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8)
    fig.tight_layout()
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=150)
    plt.close(fig)
    b.seek(0)
    return b


def pdf_bytes(k, p, coh, filtres, lignes):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            title="Fiche de synthèse CIAT Insight")
    ss = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=ss["Heading1"], textColor=BROWN, fontSize=16)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=BROWN, fontSize=12)
    n = ParagraphStyle("n", parent=ss["Normal"], fontSize=9.5, leading=13)
    small = ParagraphStyle("s", parent=n, fontSize=8, textColor=colors.grey)

    def tbl(data, widths):
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BROWN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("GRID", (0, 0), (-1, -1), 0.4, BEIGE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        return t

    el = [Paragraph("ISEP Amadou Trawaré · CIAT", small),
          Paragraph("Fiche de synthèse CIAT Insight", h),
          Paragraph(f"Éditée le {dt.date.today().strftime('%d/%m/%Y')} · Filtres : {filtres}", small), Spacer(1, 8),
          Paragraph("Indicateurs clés", h2)]
    kt = kpi_table(k)
    el.append(tbl([list(kt.columns)] + kt.values.tolist(), [1.5 * cm, 10 * cm, 5 * cm]))
    el += [Spacer(1, 8), Paragraph("Lecture des résultats", h2)]
    el += [Paragraph("• " + l, n) for l in lignes]

    if len(p):
        el += [Spacer(1, 6), Image(_bar_png(p.groupby("domaine").size(), "Idées reçues par domaine"), width=16 * cm, height=6.8 * cm)]
    if len(coh):
        c2 = coh.copy()
        for col in ["Taux de sélection", "Taux de transformation", "Part des porteuses"]:
            c2[col] = c2[col].map(pct)
        c2["Financements (FCFA)"] = c2["Financements (FCFA)"].map(fcfa)
        hs = ParagraphStyle("hs", parent=n, fontSize=7.5, leading=9, textColor=colors.white)
        heads = [Paragraph(x, hs) for x in ["Cohorte", "Idées reçues", "Sélec- tionnés", "Proto- types", "Taux de sélection",
                                           "Taux de transfor- mation", "Projets en retard", "Part des porteuses", "Financements"]]
        el.append(KeepTogether([Paragraph("Comparaison des cohortes", h2),
                                tbl([heads] + c2.astype(str).values.tolist(), [1.5 * cm] + [1.75 * cm] * 7 + [3.2 * cm])]))
    late = p[p["en_retard"]].sort_values("jours_retard", ascending=False)
    if len(late):
        el.append(KeepTogether([Paragraph("Projets en retard", h2),
                                tbl([["Projet", "Domaine", "Mentor", "Retard (jours)"]] +
                                    [[r.titre[:45], r.domaine, r.mentor or "-", str(r.jours_retard)] for r in late.itertuples()],
                                    [7 * cm, 4.5 * cm, 3.5 * cm, 2.4 * cm])]))
    el += [Spacer(1, 10), Paragraph("Document généré automatiquement par CIAT Insight. Données de démonstration fictives.", small)]
    doc.build(el)
    return buf.getvalue()
