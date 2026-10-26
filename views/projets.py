"""Gestion des projets : liste, création (avec porteur), modification."""
import datetime as dt

import pandas as pd
import streamlit as st

from core import kpi
from core.auth import CAN_EDIT_PROJECTS
from core.db import reference_date
from views.common import load, refresh, header, fmt_date, EMAIL_RE


def jalon_statements(db, id_projet, date_debut):
    """5 jalons espacés de 8 semaines à partir du début de la cohorte."""
    start = db.next_id("jalons", "id_jalon")
    out = []
    for i, tj in enumerate(kpi.TYPES_JALONS):
        prevue = (pd.Timestamp(date_debut) + pd.Timedelta(weeks=8 * i)).date().isoformat()
        out.append(("INSERT INTO jalons (id_jalon, id_projet, type_jalon, date_prevue, date_realisation, statut, commentaire) "
                    "VALUES (?, ?, ?, ?, NULL, 'Non démarré', NULL)", (start + i, id_projet, tj, prevue)))
    return out


def check_project(titre, selectionne, statut, id_mentor):
    errs = []
    if len(titre.strip()) < 5:
        errs.append("Le titre doit contenir au moins 5 caractères.")
    if selectionne == "Oui":
        if id_mentor is None:
            errs.append("Un projet sélectionné doit avoir un mentor.")
        if statut in ("Déposé", "Rejeté"):
            errs.append("Un projet sélectionné ne peut pas avoir le statut « Déposé » ou « Rejeté ».")
    else:
        if statut not in ("Déposé", "Rejeté"):
            errs.append("Un projet non sélectionné doit avoir le statut « Déposé » ou « Rejeté ».")
        if id_mentor is not None:
            errs.append("Un mentor ne peut être affecté qu'à un projet sélectionné.")
    return errs


def render(db, user):
    header("Projets", "Liste et gestion des projets de l'incubateur")
    t = load(db)
    p = kpi.enrich(t, reference_date())
    editable = user["role"] in CAN_EDIT_PROJECTS
    tabs = st.tabs(["Liste", "Nouveau projet", "Modifier un projet"] if editable else ["Liste"])

    with tabs[0]:
        c1, c2, c3 = st.columns([2, 1, 1])
        q = c1.text_input("Rechercher", placeholder="Titre ou porteur")
        dom = c2.selectbox("Domaine", ["Tous"] + kpi.DOMAINES)
        stt = c3.selectbox("Statut", ["Tous"] + kpi.STATUTS_PROJET)
        f = p
        if q.strip():
            f = f[f["titre"].str.contains(q, case=False, na=False) | f["porteur"].str.contains(q, case=False, na=False)]
        if dom != "Tous":
            f = f[f["domaine"] == dom]
        if stt != "Tous":
            f = f[f["statut"] == stt]
        st.dataframe(pd.DataFrame({
            "ID": f["id_projet"], "Titre": f["titre"], "Domaine": f["domaine"], "Cohorte": f["annee"],
            "Porteur": f["porteur"], "Dépôt": fmt_date(f["date_depot"]), "Sélectionné": f["selectionne"],
            "Statut": f["statut"], "Mentor": f["mentor"], "Avancement": (f["avancement"] * 100).round(0),
        }), hide_index=True, width="stretch",
            column_config={"Avancement": st.column_config.ProgressColumn("Avancement", min_value=0, max_value=100, format="%d %%")})
        st.caption(f"{len(f)} projet(s).")

    if not editable:
        return

    cohortes = t["cohortes"].sort_values("annee")
    mentors = t["mentors"]
    mentor_opts = {None: "Aucun"} | {int(r.id_mentor): f"{r.prenom} {r.nom} ({r.specialite})" for r in mentors.itertuples()}

    # ---------------- création
    with tabs[1]:
        mode = st.radio("Porteur", ["Porteur existant", "Nouveau porteur"], horizontal=True)
        with st.form("nouveau_projet", clear_on_submit=False):
            titre = st.text_input("Titre du projet *")
            c1, c2 = st.columns(2)
            domaine = c1.selectbox("Domaine *", kpi.DOMAINES)
            id_cohorte = c2.selectbox("Cohorte *", cohortes["id_cohorte"].tolist(),
                                      format_func=lambda i: cohortes.set_index("id_cohorte").loc[i, "libelle"])
            date_depot = c1.date_input("Date de dépôt *", dt.date.today(), max_value=dt.date.today(), format="DD/MM/YYYY")
            selectionne = c2.radio("Sélectionné par le comité ?", ["Non", "Oui"], horizontal=True)
            statut = c1.selectbox("Statut *", kpi.STATUTS_PROJET)
            id_mentor = c2.selectbox("Mentor", list(mentor_opts), format_func=lambda i: mentor_opts[i])
            if mode == "Porteur existant":
                porteurs = t["porteurs"].sort_values("nom")
                id_porteur = st.selectbox("Porteur *", porteurs["id_porteur"].tolist(),
                                          format_func=lambda i: " ".join(porteurs.set_index("id_porteur").loc[i, ["prenom", "nom"]]))
            else:
                c3, c4 = st.columns(2)
                nom = c3.text_input("Nom *")
                prenom = c4.text_input("Prénom *")
                genre = c3.selectbox("Genre *", ["F", "H"], format_func=lambda g: "Femme" if g == "F" else "Homme")
                filiere = c4.text_input("Filière")
                email = st.text_input("E-mail *")
            ok = st.form_submit_button("Enregistrer le projet", type="primary")

        if ok:
            errs = check_project(titre, selectionne, statut, id_mentor)
            if mode == "Nouveau porteur":
                if not nom.strip() or not prenom.strip():
                    errs.append("Le nom et le prénom du porteur sont obligatoires.")
                if not EMAIL_RE.match(email.strip()):
                    errs.append("L'adresse e-mail n'est pas valide.")
                elif (t["porteurs"]["email"].str.lower() == email.strip().lower()).any():
                    errs.append("Un porteur utilise déjà cette adresse e-mail.")
            if errs:
                for e in errs:
                    st.error(e)
            else:
                try:
                    stm = []
                    if mode == "Nouveau porteur":
                        id_porteur = db.next_id("porteurs", "id_porteur")
                        stm.append(("INSERT INTO porteurs (id_porteur, nom, prenom, genre, filiere, email) VALUES (?, ?, ?, ?, ?, ?)",
                                    (id_porteur, nom.strip(), prenom.strip(), genre, filiere.strip() or None, email.strip().lower())))
                    id_projet = db.next_id("projets", "id_projet")
                    stm.append(("INSERT INTO projets (id_projet, titre, domaine, id_porteur, id_cohorte, id_mentor, date_depot, selectionne, statut) "
                                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (id_projet, titre.strip(), domaine, int(id_porteur), int(id_cohorte), id_mentor,
                                 date_depot.isoformat(), selectionne, statut)))
                    if selectionne == "Oui":
                        debut = cohortes.set_index("id_cohorte").loc[id_cohorte, "date_debut"]
                        stm += jalon_statements(db, id_projet, debut)
                    db.transaction(stm)
                    refresh()
                    st.success(f"Projet n° {id_projet} enregistré" + (" avec ses 5 jalons." if selectionne == "Oui" else "."))
                except Exception as e:
                    st.error(f"Enregistrement impossible : {e}")

    # ---------------- modification
    with tabs[2]:
        if p.empty:
            st.info("Aucun projet.")
            return
        pid = st.selectbox("Projet à modifier", p.sort_values("id_projet", ascending=False)["id_projet"].tolist(),
                           format_func=lambda i: f"{i} · {p.set_index('id_projet').loc[i, 'titre']}")
        cur = p.set_index("id_projet").loc[pid]
        with st.form("modifier_projet"):
            titre = st.text_input("Titre *", cur["titre"])
            c1, c2 = st.columns(2)
            domaine = c1.selectbox("Domaine *", kpi.DOMAINES, index=kpi.DOMAINES.index(cur["domaine"]) if cur["domaine"] in kpi.DOMAINES else 0)
            selectionne = c2.radio("Sélectionné ?", ["Non", "Oui"], index=1 if cur["selectionne"] == "Oui" else 0, horizontal=True)
            statut = c1.selectbox("Statut *", kpi.STATUTS_PROJET, index=kpi.STATUTS_PROJET.index(cur["statut"]) if cur["statut"] in kpi.STATUTS_PROJET else 0)
            cur_m = None if pd.isna(cur["id_mentor"]) else int(cur["id_mentor"])
            id_mentor = c2.selectbox("Mentor", list(mentor_opts), index=list(mentor_opts).index(cur_m) if cur_m in mentor_opts else 0,
                                     format_func=lambda i: mentor_opts[i])
            ok2 = st.form_submit_button("Enregistrer les modifications", type="primary")
        if ok2:
            errs = check_project(titre, selectionne, statut, id_mentor)
            if errs:
                for e in errs:
                    st.error(e)
            else:
                try:
                    stm = [("UPDATE projets SET titre = ?, domaine = ?, selectionne = ?, statut = ?, id_mentor = ? WHERE id_projet = ?",
                            (titre.strip(), domaine, selectionne, statut, id_mentor, int(pid)))]
                    if selectionne == "Oui" and int(cur["nb_jalons"]) == 0:
                        debut = cohortes.set_index("id_cohorte").loc[int(cur["id_cohorte"]), "date_debut"]
                        stm += jalon_statements(db, int(pid), debut)
                    db.transaction(stm)
                    refresh()
                    st.success("Modifications enregistrées.")
                except Exception as e:
                    st.error(f"Enregistrement impossible : {e}")
