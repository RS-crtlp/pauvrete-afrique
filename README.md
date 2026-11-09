# Agent IA – Pauvreté en Afrique

- `agent.py` : extrait les indicateurs de pauvreté de l'API Banque mondiale (54 pays africains + agrégats régionaux), collecte les actualités récentes (Google Actualités, Le Monde Afrique, RFI, Jeune Afrique, BBC Africa) et, si possible, fait rédiger une analyse par Claude. Résultat : `web/data.json`.
- `serveur.py` : sert la page sur http://localhost:8000 et relance l'agent toutes les 6 h (`--heures` pour changer).
- `web/index.html` : tableau de bord (graphiques Chart.js), recharge les données toutes les 5 min.

## Lancer
Double-cliquer sur `lancer.bat`, ou :

    python serveur.py --heures 6

## Activer l'analyse IA (facultatif)

    pip install anthropic
    setx ANTHROPIC_API_KEY "sk-ant-..."

Modèle par défaut : `claude-opus-5-5` (variable `CLAUDE_MODEL` pour changer). Le repli automatique côté serveur (`fallbacks: "default"`) est activé en cas de refus.
