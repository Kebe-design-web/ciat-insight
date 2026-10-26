# CIAT Insight

Tableau de bord décisionnel du Centre d'Innovation, d'Application et de Transfert (CIAT) de l'ISEP Amadou Trawaré de Diamniadio.
Évaluation pratique du cours d'intelligence artificielle générative, Projet 3.

| Membre | Rôle |
|---|---|
| Fatou KEBE | Data analyst, cheffe de projet |
| Dietew NDOUR | Développeur |
| Bousso NIANG | Infographe |

## Fonctionnalités

- Connexion par e-mail et mot de passe, 5 rôles (Administrateur, Coordonnateur, Direction, Mentor, Porteur), pages filtrées par rôle
- Tableau de bord : filtres (période, cohorte, domaine, statut, genre, porteur), 11 indicateurs, graphiques interactifs
- Comparaison des cohortes, répartition par domaine et par genre, suivi des retards, des financements et des partenariats
- Lecture automatique des résultats et exports Excel, PDF et image (icône appareil photo sur chaque graphique)
- Gestion des projets avec formulaires validés ; création automatique des 5 jalons d'un projet sélectionné
- Suivi des jalons avec alertes de retard et commentaires du mentor
- Assistant IA (Google Gemini) : question en français, requête SQL générée, affichée et exécutée en lecture seule
- Contrôle de la qualité des données et administration des comptes

## Structure

```
ciat-insight/
├── app.py                  Point d'entrée : connexion, navigation, contrôle des accès
├── core/
│   ├── db.py               Base de données (SQLite en local, PostgreSQL/Supabase en ligne), création et chargement initial
│   ├── auth.py             Mots de passe (PBKDF2-SHA256 salé), connexion, droits par rôle
│   ├── kpi.py              Calcul des indicateurs K1 à K11 et lecture des résultats
│   ├── ai.py               Assistant IA et garde-fous
│   └── exports.py          Exports Excel et PDF
├── views/                  Un fichier par écran
├── data/                   Jeu de données fictif (CSV), chargé au premier lancement
├── .streamlit/config.toml  Thème aux couleurs ISEP
└── requirements.txt
```

## Lancer en local (Mac ou Windows)

1. Installer Python 3.11 ou 3.12.
2. Dans un terminal, depuis le dossier du projet :
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows : .venv\Scripts\activate
   pip install -r requirements.txt
   streamlit run app.py
   ```
3. Le navigateur s'ouvre sur http://localhost:8501. La base SQLite `ciat_insight.db` est créée et remplie automatiquement.
4. Pour activer l'assistant IA en local : copier `.streamlit/secrets.toml.example` en `.streamlit/secrets.toml`, supprimer la ligne `DATABASE_URL` et renseigner `GEMINI_API_KEY`.

## Déployer en ligne (gratuit)

### 1. Base de données Supabase
1. Créer un compte sur https://supabase.com puis un nouveau projet (noter le mot de passe de la base).
2. Bouton **Connect** > copier la chaîne **Session pooler** (format `postgresql://postgres.xxx:...@...pooler.supabase.com:5432/postgres`) et remplacer `[YOUR-PASSWORD]` par le mot de passe.
3. Rien d'autre à faire : les tables sont créées et remplies au premier lancement de l'application.

### 2. Clé Gemini
1. Aller sur https://aistudio.google.com, se connecter avec un compte Google, créer une clé d'API.
2. Vérifier dans la documentation Google le nom d'un modèle disponible (par défaut le code utilise `gemini-2.5-flash` ; le changer dans `GEMINI_MODEL` si besoin).

### 3. Streamlit Community Cloud
1. Publier ce dossier sur GitHub (dépôt public ou privé). Le fichier `secrets.toml` ne doit pas être publié (il est exclu par `.gitignore`).
2. Sur https://share.streamlit.io, **Create app** > choisir le dépôt, la branche et `app.py`.
3. **Advanced settings** : Python 3.12, puis coller dans **Secrets** le contenu de `secrets.toml.example` avec les vraies valeurs.
4. **Deploy**. Le lien obtenu est le livrable 10 à transmettre au jury.

## Comptes de démonstration

Créés au premier lancement avec le mot de passe défini par `DEMO_PASSWORD` (par défaut `Ciat2026!`).

| Rôle | E-mail |
|---|---|
| Administrateur | admin@exemple.sn |
| Coordonnateur | coordination@exemple.sn |
| Direction | direction@exemple.sn |
| Mentor | mentor01@exemple.sn (mentor01 à mentor08) |
| Porteur | porteur002@exemple.sn (porteurs des projets sélectionnés) |

Changer ces mots de passe (page Utilisateurs) si l'application reste en ligne après l'évaluation.

## Sécurité et données

- Mots de passe stockés uniquement sous forme d’empreinte PBKDF2-SHA256 salée (120 000 itérations), dans la colonne mot_de_passe_hash.
- Blocage de 60 secondes après 5 échecs de connexion.
- Contrôle des droits sur chaque page ; requêtes paramétrées (pas d'injection SQL).
- Clés et mots de passe dans les secrets Streamlit, jamais dans le code.
- Assistant IA : seule la structure des tables est envoyée au modèle, sans nom ni e-mail ; la requête générée est filtrée (SELECT uniquement), exécutée sur une copie en mémoire avec un autorisateur SQLite en lecture seule, limitée en durée et en nombre de lignes, et toujours affichée.
- Données de démonstration entièrement fictives (domaine `exemple.sn`).

## Limites connues

- Les identifiants sont attribués par l'application (MAX + 1) : adapté à quelques utilisateurs simultanés, pas à un usage intensif.
- L'import de fichiers CSV/Excel (exigence F15) et la notification par e-mail (F17) ne sont pas réalisés dans cette version.
- L'offre gratuite de Gemini est soumise à des quotas ; en cas de dépassement, les questions types restent disponibles.
- Sur l'offre gratuite de Streamlit Cloud, l'application se met en veille après une période sans visite : l'ouvrir quelques minutes avant la démonstration.
