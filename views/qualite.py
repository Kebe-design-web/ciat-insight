"""Contrôle de la qualité des données (mêmes contrôles que le classeur Excel)."""
import pandas as pd
import streamlit as st

from core.db import reference_date
from views.common import load, header


def checks(t, ref):
    pr, po, j, f, pa = t["projets"], t["porteurs"], t["jalons"], t["financements"], t["partenariats"]
    return [
        ("Projets sans titre", int(pr["titre"].fillna("").str.strip().eq("").sum())),
        ("Doublons d'identifiant projet", int(pr["id_projet"].duplicated().sum())),
        ("Projets dont le porteur n'existe pas", int((~pr["id_porteur"].isin(po["id_porteur"])).sum())),
        ("Projets sélectionnés sans mentor", int((pr["selectionne"].eq("Oui") & pr["id_mentor"].isna()).sum())),
        ("Projets non sélectionnés avec mentor", int((pr["selectionne"].eq("Non") & pr["id_mentor"].notna()).sum())),
        ("Porteurs sans genre renseigné", int(po["genre"].isna().sum())),
        ("Doublons d'e-mail porteur", int(po["email"].str.lower().duplicated().sum())),
        ("Jalons dont le projet n'existe pas", int((~j["id_projet"].isin(pr["id_projet"])).sum())),
        ("Jalons validés sans date de réalisation", int((j["statut"].eq("Validé") & j["date_realisation"].isna()).sum())),
        ("Jalons non validés avec date de réalisation", int((~j["statut"].eq("Validé") & j["date_realisation"].notna()).sum())),
        ("Dates de dépôt postérieures à la date de référence", int((pr["date_depot"] > ref).sum())),
        ("Financements à montant nul ou négatif", int((f["montant_fcfa"] <= 0).sum())),
        ("Partenariats avec date de fin avant date de début", int((pa["date_fin"] < pa["date_debut"]).sum())),
    ]


def render(db, user):
    header("Qualité des données", "Contrôles automatiques de cohérence")
    t = load(db)
    res = pd.DataFrame(checks(t, reference_date()), columns=["Contrôle", "Anomalies"])
    res["Résultat"] = res["Anomalies"].map(lambda n: "OK" if n == 0 else "À corriger")
    total = int(res["Anomalies"].sum())
    (st.success if total == 0 else st.warning)(f"{total} anomalie(s) détectée(s) sur {len(res)} contrôles.")
    st.dataframe(res, hide_index=True, width="stretch")

    with st.expander("Taux de complétude par table"):
        rows = []
        for name in ["porteurs", "projets", "jalons", "financements", "partenariats"]:
            df = t[name]
            for c in df.columns:
                rows.append({"Table": name, "Colonne": c, "Complétude": round(100 * df[c].notna().mean(), 1) if len(df) else 0})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={"Complétude": st.column_config.ProgressColumn("Complétude", min_value=0, max_value=100, format="%.1f %%")})
        st.caption("Une complétude inférieure à 100 % est normale pour les colonnes facultatives (mentor d'un projet non sélectionné, date de réalisation d'un jalon non validé).")
