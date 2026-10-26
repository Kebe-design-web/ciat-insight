"""Calcul des indicateurs K1 à K11 (définitions : cahier des charges, section 7)."""
import pandas as pd

DOMAINES = ["TIC et IA", "Mécanique et maintenance", "Agriculture et environnement",
            "Énergie renouvelable", "Pharmaceutique et biomédical",
            "Éducation et insertion", "Services et entrepreneuriat"]
STATUTS_PROJET = ["Déposé", "Rejeté", "En incubation", "Prototype réalisé", "Abandonné"]
TYPES_JALONS = ["Cadrage", "Étude de marché", "Maquette", "Prototype", "Pitch final"]
STATUTS_JALON = ["Non démarré", "En cours", "Validé", "Annulé"]


def enrich(t, ref):
    """Vue d'analyse des projets : ajoute genre, année, avancement, prototype, retard, financement."""
    p = t["projets"].copy()
    p = p.merge(t["porteurs"][["id_porteur", "nom", "prenom", "genre"]], on="id_porteur", how="left")
    p = p.merge(t["cohortes"][["id_cohorte", "annee"]], on="id_cohorte", how="left")
    m = t["mentors"][["id_mentor", "nom", "prenom"]].rename(columns={"nom": "mentor_nom", "prenom": "mentor_prenom"})
    p = p.merge(m, on="id_mentor", how="left")
    p["porteur"] = p["prenom"].fillna("") + " " + p["nom"].fillna("")
    p["mentor"] = (p["mentor_prenom"].fillna("") + " " + p["mentor_nom"].fillna("")).str.strip()

    j = t["jalons"].copy()
    if j.empty:
        for c in ["nb_jalons", "nb_valides", "avancement", "jours_retard"]:
            p[c] = 0
        p["prototype"] = False
        p["en_retard"] = False
    else:
        j["valide"] = j["statut"].eq("Validé")
        agg = j.groupby("id_projet").agg(nb_jalons=("id_jalon", "count"), nb_valides=("valide", "sum")).reset_index()
        p = p.merge(agg, on="id_projet", how="left")
        p[["nb_jalons", "nb_valides"]] = p[["nb_jalons", "nb_valides"]].fillna(0).astype(int)
        p["avancement"] = (p["nb_valides"] / p["nb_jalons"].where(p["nb_jalons"] > 0)).fillna(0.0)

        proto = set(j.loc[j["type_jalon"].eq("Prototype") & j["valide"], "id_projet"])
        p["prototype"] = p["id_projet"].isin(proto)

        late = j[~j["statut"].isin(["Validé", "Annulé"]) & (j["date_prevue"] < ref)].copy()
        late["jours"] = (ref - late["date_prevue"]).dt.days
        retard = late.groupby("id_projet")["jours"].max()
        p["jours_retard"] = p["id_projet"].map(retard).fillna(0).astype(int)
        p["en_retard"] = p["statut"].eq("En incubation") & (p["jours_retard"] > 0)
        p.loc[~p["en_retard"], "jours_retard"] = 0

    fin = t["financements"]
    tot = fin[fin["statut"].eq("Accordé")].groupby("id_projet")["montant_fcfa"].sum()
    p["financement"] = p["id_projet"].map(tot).fillna(0).astype(int)
    return p


def ratio(a, b):
    return (a / b) if b else 0.0


def compute(p, t, ref):
    """p : vue des projets déjà filtrée. Renvoie un dictionnaire d'indicateurs."""
    k1 = len(p)
    k2 = int(p["selectionne"].eq("Oui").sum())
    k4 = int(p["prototype"].sum())
    actifs = p[p["statut"].eq("En incubation")]
    k6 = int(p["en_retard"].sum())
    fin = t["financements"]
    k10 = int(fin[fin["statut"].eq("Accordé") & fin["id_projet"].isin(p["id_projet"])]["montant_fcfa"].sum())
    part = t["partenariats"]
    k11 = int(((part["date_debut"] <= ref) & (part["date_fin"] >= ref)).sum())
    return {
        "K1": k1,
        "K2": k2,
        "K3": ratio(k2, k1),
        "K4": k4,
        "K5": ratio(k4, k2),
        "actifs": len(actifs),
        "K6": k6,
        "K7": ratio(k6, len(actifs)),
        "K8": float(actifs["avancement"].mean()) if len(actifs) else 0.0,
        "K9": ratio(int(p["genre"].eq("F").sum()), k1),
        "K10": k10,
        "K11": k11,
    }


def by_cohort(p, t, ref):
    rows = []
    for an in sorted(p["annee"].dropna().unique()):
        k = compute(p[p["annee"] == an], t, ref)
        rows.append({"Cohorte": an, "Idées reçues": k["K1"], "Sélectionnés": k["K2"], "Prototypes": k["K4"],
                     "Taux de sélection": k["K3"], "Taux de transformation": k["K5"],
                     "Projets en retard": k["K6"], "Part des porteuses": k["K9"], "Financements (FCFA)": k["K10"]})
    return pd.DataFrame(rows)


def pct(x):
    return f"{x * 100:.1f} %".replace(".", ",")


def fcfa(x):
    return f"{x:,.0f} FCFA".replace(",", " ")


def interpretation(k, coh):
    """Lecture automatique des résultats (règles fixes, sans IA)."""
    lines = []
    if k["K1"] == 0:
        return ["Aucun projet ne correspond aux filtres choisis."]
    lines.append(f"Sur {k['K1']} idées reçues, {k['K2']} ont été sélectionnées, soit un taux de sélection de {pct(k['K3'])}.")
    if k["K2"]:
        lines.append(f"{k['K4']} projets sélectionnés ont atteint le prototype ({pct(k['K5'])} de transformation).")
    if k["actifs"]:
        msg = f"{k['K6']} projets actifs sur {k['actifs']} sont en retard ({pct(k['K7'])})."
        if k["K7"] >= 0.3:
            msg += " Ce niveau justifie un point de suivi prioritaire avec les mentors concernés."
        lines.append(msg)
        lines.append(f"L'avancement moyen des projets actifs est de {pct(k['K8'])} des jalons validés.")
    lines.append(f"Les femmes portent {pct(k['K9'])} des projets.")
    if len(coh) >= 2:
        a, b = coh.iloc[-2], coh.iloc[-1]
        diff = (b["Taux de sélection"] - a["Taux de sélection"]) * 100
        sens = "hausse" if diff > 0 else "baisse" if diff < 0 else "stabilité"
        lines.append(f"Entre {a['Cohorte']} et {b['Cohorte']}, le taux de sélection est en {sens} "
                     f"({abs(diff):.1f} points).".replace(".", ",", 1) if sens != "stabilité" else
                     f"Entre {a['Cohorte']} et {b['Cohorte']}, le taux de sélection est stable.")
    lines.append(f"Financements accordés : {fcfa(k['K10'])}. Partenariats actifs : {k['K11']}.")
    return lines
