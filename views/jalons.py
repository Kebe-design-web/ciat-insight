"""Suivi des jalons d'un projet : avancement, alertes de retard, mise à jour, commentaires."""
import datetime as dt

import pandas as pd
import streamlit as st

from core import kpi
from core.auth import CAN_COMMENT
from core.db import reference_date, now_str
from views.common import load, refresh, header, fmt_date


def visible_projects(p, user):
    role = user["role"]
    if role == "Porteur":
        return p[p["id_porteur"] == user["id_porteur"]]
    if role == "Mentor":
        return p[p["id_mentor"] == user["id_mentor"]]
    return p[p["selectionne"] == "Oui"]


def render(db, user):
    porteur = user["role"] == "Porteur"
    header("Mon projet" if porteur else "Suivi des jalons",
           "Avancement, échéances et échanges avec le mentor" if porteur else "Avancement des projets accompagnés")
    t = load(db)
    ref = reference_date()
    p = visible_projects(kpi.enrich(t, ref), user)
    if p.empty:
        st.info("Aucun projet associé à votre compte." if user["role"] in ("Porteur", "Mentor") else "Aucun projet sélectionné.")
        return

    if len(p) == 1:
        pid = int(p.iloc[0]["id_projet"])
    else:
        order = p.sort_values(["en_retard", "jours_retard"], ascending=False)
        pid = st.selectbox("Projet", order["id_projet"].tolist(),
                           format_func=lambda i: f"{order.set_index('id_projet').loc[i, 'titre']}"
                                                 + ("  (en retard)" if order.set_index('id_projet').loc[i, 'en_retard'] else ""))
    cur = p.set_index("id_projet").loc[pid]

    st.subheader(cur["titre"])
    c = st.columns(4)
    c[0].metric("Statut", cur["statut"])
    c[1].metric("Cohorte", cur["annee"])
    c[2].metric("Mentor", cur["mentor"] or "Non affecté")
    c[3].metric("Jalons validés", f"{int(cur['nb_valides'])} / {int(cur['nb_jalons'])}")
    st.progress(float(cur["avancement"]), text=f"Avancement : {kpi.pct(cur['avancement'])}")

    if cur["selectionne"] != "Oui":
        st.info("Ce projet n'a pas été sélectionné pour l'incubation : il n'a pas de jalons.")
        return

    j = t["jalons"][t["jalons"]["id_projet"] == pid].copy()
    j["ordre"] = j["type_jalon"].map({tj: i for i, tj in enumerate(kpi.TYPES_JALONS)})
    j = j.sort_values("ordre")
    if cur["statut"] == "En incubation":
        for r in j.itertuples():
            if r.statut not in ("Validé", "Annulé") and r.date_prevue < ref:
                st.error(f"Retard : le jalon « {r.type_jalon} » devait être atteint le {r.date_prevue.strftime('%d/%m/%Y')} "
                         f"({(ref - r.date_prevue).days} jours de retard).")

    st.dataframe(pd.DataFrame({"Jalon": j["type_jalon"], "Date prévue": fmt_date(j["date_prevue"]),
                               "Date de réalisation": fmt_date(j["date_realisation"]), "Statut": j["statut"],
                               "Commentaire": j["commentaire"].fillna("")}),
                 hide_index=True, width="stretch")

    # ---------------- mise à jour d'un jalon
    st.subheader("Mettre à jour un jalon")
    statuts = ["Non démarré", "En cours"] if porteur else kpi.STATUTS_JALON
    if porteur:
        st.caption("La validation d'un jalon est faite par votre mentor ou la coordination.")
    with st.form("maj_jalon"):
        idj = st.selectbox("Jalon", j["id_jalon"].tolist(), format_func=lambda i: j.set_index("id_jalon").loc[i, "type_jalon"])
        jc = j.set_index("id_jalon").loc[idj]
        c1, c2 = st.columns(2)
        new_statut = c1.selectbox("Nouveau statut", statuts, index=statuts.index(jc["statut"]) if jc["statut"] in statuts else 0)
        prevue = c2.date_input("Date prévue", jc["date_prevue"].date(), format="DD/MM/YYYY")
        realisation = None
        if not porteur:
            default = jc["date_realisation"].date() if pd.notna(jc["date_realisation"]) else dt.date.today()
            realisation = c1.date_input("Date de réalisation (si validé)", default, max_value=dt.date.today(), format="DD/MM/YYYY")
        com_jalon = None
        if not porteur:
            old = jc["commentaire"] if isinstance(jc["commentaire"], str) else ""
            com_jalon = st.text_input("Commentaire sur ce jalon", old, max_chars=500)
        ok = st.form_submit_button("Enregistrer", type="primary")
    if ok:
        real = realisation.isoformat() if (new_statut == "Validé" and realisation) else None
        saved = False
        try:
            if porteur:
                db.execute("UPDATE jalons SET statut = ?, date_prevue = ?, date_realisation = ? WHERE id_jalon = ?",
                           (new_statut, prevue.isoformat(), real, int(idj)))
            else:
                db.execute("UPDATE jalons SET statut = ?, date_prevue = ?, date_realisation = ?, commentaire = ? WHERE id_jalon = ?",
                           (new_statut, prevue.isoformat(), real, (com_jalon or "").strip() or None, int(idj)))
            refresh()
            saved = True
        except Exception as e:
            st.error(f"Mise à jour impossible : {e}")
        if saved:
            st.rerun()

    # ---------------- commentaires
    st.subheader("Commentaires")
    com = t["commentaires"][t["commentaires"]["id_projet"] == pid].sort_values("date_heure", ascending=False)
    if com.empty:
        st.caption("Aucun commentaire.")
    users = t["utilisateurs"].set_index("id_utilisateur")
    for r in com.itertuples():
        auteur = users.loc[r.id_utilisateur, "role"] if r.id_utilisateur in users.index else "?"
        with st.chat_message("assistant" if auteur != "Porteur" else "user"):
            st.markdown(f"**{auteur}** · {r.date_heure[:16]}")
            st.write(r.texte)
    if user["role"] in CAN_COMMENT:
        with st.form("commentaire", clear_on_submit=True):
            texte = st.text_area("Ajouter un commentaire", max_chars=1000)
            if st.form_submit_button("Publier"):
                if len(texte.strip()) < 3:
                    st.error("Le commentaire est vide.")
                else:
                    db.execute("INSERT INTO commentaires (id_commentaire, id_projet, id_utilisateur, texte, date_heure) VALUES (?, ?, ?, ?, ?)",
                               (db.next_id("commentaires", "id_commentaire"), pid, user["id"], texte.strip(), now_str()))
                    refresh()
                    st.rerun()
