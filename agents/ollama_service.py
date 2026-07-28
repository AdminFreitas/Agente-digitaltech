import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Configurações lidas do .env
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")


class OllamaService:
    """
    Serviço [service] de comunicação com o Ollama.
    Responsabilidade única: enviar mensagens e receber respostas do modelo local.
    Não acessa banco de dados — isso é responsabilidade do repositório.
    """

    def __init__(self):
        self.url = OLLAMA_URL
        self.model = OLLAMA_MODEL
        self.endpoint = f"{self.url}/api/chat"

    def verificar_conexao(self) -> bool:
        """
        Verifica se o Ollama está rodando antes de tentar conversar.
        Evita erros confusos — falha rápido com mensagem clara.
        """
        try:
            resposta = requests.get(f"{self.url}/api/tags", timeout=3)
            return resposta.status_code == 200
        except requests.exceptions.ConnectionError:
            return False

    def chat(self, mensagens: list[dict]) -> str:
        """
        Envia o histórico [lista de mensagens] para o modelo e retorna a resposta.

        Parâmetro mensagens: lista no formato
            [
                {"role": "system",    "content": "Você é um assistente..."},
                {"role": "user",      "content": "Olá!"},
                {"role": "assistant", "content": "Olá! Como posso ajudar?"},
                {"role": "user",      "content": "Me fale sobre Python"}
            ]

        O modelo recebe TODO o histórico a cada chamada — é assim que ele
        'lembra' da conversa. Não existe memória automática no LLM.
        """
        payload = {
            "model": self.model,
            "messages": mensagens,
            "stream": False  # stream=False retorna tudo de uma vez (mais simples para aprender)
        }

        try:
            resposta = requests.post(
                self.endpoint,
                json=payload,
                timeout=120  # Qwen3 pode demorar até 2 min na primeira chamada
            )
            resposta.raise_for_status()  # Lança erro se status for 4xx ou 5xx

            dados = resposta.json()
            return dados["message"]["content"]

        except requests.exceptions.Timeout:
            return "❌ Erro: O modelo demorou demais para responder. Tente novamente."
        except requests.exceptions.ConnectionError:
            return "❌ Erro: Ollama não está rodando. Execute: ollama serve"
        except KeyError:
            return "❌ Erro: Resposta inesperada do Ollama. Verifique o modelo instalado."
