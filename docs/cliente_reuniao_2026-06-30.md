# Ata da Reunião de Controle da Jornada Clínica

> ## ⚠️ RASCUNHO v0.1 — pendente de validação
>
> Documento estruturado a partir de transcrição automática do Gemini.
> Nomes, termos técnicos e detalhes de §14 (linha do tempo) devem ser
> **validados com Diego + Jader** antes de virar base de implementação.
> Mudanças de escopo, ambiguidades em aberto (Q1–Q9) e decisões de
> arquitetura decorrentes estão consolidadas em
> [[../../mvp-jornada-clinica-2026-06-30]] (memória do projeto) e em
> `docs/mvp_plano.md`.

**Data:** 2026-06-30, 21:25 GMT-03:00
**Duração:** 01:12:05
**Participantes:** Diego Duarte Menescal, Jader Braz
**Origem:** Anotações e transcrição automática do Gemini
**Tema central:** Transformar planos de acompanhamento e agendamentos em controle operacional com alertas preditivos.

---

## 1. Leitura executiva

- A conversa técnica começa por volta de 00:14:48. Antes disso, há contexto pessoal e assuntos externos ao projeto, sem impacto direto nos requisitos do sistema.
- **Decisão principal:** não tentar espelhar todo o sistema atual da clínica. O foco será capturar o que realmente governa a jornada do paciente: PDFs de plano de acompanhamento, relatórios de agendamento em Excel e uma lista ativa de serviços/procedimentos.
- O aplicativo deve comparar o plano ideal com os registros reais de agendamento/atendimento. Quando uma sessão ou consulta esperada não aparecer, o sistema deve gerar alerta visual, **exigir justificativa** e registrar log para acompanhamento administrativo.
- O objetivo prático é reduzir o trabalho de caçar falhas manualmente em dezenas de pacientes. O sistema deve apontar **poucos casos críticos por semana**, em vez de obrigar a equipe a revisar tudo na unha.

## 2. Problema operacional identificado

- O sistema atual gera muitos dados, mas parte deles é ruidosa, redundante ou difícil de reaproveitar para auditoria.
- Os relatórios importantes de planos/orçamentos são exportados apenas em PDF, sem opção direta de CSV, Excel ou XML.
- Um mesmo paciente pode ter vários orçamentos vinculados ao mesmo plano, o que torna o **ID do orçamento uma chave fraca** para rastreabilidade.
- O status de atendimento depende de **atualização manual** da equipe. Se a pessoa não muda de "agendado" para "atendido", o dado operacional fica ambíguo.
- O risco real não é só saber se algo foi vendido, mas se o paciente está seguindo a **periodicidade** necessária para o plano gerar resultado.

## 3. Decisões consolidadas (D1–D10)

| ID | Decisão | Implicação prática |
|---|---|---|
| **D1** | Evitar espelhar o sistema inteiro | Usar apenas os dados necessários para controle da jornada; dados poluídos ficam fora do MVP. |
| **D2** | **PDF do plano é a fonte de cadastro** | Paciente, plano e itens esperados entram no app a partir do PDF importado. |
| **D3** | **Excel de agendamento não cria paciente** | A planilha serve para atualizar realidade operacional e comparar com o plano já cadastrado. |
| **D4** | **Nomenclatura do plano é canônica** | O sistema deve procurar nos relatórios somente os nomes de serviços existentes no plano/catálogo. |
| **D5** | **Vírgula separa procedimentos** | Nas descrições longas, a vírgula é o delimitador principal para distinguir itens do plano. |
| **D6** | **Nome do paciente será a chave inicial** | Usar o nome completo como vínculo entre PDF e Excel; duplicidades e homônimos ficam fora do escopo inicial. |
| **D7** | **Relatório de agendamento é prioritário** | Ele informa datas e previsões; o relatório de frequência é complementar. |
| **D8** | **Alertas devem exigir justificativa** | A equipe só avança após registrar motivo da ausência, erro, remarcação ou outra exceção. |
| **D9** | **Carga histórica será controlada** | Jader fará upload dos PDFs desde janeiro; depois será importada a base de agendamentos para cruzamento. |
| **D10** | **Urgência na liberação** | A prioridade é colocar o fluxo rodando, mesmo que algumas bordas fiquem para evolução posterior. |

## 4. Glossário operacional

| Termo | Definição operacional |
|---|---|
| Plano de acompanhamento | Estrutura clínica com procedimentos, quantidades e frequência. |
| Orçamento | Registro comercial/financeiro gerado a partir de venda ou plano. Todo plano gera orçamento, mas nem todo orçamento vira plano. |
| PDF do plano | Arquivo exportado do sistema atual. Será usado como fonte oficial para cadastrar paciente, plano, itens e expectativas. |
| Relatório de agendamento | Planilha Excel com datas, serviços, status e registros criados pela equipe. |
| Relatório de frequência | Relatório que ajuda a confirmar execução/status, mas não substitui o agendamento. |
| Nomenclatura canônica | Nome do serviço/procedimento como aparece no plano/catálogo e que será usado para matching. |
| Alerta operacional | Sinal visual gerado quando há divergência entre o esperado e o registrado. |
| Justificativa obrigatória | Campo que a equipe deve preencher quando o sistema sinaliza ausência, atraso ou inconsistência. |

## 5. Fontes de dados e papel de cada uma

| Fonte | Papel | Uso no sistema |
|---|---|---|
| PDF do plano de acompanhamento | Entrada primária | Cria/atualiza paciente, plano, itens, quantidades, periodicidade e expectativas futuras. |
| Excel de agendamentos | Entrada recorrente | Atualiza o que foi agendado, quando foi criado, status e data esperada/real operacional. |
| Relatório de frequência | Fonte complementar | Ajuda a validar se algo foi atendido, mas depende de status manual. |
| Lista ativa de serviços/procedimentos | Parametrização | Define o vocabulário aceito pelo sistema e reduz ruído de nomes obsoletos ou raros. |
| Lista usada pela Dane nos orçamentos | Parametrização prioritária | Deve ser preferida porque reflete o uso real no dia a dia da clínica. |

## 6. Regras de negócio

- Todo plano gera um orçamento automaticamente, mas orçamentos podem existir sem virar plano de acompanhamento.
- Um paciente pode ter **múltiplos orçamentos para o mesmo ciclo/mesmo plano**. Portanto, o **ID do orçamento não deve ser a chave principal do MVP**.
- A comparação principal deve ser entre itens do plano e registros de agendamento/atendimento, usando **nome do paciente** e **nomenclatura do serviço**.
- Itens que não aparecem na nomenclatura do plano/catálogo devem ser **ignorados** no matching inicial, para evitar falsa complexidade.
- Para **injetáveis/EV/IM**, a lógica tende a ser **semanal** quando o plano indicar sessões semanais.
- Para **acompanhamento profissional/consultas**, a lógica tende a ser **mensal**, com tolerância operacional de alguns dias para finais de semana e remarcações.
- Quando existir **agendamento futuro real diferente da data ideal calculada**, o sistema deve respeitar a data agendada e **postergar o alerta para ela**.
- Se **não existir agendamento ou atendimento dentro da janela esperada**, deve surgir alerta para a área responsável.
- A justificativa deve gerar log administrativo: **quem justificou, quando, paciente, item afetado, motivo e, se houver, nova data combinada**.

## 7. Estratégia de parsing e normalização

- O parsing deve começar simples e auditável: extrair do PDF os itens do plano, suas quantidades e frequências; depois cruzar com os registros do Excel.
- Nas descrições compostas, usar a **vírgula** como separador de itens. Exemplo conceitual: *"medicamento X, injetáveis IM, injetáveis EV"* deve virar três itens distintos.
- Aplicar normalização técnica leve: remover espaços duplicados, padronizar quebras de linha e comparar textos de forma consistente. **Evitar matching semântico agressivo no MVP**, porque ele pode criar certeza falsa.
- A lista ativa de serviços deve funcionar como **whitelist**. O que estiver fora dela deve ir para uma **fila de revisão/parametrização**, não para o cálculo automático principal.

## 8. Fluxo operacional proposto

| Etapa | Ação | Resultado esperado |
|---|---|---|
| 1 | Parametrizar catálogo | Importar/colar lista ativa de serviços e lista usada nos orçamentos. Marcar ativos, raros e obsoletos. |
| 2 | Importar PDF do plano | Criar ou localizar paciente por nome; extrair plano, itens, quantidades e frequências. |
| 3 | Gerar jornada esperada | Calcular datas esperadas conforme frequência do plano e data de referência do PDF/plano. |
| 4 | Importar Excel de agendamento | Ler agendamentos, status, datas e serviços; vincular por nome do paciente e nomenclatura. |
| 5 | Cruzar esperado versus registrado | Verificar se cada item esperado tem agendamento/atendimento dentro da janela aceitável. |
| 6 | Gerar alertas | Criar alerta vermelho para lacunas relevantes, direcionando para enfermagem ou agendamento. |
| 7 | Exigir justificativa | Equipe registra motivo, erro, ausência, viagem, remarcação ou pendência. **Sem justificativa, não avança.** |
| 8 | Acompanhar logs | Administrador revisa alertas, justificativas e próximos agendamentos para cobrança operacional. |

## 9. Matriz de alertas

| Condição | Severidade | Responsável | Mensagem | Ação esperada |
|---|---|---|---|---|
| Sessão injetável/EV/IM semanal não encontrada | Alta | Enfermagem | Alerta vermelho: paciente não compareceu ou não foi agendado na semana esperada. | Justificar e informar próxima data. |
| Acompanhamento profissional mensal não encontrado | Alta | Agendamento | Alerta vermelho: consulta do mês não localizada dentro da tolerância. | Justificar e reagendar. |
| Paciente previsto não aparece no Excel | Alta | Área responsável pelo item | Possível perda de seguimento ou falha de agendamento. | Justificar ausência e indicar plano de ação. |
| Status permanece como agendado/atrasado | Média | Profissional/equipe técnica | Atendimento pode ter ocorrido, mas não foi atualizado manualmente. | Atualizar status ou justificar. |
| Serviço do Excel não existe no catálogo | Média | Administrador/parametrização | Nomenclatura nova, rara ou não padronizada. | Classificar serviço e atualizar whitelist. |
| Duplicidade ou mudança de nome | Baixa no MVP | Administrador | Pode quebrar histórico, mas não bloqueia primeira versão. | Registrar exceção e corrigir cadastro quando necessário. |

## 10. Escopo do MVP

### Dentro do MVP
- Importar PDF de plano de acompanhamento.
- Cadastrar paciente/plano a partir do PDF.
- Importar Excel de agendamentos.
- Parametrizar lista ativa de serviços/procedimentos.
- Cruzar plano esperado versus agendamento/atendimento registrado.
- Gerar alertas por paciente, serviço, data esperada e responsável.
- Exigir justificativa para encerramento/tratamento do alerta.
- Registrar log administrativo das justificativas.

### Fora do MVP
- **Espelhar todas as telas e dados do sistema atual** (recusa explícita do espelho SupportHealth).
- Resolver definitivamente homônimos, CPF, duplicidades e histórico antigo inconsistente.
- Usar ID do orçamento como chave central.
- Automatizar remarcação direta na agenda do sistema externo.
- Interpretar semanticamente qualquer nomenclatura desconhecida sem revisão humana.

## 11. Plano de carga histórica

- A carga histórica deve ser feita de forma controlada para evitar sobreposição e falsas inconsistências.
- Jader fará upload dos PDFs dos pacientes de janeiro/2026 até a data atual, um a um ou em lotes controlados.
- Após essa base inicial, será importado o Excel de agendamentos para o mesmo período.
- O sistema deve cruzar todos os dados e gerar **muitos alertas iniciais**; essa primeira leva será usada para **calibragem manual**.
- Depois da calibragem, o processo recorrente pode ser **semanal**, com importação do relatório de agendamentos e revisão dos alertas gerados.

## 12. Riscos e cuidados

| Risco | Impacto | Mitigação |
|---|---|---|
| Parsing de PDF instável | Alto | Criar parser com logs, tela de pré-visualização e fallback manual. |
| Nomenclatura inconsistente | Alto | Usar whitelist ativa e fila de parametrização. |
| Status manual não atualizado | Alto | Alertas também devem cobrar atualização do status. |
| Mudança de nome do paciente | Médio | Registrar aliases futuramente; no MVP aceitar limitação. |
| Carga histórica com sobreposição | Médio | Controlar janela de datas e hash de arquivo/importação. |
| Excesso de alertas iniciais | Médio | Separar alerta crítico, aviso e revisão de parametrização. |

## 13. Pendências e responsáveis

| Responsável | Pendência | Prioridade |
|---|---|---|
| Diego | Parametrizar parser do PDF (extrair paciente, itens, quantidade, frequência, datas esperadas). | Alta |
| Diego | Implementar import do Excel (vínculo por nome + nomenclatura). | Alta |
| Diego | Lógica de auditoria (comparar jornada esperada versus registros importados). | Alta |
| Diego | Tela/painel de alertas (alerta vermelho + justificativa obrigatória + log administrativo). | Alta |
| Jader | Enviar lista ativa de serviços + lista usada pela Dane. | Alta |
| Jader | Fazer upload histórico dos PDFs jan/2026→hoje. | Alta |
| Equipe clínica | Manter status de atendimento atualizado. | Alta |

## 15. Formulação final do requisito

- Construir um módulo de controle da jornada do paciente capaz de **importar PDFs de planos de acompanhamento**, **importar relatórios Excel de agendamento**, **parametrizar serviços clínicos ativos** e **gerar alertas operacionais** quando houver divergência entre o plano esperado e os registros reais.
- O sistema deve **priorizar utilidade operacional sobre perfeição cadastral**. A primeira versão deve aceitar matching por nome, ignorar ruídos fora da nomenclatura canônica, registrar exceções e **obrigar justificativas** quando o paciente não seguir a periodicidade esperada.
- Em termos práticos: *"o sistema não precisa saber tudo. Ele precisa cutucar a pessoa certa, na hora certa, com o motivo certo. O resto é decoração de dashboard."*

---

## Aplicação das decisões (Diego, 2026-06-30)

As ambiguidades técnicas (Q1–Q9) foram respondidas em conversa subsequente e estão registradas em [[../../mvp-jornada-clinica-2026-06-30]]. Resumo:

- **Q1, Q3:** Excel é `.xlsx` → `src/excel_importer/` usa `openpyxl` (CLAUDE.md atualizado, parser Excel é agora exceção do Cliente).
- **Q2:** Layout único → parser sem perfis.
- **Q4:** Data de referência = **data do rodapé do PDF** (parser já entrega; não precisa estender parser).
- **Q5:** Tolerância = **desconsidere** → alerta dispara estritamente em `expected_date` (tolerância vira flag na Fase 7).
- **Q6:** 1 tabela `alerts` com coluna `severity`.
- **Q7:** Lista ativa entra via **upload CSV** (não Excel, não CRUD).
- **Q8:** Alerta **pode reabrir** após fechamento.
- **Q9:** `expected_date` é **rolante** — recalculada a cada sessão real; alerta dispara a partir da última `expected_date` atualizada.

Plano de implementação em 8 fases: `docs/mvp_plano.md`.