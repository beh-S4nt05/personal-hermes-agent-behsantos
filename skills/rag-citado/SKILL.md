---
name: rag-citado
description: Responder com base em documentos e fontes com citação — contexto, evidência, fonte, citação, referência, contradição entre fontes, base de conhecimento, rag e verificação de informação.
---

# RAG com citação (resposta verificável)

## Regras
1. **Uma afirmação, uma fonte**: todo fato que veio de documento/web leva a
   origem (arquivo+página ou URL) na frente ou em rodapé "Fontes:".
2. **Contexto insuficiente?** Diga o que falta e FAÇA a segunda busca
   (web_search / ler outro arquivo) em vez de responder pela metade.
3. **Contradição**: se duas fontes discordam, mostre as duas com origem e
   diga qual parece mais confiável e por quê.
4. **Não achou?** "Não encontrei" é uma resposta válida e honesta —
   preencher lacuna com suposição é proibido.
5. Separe FATO (com fonte) de OPINIÃO/ESTIMATIVA (marcada como tal).
