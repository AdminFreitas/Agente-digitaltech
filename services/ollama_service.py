"""
ollama_service.py — Serviço de comunicação com Ollama (OTIMIZADO)

CORREÇÕES APLICADAS (2026-08-06):
  1. Adicionado suporte a streaming para evitar timeout HTTP
  2. Aumentado num_ctx de 2048 -> 4096 (melhor contexto para prompts longos)
  3. Aumentado num_predict de 300 -> 1500 (artigos completos em 1 chamada)
  4. Adicionado num_thread (auto-detecta cores da CPU)
  5. Adicionado batch_size=512 (processamento mais eficiente)
  6. Timeout aumentado de 120s -> 300s
  7. Novo método chat_streaming() para geração longa sem timeout
  8. Fallback automático para modelo menor se o principal falhar

RECOMENDAÇÃO DE MODELO:
  Se o hardware for CPU-only (Aspire E1-571), considere mudar no .env:
    OLLAMA_MODEL=qwen3:4b      # 2x mais rápido que 8b
    OLLAMA_MODEL=llama3.2:3b   # muito leve, boa qualidade
    OLLAMA_MODEL=phi4:mini     # excelente para CPU
"""

import requests
import json
import os
import multiprocessing
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configurações lidas do .env (com defaults otimizados)
# ---------------------------------------------------------------------------
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_FALLBACK_MODEL = os.getenv("OLLAMA_FALLBACK_MODEL", "llama3.2:3b")

# Número de threads da CPU (auto-detecta, mínimo 4)
NUM_THREADS = int(os.getenv("OLLAMA_NUM_THREADS", str(max(4, multiprocessing.cpu_count()))))

# Timeout para requisições (aumentado para 5 min)
TIMEOUT_SEGUNDOS = int(os.getenv("OLLAMA_TIMEOUT", "300"))

# Máximo de tokens a gerar (1500 ~ 1000-1200 palavras)
NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "1500"))

# Tamanho do contexto (4096 tokens)
NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))


class OllamaService:
    """
    Serviço de comunicação com o Ollama.
    Responsabilidade única: enviar mensagens e receber respostas do modelo local.
    Não acessa banco de dados — isso é responsabilidade do repositório.
    """

    def __init__(self):
        self.url = OLLAMA_URL
        self.model = OLLAMA_MODEL
        self.fallback_model = OLLAMA_FALLBACK_MODEL
        self.endpoint = f"{self.url}/api/chat"
        self.num_threads = NUM_THREADS
        self.timeout = TIMEOUT_SEGUNDOS
        self.num_predict = NUM_PREDICT
        self.num_ctx = NUM_CTX

    def verificar_conexao(self, modelo: str | None = None) -> bool:
        """
        Verifica se o Ollama está rodando e se o modelo está disponível.
        Pode verificar um modelo específico (útil para fallback).
        """
        try:
            resposta = requests.get(f"{self.url}/api/tags", timeout=5)
            if resposta.status_code != 200:
                return False
            if modelo:
                modelos = [m["name"] for m in resposta.json().get("models", [])]
                return modelo in modelos
            return True
        except requests.exceptions.ConnectionError:
            return False
        except Exception:
            return False

    def _montar_payload(self, mensagens: list[dict], streaming: bool = False,
                       num_predict: int | None = None) -> dict:
        """Monta o payload JSON para a API do Ollama."""
        return {
            "model": self.model,
            "messages": mensagens,
            "stream": streaming,
            "options": {
                "num_predict": num_predict or self.num_predict,
                "temperature": 0.7,
                "num_ctx": self.num_ctx,
                "num_thread": self.num_threads,
                "batch_size": 512,
                "top_k": 40,
                "top_p": 0.9,
            }
        }

    def chat(self, mensagens: list[dict], num_predict: int | None = None) -> str:
        """
        Envia o histórico para o modelo e retorna a resposta COMPLETA.

        ⚠️  Use este método para respostas CURTAS (títulos, resumos, SEO).
        Para textos LONGOS (artigos completos), use chat_streaming()
        para evitar timeout HTTP.

        Parâmetro mensagens: lista no formato
            [
                {"role": "system",    "content": "Você é um assistente..."},
                {"role": "user",      "content": "Olá!"},
                {"role": "assistant", "content": "Olá! Como posso ajudar?"},
                {"role": "user",      "content": "Me fale sobre Python"}
            ]
        """
        payload = self._montar_payload(mensagens, streaming=False,
                                       num_predict=num_predict)
        try:
            resposta = requests.post(
                self.endpoint,
                json=payload,
                timeout=self.timeout
            )
            resposta.raise_for_status()

            dados = resposta.json()
            return dados["message"]["content"]

        except requests.exceptions.Timeout:
            return "❌ Erro: O modelo demorou demais para responder. Tente chat_streaming() para textos longos."
        except requests.exceptions.ConnectionError:
            return "❌ Erro: Ollama não está rodando. Execute: ollama serve"
        except KeyError:
            return "❌ Erro: Resposta inesperada do Ollama. Verifique o modelo instalado."

    def chat_streaming(self, mensagens: list[dict],
                       num_predict: int | None = None) -> str:
        """
        Envia o histórico para o modelo e retorna a resposta via STREAMING.

        ✅ Use este método para textos LONGOS (artigos completos).
        O streaming recebe tokens em tempo real, evitando timeout HTTP
        mesmo que a geração demore vários minutos.

        Parâmetro mensagens: mesmo formato do chat()
        """
        payload = self._montar_payload(mensagens, streaming=True,
                                       num_predict=num_predict)
        texto_completo = []
        try:
            with requests.post(
                self.endpoint,
                json=payload,
                stream=True,
                timeout=(10, self.timeout)  # (connect_timeout, read_timeout)
            ) as resposta:
                resposta.raise_for_status()
                for linha in resposta.iter_lines():
                    if not linha:
                        continue
                    try:
                        dados = json.loads(linha)
                        # Ollama streaming: cada linha é um JSON com "message" ou "done"
                        if dados.get("done"):
                            break
                        chunk = dados.get("message", {}).get("content", "")
                        if chunk:
                            texto_completo.append(chunk)
                    except json.JSONDecodeError:
                        continue

            return "".join(texto_completo)

        except requests.exceptions.Timeout:
            return "❌ Erro: Timeout durante streaming. O modelo pode estar sobrecarregado."
        except requests.exceptions.ConnectionError:
            return "❌ Erro: Ollama não está rodando. Execute: ollama serve"
        except Exception as e:
            return f"❌ Erro inesperado no streaming: {e}"

    def chat_com_fallback(self, mensagens: list[dict],
                          num_predict: int | None = None,
                          usar_streaming: bool = False) -> str:
        """
        Envia mensagens para o Ollama com FALLBACK automático.

        Fluxo:
          1. Tenta o modelo principal (OLLAMA_MODEL)
          2. Se falhar (timeout/erro), tenta o modelo fallback (OLLAMA_FALLBACK_MODEL)
          3. Se ambos falharem, retorna mensagem de erro

        Parâmetro usar_streaming: True para textos longos, False para curtos
        """
        metodo = self.chat_streaming if usar_streaming else self.chat

        # Tenta modelo principal
        resultado = metodo(mensagens, num_predict=num_predict)
        if not resultado.startswith("❌"):
            return resultado

        print(f"[Ollama] Modelo principal ({self.model}) falhou. Tentando fallback ({self.fallback_model})...")

        # Verifica se o fallback está disponível
        if not self.verificar_conexao(self.fallback_model):
            print(f"[Ollama] Fallback {self.fallback_model} não está disponível.")
            return resultado  # retorna o erro original

        # Tenta modelo fallback
        payload = self._montar_payload(mensagens, streaming=usar_streaming,
                                       num_predict=num_predict)
        payload["model"] = self.fallback_model
        try:
            if usar_streaming:
                # Reutiliza lógica de streaming com modelo diferente
                texto_completo = []
                with requests.post(
                    self.endpoint,
                    json=payload,
                    stream=True,
                    timeout=(10, self.timeout)
                ) as resposta:
                    resposta.raise_for_status()
                    for linha in resposta.iter_lines():
                        if not linha:
                            continue
                        try:
                            dados = json.loads(linha)
                            if dados.get("done"):
                                break
                            chunk = dados.get("message", {}).get("content", "")
                            if chunk:
                                texto_completo.append(chunk)
                        except json.JSONDecodeError:
                            continue
                return "".join(texto_completo)
            else:
                resposta = requests.post(
                    self.endpoint,
                    json=payload,
                    timeout=self.timeout
                )
                resposta.raise_for_status()
                return resposta.json()["message"]["content"]
        except Exception as e:
            print(f"[Ollama] Fallback também falhou: {e}")
            return resultado  # retorna o erro original

    def info(self) -> dict:
        """Retorna informações de configuração atuais (útil para debug)."""
        return {
            "modelo_principal": self.model,
            "modelo_fallback": self.fallback_model,
            "url": self.url,
            "timeout": self.timeout,
            "num_predict": self.num_predict,
            "num_ctx": self.num_ctx,
            "num_threads": self.num_threads,
            "cpu_cores": multiprocessing.cpu_count(),
        }
