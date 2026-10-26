"""Assistant IA : interroger les données en langage naturel."""
import plotly.express as px
import streamlit as st

from core import ai, kpi
from core.db import reference_date, now_str
from views.common import load, header, plot


def _log(db, user, question, sql, statut):
    try:
        db.execute("INSERT INTO questions_ia (id_question, id_utilisateur, question, requete_generee, statut, date_heure) "
                   "VALUES (?, ?, ?, ?, ?, ?)",
                   (db.next_id("questions_ia", "id_question"), user["id"], question[:1000], sql, statut, now_str()))
    except Exception:
        pass  # le journal ne doit jamais bloquer la réponse


def _chart(df, kind):
    if df.shape[1] < 2 or len(df) > 60 or not str(df.dtypes.iloc[-1]).startswith(("int", "float")):
        return
    x, y = df.columns[0], df.columns[-1]
    if kind == "camembert":
        plot(px.pie(df, names=x, values=y))
    elif kind == "ligne":
        plot(px.line(df, x=x, y=y, markers=True))
    else:
        fig = px.bar(df, x=x, y=y)
        plot(fig)


def _show(db, user, question, sql, explication, kind, tables, statut_ok):
    sql_ok, err = ai.check_sql(sql)
    if err:
        st.error(f"Requête refusée par les garde-fous : {err}")
        _log(db, user, question, sql, "Refusée")
        return
    try:
        df = ai.run_sql(sql_ok, tables)
    except Exception:
        st.error("La requête n'a pas pu être exécutée. Reformulez la question.")
        _log(db, user, question, sql_ok, "Erreur")
        return
    _log(db, user, question, sql_ok, statut_ok)
    if explication:
        st.markdown(f"**Réponse :** {explication}")
    with st.expander("Requête utilisée (à vérifier)"):
        st.code(sql_ok, language="sql")
    if df.empty:
        st.info("La requête ne renvoie aucun résultat.")
        return
    st.dataframe(df, hide_index=True, width="stretch")
    _chart(df, kind)
    st.download_button("Télécharger le résultat (CSV)", df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="resultat_assistant.csv", mime="text/csv")


def render(db, user):
    header("Assistant IA", "Posez une question en français sur les données du CIAT")
    st.info("Les réponses sont générées par une IA (Google Gemini) et doivent être vérifiées. "
            "L'IA reçoit uniquement votre question et la structure des tables, jamais les noms ni les e-mails. "
            "La requête utilisée est toujours affichée et s'exécute en lecture seule.")
    t = load(db)
    p = kpi.enrich(t, reference_date())
    tables = ai.analysis_tables(p, t)

    if ai.configured():
        with st.form("question"):
            q = st.text_area("Votre question", placeholder="Ex. : Combien de projets agricoles sont en retard dans la cohorte 2026 ?", max_chars=500)
            go = st.form_submit_button("Demander à l'assistant", type="primary")
        if go and len(q.strip()) >= 5:
            with st.spinner("L'assistant prépare la requête..."):
                try:
                    rep = ai.ask_gemini(q.strip())
                except Exception as e:
                    st.error(str(e))
                    _log(db, user, q, None, "Erreur")
                    rep = None
            if rep:
                if not rep["sql"]:
                    st.warning(rep["explication"] or "Je ne trouve pas cette information dans les données disponibles.")
                    _log(db, user, q, None, "Sans réponse")
                else:
                    _show(db, user, q, rep["sql"], rep["explication"], rep["graphique"], tables, "Réussie")
    else:
        st.warning("L'assistant IA n'est pas configuré (clé GEMINI_API_KEY absente). Les questions types restent disponibles.")

    st.divider()
    st.markdown("**Questions types** (requêtes préparées par l'équipe, utilisables sans IA)")
    ex = st.selectbox("Choisir une question", list(ai.EXEMPLES))
    if st.button("Afficher la réponse"):
        _show(db, user, ex, ai.EXEMPLES[ex], None, "barres", tables, "Question type")

    with st.expander("Mon historique de questions"):
        h = db.query("SELECT date_heure, question, statut FROM questions_ia WHERE id_utilisateur = ? ORDER BY date_heure DESC",
                     (user["id"],)).head(15)
        if h.empty:
            st.caption("Aucune question posée.")
        else:
            st.dataframe(h.rename(columns={"date_heure": "Date", "question": "Question", "statut": "Statut"}),
                         hide_index=True, width="stretch")
