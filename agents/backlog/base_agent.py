"""
base_agent.py
--------------
Classe base utilizada por todos os agentes do projeto.

Concentra a lógica comum de comunicação com a API da Anthropic (Claude),
para que cada agente especializado só precise se preocupar com o seu
prompt de sistema e com a formatação da tarefa específica.

Requer a variável de ambiente ANTHROPIC_API_KEY (ou que a chave seja
passada diretamente no construtor via `api_key=`).
"""

import os
import json
import re
from typing import Optional, Any

from anthropic import Anthropic


class BaseAgent:
    """Classe base para todos os agentes de IA do projeto."""

    def __init__(
        self,
        name: str,
        system_prompt: str,
        model: str = "claude-sonnet-4-5",
        max_tokens: int = 2000,
        temperature: float = 0.7,
        api_key: Optional[str] = None,
    ):
        """
        Args:
            name: Nome identificador do agente (usado em logs).
            system_prompt: Prompt de sistema que define o comportamento do agente.
            model: Modelo Claude a ser utilizado.
            max_tokens: Limite padrão de tokens de saída.
            temperature: Criatividade das respostas (0 = mais determinístico).
            api_key: Chave de API opcional (senão usa ANTHROPIC_API_KEY do ambiente).
        """
        self.name = name
        self.system_prompt = system_prompt
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def _call_llm(
        self,
        user_message: str,
        system_prompt_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
        temperature_override: Optional[float] = None,
    ) -> str:
        """Faz uma chamada simples de texto -> texto ao modelo."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens_override or self.max_tokens,
            temperature=(
                self.temperature if temperature_override is None else temperature_override
            ),
            system=system_prompt_override or self.system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    @staticmethod
    def _extract_json(text: str) -> Any:
        """
        Extrai e faz o parse do primeiro bloco JSON (objeto ou lista)
        encontrado em uma resposta de texto do modelo.

        Útil quando o prompt de sistema pede uma resposta estruturada.
        """
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if not match:
            raise ValueError(
                f"Nenhum JSON encontrado na resposta do modelo '{text[:200]}...'"
            )
        return json.loads(match.group(0))

    def run(self, *args, **kwargs):
        """Cada agente especializado deve implementar seu próprio run()."""
        raise NotImplementedError("Cada agente deve implementar seu próprio método run().")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} model={self.model}>"
