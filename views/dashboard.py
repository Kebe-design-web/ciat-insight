"""Tableau de bord décisionnel : filtres, indicateurs, graphiques, synthèse et exports."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import kpi, exports
from core.db import reference_date
from views.common import load, header, plot, fmt_date, PALETTE


def _filters(p):
    with st.expander("Filtres", expanded=True):
        c1, c2, c3 = st.columns(3)
        dmin, dmax = p["date_depot"].min().date(), p["date_depot"].max().date()
        periode = c1.date_input("Période de dépôt", (dmin, dmax), min_value=dmin, max_value=dmax, format="DD/MM/YYYY")
        cohortes = c2.multiselect("Cohorte", sorted(p["annee"].dropna().unique()), placeholder="Toutes")
        domaines = c3.multiselect("Domaine", kpi.DOMAINES, placeholder="Tous")
        c4, c5, c6 = st.columns(3)
        statuts = c4.multiselect("Statut", kpi.STATUTS_PROJET, placeholder="Tous")
        genres = c5.multiselect("Genre du porteur", ["F", "H"], format_func=lambda g: "Femme" if g == "F" else "Homme", placeholder="Tous")
        porteur = c6.text_input("Porteur de projet", placeholder="Nom ou prénom")

    f = p.copy()
    if isinstance(periode, (list, tuple)) and len(periode) == 2:
        f = f[(f["date_depot"] >= pd.Timestamp(periode[0])) & (f["date_depot"] <= pd.Timestamp(periode[1]))]
    if cohortes:
        f = f[f["annee"].isin(cohortes)]
    if domaines:
        f = f[f["domaine"].isin(domaines)]
    if statuts:
        f = f[f["statut"].isin(statuts)]
    if genres:
        f = f[f["genre"].isin(genres)]
    if porteur.strip():
        f = f[f["porteur"].str.contains(porteur.strip(), case=False, na=False)]

    desc = []
    if cohortes: desc.append("cohortes " + ", ".join(cohortes))
    if domaines: desc.append("domaines " + ", ".join(domaines))
    if statuts: desc.append("statuts " + ", ".join(statuts))
    if genres: desc.append("genre " + ", ".join(genres))
    if porteur.strip(): desc.append(f"porteur « {porteur.strip()} »")
    return f, ("; ".join(desc) or "aucun (tous les projets)")


def _cards(k):
    r1 = st.columns(4)
    r1[0].metric("Idées reçues", k["K1"], help="K1 : nombre de dossiers déposés")
    r1[1].metric("Projets sélectionnés", k["K2"], help="K2 : projets retenus par le comité")
    r1[2].metric("Taux de sélection", kpi.pct(k["K3"]), help="K3 = K2 ÷ K1")
    r1[3].metric("Prototypes réalisés", k["K4"], help="K4 : jalon « Prototype » validé")
    r2 = st.columns(4)
    r2[0].metric("Taux de transformation", kpi.pct(k["K5"]), help="K5 = K4 ÷ K2")
    r2[1].metric("Projets en retard", f"{k['K6']} / {k['actifs']}", help="K6 : projets actifs avec au moins un jalon non validé dont l'échéance est dépassée")
    r2[2].metric("Taux de retard", kpi.pct(k["K7"]), help="K7 = K6 ÷ projets actifs")
    r2[3].metric("Avancement moyen", kpi.pct(k["K8"]), help="K8 : moyenne des % de jalons validés des projets actifs")
    r3 = st.columns(4)
    r3[0].metric("Part des porteuses", kpi.pct(k["K9"]), help="K9 : projets portés par une femme ÷ K1")
    r3[1].metric("Financements obtenus", kpi.fcfa(k["K10"]), help="K10 : somme des montants accordés")
    r3[2].metric("Partenariats actifs", k["K11"], help="K11 : partenariats en cours à la date de référence (non filtré)")


def render(db, user):
    header("Tableau de bord décisionnel", "Suivi des activités et des résultats du CIAT et de son incubateur")
    t = load(db)
    ref = reference_date()
    p = kpi.enrich(t, ref)
    if p.empty:
        st.info("Aucun projet enregistré pour le moment.")
        return
    f, filtres = _filters(p)
    k = kpi.compute(f, t, ref)
    coh = kpi.by_cohort(f, t, ref)
    _cards(k)
    st.caption(f"Date de référence pour les retards : {ref.strftime('%d/%m/%Y')} · {len(f)} projets affichés · "
               "Données de démonstration fictives.")

    tabs = st.tabs(["Vue d'ensemble", "Cohortes", "Retards", "Financements et partenariats", "Synthèse et exports"])

    with tabs[0]:
        if f.empty:
            st.info("Aucun projet ne correspond aux filtres.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                fig = go.Figure(go.Funnel(y=["Idées reçues", "Sélectionnés", "Prototypes"], x=[k["K1"], k["K2"], k["K4"]],
                                          marker=dict(color=[PALETTE[0], PALETTE[1], PALETTE[4]]), textinfo="value+percent initial"))
                fig.update_layout(title="Parcours des projets")
                plot(fig)
            with c2:
                st_ = f.groupby("statut").size().reset_index(name="Projets")
                plot(px.pie(st_, names="statut", values="Projets", title="Répartition par statut", hole=0.45))
            dom = f.groupby(["domaine", "selectionne"]).size().reset_index(name="Projets")
            fig = px.bar(dom, y="domaine", x="Projets", color="selectionne", orientation="h", barmode="stack",
                         title="Idées reçues par domaine", labels={"domaine": "", "selectionne": "Sélectionné"},
                         color_discrete_map={"Oui": PALETTE[0], "Non": PALETTE[3]})
            fig.update_yaxes(categoryorder="total ascending")
            plot(fig)

    with tabs[1]:
        if coh.empty:
            st.info("Aucune cohorte à comparer.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                m = coh.melt(id_vars="Cohorte", value_vars=["Idées reçues", "Sélectionnés", "Prototypes"], var_name="Étape", value_name="Nombre")
                plot(px.bar(m, x="Cohorte", y="Nombre", color="Étape", barmode="group", title="Comparaison des cohortes"))
            with c2:
                m = coh.melt(id_vars="Cohorte", value_vars=["Taux de sélection", "Taux de transformation", "Part des porteuses"], var_name="Taux", value_name="Valeur")
                fig = px.line(m, x="Cohorte", y="Valeur", color="Taux", markers=True, title="Évolution des taux")
                fig.update_yaxes(tickformat=".0%", range=[0, 1])
                plot(fig)
            g = f.groupby(["annee", "genre"]).size().reset_index(name="Projets")
            g["genre"] = g["genre"].map({"F": "Femmes", "H": "Hommes"})
            plot(px.bar(g, x="annee", y="Projets", color="genre", barmode="stack", title="Répartition par genre et par cohorte",
                        labels={"annee": "Cohorte", "genre": ""}))
            show = coh.copy()
            for c in ["Taux de sélection", "Taux de transformation", "Part des porteuses"]:
                show[c] = show[c].map(kpi.pct)
            show["Financements (FCFA)"] = show["Financements (FCFA)"].map(kpi.fcfa)
            st.dataframe(show, hide_index=True, width="stretch")

    with tabs[2]:
        late = f[f["en_retard"]].sort_values("jours_retard", ascending=False)
        if late.empty:
            st.success("Aucun projet actif en retard pour ces filtres.")
        else:
            st.warning(f"{len(late)} projet(s) actif(s) en retard sur {k['actifs']}.")
            fig = px.bar(late, x="jours_retard", y="titre", orientation="h", title="Retard maximal par projet (jours)",
                         labels={"jours_retard": "Jours de retard", "titre": ""}, color_discrete_sequence=[PALETTE[5]])
            fig.update_yaxes(categoryorder="total ascending")
            plot(fig)
            st.dataframe(pd.DataFrame({
                "Projet": late["titre"], "Domaine": late["domaine"], "Cohorte": late["annee"], "Mentor": late["mentor"],
                "Jours de retard": late["jours_retard"], "Avancement": (late["avancement"] * 100).round(0).astype(int).astype(str) + " %",
            }), hide_index=True, width="stretch")

    with tabs[3]:
        fin = t["financements"][t["financements"]["id_projet"].isin(f["id_projet"])].merge(f[["id_projet", "annee", "titre"]], on="id_projet")
        c1, c2 = st.columns(2)
        with c1:
            if fin.empty:
                st.info("Aucun financement pour ces filtres.")
            else:
                s = fin.groupby("annee")["montant_fcfa"].sum().reset_index()
                plot(px.bar(s, x="annee", y="montant_fcfa", title="Financements accordés par cohorte (FCFA)",
                            labels={"annee": "Cohorte", "montant_fcfa": "FCFA"}))
        with c2:
            if not fin.empty:
                s = fin.groupby("source")["montant_fcfa"].sum().reset_index()
                plot(px.pie(s, names="source", values="montant_fcfa", title="Financements par source", hole=0.45))
        part = t["partenariats"].copy()
        part["Actif"] = ((part["date_debut"] <= ref) & (part["date_fin"] >= ref)).map({True: "Oui", False: "Non"})
        st.subheader("Partenariats")
        st.dataframe(pd.DataFrame({"Partenaire": part["nom_partenaire"], "Type": part["type_partenaire"],
                                   "Début": fmt_date(part["date_debut"]), "Fin": fmt_date(part["date_fin"]), "Actif": part["Actif"]}),
                     hide_index=True, width="stretch")

    with tabs[4]:
        st.subheader("Lecture des résultats")
        lignes = kpi.interpretation(k, coh)
        for l in lignes:
            st.markdown(f"- {l}")
        st.caption("Cette lecture est produite par des règles fixes à partir des indicateurs, pas par l'IA.")
        c1, c2 = st.columns(2)
        c1.download_button("Exporter en Excel", exports.excel_bytes(k, f, coh), file_name="ciat_insight_analyse.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
        c2.download_button("Exporter la fiche de synthèse (PDF)", exports.pdf_bytes(k, f, coh, filtres, lignes),
                           file_name="ciat_insight_synthese.pdf", mime="application/pdf", width="stretch")
        st.caption("Export en image : survolez un graphique et cliquez sur l'icône d'appareil photo.")
