"""
revisor.py — Agente revisor

Recebe o artigo já escrito pelo editor.py e devolve uma versão
corrigida: gramática, clareza, repetições, coerência, estrutura
Markdown, legibilidade e qualidade editorial geral.

Nunca muda o assunto principal, a intenção do artigo, os fatos,
os links, as imagens, o código, os metadados, o slug, a categoria
ou o título. Não inventa informações. Não remove conteúdo importante.

Não acessa nenhuma API diretamente — todo texto passa por
services.llm_service.gerar_texto().
"""

import re

from services.llm_service import gerar_texto


def revisar_artigo(artigo: dict) -> dict:
    """
    Recebe um dict de artigo (no formato produzido por
    editor.gerar_artigo_base/gerar_noticia_base) e devolve uma CÓPIA
    com `conteudo_markdown` revisado.

    Os demais campos (titulo, slug, excerpt, categoria, tags,
    imagem_destaque, metadados etc.) NÃO são alterados aqui —
    isso é trabalho de outros agentes (seo.py, publicador etc.).

    Não modifica o dict recebido.
    """
    if not isinstance(artigo, dict):
        raise TypeError("revisar_artigo espera um dict")

    conteudo_original = artigo.get("conteudo_markdown", "")
    if not conteudo_original or not isinstance(conteudo_original, str):
        # Nada a revisar; devolve cópia intacta
        return dict(artigo)

    prompt = _montar_prompt_revisao(conteudo_original)

    conteudo_revisado = gerar_texto(prompt)
    conteudo_revisado = _remover_cerca_envolvente(conteudo_revisado)
    conteudo_revisado = conteudo_revisado.strip()

    # Fallback de segurança: se o LLM retornar vazio ou claramente inválido,
    # preserva o conteúdo original para não destruir o artigo.
    if not _resposta_eh_valida(conteudo_revisado, conteudo_original):
        conteudo_revisado = conteudo_original

    artigo_revisado = dict(artigo)
    artigo_revisado["conteudo_markdown"] = conteudo_revisado
    return artigo_revisado


def _montar_prompt_revisao(texto: str) -> str:
    """
    Monta o prompt completo de revisão editorial com todas as
    instruções e restrições do agente revisor.
    """
    return f"""Você é um revisor editorial de qualidade brasileiro, especialista em textos de tecnologia.

Sua única tarefa é revisar o artigo em Markdown abaixo, corrigindo problemas e melhorando a qualidade editorial, MAS SEM reescrever o artigo por completo e SEM mudar sua intenção, assunto ou fatos.

============================================================
REGRAS ABSOLUTAS — NEGATIVAS (NUNCA FAÇA)
============================================================

1. NUNCA mude o assunto principal do texto.
2. NUNCA mude a intenção do artigo.
3. NUNCA adicione informação nova: não invente números, estatísticas, nomes, datas, versões, preços, empresas, recursos, links, acontecimentos ou afirmações técnicas.
4. NUNCA remova fatos, dados, links, imagens, exemplos de código ou informações importantes presentes no texto original.
5. NUNCA transforme opinião em fato nem fato em opinião.
6. NUNCA altere código: preserve linguagem, sintaxe, comandos, caminhos, nomes de variáveis, URLs e exemplos técnicos. Não "corrija" código sem certeza absoluta de que está errado.
7. NUNCA remova links válidos existentes (documentação oficial, GitHub, páginas de produto, fontes de notícias, APIs etc.).
8. NUNCA remova marcadores ou referências de imagem.
9. NUNCA invente URLs de links ou de imagens.
10. NUNCA reescreva o título por conta própria. Detecte apenas problemas graves (título vazio, incompatível com o conteúdo, claramente enganoso ou sensacionalismo absurdo). Se houver, preserve o título original — a otimização do título é de outro agente.
11. NUNCA altere o slug, a categoria ou quaisquer metadados do artigo.
12. NUNCA resuma seções inteiras apenas para encurtar o texto.
13. NUNCA aumente o texto artificialmente apenas para atingir um número de palavras.
14. NUNCA adicione palavras-chave artificialmente nem faça keyword stuffing.
15. NUNCA escreva para "enganar" mecanismos de busca ou IA.

============================================================
REGRAS DE REVISÃO — POSITIVAS (FAÇA)
============================================================

A. GRAMÁTICA E ORTOGRAFIA
   - Corrija ortografia, acentuação, concordância, regência e pontuação.
   - Corrija erros de digitação e construções gramaticais ruins.
   - Corrija frases quebradas e repetições desnecessárias de palavras.
   - Use português brasileiro natural. Evite português artificial ou excessivamente formal.

B. CLAREZA E LEGIBILIDADE
   - Divida frases muito longas quando prejudicarem a compreensão.
   - Divida parágrafos excessivamente grandes.
   - Elimine frases redundantes.
   - Melhore transições entre parágrafos e seções.
   - Evite excesso de voz passiva.
   - Explique termos técnicos somente quando o público provavelmente não os conhecer.
   - Evite linguagem robótica ou genérica típica de IA.
   - NÃO transforme artigo técnico em texto superficial; preserve a precisão técnica.

C. ESTRUTURA EDITORIAL
   - Verifique se o artigo possui estrutura lógica coerente com seu tipo:
     * Tutorial → deve parecer tutorial (passo a passo, comandos, exemplos).
     * Notícia → deve parecer notícia (fatos, datas, natureza jornalística).
     * Análise → deve parecer análise (argumentos, evidências, conclusões).
     * Artigo explicativo → deve parecer artigo explicativo (contexto, explicação, aplicação).
   - NÃO force uma estrutura única em todos os artigos.
   - Quando apropriado, organize com: Introdução, Contexto, O que aconteceu/Como funciona, Por que importa, Como fazer/utilizar, Vantagens e limitações, Conclusão.

D. PARÁGRAFOS
   - Evite blocos gigantes de texto.
   - Evite parágrafos de uma única frase sem necessidade.
   - Evite excesso de listas ou excesso de subtítulos.
   - Evite repetir a mesma ideia em várias seções.
   - Prefira parágrafos curtos e médios, confortáveis para leitura em celular.

E. MARKDOWN
   - Verifique e corrija: ##, ###, listas, listas numeradas, negrito, itálico, links Markdown, blocos de código, tabelas.
   - Preserve o espaçamento lógico entre seções.
   - NÃO destrua Markdown válido.
   - NÃO transforme código de programação em texto comum.
   - NÃO altere exemplos de código por questões estilísticas.

F. NOTÍCIAS (quando aplicável)
   - Preserve a natureza jornalística.
   - Deixe claro o que aconteceu.
   - Preserve datas e fatos.
   - NÃO transforme notícia em opinião.
   - NÃO invente contexto.
   - NÃO transforme especulação em fato.
   - NÃO use linguagem sensacionalista.
   - NÃO exagere títulos ou afirmações.
   - Separe claramente fato de interpretação quando já estiver presente.

G. ARTIGOS EVERGREEN (quando aplicável)
   - Melhore a organização.
   - Garanta que a introdução deixe claro o assunto.
   - Elimine explicações circulares.
   - Melhore exemplos (sem inventar novos).
   - Mantenha profundidade.
   - Evite conteúdo genérico.
   - Remova frases vazias que não acrescentam informação, como:
     "No mundo atual da tecnologia..."
     "A tecnologia está evoluindo rapidamente..."
     "Neste artigo vamos explorar..."

H. TEXTO ARTIFICIAL DE IA
   - Reduza sinais de texto genérico produzido por IA.
   - Evite construções de preenchimento como:
     "é importante destacar que", "vale ressaltar que", "no cenário atual",
     "em um mundo cada vez mais digital", "neste contexto",
     "podemos concluir que", "sem dúvida", "de forma significativa",
     "revolucionário", "transformador", "solução inovadora".
   - NÃO elimine expressões apenas por existirem; elimine apenas quando forem preenchimento vazio.

I. UTILIDADE PARA O LEITOR
   - O artigo deve responder claramente: "Por que o leitor deveria terminar este artigo?"
   - Organize a informação existente para que a resposta fique evidente.
   - NÃO invente informações para aumentar o tamanho.
   - Qualidade é mais importante que quantidade.

J. GEO / BUSCA GENERATIVA (sem virar SEO)
   - Deixe respostas importantes explícitas.
   - Evite referências ambíguas.
   - Use nomes completos na primeira menção.
   - Separe fatos e explicações.
   - Organize informações em seções claras.
   - Utilize listas ou tabelas quando realmente ajudarem.
   - Mantenha definições objetivas.

============================================================
FORMATO DE RESPOSTA
============================================================

- Responda APENAS com o texto revisado em Markdown.
- NÃO envolva a resposta inteira em um bloco de código (```markdown ... ```).
- Blocos de código que já existem DENTRO do artigo (exemplos de tutorial,
  comandos, trechos de programação) devem ser mantidos exatamente como
  estão, incluindo as cercas ``` que os delimitam.
- NÃO adicione comentários, explicações, prefácios ou pós-escritos.
- O texto revisado deve estar pronto para uso direto no campo `conteudo_markdown`.

============================================================
TEXTO ORIGINAL A REVISAR
============================================================

{texto}
"""


def _remover_cerca_envolvente(texto: str) -> str:
    """
    Remove APENAS uma cerca de código Markdown que envolve a resposta
    inteira (ex.: o modelo devolvendo ```markdown ... ``` em volta de
    todo o artigo, mesmo depois de instruído a não fazer isso).

    Diferente de uma versão anterior deste arquivo, esta função NUNCA
    remove cercas ``` que apareçam no meio do texto — isso destruiria
    blocos de código legítimos dentro do artigo (ex.: tutoriais com
    exemplos em Python/JS/bash), violando a regra de preservação de
    código do revisor.
    """
    if not isinstance(texto, str):
        return ""

    resultado = texto.strip()

    # Cerca de abertura envolvendo a resposta inteira, ex: ```markdown\n ou ```\n
    match_abertura = re.match(r"^```[a-zA-Z]*\s*\n", resultado)
    if match_abertura:
        # Só remove se também houver uma cerca de fechamento isolada no final
        match_fechamento = re.search(r"\n```\s*$", resultado)
        if match_fechamento:
            resultado = resultado[match_abertura.end():match_fechamento.start()]

    return resultado.strip()


def _resposta_eh_valida(revisado: str, original: str) -> bool:
    """
    Verifica se a resposta do LLM é válida e segura para uso.
    Critérios:
      - Não pode ser vazia ou apenas espaços.
      - Deve ter um tamanho mínimo razoável (pelo menos 25% do original
        ou 100 caracteres, o que for maior), a menos que o original já
        seja muito curto.
      - Não pode ser apenas uma repetição do prompt ou de instruções.
      - Deve conter algum conteúdo que pareça artigo (Markdown ou texto).
    """
    if not revisado or not isinstance(revisado, str):
        return False

    revisado_limpo = revisado.strip()
    original_limpo = original.strip()

    # Vazio após limpeza
    if not revisado_limpo:
        return False

    # Muito curto em relação ao original (possível truncamento ou resposta inválida)
    # Exceto se o original já for extremamente curto
    len_original = len(original_limpo)
    len_revisado = len(revisado_limpo)

    if len_original > 300:
        if len_revisado < max(100, len_original * 0.25):
            return False

    # Se a resposta contiver trechos do prompt de instrução, é sinal de
    # que o modelo repetiu o prompt em vez de revisar
    trechos_prompt = [
        "REGRAS ABSOLUTAS",
        "REGRAS DE REVISÃO",
        "FORMATO DE RESPOSTA",
        "TEXTO ORIGINAL A REVISAR",
        "NUNCA mude o assunto",
        "NUNCA adicione informação nova",
    ]
    ocorrencias_prompt = sum(1 for trecho in trechos_prompt if trecho in revisado_limpo)
    if ocorrencias_prompt >= 2:
        return False

    # Se a resposta for apenas a repetição de uma única frase curta
    # (comportamento de modelo "preso")
    linhas = [l for l in revisado_limpo.splitlines() if l.strip()]
    if len(linhas) <= 2 and len_revisado < 200 and len_original > 500:
        return False

    return True