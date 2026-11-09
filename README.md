# Agent IA – Pauvreté en Afrique

- `agent.py` : extrait les indicateurs de pauvreté de l'API Banque mondiale (54 pays africains + agrégats régionaux), collecte les actualités récentes (Google Actualités, Le Monde Afrique, RFI, Jeune Afrique, BBC Africa) et, si possible, fait rédiger une analyse par Claude. Résultat : `web/data.json`.
- `serveur.py` : sert la page sur http://localhost:8000 et relance l'agent toutes les 6 h (`--heures` pour changer).
- `web/index.html` : tableau de bord (graphiques Chart.js), recharge les données toutes les 5 min.

## Lancer
Double-cliquer sur `lancer.bat`, ou :

    python serveur.py --heures 6

## Activer l'analyse IA (facultatif)

Créer un fichier `.env` à la racine du projet (il est exclu de Git) avec **une** de ces lignes :

    GEMINI_API_KEY=...        # clé gratuite : https://aistudio.google.com/apikey
    ANTHROPIC_API_KEY=sk-ant-...   # https://console.anthropic.com (nécessite aussi : pip install anthropic)

Si les deux sont présentes, Claude est utilisé en priorité et Gemini sert de secours.
Modèles par défaut : `gemini-3.8-flash` (`GEMINI_MODEL` pour changer) et `claude-opus-5-5` (`CLAUDE_MODEL`).
Pas besoin de redémarrer le serveur : cliquer sur « Actualiser » suffit.
