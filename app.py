"""
CIAT Insight · Tableau de bord décisionnel du CIAT et de son incubateur
ISEP Amadou Trawaré de Diamniadio · Évaluation pratique du cours d'IA générative
Équipe : Fatou KEBE (data analyst), Dietew NDOUR (développeur), Bousso NIANG (infographe)

Lancement local : streamlit run app.py
"""
import time

import streamlit as st

st.set_page_config(page_title="CIAT Insight", layout="wide", initial_sidebar_state="expanded")

from core import auth
from core.db import secret
from views import common, dashboard, projets, jalons, assistant, qualite, utilisateurs

common.style()

try:
    db = common.get_db()
except Exception as e:
    import re as _re
    st.error("Connexion à la base de données impossible. Vérifiez DATABASE_URL dans les secrets.")
    msg = str(e).strip().splitlines()[0] if str(e).strip() else ""
    msg = _re.sub(r"postgres(ql)?://\S+", "[adresse masquée]", msg)  # ne jamais afficher l'adresse complète
    st.caption(f"Détail technique : {type(e).__name__} : {msg[:300]}")
    low = msg.lower()
    if "password authentication failed" in low:
        st.info("Le mot de passe dans DATABASE_URL ne correspond pas à celui de la base Supabase.")
    elif "tenant or user not found" in low:
        st.info("L'identifiant ou le serveur de l'adresse est incorrect : recopiez l'adresse « Session pooler » de Supabase.")
    elif "could not translate host name" in low or "name or service not known" in low:
        st.info("Le nom du serveur dans DATABASE_URL est incorrect (faute de frappe ou caractère en trop).")
    st.stop()

ROUTES = {
    "Tableau de bord": dashboard.render,
    "Assistant IA": assistant.render,
    "Projets": projets.render,
    "Suivi des jalons": jalons.render,
    "Mon projet": jalons.render,
    "Qualité des données": qualite.render,
    "Utilisateurs": utilisateurs.render,
}


def login_page():
    left, mid, right = st.columns([1, 1.3, 1])
    with mid:
        st.markdown("<h1 style='margin-bottom:0'>CIAT Insight</h1>", unsafe_allow_html=True)
        st.caption("Tableau de bord décisionnel du Centre d'Innovation, d'Application et de Transfert · ISEP Amadou Trawaré")
        s = st.session_state
        s.setdefault("echecs", 0)
        s.setdefault("bloque_jusqua", 0.0)
        with st.form("login"):
            email = st.text_input("E-mail")
            pwd = st.text_input("Mot de passe", type="password")
            ok = st.form_submit_button("Se connecter", type="primary", width="stretch")
        if ok:
            if time.time() < s.bloque_jusqua:
                st.error(f"Trop de tentatives. Réessayez dans {int(s.bloque_jusqua - time.time())} secondes.")
            else:
                user = auth.authenticate(db, email, pwd)
                if user:
                    s.user, s.echecs = user, 0
                    st.rerun()
                else:
                    s.echecs += 1
                    if s.echecs >= 5:
                        s.bloque_jusqua, s.echecs = time.time() + 60, 0
                    st.error("E-mail ou mot de passe incorrect.")
        if str(secret("SHOW_DEMO_ACCOUNTS", "oui")).lower() == "oui":
            with st.expander("Comptes de démonstration (jury)"):
                st.markdown(
                    "| Rôle | E-mail |\n|---|---|\n"
                    "| Administrateur | admin@exemple.sn |\n| Coordonnateur | coordination@exemple.sn |\n"
                    "| Direction | direction@exemple.sn |\n| Mentor | mentor01@exemple.sn |\n| Porteur | porteur002@exemple.sn |")
                st.caption("Le mot de passe de démonstration est indiqué dans le guide utilisateur.")
        st.markdown("<p class='ciat-note'>Données de démonstration fictives. Les données personnelles sont traitées "
                    "conformément à la loi sénégalaise n° 2008-12 sur la protection des données à caractère personnel.</p>",
                    unsafe_allow_html=True)


if "user" not in st.session_state:
    login_page()
    st.stop()

user = st.session_state.user
pages = auth.PAGES.get(user["role"], [])

with st.sidebar:
    st.markdown("### CIAT Insight")
    st.caption(f"{user['email']}  \nRôle : **{user['role']}**")
    page = st.radio("Navigation", pages, label_visibility="collapsed")
    st.divider()
    if st.button("Se déconnecter", width="stretch"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()
    with st.expander("Usage de l'IA et données"):
        st.caption("L'assistant utilise Google Gemini. Il ne reçoit ni nom ni e-mail. Ses réponses sont à vérifier : "
                   "la requête utilisée est toujours affichée. Les tableaux de bord et la lecture des résultats "
                   "sont calculés sans IA.")

if page not in pages:  # sécurité : une page non autorisée n'est jamais affichée
    st.error("Accès non autorisé.")
    st.stop()

try:
    ROUTES[page](db, user)
except Exception as e:
    st.error("Une erreur est survenue sur cette page. Rechargez la page ou contactez l'administrateur.")
    st.caption(f"Détail technique : {type(e).__name__} : {e}")
