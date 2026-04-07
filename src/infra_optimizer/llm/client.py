"""Wrapper autour du client Mistral.

Choix d'un wrapper plutôt que d'utiliser le SDK directement :
- centralise la configuration et la gestion d'erreurs
- facilite le mock dans les tests
- permet de basculer vers un autre fournisseur (Claude, OpenAI) sans toucher aux nœuds
"""

import json
from typing import Any

from loguru import logger
from mistralai.client.sdk import Mistral

from infra_optimizer.config import settings


class MistralClient:
    """Client Mistral avec parsing JSON robuste et gestion d'erreurs."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.mistral_api_key
        self.model = model or settings.mistral_model
        if not self.api_key:
            logger.warning("MISTRAL_API_KEY non défini — le pipeline tournera en mode dégradé")
            self._client = None
        else:
            # Timeout généreux car certains prompts contiennent beaucoup de contexte
            self._client = Mistral(api_key=self.api_key, timeout_ms=120_000)

    def is_available(self) -> bool:
        return self._client is not None

    def chat_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Appel au modèle avec un prompt système + utilisateur, parsing JSON.

        On force `response_format={"type": "json_object"}` pour garantir un retour parsable.
        """
        if not self._client:
            logger.error("Client Mistral non initialisé — retour vide")
            return {}

        try:
            response = self._client.chat.complete(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Erreur de parsing JSON depuis Mistral : {e}")
            return {}
        except Exception as e:
            logger.error(f"Erreur appel Mistral : {e}")
            return {}

    def chat_text(self, system: str, user: str, temperature: float = 0.3) -> str:
        """Appel au modèle pour une réponse en texte libre (synthèse exécutive)."""
        if not self._client:
            return "Synthèse indisponible — client LLM non configuré."

        try:
            response = self._client.chat.complete(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=1024,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Erreur appel Mistral (texte) : {e}")
            return f"Erreur de génération : {e}"
