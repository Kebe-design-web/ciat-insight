"""Mots de passe et connexion.

Les mots de passe ne sont jamais stockés en clair : seule une empreinte
PBKDF2-SHA256 salée (bibliothèque standard Python) est enregistrée.
"""
import hashlib
import hmac
import secrets

ITERATIONS = 120_000

ROLES = ["Administrateur", "Coordonnateur", "Direction", "Mentor", "Porteur"]


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, it, salt, digest = stored.split("$")
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(it)).hex()
        return hmac.compare_digest(test, digest)
    except Exception:
        return False


def password_problem(pwd: str):
    """Renvoie un message si le mot de passe est trop faible, sinon None."""
    if len(pwd) < 8:
        return "Le mot de passe doit contenir au moins 8 caractères."
    if not any(c.isdigit() for c in pwd) or not any(c.isalpha() for c in pwd):
        return "Le mot de passe doit contenir des lettres et des chiffres."
    return None


def authenticate(db, email: str, password: str):
    df = db.query(
        "SELECT id_utilisateur, email, mot_de_passe_hash, role, id_mentor, id_porteur "
        "FROM utilisateurs WHERE LOWER(email) = LOWER(?) AND actif = 1",
        (email.strip(),))
    if df.empty:
        return None
    u = df.iloc[0]
    if not verify_password(password, u["mot_de_passe_hash"]):
        return None
    return {
        "id": int(u["id_utilisateur"]),
        "email": u["email"],
        "role": u["role"],
        "id_mentor": None if u["id_mentor"] is None or str(u["id_mentor"]) in ("", "nan", "None") else int(u["id_mentor"]),
        "id_porteur": None if u["id_porteur"] is None or str(u["id_porteur"]) in ("", "nan", "None") else int(u["id_porteur"]),
    }


# Pages autorisées par rôle (cahier des charges, section 5)
PAGES = {
    "Administrateur": ["Tableau de bord", "Assistant IA", "Projets", "Suivi des jalons", "Qualité des données", "Utilisateurs"],
    "Coordonnateur": ["Tableau de bord", "Assistant IA", "Projets", "Suivi des jalons", "Qualité des données"],
    "Direction": ["Tableau de bord", "Assistant IA", "Projets"],
    "Mentor": ["Suivi des jalons"],
    "Porteur": ["Mon projet"],
}

CAN_EDIT_PROJECTS = {"Administrateur", "Coordonnateur"}
CAN_COMMENT = {"Administrateur", "Coordonnateur", "Mentor"}
