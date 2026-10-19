---
name: revisao-seguranca
description: Revisão de segurança — senha, token, credencial, chave, vazamento, exposição de dados, permissão de arquivo, comando arriscado, vulnerabilidade ou segredo no código antes de entregar.
---

# Revisão de segurança (à prova de vazamento)

Neste agente, vazamento de credencial é o erro mais grave que existe.

## Checklist antes de entregar qualquer coisa
1. **Segredos**: nenhuma senha/token/chave aparece em arquivo, comando,
   resposta ou log. Se precisou ler segredo, ele fica no cofre (600) e o
   valor NUNCA é ecoado.
2. **Permissões**: arquivos com dado sensível → `chmod 600` (diretório 700).
3. **Comandos**: antes de executar algo destrutivo (rm, dd, mkfs, > em
   arquivo de sistema), confirme o alvo exato — caminho absoluto, não
   relativo.
4. **Rede**: nada de enviar dado local para serviço externo sem o operador
   pedir explicitamente.
5. **Código gerado**: procure padrões perigosos (eval em entrada externa,
   shell=True com string, SQL concatenado, hardcode de credencial).

## Na entrega
Liste o que foi verificado e o que (se algo) continua sensível e por quê.
