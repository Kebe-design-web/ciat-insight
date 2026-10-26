"""
Accès aux données de CIAT Insight.

- En local : base SQLite (fichier ciat_insight.db), créée automatiquement.
- En ligne : PostgreSQL de Supabase, via la variable DATABASE_URL (secrets Streamlit).

Au premier lancement, les tables sont créées puis remplies avec le jeu de
données fictif du dossier data/ et les comptes de démonstration.
"""
import os
import sqlite3
import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def secret(name, default=None):
    """Lit un paramètre dans les secrets Streamlit, puis dans les variables d'environnement."""
    try:
        import streamlit as st
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, default)


# ---------------------------------------------------------------- schéma
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS cohortes (
        id_cohorte INTEGER PRIMARY KEY,
        annee VARCHAR(4) NOT NULL,
        libelle VARCHAR(50) NOT NULL,
        date_debut DATE NOT NULL,
        date_fin DATE NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS porteurs (
        id_porteur INTEGER PRIMARY KEY,
        nom VARCHAR(80) NOT NULL,
        prenom VARCHAR(80) NOT NULL,
        genre CHAR(1) NOT NULL CHECK (genre IN ('F', 'H')),
        filiere VARCHAR(100),
        email VARCHAR(120) NOT NULL UNIQUE)""",
    """CREATE TABLE IF NOT EXISTS mentors (
        id_mentor INTEGER PRIMARY KEY,
        nom VARCHAR(80) NOT NULL,
        prenom VARCHAR(80) NOT NULL,
        specialite VARCHAR(80) NOT NULL,
        email VARCHAR(120) NOT NULL UNIQUE)""",
    """CREATE TABLE IF NOT EXISTS projets (
        id_projet INTEGER PRIMARY KEY,
        titre VARCHAR(200) NOT NULL,
        domaine VARCHAR(80) NOT NULL,
        id_porteur INTEGER NOT NULL REFERENCES porteurs(id_porteur),
        id_cohorte INTEGER NOT NULL REFERENCES cohortes(id_cohorte),
        id_mentor INTEGER REFERENCES mentors(id_mentor),
        date_depot DATE NOT NULL,
        selectionne VARCHAR(3) NOT NULL CHECK (selectionne IN ('Oui', 'Non')),
        statut VARCHAR(30) NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS jalons (
        id_jalon INTEGER PRIMARY KEY,
        id_projet INTEGER NOT NULL REFERENCES projets(id_projet),
        type_jalon VARCHAR(30) NOT NULL,
        date_prevue DATE NOT NULL,
        date_realisation DATE,
        statut VARCHAR(20) NOT NULL,
        commentaire VARCHAR(500))""",
    """CREATE TABLE IF NOT EXISTS partenariats (
        id_partenariat INTEGER PRIMARY KEY,
        nom_partenaire VARCHAR(150) NOT NULL,
        type_partenaire VARCHAR(50) NOT NULL,
        id_projet INTEGER REFERENCES projets(id_projet),
        date_debut DATE NOT NULL,
        date_fin DATE NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS financements (
        id_financement INTEGER PRIMARY KEY,
        id_projet INTEGER NOT NULL REFERENCES projets(id_projet),
        source VARCHAR(150) NOT NULL,
        montant_fcfa INTEGER NOT NULL CHECK (montant_fcfa > 0),
        date_octroi DATE NOT NULL,
        statut VARCHAR(20) NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS utilisateurs (
        id_utilisateur INTEGER PRIMARY KEY,
        email VARCHAR(120) NOT NULL UNIQUE,
        mot_de_passe_hash VARCHAR(200) NOT NULL,
        role VARCHAR(20) NOT NULL,
        id_mentor INTEGER REFERENCES mentors(id_mentor),
        id_porteur INTEGER REFERENCES porteurs(id_porteur),
        actif INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1)))""",
    """CREATE TABLE IF NOT EXISTS commentaires (
        id_commentaire INTEGER PRIMARY KEY,
        id_projet INTEGER NOT NULL REFERENCES projets(id_projet),
        id_utilisateur INTEGER NOT NULL REFERENCES utilisateurs(id_utilisateur),
        texte TEXT NOT NULL,
        date_heure VARCHAR(19) NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS questions_ia (
        id_question INTEGER PRIMARY KEY,
        id_utilisateur INTEGER NOT NULL REFERENCES utilisateurs(id_utilisateur),
        question TEXT NOT NULL,
        requete_generee TEXT,
        statut VARCHAR(20) NOT NULL,
        date_heure VARCHAR(19) NOT NULL)""",
]

# Ordre de chargement (respecte les clés étrangères) et colonnes entières
SEED = [
    ("cohortes", ["id_cohorte"]),
    ("porteurs", ["id_porteur"]),
    ("mentors", ["id_mentor"]),
    ("projets", ["id_projet", "id_porteur", "id_cohorte", "id_mentor"]),
    ("jalons", ["id_jalon", "id_projet"]),
    ("partenariats", ["id_partenariat", "id_projet"]),
    ("financements", ["id_financement", "id_projet", "montant_fcfa"]),
]

DATE_COLS = {
    "cohortes": ["date_debut", "date_fin"],
    "projets": ["date_depot"],
    "jalons": ["date_prevue", "date_realisation"],
    "partenariats": ["date_debut", "date_fin"],
    "financements": ["date_octroi"],
}

TABLES = ["cohortes", "porteurs", "mentors", "projets", "jalons", "partenariats",
          "financements", "utilisateurs", "commentaires", "questions_ia"]


class DB:
    def __init__(self, url=None):
        self.url = url or secret("DATABASE_URL", f"sqlite:///{ROOT / 'ciat_insight.db'}")
        self.pg = self.url.startswith(("postgres://", "postgresql://"))

    # -- connexion
    def connect(self):
        if self.pg:
            import psycopg2  # installé via requirements.txt
            return psycopg2.connect(self.url, connect_timeout=10)
        con = sqlite3.connect(self.url.replace("sqlite:///", "", 1), check_same_thread=False)
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def _sql(self, sql):
        # SQLite utilise ? ; psycopg2 utilise %s
        return sql.replace("?", "%s") if self.pg else sql

    # -- lecture / écriture
    def query(self, sql, params=()):
        con = self.connect()
        try:
            cur = con.cursor()
            cur.execute(self._sql(sql), tuple(params))
            cols = [d[0] for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=cols)
        finally:
            con.close()

    def execute(self, sql, params=()):
        con = self.connect()
        try:
            cur = con.cursor()
            cur.execute(self._sql(sql), tuple(params))
            con.commit()
        finally:
            con.close()

    def executemany(self, sql, rows):
        con = self.connect()
        try:
            cur = con.cursor()
            cur.executemany(self._sql(sql), rows)
            con.commit()
        finally:
            con.close()

    def transaction(self, statements):
        """Exécute plusieurs requêtes d'un bloc : tout passe ou rien ne passe."""
        con = self.connect()
        try:
            cur = con.cursor()
            for sql, params in statements:
                cur.execute(self._sql(sql), tuple(params))
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def next_id(self, table, col):
        df = self.query(f"SELECT COALESCE(MAX({col}), 0) AS m FROM {table}")
        return int(df.iloc[0, 0]) + 1

    # -- initialisation
    def init(self):
        for ddl in SCHEMA:
            self.execute(ddl)
        if self.pg:
            # Supabase expose le schéma public via son API REST (Data API).
            # Activer la sécurité au niveau des lignes (RLS) sans aucune règle
            # bloque tout accès par cette API. L'application, connectée avec le
            # rôle propriétaire des tables, n'est pas concernée.
            for t in TABLES:
                self.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        if int(self.query("SELECT COUNT(*) AS n FROM cohortes").iloc[0, 0]) == 0:
            self._seed()

    def _seed(self):
        from core.auth import hash_password
        for table, int_cols in SEED:
            df = pd.read_csv(DATA_DIR / f"{table}.csv", dtype=str, keep_default_na=False)
            # on ne garde que les colonnes définies dans le schéma (colonnes en trop ignorées)
            known = self.query(f"SELECT * FROM {table} WHERE 1 = 0").columns
            df = df[[c for c in df.columns if c in known]]
            rows = []
            for rec in df.to_dict("records"):
                row = []
                for col in df.columns:
                    v = rec[col]
                    if v == "":
                        row.append(None)
                    elif col in int_cols:
                        row.append(int(float(v)))
                    else:
                        row.append(v)
                rows.append(tuple(row))
            cols = ", ".join(df.columns)
            marks = ", ".join(["?"] * len(df.columns))
            self.executemany(f"INSERT INTO {table} ({cols}) VALUES ({marks})", rows)

        demo_pwd = secret("DEMO_PASSWORD", "Ciat2026!")
        users = pd.read_csv(DATA_DIR / "utilisateurs.csv", dtype=str, keep_default_na=False)
        rows = []
        for u in users.to_dict("records"):
            rows.append((int(u["id_utilisateur"]), u["email"], hash_password(demo_pwd), u["role"],
                         int(float(u["id_mentor"])) if u["id_mentor"] else None,
                         int(float(u["id_porteur"])) if u["id_porteur"] else None, 1))
        self.executemany(
            "INSERT INTO utilisateurs (id_utilisateur, email, mot_de_passe_hash, role, id_mentor, id_porteur, actif) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)", rows)

    # -- chargement pour l'analyse
    def load_all(self):
        out = {}
        for t in TABLES:
            df = self.query(f"SELECT * FROM {t}")
            for c in DATE_COLS.get(t, []):
                df[c] = pd.to_datetime(df[c], errors="coerce")
            out[t] = df
        out["utilisateurs"] = out["utilisateurs"].drop(columns=["mot_de_passe_hash"])
        return out


def now_str():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def reference_date():
    """Date utilisée pour calculer les retards : aujourd'hui, sauf si DATE_REFERENCE est définie."""
    v = secret("DATE_REFERENCE")
    return pd.Timestamp(v) if v else pd.Timestamp(dt.date.today())
