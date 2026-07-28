from sqlalchemy.orm import Session
from sqlalchemy import text


class ChatRepository:
    """
    Camada de acesso ao banco para o histórico de conversas.
    Responsabilidade única: salvar e recuperar mensagens do PostgreSQL.
    """

    def __init__(self, db: Session):
        self.db = db

    def salvar_mensagem(self, session_id: str, papel: str, conteudo: str):
        """
        Salva uma mensagem no banco.
        papel: 'usuario' ou 'agente'
        """
        self.db.execute(
            text("""
                INSERT INTO historico_chat (session_id, papel, conteudo)
                VALUES (:session_id, :papel, :conteudo)
            """),
            {"session_id": session_id, "papel": papel, "conteudo": conteudo}
        )
        self.db.commit()

    def carregar_historico(self, session_id: str, limite: int = 20) -> list[dict]:
        """
        Carrega as últimas N mensagens de uma sessão.
        limite=20 evita sobrecarregar o contexto do modelo com histórico longo.
        Retorna no formato que o Ollama espera: [{"role": ..., "content": ...}]
        """
        resultado = self.db.execute(
            text("""
                SELECT papel, conteudo
                FROM historico_chat
                WHERE session_id = :session_id
                ORDER BY criado_em ASC
                LIMIT :limite
            """),
            {"session_id": session_id, "limite": limite}
        )
        mensagens = []
        for row in resultado.fetchall():
            # Converte 'usuario'/'agente' para 'user'/'assistant' (formato do Ollama)
            role = "user" if row.papel == "usuario" else "assistant"
            mensagens.append({"role": role, "content": row.conteudo})
        return mensagens

    def listar_sessoes(self) -> list[str]:
        """Lista todas as sessões existentes no banco."""
        resultado = self.db.execute(
            text("""
                SELECT DISTINCT session_id, MIN(criado_em) as inicio
                FROM historico_chat
                GROUP BY session_id
                ORDER BY inicio DESC
            """)
        )
        return [row.session_id for row in resultado.fetchall()]
