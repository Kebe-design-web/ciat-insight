"""
Assistant IA : question en français -> requête SQL générée par Gemini -> exécution sécurisée.

Garde-fous :
1. Le modèle reçoit la question et la STRUCTURE des tables, jamais les données.
2. Les tables exposées ne contiennent ni nom, ni prénom, ni e-mail.
3. La requête est contrôlée (SELECT uniquement, une seule instruction).
4. Elle s'exécute sur une copie en mémoire, avec un autorisateur SQLite qui
   refuse toute opération autre que la lecture.
5. La requête est toujours affichée pour vérification humaine.
"""
import json
import re
import sqlite3

import pandas as pd
import requests

from core.db import secret

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SCHEMA_TEXT = """
Tables disponibles (SQLite). Les dates sont du texte au format 'AAAA-MM-JJ'.

projets(id_projet, titre, domaine, annee_cohorte, statut, selectionne, date_depot,
        genre_porteur, prototype_valide, en_retard, jours_retard, avancement_pct, financement_fcfa)
  - domaine : 'TIC et IA', 'Mécanique et maintenance', 'Agriculture et environnement',
    'Énergie renouvelable', 'Pharmaceutique et biomédical', 'Éducation et insertion',
    'Services et entrepreneuriat'
  - annee_cohorte : '2024', '2025', '2026' (texte)
  - statut : 'Rejeté', 'En incubation', 'Prototype réalisé', 'Abandonné', 'Déposé'
  - selectionne, prototype_valide, en_retard : 'Oui' ou 'Non'
  - genre_porteur : 'F' ou 'H'
  - avancement_pct : nombre entre 0 et 100 (part des jalons validés)
jalons(id_projet, type_jalon, date_prevue, date_realisation, statut)
  - type_jalon : 'Cadrage', 'Étude de marché', 'Maquette', 'Prototype', 'Pitch final'
  - statut : 'Non démarré', 'En cours', 'Validé', 'Annulé'
financements(id_projet, source, montant_fcfa, date_octroi, statut, annee_cohorte)
partenariats(id_projet, nom_partenaire, type_partenaire, date_debut, date_fin)
"""

PROMPT = """Tu es l'assistant d'analyse de données du CIAT (Centre d'Innovation, d'Application
et de Transfert de l'ISEP Amadou Trawaré, Sénégal).
Ta seule tâche : traduire la question de l'utilisateur en UNE requête SQL SQLite de lecture.
{schema}
Règles :
- Utilise uniquement les tables et colonnes listées.
- Une seule instruction SELECT (ou WITH ... SELECT), sans point-virgule.
- Donne des noms de colonnes lisibles en français avec AS.
- "explication" décrit en une phrase CE QUE CALCULE la requête, sans aucun chiffre :
  tu ne connais pas les résultats, ils seront calculés après toi.
- Si la question ne peut pas être traitée avec ces données, mets "sql" à null et explique
  pourquoi dans "explication". N'invente jamais de donnée.
Réponds uniquement en JSON : {{"sql": "...", "explication": "une phrase", "graphique": "barres" | "ligne" | "camembert" | "aucun"}}

Question : {question}
"""

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex|"
    r"analyze|begin|commit|rollback|savepoint|release|load_extension|trigger)\b", re.IGNORECASE)

# Questions types utilisables sans clé d'API (requêtes écrites par l'équipe, pas par l'IA)
EXEMPLES = {
    "Combien de projets sont en retard par domaine ?":
        "SELECT domaine AS Domaine, COUNT(*) AS \"Projets en retard\" FROM projets WHERE en_retard = 'Oui' "
        "GROUP BY domaine ORDER BY 2 DESC",
    "Compare le taux de sélection des cohortes":
        "SELECT annee_cohorte AS Cohorte, ROUND(100.0 * SUM(selectionne = 'Oui') / COUNT(*), 1) AS \"Taux de sélection (%)\" "
        "FROM projets GROUP BY annee_cohorte ORDER BY annee_cohorte",
    "Quels domaines ont produit le plus de prototypes ?":
        "SELECT domaine AS Domaine, COUNT(*) AS Prototypes FROM projets WHERE prototype_valide = 'Oui' "
        "GROUP BY domaine ORDER BY 2 DESC",
    "Quelle est la part des porteuses par cohorte ?":
        "SELECT annee_cohorte AS Cohorte, ROUND(100.0 * SUM(genre_porteur = 'F') / COUNT(*), 1) AS \"Part des porteuses (%)\" "
        "FROM projets GROUP BY annee_cohorte ORDER BY annee_cohorte",
    "Montant des financements par source":
        "SELECT source AS Source, SUM(montant_fcfa) AS \"Montant (FCFA)\" FROM financements WHERE statut = 'Accordé' "
        "GROUP BY source ORDER BY 2 DESC",
}


KEY_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY", "API_KEY_GEMINI", "gemini_api_key", "google_api_key")


def gemini_key():
    """Cherche la clé Gemini sous plusieurs noms possibles, y compris dans une section [gemini]."""
    for n in KEY_NAMES:
        v = secret(n)
        if v and str(v).strip().strip('"').strip("'"):
            return str(v).strip().strip('"').strip("'")
    try:
        import streamlit as st
        for sec in ("gemini", "GEMINI", "google", "api"):
            if sec in st.secrets:
                d = st.secrets[sec]
                for n in ("api_key", "API_KEY", "key", "GEMINI_API_KEY"):
                    if n in d and str(d[n]).strip():
                        return str(d[n]).strip()
    except Exception:
        pass
    return None


def secret_names():
    """Noms (jamais les valeurs) des secrets visibles, pour le diagnostic."""
    try:
        import streamlit as st
        return sorted(st.secrets.keys())
    except Exception:
        return []


def configured():
    return bool(gemini_key())


def analysis_tables(p, t):
    """Tables exposées à l'assistant : aucune donnée nominative."""
    d = lambda s: s.dt.strftime("%Y-%m-%d")
    proj = pd.DataFrame({
        "id_projet": p["id_projet"], "titre": p["titre"], "domaine": p["domaine"],
        "annee_cohorte": p["annee"].astype(str), "statut": p["statut"], "selectionne": p["selectionne"],
        "date_depot": d(p["date_depot"]), "genre_porteur": p["genre"],
        "prototype_valide": p["prototype"].map({True: "Oui", False: "Non"}),
        "en_retard": p["en_retard"].map({True: "Oui", False: "Non"}),
        "jours_retard": p["jours_retard"], "avancement_pct": (p["avancement"] * 100).round(1),
        "financement_fcfa": p["financement"],
    })
    j = t["jalons"].copy()
    jal = pd.DataFrame({"id_projet": j["id_projet"], "type_jalon": j["type_jalon"], "date_prevue": d(j["date_prevue"]),
                        "date_realisation": d(j["date_realisation"]), "statut": j["statut"]})
    f = t["financements"].merge(p[["id_projet", "annee"]], on="id_projet", how="left")
    fin = pd.DataFrame({"id_projet": f["id_projet"], "source": f["source"], "montant_fcfa": f["montant_fcfa"],
                        "date_octroi": d(f["date_octroi"]), "statut": f["statut"], "annee_cohorte": f["annee"].astype(str)})
    pa = t["partenariats"]
    par = pd.DataFrame({"id_projet": pa["id_projet"], "nom_partenaire": pa["nom_partenaire"],
                        "type_partenaire": pa["type_partenaire"], "date_debut": d(pa["date_debut"]), "date_fin": d(pa["date_fin"])})
    return {"projets": proj, "jalons": jal, "financements": fin, "partenariats": par}


def check_sql(sql):
    """Renvoie (requête nettoyée, None) ou (None, message d'erreur)."""
    if not sql or not isinstance(sql, str):
        return None, "Aucune requête fournie."
    s = sql.strip().rstrip(";").strip()
    if ";" in s:
        return None, "Une seule instruction est autorisée."
    if not re.match(r"^(select|with)\b", s, re.IGNORECASE):
        return None, "Seules les requêtes de lecture (SELECT) sont autorisées."
    if FORBIDDEN.search(s):
        return None, "La requête contient une instruction interdite."
    return s, None


def _authorizer(action, *args):
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
               getattr(sqlite3, "SQLITE_RECURSIVE", 33)}
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def run_sql(sql, tables, limit=500):
    con = sqlite3.connect(":memory:")
    try:
        for name, df in tables.items():
            df.to_sql(name, con, index=False)
        con.set_authorizer(_authorizer)
        steps = {"n": 0}

        def guard():  # interrompt une requête trop longue
            steps["n"] += 1
            return 1 if steps["n"] > 2000 else 0
        con.set_progress_handler(guard, 1000)
        return pd.read_sql_query(f"SELECT * FROM ({sql}) LIMIT {int(limit)}", con)
    finally:
        con.close()


_MODEL_CACHE = {}


def _candidates(key):
    """Liste ordonnée de modèles Gemini utilisables pour cette clé (Flash stables d'abord)."""
    if "list" in _MODEL_CACHE:
        return _MODEL_CACHE["list"]
    try:
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                         headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=20)
        models = r.json().get("models", []) if r.status_code == 200 else []
    except Exception:
        models = []
    usable = [m["name"].split("/", 1)[-1] for m in models
              if "generateContent" in m.get("supportedGenerationMethods", [])]

    def score(n):
        stable = not any(w in n for w in ("preview", "exp", "image", "tts", "live", "audio", "thinking", "embedding"))
        nums = [float(x) for x in re.findall(r"gemini-(\d+(?:\.\d+)?)", n)]
        return ("flash" in n, stable, "lite" not in n, nums[0] if nums else 0.0)
    gemini = sorted((n for n in usable if n.startswith("gemini-")), key=score, reverse=True)
    for fallback in ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"):
        if fallback not in gemini:
            gemini.append(fallback)
    _MODEL_CACHE["list"] = gemini[:5]
    return _MODEL_CACHE["list"]


def _pick_model(key):
    c = _candidates(key)
    return c[0] if c else None


def ask_gemini(question):
    """Renvoie un dict {sql, explication, graphique} ou lève une exception explicite.

    En cas de surcharge (503, 500) ou de modèle introuvable (404), essaie le modèle
    suivant de la liste ; en cas de quota (429), attend 2 secondes et réessaie une fois.
    """
    import time
    key = gemini_key()
    if not key:
        raise RuntimeError("Assistant non configuré : ajoutez GEMINI_API_KEY dans les secrets.")
    forced = secret("GEMINI_MODEL")
    models = [forced] if forced else _candidates(key)
    body = {
        "contents": [{"role": "user", "parts": [{"text": PROMPT.format(schema=SCHEMA_TEXT, question=question)}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    last = None
    t0 = time.time()
    for model in models[:4]:
        for attempt in range(2):
            if time.time() - t0 > 30:
                raise RuntimeError("Gemini met trop de temps à répondre.")
            try:
                r = requests.post(GEMINI_URL.format(model=model), headers={"x-goog-api-key": key}, json=body, timeout=15)
            except requests.RequestException:
                last = "réseau"; break
            last = r.status_code
            if r.status_code == 200:
                try:
                    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    text = re.sub(r"^```(json)?|```$", "", text.strip()).strip()
                    out = json.loads(text)
                except Exception:
                    raise RuntimeError("Réponse de l'IA illisible. Reformulez la question.")
                if not forced and _MODEL_CACHE.get("list") and model in _MODEL_CACHE["list"]:
                    lst = _MODEL_CACHE["list"]; lst.remove(model); lst.insert(0, model)  # le prochain appel commence par lui
                return {"sql": out.get("sql"), "explication": out.get("explication", ""),
                        "graphique": out.get("graphique", "aucun"), "modele": model}
            if r.status_code in (401, 403):
                raise RuntimeError("Clé d'API refusée par Google : vérifiez GEMINI_API_KEY dans les secrets.")
            if r.status_code in (429, 500, 503) and attempt == 0:
                time.sleep(2); continue
            break  # 404, 400 ou échec répété : modèle suivant
    if last == 429:
        raise RuntimeError("Quota gratuit de Gemini atteint pour le moment.")
    raise RuntimeError(f"Service Gemini indisponible pour le moment (code {last}).")
