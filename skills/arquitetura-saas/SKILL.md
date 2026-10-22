---
name: arquitetura-saas
description: "Arquitetura SaaS: multi-tenancy, autenticação, planos e billing, onboarding, isolamento e escalabilidade. Use quando a tarefa envolver saas, software como serviço, multitenant, multi inquilino, assinatura, planos, billing, onboarding, jwt ou api comercial."
---
# SaaS — arquitetura de produto como serviço

## Decisão nº1: multi-tenancy
| Estratégia | Quando | Custo |
|---|---|---|
| Coluna `tenant_id` em cada tabela | começo, 90% dos casos | simples; índice composto OBRIGATÓRIO |
| Schema por tenant | centenas de tenants, compliance | migração por tenant |
| Banco por tenant | enterprise/corporativo | ops pesada |

Regra: **tenant_id entra em TODO query** (filter no ORM/repositório —
nunca confiar no controller lembrar disso).

## Pilares
1. **Auth**: JWT curto + refresh; org/tenant no token. RBAC (papel por
   tenant, não global).
2. **Planos/limites**: feature flags + limites (usuários, API) checados
   no domínio — `plano allow X senão 402/upgrade`.
3. **Billing**: webhooks de pagamento → estado de assinagem; NUNCA
   confiar no cliente sobre o que ele pagou.
4. **Onboarding**: cadastro → espaço pronto em <2min (provisionamento
   idempotente) — trial sem cartão converte mais.
5. **Dados**: RPO/RTO definidos, backup POR TENANT (LGPD: export/erase).

## Armadilhas clássicas
- ID sequencial global (um tenant adivinha o tamanho do outro) — UUID.
- Uploads compartilhados sem ACL por tenant.
- Cron global que processa tenant desativado.

## Verificação
Teste A NUNCA lê dado de B · plano limita de fato · exclusão LGPD funciona.
