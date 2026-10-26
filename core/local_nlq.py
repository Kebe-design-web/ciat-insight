"""
Moteur de secours de l'assistant : traduit une question en français en requête SQL
à l'aide de règles fixes (mots-clés), sans IA générative.

Il sert quand Gemini est indisponible (clé absente, quota atteint, réseau coupé).
Il couvre les questions les plus courantes : nombre de projets, retards, prototypes,
taux, part des porteuses, financements, avancement, partenariats, avec des
regroupements (domaine, cohorte, statut, genre, source) et des filtres
(domaine, année de cohorte, statut).
"""
import re
import unicodedata

DOMAINES = [
    (r"agri|agro|environnement|maraich|elevage", "Agriculture et environnement"),
    (r"energ|solaire|electri", "Énergie renouvelable"),
    (r"\btic\b|numerique|informatique|digital|\bia\b|intelligence artificielle|logiciel|appli", "TIC et IA"),
    (r"mecani|maintenance|fabrication", "Mécanique et maintenance"),
    (r"pharma|sante|biomed|medic", "Pharmaceutique et biomédical"),
    (r"educ|\bformation|insertion|enseign", "Éducation et insertion"),
    (r"servic|entrepren|collectivit|commerce", "Services et entrepreneuriat"),
]
STATUTS = [
    (r"en incubation|actif|en cours", "En incubation"),
    (r"rejet|refus|non retenu", "Rejeté"),
    (r"abandon", "Abandonné"),
    (r"prototype realise", "Prototype réalisé"),
]


def _norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _has(q, pattern):
    return re.search(pattern, q) is not None


def translate(question):
    """Renvoie {sql, explication, graphique} ou None si la question n'est pas comprise."""
    q = _norm(question)

    # ---------------- filtres
    where, desc = [], []
    for pat, dom in DOMAINES:
        if _has(q, pat) and not _has(q, r"par (domaine|secteur)"):
            where.append(f"domaine = '{dom}'"); desc.append(f"domaine « {dom} »")
            break
    years = sorted(set(re.findall(r"\b(2024|2025|2026)\b", q)))
    if years and not _has(q, r"compar|evolution|par (cohorte|annee)"):
        where.append("annee_cohorte IN (" + ", ".join(f"'{y}'" for y in years) + ")")
        desc.append("cohorte " + " et ".join(years))
    for pat, stt in STATUTS:
        if _has(q, pat) and not _has(q, r"par statut"):
            where.append(f"statut = '{stt}'"); desc.append(f"statut « {stt} »")
            break

    # ---------------- regroupement
    group, glabel = None, None
    if _has(q, r"par (domaine|secteur)|quels? domaines?|quel secteur|chaque domaine"):
        group, glabel = "domaine", "Domaine"
    elif _has(q, r"par (cohorte|annee|promotion)|compar|evolution|chaque cohorte|cohortes"):
        group, glabel = "annee_cohorte", "Cohorte"
    elif _has(q, r"par statut|repartition des statuts|chaque statut"):
        group, glabel = "statut", "Statut"
    elif _has(q, r"par (genre|sexe)|hommes? et (les )?femmes?|repartition .*genre"):
        group, glabel = "genre_porteur", "Genre"

    def build(select, table="projets", extra_where=None, order="2 DESC", label=""):
        w = list(where) + (extra_where or [])
        if table != "projets":
            w = [c for c in w if not c.startswith(("domaine", "statut"))]  # colonnes absentes
        clause = (" WHERE " + " AND ".join(w)) if w else ""
        if group and (table == "projets" or group == "annee_cohorte"):
            sql = f"SELECT {group} AS {glabel}, {select} FROM {table}{clause} GROUP BY {group} ORDER BY {order if group != 'annee_cohorte' else '1'}"
        else:
            sql = f"SELECT {select} FROM {table}{clause}"
        expl = label + (f", par {glabel.lower()}" if group else "") + (" (" + ", ".join(desc) + ")" if desc else "") + "."
        return {"sql": sql, "explication": expl[0].upper() + expl[1:],
                "graphique": "ligne" if group == "annee_cohorte" else ("barres" if group else "aucun")}

    # ---------------- liste de projets
    if _has(q, r"\bquels projets|liste|lesquels|quels sont les projets|nomme"):
        cond = []
        lab = "liste des projets"
        if _has(q, r"retard"):
            cond.append("en_retard = 'Oui'"); lab = "liste des projets en retard, du plus grand retard au plus petit"
            order = "jours_retard DESC"
        elif _has(q, r"prototype"):
            cond.append("prototype_valide = 'Oui'"); lab = "liste des projets ayant atteint le prototype"; order = "annee_cohorte"
        else:
            order = "annee_cohorte, domaine"
        w = list(where) + cond
        clause = (" WHERE " + " AND ".join(w)) if w else ""
        sql = (f"SELECT titre AS Projet, domaine AS Domaine, annee_cohorte AS Cohorte, statut AS Statut, "
               f"jours_retard AS \"Jours de retard\" FROM projets{clause} ORDER BY {order}")
        return {"sql": sql, "explication": (lab + (" (" + ", ".join(desc) + ")" if desc else "") + ".").capitalize(), "graphique": "aucun"}

    # ---------------- indicateurs
    if _has(q, r"financ|montant|fcfa|argent|budget|subvention"):
        if _has(q, r"par source|quelle source|sources|bailleur|financeur"):
            group_save = ("source", "Source")
            w = [c for c in where if c.startswith("annee_cohorte")] + ["statut = 'Accordé'"]
            sql = (f"SELECT source AS Source, SUM(montant_fcfa) AS \"Montant (FCFA)\" FROM financements WHERE {' AND '.join(w)} "
                   f"GROUP BY source ORDER BY 2 DESC")
            return {"sql": sql, "explication": "Somme des financements accordés, par source" + (" (" + ", ".join(d for d in desc if d.startswith('cohorte')) + ")" if any(d.startswith('cohorte') for d in desc) else "") + ".", "graphique": "barres"}
        if any(c.startswith(("domaine", "statut")) for c in where) or group in ("domaine", "statut", "genre_porteur"):
            return build("SUM(financement_fcfa) AS \"Financements (FCFA)\"", label="somme des financements accordés aux projets")
        return build("SUM(montant_fcfa) AS \"Montant (FCFA)\"", table="financements", extra_where=["statut = 'Accordé'"], label="somme des financements accordés")
    if _has(q, r"partenari"):
        sql = "SELECT type_partenaire AS \"Type de partenaire\", COUNT(*) AS Partenariats FROM partenariats GROUP BY type_partenaire ORDER BY 2 DESC"
        return {"sql": sql, "explication": "Nombre de partenariats par type de partenaire.", "graphique": "barres"}
    if _has(q, r"taux de transformation|transform"):
        return build("ROUND(100.0 * SUM(prototype_valide = 'Oui') / NULLIF(SUM(selectionne = 'Oui'), 0), 1) AS \"Taux de transformation (%)\"",
                     label="part des projets sélectionnés qui ont atteint le prototype")
    if _has(q, r"taux de selection|taux de reussite|taux.*retenu|pourcentage.*selection"):
        return build("ROUND(100.0 * SUM(selectionne = 'Oui') / COUNT(*), 1) AS \"Taux de sélection (%)\"",
                     label="part des idées reçues qui ont été sélectionnées")
    if _has(q, r"taux de retard|pourcentage.*retard|part.*retard"):
        return build("ROUND(100.0 * SUM(en_retard = 'Oui') / NULLIF(SUM(statut = 'En incubation'), 0), 1) AS \"Taux de retard (%)\"",
                     label="part des projets en incubation qui sont en retard")
    if _has(q, r"porteuse|femme|fille|feminin") and not group == "genre_porteur":
        return build("ROUND(100.0 * SUM(genre_porteur = 'F') / COUNT(*), 1) AS \"Part des porteuses (%)\"",
                     label="part des projets portés par une femme")
    if group == "genre_porteur" or _has(q, r"\bgenre\b|\bsexe\b"):
        group, glabel = "genre_porteur", "Genre"
        return build("COUNT(*) AS Projets", label="nombre de projets selon le genre du porteur")
    if _has(q, r"avancement|progression|progres"):
        return build("ROUND(AVG(avancement_pct), 1) AS \"Avancement moyen (%)\"", extra_where=["statut = 'En incubation'"] if not any(c.startswith("statut") for c in where) else None,
                     label="avancement moyen (part des jalons validés) des projets en incubation")
    if _has(q, r"retard"):
        return build("COUNT(*) AS \"Projets en retard\"", extra_where=["en_retard = 'Oui'"], label="nombre de projets en retard")
    if _has(q, r"prototype"):
        return build("COUNT(*) AS Prototypes", extra_where=["prototype_valide = 'Oui'"], label="nombre de projets ayant atteint le prototype")
    if _has(q, r"selection|retenu|accepte"):
        return build("COUNT(*) AS \"Projets sélectionnés\"", extra_where=["selectionne = 'Oui'"], label="nombre de projets sélectionnés")
    if _has(q, r"combien|nombre|total|idees?|projets?|dossiers?|candidatures?|depos"):
        if any(c.startswith("statut") for c in where):
            return build("COUNT(*) AS Projets", label="nombre de projets")
        return build("COUNT(*) AS \"Idées reçues\"", label="nombre d'idées reçues")
    return None


EXEMPLES_LIBRES = [
    "Combien de projets agricoles sont en retard ?",
    "Compare le taux de sélection des cohortes",
    "Quels projets sont en retard en 2026 ?",
    "Quelle est la part des porteuses par domaine ?",
    "Montant des financements par source",
    "Avancement moyen des projets en énergie",
]
