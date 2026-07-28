"""
fact_check_agent.py
---------------------
Agente responsável por verificar a veracidade de afirmações.

Suporta uma função de busca externa opcional (`search_function`) para
injetar resultados de pesquisa na web (ex: via Tavily, SerpAPI, Brave
Search API, ou qualquer outra fonte) antes da análise do modelo. Sem essa
função, o agente avalia a afirmação apenas com o conhecimento do modelo,
o que deve ser tratado com cautela e sinalizado ao usuário final.
"""

from typing import Optional, Callable, List, Dict, Any

from .base_agent import BaseAgent


class FactCheckAgent(BaseAgent):
    """Agente de verificação de fatos com veredito estruturado."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-5",
        search_function: Optional[Callable[[str], str]] = None,
        **kwargs,
    ):
        """
        Args:
            search_function: função opcional `def buscar(query: str) -> str`
                que retorna um resumo textual de resultados de busca na web.
                Se não for fornecida, o agente avalia só com conhecimento interno
                e sinaliza isso no resultado.
        """
        system_prompt = (
            "Você é um agente de fact-checking rigoroso e imparcial. Dada uma "
            "afirmação (e, quando disponíveis, evidências de busca na web), "
            "avalie sua veracidade.\n\n"
            "Responda APENAS com um JSON válido, sem texto adicional, no formato:\n"
            "{\n"
            '  "afirmacao": "<afirmação avaliada>",\n'
            '  "veredito": "verdadeiro" | "falso" | "impreciso" | "sem_evidencia_suficiente",\n'
            '  "confianca": <número de 0 a 1>,\n'
            '  "explicacao": "<explicação objetiva e concisa>",\n'
            '  "fontes": ["<fonte 1>", "<fonte 2>"]\n'
            "}\n"
            "Se não houver evidências de busca fornecidas, use 'fontes': [] e "
            "reduza a confiança, deixando claro que a avaliação se baseia apenas "
            "em conhecimento geral do modelo."
        )
        super().__init__(
            name="FactCheckAgent",
            system_prompt=system_prompt,
            model=model,
            **kwargs,
        )
        self.search_function = search_function

    def run(self, claim: str, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Verifica uma única afirmação.

        Args:
            claim: A afirmação a ser checada.
            context: Contexto adicional opcional (ex: de onde veio a afirmação).

        Returns:
            Dicionário com veredito, confiança, explicação e fontes.
        """
        evidencias = ""
        if self.search_function:
            resultados_busca = self.search_function(claim)
            evidencias = f"\n\nEvidências encontradas na web:\n{resultados_busca}"
        else:
            evidencias = "\n\n(Nenhuma busca na web foi realizada para esta checagem.)"

        contexto_txt = f"\n\nContexto adicional: {context}" if context else ""

        prompt = f"Afirmação a verificar: \"{claim}\"{contexto_txt}{evidencias}"
        resposta = self._call_llm(prompt)
        try:
            return self._extract_json(resposta)
        except ValueError:
            return {
                "afirmacao": claim,
                "veredito": "sem_evidencia_suficiente",
                "confianca": 0.0,
                "explicacao": "Não foi possível interpretar a resposta do modelo.",
                "fontes": [],
                "resposta_bruta": resposta,
            }

    def check_batch(self, claims: List[str]) -> List[Dict[str, Any]]:
        """Verifica uma lista de afirmações, retornando um veredito para cada."""
        return [self.run(c) for c in claims]


if __name__ == "__main__":
    agent = FactCheckAgent()
    resultado = agent.run("A Grande Muralha da China é visível a olho nu do espaço.")
    print(resultado)
