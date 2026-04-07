# Spécification Technique — Test Modulaire PME

## Contexte

Dans ce test, vous devez développer une application modulaire répondant à deux problématiques concrètes pour une PME française, en structurant votre solution en plusieurs étapes (ou nœuds) qui se succèdent pour transformer et enrichir les données. Vous êtes libre de choisir le langage, le framework et les outils (par exemple, langgraph, LangChain, etc.), ainsi que les modèles de LLM (OpenAI, Mistral, Claude, etc.).

## Optimisation de l'Infrastructure Technique pour Jean (CTO)

### Objectif

Développer une solution qui permet de :

- **Ingestion et Analyse de Données Techniques** — Traiter des données simulées issues d'un fichier JSON ou d'un flux en temps réel.
- **Détection d'Anomalies** — Identifier des indicateurs anormaux (par exemple, une utilisation excessive du CPU, une latence élevée, etc.).
- **Génération de Recommandations** — Produire un rapport structuré (format JSON ou affichage console) proposant des actions concrètes pour optimiser la performance de l'infrastructure (par exemple, répartition de charge, ajustement des ressources, etc.).

### Exigences Techniques

**Format d'Entrée Exemple:**

```json
{
  "timestamp": "2023-10-01T12:00:00Z",
  "cpu_usage": 85,
  "memory_usage": 70,
  "latency_ms": 250,
  "disk_usage": 65,
  "network_in_kbps": 1200,
  "network_out_kbps": 900,
  "io_wait": 5,
  "thread_count": 150,
  "active_connections": 45,
  "error_rate": 0.02,
  "uptime_seconds": 360000,
  "temperature_celsius": 65,
  "power_consumption_watts": 250,
  "service_status": {
    "database": "online",
    "api_gateway": "degraded",
    "cache": "online"
  }
}
```

La liste complète est fournie dans `data/infrastructure_metrics.json` (487 entrées, intervalle 30min, du 2023-10-01 au 2023-10-11).

### Architecture Multi-Nœuds

Votre solution doit être organisée en plusieurs étapes (par exemple : ingestion → analyse → recommandation). La structuration de ces étapes est laissée à votre discrétion.

### Documentation

Expliquez vos choix techniques et architecturaux (langage, bibliothèques, etc.) via des commentaires dans le code ou un document annexe.
