"""Administration des comptes et des rôles."""
import pandas as pd
import streamlit as st

from core.auth import ROLES, hash_password, password_problem
from views.common import load, refresh, header, EMAIL_RE


def render(db, user):
    header("Utilisateurs", "Comptes, rôles et accès")
    t = load(db)
    u = t["utilisateurs"].sort_values("id_utilisateur")
    st.dataframe(u.rename(columns={"id_utilisateur": "ID", "email": "E-mail", "role": "Rôle", "id_mentor": "Mentor lié",
                                   "id_porteur": "Porteur lié", "actif": "Actif (1 = oui)"}), hide_index=True, width="stretch")
    st.caption("Les mots de passe ne sont jamais affichés ni stockés en clair.")

    mentors = {int(r.id_mentor): f"{r.prenom} {r.nom}" for r in t["mentors"].itertuples()}
    porteurs = {int(r.id_porteur): f"{r.prenom} {r.nom}" for r in t["porteurs"].itertuples()}

    tab1, tab2 = st.tabs(["Créer un compte", "Modifier un compte"])
    with tab1:
        role = st.selectbox("Rôle", ROLES, key="new_role")
        with st.form("nouveau_compte", clear_on_submit=True):
            email = st.text_input("E-mail *")
            lien = None
            if role == "Mentor":
                lien = st.selectbox("Fiche mentor *", list(mentors), format_func=lambda i: mentors[i])
            elif role == "Porteur":
                lien = st.selectbox("Fiche porteur *", list(porteurs), format_func=lambda i: porteurs[i])
            pwd = st.text_input("Mot de passe provisoire *", type="password")
            ok = st.form_submit_button("Créer le compte", type="primary")
        if ok:
            errs = []
            if not EMAIL_RE.match(email.strip()):
                errs.append("L'adresse e-mail n'est pas valide.")
            elif (u["email"].str.lower() == email.strip().lower()).any():
                errs.append("Cette adresse e-mail a déjà un compte.")
            if password_problem(pwd):
                errs.append(password_problem(pwd))
            for e in errs:
                st.error(e)
            if not errs:
                db.execute("INSERT INTO utilisateurs (id_utilisateur, email, mot_de_passe_hash, role, id_mentor, id_porteur, actif) "
                           "VALUES (?, ?, ?, ?, ?, ?, 1)",
                           (db.next_id("utilisateurs", "id_utilisateur"), email.strip().lower(), hash_password(pwd), role,
                            lien if role == "Mentor" else None, lien if role == "Porteur" else None))
                refresh()
                st.success("Compte créé. Communiquez le mot de passe provisoire à la personne par un canal sûr.")

    with tab2:
        uid = st.selectbox("Compte", u["id_utilisateur"].tolist(),
                           format_func=lambda i: f"{u.set_index('id_utilisateur').loc[i, 'email']} ({u.set_index('id_utilisateur').loc[i, 'role']})")
        cur = u.set_index("id_utilisateur").loc[uid]
        with st.form("modifier_compte"):
            c1, c2 = st.columns(2)
            new_role = c1.selectbox("Rôle", ROLES, index=ROLES.index(cur["role"]) if cur["role"] in ROLES else 0)
            actif = c2.radio("Compte actif", [1, 0], index=0 if int(cur["actif"]) == 1 else 1, horizontal=True,
                              format_func=lambda v: "Oui" if v == 1 else "Non")
            new_pwd = st.text_input("Nouveau mot de passe (laisser vide pour ne pas changer)", type="password")
            ok2 = st.form_submit_button("Enregistrer", type="primary")
        if ok2:
            if int(uid) == user["id"] and (actif == 0 or new_role != "Administrateur"):
                st.error("Vous ne pouvez pas désactiver votre propre compte ni retirer votre rôle d'administrateur.")
            elif new_role in ("Mentor", "Porteur") and pd.isna(cur["id_mentor" if new_role == "Mentor" else "id_porteur"]):
                st.error("Ce rôle demande un lien vers une fiche mentor ou porteur : créez plutôt un nouveau compte.")
            elif new_pwd and password_problem(new_pwd):
                st.error(password_problem(new_pwd))
            else:
                if new_pwd:
                    db.execute("UPDATE utilisateurs SET role = ?, actif = ?, mot_de_passe_hash = ? WHERE id_utilisateur = ?",
                               (new_role, actif, hash_password(new_pwd), int(uid)))
                else:
                    db.execute("UPDATE utilisateurs SET role = ?, actif = ? WHERE id_utilisateur = ?", (new_role, actif, int(uid)))
                refresh()
                st.success("Compte mis à jour.")
