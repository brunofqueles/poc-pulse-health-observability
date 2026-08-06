# Contexto de negócio — Pulse Health Group

> POC de plataforma de observabilidade de pipelines de dados, simulando a área de dados de um conglomerado fictício de Life Sciences. Este documento descreve o domínio de negócio simulado: missões, processos, entidades, regras e KPIs de cada área. Decisões técnicas (arquitetura, código, infraestrutura) vivem em `docs/architecture.md` e `docs/adr/`, não aqui.

## Visão geral

**Pulse Health Group** é uma holding fictícia composta por quatro empresas operacionais e um serviço compartilhado, integrados por um fluxo contínuo de dados: um pedido gera produção, que gera estoque, que gera entrega, que gera faturamento — com rastreabilidade de lote atravessando toda a cadeia.

```
Pulse Commercial      Pulse Pharma Mfg     Pulse Distribution   Pulse Logistics    SSC Financeiro
  (CRM)                 (ERP - Produção)     (ERP - Estoque)      (TMS)             (Financeiro)
     |                        |                    |                  |                   |
  Pedido  ------------->  (consome lote) -----> Separação ------> Entrega -------> Faturamento
     |                        |                    |                  |                   |
     +--- pedido_id propagado até aqui ------------+------------------+-------------------+
                              +--- lote_id propagado até aqui ---------+
```

**Escopo técnico Fase 1 (4 pipelines):** Manufacturing e Distribution nascem como módulos de uma única fonte ERP. Commercial (CRM), Logistics (TMS) e Financeiro são fontes próprias desde o início.
**Fase de escala (5º pipeline):** separação de Distribution como fonte independente do ERP, demonstrando evolução de arquitetura.

---

## Área 1 — Pulse Pharma Manufacturing

| Seção | Conteúdo |
|---|---|
| Missão/responsabilidade | Fabricação de medicamentos: controle de matéria-prima, produção, controle de qualidade, liberação de lote |
| Processos-chave | Recebimento de matéria-prima → Ordem de Produção → Produção → Controle de Qualidade → Liberação (ou Rejeição) de Lote |
| Entidades de negócio | Produto (SKU), Matéria-Prima, Lote de Produção, Ordem de Produção, Resultado de QC, Centro de Produção |
| Regras de negócio críticas | 1. Um lote só é liberado se passar no controle de qualidade — reprovação bloqueia distribuição.<br>2. Matéria-prima com validade vencida não pode entrar em ordem de produção.<br>3. Todo lote carrega validade própria (shelf life) que precisa ser propagada adiante.<br>4. `lote_id` é a chave que precisa sobreviver a todas as camadas seguintes — viabiliza recall |

**Catálogo de produtos (fixo, 3 SKUs):**

| Produto | Forma farmacêutica | Exige cadeia fria | Validade padrão |
|---|---|---|---|
| Vitalectra 500mg | Comprimido | Não | 730 dias |
| Imunorax | Injetável | **Sim** | 365 dias |
| Pulmoxil | Xarope | Não | 180 dias |

Catálogo reduzido a 3 produtos deliberadamente, cada um cobrindo uma forma farmacêutica distinta, para manter os cenários de teste concretos e verificáveis (ex.: Imunorax é o único produto que deveria acionar a regra de cadeia fria na Logistics).
| KPIs de negócio | Taxa de rejeição de lote (reprovados / total); tempo médio de ciclo (ordem aberta → lote liberado); aderência ao plano de produção (produzido vs. planejado) |
| Volumetria assumida (premissa) | ~80–150 ordens de produção/dia; ~40–80 lotes fechados/dia |
| Consumidor do dado | Qualidade/Compliance (rastreabilidade e recall); Pulse Distribution (o que está liberado pra despacho); plataforma de observabilidade (SLA de liberação de lote) |

---

## Área 2 — Pulse Distribution

| Seção | Conteúdo |
|---|---|
| Missão/responsabilidade | Centros de distribuição: gestão de estoque, separação de pedidos, expedição |
| Processos-chave | Recebimento do lote liberado (Manufacturing) → Armazenagem no Centro de Distribuição → Alocação contra Pedido (Commercial) → Separação (picking) → Expedição para transporte |
| Entidades de negócio | Centro de Distribuição, Posição de Estoque (lote + local + quantidade), Pedido de Separação, Nota de Expedição |
| Regras de negócio críticas | 1. Só entra em estoque lote com status "liberado" pela Manufacturing.<br>2. Alocação de pedido segue FEFO (first-expired, first-out) — não FIFO simples.<br>3. `lote_id` propagado da posição de estoque até a nota de expedição, sem quebra.<br>4. Estoque negativo é estado inválido — nunca deveria acontecer |
| KPIs de negócio | Acuracidade de estoque (contagem física vs. sistema, simulada); tempo de ciclo de separação (pedido recebido → expedido); % de pedidos separados via FEFO corretamente |
| Volumetria assumida (premissa) | ~150–300 pedidos de separação/dia (notas de expedição); ~30–60 posições de estoque/dia (snapshot por centro de distribuição, não é 1:1 com pedidos) |
| Consumidor do dado | Pulse Logistics (o que está pronto pra rota); Commercial (status do pedido); plataforma de observabilidade (SLA de separação, alerta de estoque negativo) |

---

## Área 3 — Pulse Logistics

| Seção | Conteúdo |
|---|---|
| Missão/responsabilidade | Transporte, roteirização, rastreamento, cadeia fria (temperatura), entregas |
| Processos-chave | Recebimento da Nota de Expedição (Distribution) → Roteirização (rota/veículo) → Transporte com monitoramento de temperatura → Entrega no destino → Comprovante de Entrega (POD) |
| Entidades de negócio | Rota, Veículo, Remessa (vincula nota de expedição a uma rota), Leitura de Temperatura (evento por remessa), Comprovante de Entrega |
| Regras de negócio críticas | 1. Remessa de produto com exigência de cadeia fria precisa manter temperatura dentro da faixa (ex.: 2–8°C) durante todo o transporte — violação é evento crítico.<br>2. `pedido_id` e `lote_id` propagados da Remessa até o Comprovante de Entrega — fecha a rastreabilidade ponta a ponta.<br>3. SLA de entrega definido por janela contratada — violação vira evento de SLA.<br>4. Entrega sem comprovante (POD ausente) é estado inválido.<br>5. **Veículo alocado a uma remessa de produto que exige cadeia fria precisa ser um veículo refrigerado** — violação é detectável apenas cruzando Logistics (veículo) com Manufacturing (produto/lote), não é verificação de uma tabela isolada |
| KPIs de negócio | OTIF (On Time In Full); % de remessas com violação de cadeia fria; tempo médio de trânsito por rota |
| Volumetria assumida (premissa) | ~150–300 remessas/dia (1:1 com notas de expedição); 3–6 leituras de temperatura por remessa refrigerada, distribuídas ao longo do trajeto (não em intervalo fixo de 30min — simplificação da implementação) |
| Consumidor do dado | Commercial (status de entrega); Compliance/Qualidade (violação de cadeia fria pode implicar recall); plataforma de observabilidade (SLA de OTIF, anomalia de temperatura) |

**Nota de implementação:** veículos (6, sendo 2 refrigerados) e rotas (4) nascem como catálogo fixo, mesmo padrão de simplificação já usado no CRM.

---

## Área 4 — Pulse Commercial

| Seção | Conteúdo |
|---|---|
| Missão/responsabilidade | Vendas, CRM, atendimento, clientes, representantes comerciais, pedidos |
| Processos-chave | Cadastro de Cliente → Representante registra Pedido → Pedido enviado pra separação (Distribution) → Acompanhamento de status → Atendimento pós-venda / tratamento de reclamação |
| Entidades de negócio | Cliente, Representante Comercial, Pedido (nasce aqui), Item de Pedido (SKU + quantidade), Interação de Atendimento |
| Regras de negócio críticas | 1. `pedido_id` é gerado aqui — Distribution e Logistics apenas consomem e propagam.<br>2. Pedido não pode conter SKU inexistente ou descontinuado (integridade referencial contra catálogo de Manufacturing).<br>3. Reclamação vinculada a `lote_id` é sinal de possível gatilho de recall.<br>4. Cliente inativo/bloqueado não pode gerar pedido novo |
| KPIs de negócio | Volume de pedidos por representante/região; taxa de reclamação por lote; tempo médio de primeira resposta em atendimento |
| Volumetria assumida (premissa) | ~150–300 pedidos/dia; ~20–40 interações de atendimento/dia |
| Consumidor do dado | Distribution (o que precisa ser separado); Logistics (destino da entrega); Qualidade/Compliance (reclamação x lote); plataforma de observabilidade (volume anômalo, taxa de reclamação por lote) |

**Nota de implementação:** nesta fase, clientes e representantes nascem como catálogo fixo (25 clientes, 8 representantes) gerado uma única vez — simplificação consciente do "crescimento esporádico" mencionado no processo-chave. Cadastro incremental real de cliente fica para uma evolução futura, não implementado nesta entrega.

---

## Área 5 — SSC Financeiro (Shared Services Center)

| Seção | Conteúdo |
|---|---|
| Missão/responsabilidade | Serviço compartilhado que consolida contas a pagar, contas a receber, faturamento, custos, fluxo de caixa e fechamento mensal — não é uma empresa operacional, consolida o que as outras já geraram |
| Processos-chave | Confirmação de entrega (POD, Logistics) → Geração de Fatura → Conta a Receber → Conciliação de pagamento → Lançamento contábil → Fechamento mensal |
| Entidades de negócio | Fatura, Conta a Receber, Conta a Pagar, Lançamento Contábil, Centro de Custo, Fechamento Mensal |
| Regras de negócio críticas | 1. Fatura só pode ser gerada após confirmação de entrega (POD).<br>2. Valor faturado precisa bater com o valor do pedido original de Commercial — ponto de reconciliação de negócio.<br>3. Fechamento mensal depende de todos os outros pipelines terem processado o período completo — dependência de orquestração.<br>4. Lançamento sem centro de custo válido é estado inválido |
| KPIs de negócio | DSO (dias médios até recebimento); % de faturas conciliadas sem divergência; tempo de fechamento mensal |
| Volumetria assumida (premissa) | ~150–300 faturas/dia |
| Consumidor do dado | Diretoria (consolidado financeiro); plataforma de observabilidade (reconciliação de valor, dependência de orquestração entre pipelines) |

**Nota de implementação:** centros de custo (4, um por área operacional) nascem como catálogo fixo, mesmo padrão de simplificação já usado no CRM e no TMS. Adicionalmente: na simulação atual, a cadeia completa (pedido → produção → expedição → entrega → faturamento) colapsa na mesma `data_referencia` — não há defasagem real de dias entre pedido e entrega como aconteceria numa operação real (ver ADR-011, adendo).

---

## Glossário de chaves compartilhadas

| Chave | Nasce em | Propaga até | Função |
|---|---|---|---|
| `lote_id` | Manufacturing | Distribution, Logistics | Rastreabilidade e recall |
| `pedido_id` | Commercial | Distribution, Logistics, Financeiro | Acompanhamento do pedido e faturamento |

## Calendário de operação por sistema

Premissa de negócio, não decisão técnica — reflete que a Manufacturing é indústria (não opera fim de semana) e que o Commercial recebe pedido por canal online mesmo fora do expediente.

| Sistema | Calendário |
|---|---|
| ERP — Manufacturing | Segunda a sexta |
| ERP — Distribution | Segunda a sábado |
| CRM — Commercial | Todos os dias |
| TMS — Logistics | Segunda a sábado |
| Financeiro — SSC | Segunda a sexta |

Ausência de execução em dia não operacional não é falha — é estado esperado, e a plataforma de observabilidade precisa distinguir os dois casos.

## Pontos transversais de observabilidade

- **Reconciliação de negócio:** valor do pedido (Commercial) vs. valor faturado (Financeiro).
- **Dependência de orquestração:** Financeiro não fecha o mês sem os outros quatro pipelines terem processado o período.
- **Anomalia de qualidade (dentro de um sistema):** violação de faixa de temperatura em remessas de cadeia fria (Logistics) — pode ocorrer por falha de equipamento mesmo em veículo refrigerado.
- **Anomalia de qualidade (cruzando sistemas):** veículo não refrigerado alocado a remessa de produto que exige cadeia fria — só detectável cruzando Logistics × Manufacturing (ver detalhamento técnico em `docs/schemas/tms.md`).
- **Estados inválidos a detectar:** estoque negativo (Distribution), entrega sem POD (Logistics), lançamento sem centro de custo (Financeiro).

## Os três eixos de observabilidade aplicados ao domínio

| Eixo | Pergunta | Exemplo neste domínio |
|---|---|---|
| Execução | Rodou? Quanto demorou? Falhou onde? | Pipeline do TMS atrasou X min hoje |
| Dados/qualidade | Volume normal? Regra violada? | Temperatura fora da faixa em um lote |
| Negócio | O indicador final bate com a origem? | Faturamento do SSC bate com pedidos do Commercial? |