/**
 * Portfólio Técnico — Engenharia de Dados, Analytics Engineering & BI
 * Configuração Centralizada e Motores Interativos de Simulação (100% Dados Sintéticos)
 */

const CONFIG = {
  github: "https://github.com/PedroEdus",
  portfolioRepo: "https://github.com/PedroEdus/portifolio",
  linkedin: "https://www.linkedin.com/in/pedro-eduardo-carneiro-moura-183612179/",
  email: "pedroeduardo8577@gmail.com",
  phone: "+55 (62) 98595-5399",
  location: "Goiânia, GO — Brasil"
};

// Espelho de assets/data/projects.json, embutido para o site funcionar também via file://
const FALLBACK_PORTFOLIO_DATA = {
  "projects": [
    {
      "id": "projeto-03-dw-snapshots-diff",
      "code": "CASE 03 · DESTAQUE ENGENHARIA DE DADOS",
      "featured": true,
      "title": "DW Financeiro: Motor de Historização por Snapshots Semanais/Diários e Diff Engine para ERPs Mutáveis",
      "company": "Brasil Terrenos / Buriti Empreendimentos",
      "role": "Data Engineer & Analytics Engineer",
      "categories": [
        "Data Engineering",
        "Data Warehousing & Snapshots",
        "Analytics Engineering"
      ],
      "stack": [
        "Microsoft Fabric Warehouse",
        "T-SQL",
        "Dataflows Gen2",
        "Pipelines Fabric",
        "Direct Lake",
        "Python",
        "Pytest"
      ],
      "repoPath": "../case-studies/projeto-03-dw-snapshots-diff",
      "demoCommand": "python case-studies/projeto-03-dw-snapshots-diff/run_demo.py",
      "testCommand": "pytest case-studies/projeto-03-dw-snapshots-diff/tests/",
      "headlineMetrics": [
        "2.583.883 linhas por snapshot semanal (~134M linhas/ano projetadas)",
        "5.309 mutações diárias auditadas ao nível de parcela e fatia de rateio",
        "87.876 fornecedores em dimensão acumulativa com 0 órfãos (Decisão D-39)",
        "~12 min de tempo total de carga ponta a ponta (64+7 colunas sob contrato)"
      ],
      "context": "O ERP operacional (UAU / Globaltec) consolida o Contas a Pagar em visões operacionais mutáveis: quando uma parcela sofre prorrogação de vencimento, alteração de valor, reclassificação de centro de custo/insumo ou exclusão física no sistema de origem, o registro anterior é sobrescrito in-place sem trilha nativa de versão. A diretoria financeira precisava responder exatamente 'o que mudou na carteira de desembolso entre a semana passada e hoje?' sem distorcer relatórios históricos já fechados.",
      "challenge": "Construir um Data Warehouse corporativo capaz de fotografar 2,58 milhões de linhas toda semana (e manter uma camada operacional diária), garantindo idempotência absoluta em reprocessamentos, separando o rótulo lógico da fotografia (data_snapshot) do carimbo físico de execução (dt_carga), blindando o pipeline contra Schema Drift silencioso e computando o delta exato ao grão de parcela + fatia de rateio contábil.",
      "architecture": {
        "summary": "Arquitetura em 5 schemas no Microsoft Fabric Data Warehouse (wh_dw_financeiro) orquestrada por Pipeline parametrizado.",
        "nodes": [
          "ERP SQL Server (Query Consolidada 64 cols)",
          "stg.fin_contas_pagar (TRUNCATE + Carga Bruta)",
          "ctl.sp_verificar_contrato (Guarda sys.columns = 64)",
          "snap.fin_contas_pagar_s (Série Histórica Semanal Idempotente)",
          "cur.fin_contas_pagar (Visão Operacional Diária)",
          "dim.* (10 Dimensões Acumulativas sem Órfãos)",
          "snap/cur.mudanca_parcela (Diff Engine Parcela & Rateio)"
        ]
      },
      "decisions": [
        {
          "title": "Separação Semântica entre data_snapshot e dt_carga",
          "detail": "data_snapshot é o rótulo lógico imutável da foto na série temporal (ex.: domingo '2026-03-29'), enquanto dt_carga registra o instante físico da extração em America/Sao_Paulo. Reprocessar uma carga com falha substitui atomicamente a partição lógica (DELETE WHERE data_snapshot = @data + INSERT) sem duplicar nem contaminar o histórico."
        },
        {
          "title": "As 5 Armadilhas Reais do Fabric Warehouse Documentadas e Resolvidas",
          "detail": "(1) Collation Case-Insensitive exigindo comparação binária explícita quando necessário; (2) VARCHAR contando bytes em UTF-8 (caracteres acentuados ocupam 2 bytes, exigindo folga de +50% no DDL); (3) Medidas DAX sem guarda HASONEVALUE(data_snapshot) que somavam 52 fotos e inflavam valores em 52x; (4) TriggerTime em UTC às 22h BRT virando o dia seguinte (corrigido com AT TIME ZONE 'E. South America Standard Time'); (5) SELECT * silencioso substituído por guarda estrita em sys.columns."
        },
        {
          "title": "Dimensões Acumulativas sem Órfãos (D-39)",
          "detail": "Como fornecedores ou obras podem deixar de aparecer na foto corrente mas continuam presentes em snapshots históricos, as 10 dimensões operam em modo acumulativo incremental (INSERT WHERE NOT EXISTS + UPDATE de atributos), garantindo 0 chaves órfãs em 87.876 fornecedores."
        },
        {
          "title": "Motor de Diff em Dois Níveis (Parcela e Fatia de Rateio)",
          "detail": "As procedures sp_calcular_mudanca_semanal e sp_calcular_mudanca_diaria comparam T vs T-1 com FULL OUTER JOIN na chave composta da parcela e da apropriação de insumo/centro de custo, persistindo apenas os registros que sofreram mutação (INCLUIDA, EXCLUIDA, VALOR_ALTERADO, VENCIMENTO_ALTERADO, STATUS_ALTERADO, RECLASSIFICADA_RATEIO) com colunas antes/depois lado a lado."
        }
      ],
      "demoVsReal": {
        "real": "Implementado em Microsoft Fabric Warehouse (wh_dw_financeiro) com 19 scripts T-SQL numerados, Dataflow Gen2 de ingestão, pipeline pl_dw_financeiro_semanal, 10 dimensões, tabelas de diff semanal/diário e modelo Direct Lake com 46 medidas DAX auditadas.",
        "demo": "Reconstrução 100% executável em Python + SQLite/DuckDB (src/warehouse_snapshot_engine.py) simulando 3 snapshots semanais consecutivos + carga diária cur, injetando mutações realistas in-place, testando reexecução idempotente da mesma data_snapshot e validando o motor de diff com Pytest."
      },
      "quality": "Guarda contratual de colunas pré-publicação, transação explícita no swap de snapshot, bloqueio de contaminação retroativa (impede gravar snapshot com data anterior à última foto sem flag de backfill), auditoria de órfãos nas dimensões e suíte automatizada de testes unitários.",
      "results": "Capacidade inédita de auditoria financeira retrospectiva sobre 2,58M de linhas por semana em ~12 minutos de execução total, identificando automaticamente milhares de reprogramações de vencimento e reclassificações de rateio que antes passavam despercebidas.",
      "lessons": "Em Data Warehouses baseados em snapshots periódicos sobre ERPs mutáveis, a governança da etiqueta temporal (data_snapshot) e a proteção semântica no consumo BI (guarda obrigatória de foto única nas medidas DAX) são tão críticas quanto a própria ingestão."
    },
    {
      "id": "projeto-01-lakehouse-recebiveis",
      "code": "CASE 01 · LAKEHOUSE & ANALYTICS ENGINEERING",
      "featured": true,
      "title": "Plataforma Lakehouse Medallion, Controle Transacional e Matriz Roll-Rate de Recebíveis",
      "company": "Brasil Terrenos / Buriti Empreendimentos",
      "role": "Lead Data Engineer & Analytics Engineer",
      "categories": [
        "Data Engineering",
        "Analytics Engineering"
      ],
      "stack": [
        "Microsoft Fabric Lakehouse",
        "PySpark",
        "Delta Lake",
        "T-SQL Warehouse",
        "Direct Lake",
        "PBIR / TMDL",
        "Python",
        "Pytest"
      ],
      "repoPath": "../case-studies/projeto-01-lakehouse-recebiveis",
      "demoCommand": "python case-studies/projeto-01-lakehouse-recebiveis/run_demo.py",
      "testCommand": "pytest case-studies/projeto-01-lakehouse-recebiveis/tests/",
      "headlineMetrics": [],
      "context": "A análise corporativa de inadimplência, carteira ativa, renegociações e fluxo de recebíveis dependia de extrações legadas opacas em QlikView (.qvd), onde distratos eram confundidos com cessões de direitos, custas jurídicas se misturavam às parcelas contratuais e não havia garantias de consistência quando o processo noturno de cálculo de juros do ERP atrasava.",
      "challenge": "Projetar uma plataforma Lakehouse Medallion ponta a ponta no Microsoft Fabric que impedisse a publicação de dados quando o job noturno do ERP (ProUAU) estivesse incompleto, preservasse fotografias mensais cruas imutáveis, isolasse cadeias de cessão de crédito e calculasse matrizes de transição Roll-Rate (M -> M+1) com paridade matemática entre as duas implementações.",
      "architecture": {
        "summary": "Orquestração mestre (pl_inad_orchestrator) coordenando Warehouse de Controle Transacional (wh_ctl_inad) e Lakehouses Bronze, Silver e Gold.",
        "nodes": [
          "ERP SQL Server (Tabelas de Origem)",
          "wh_ctl_inad (sp_abrir_rodada / controle ACID)",
          "lh_bronze_inad (Staging stg_* -> Gate >=99.5% -> bronze_* + Foto Mensal Dia 1)",
          "lh_silver_inad (Contrato Declarativo snake_case + Bloqueio Schema Drift)",
          "lh_gold_inad (Tabelas Star Schema: Roll-Rate, Coorte Reneg, Cessões)",
          "sm_inad & rpt_inad (Direct Lake com Medidas DAX / PBIR)"
        ]
      },
      "decisions": [
        {
          "title": "Ingestão Staging-First Atômica e Gate de Cobertura >= 99,5%",
          "detail": "Os Dataflows nunca sobrescrevem a Bronze diretamente; gravam em stg_*. O notebook nb_bronze_promote_and_validate cruza as chaves de ContasReceber contra ContasReceberCalc. Se a cobertura for < 99,5% (job noturno ProUAU incompleto), a promoção é abortada e a tabela de produção permanece intacta."
        },
        {
          "title": "Exceção Parametrizada de Virada de Mês (aceitar_calc_defasada)",
          "detail": "No dia 1 de cada mês, a foto contábil da virada não pode ser perdida caso a tabela auxiliar de cálculo atrase. O parâmetro permite registrar a foto com flag auditável no controle transacional."
        },
        {
          "title": "Linhagem de Cessões vs. Distratos Reais",
          "detail": "Descoberta via engenharia reversa (baterias de consultas SQL) de que a manutenção TipoMnt = 2 representa transferência/cessão de titularidade e não distrato comercial, evitando inflar artificialmente o indicador de rescisões."
        },
        {
          "title": "Duplo Eixo de Atraso e Matriz de Transição Roll-Rate (M -> M+1)",
          "detail": "Separação estrita entre atraso contratual (data_vencimento_original) e atraso operacional prorrogado (data_vencimento_atual), além de matriz de migração entre faixas de aging com precedência determinística (cedido > cancelado > renegociado > pago > em_aberto)."
        }
      ],
      "demoVsReal": {
        "real": "Em produção no Microsoft Fabric com tabelas Bronze/Silver, tabelas de foto mensal, tabelas Gold em PySpark, Warehouse de controle T-SQL e modelo Direct Lake com medidas DAX governadas.",
        "demo": "Motor completo em Python + SQLite/DuckDB (src/pipeline_lakehouse.py) reproduzindo o controle transacional, o gate de 99,5%, a foto idempotente de dia 1, o bloqueio de Schema Drift na Silver, a matriz Roll-Rate na Gold e o teste automatizado que prova a paridade célula a célula entre SQL puro e o pipeline."
      },
      "quality": "Suítes de validação em produção (contagem Bronze==Silver, soma financeira, zero chaves nulas, reconciliação com as cidades dos PDFs legados e paridade célula a célula entre protótipo SQL e PySpark Gold).",
      "results": "Eliminação de divergências entre relatórios financeiros e comerciais, visibilidade inédita da mortalidade de renegociações por safra (coorte) e confiança matemática auditada célula a célula.",
      "lessons": "Separar a validação de consistência da fonte (Staging Gate) da camada Bronze pública é a forma mais eficaz de proteger modelos Direct Lake contra falhas de jobs noturnos no ERP."
    },
    {
      "id": "projeto-02-conciliacao-bancaria",
      "code": "CASE 02 · MOTOR CONTÁBIL & AUDITORIA DE CICLOS",
      "featured": true,
      "title": "Motor de Conciliação Bancária, Recálculo de 5 Pernas do Razão e Auditoria de Ciclos Multi-Snapshot",
      "company": "Brasil Terrenos / Buriti Empreendimentos",
      "role": "Data Engineer & Analytics Engineer",
      "categories": [
        "Data Engineering",
        "Analytics Engineering",
        "Data Warehousing & Snapshots"
      ],
      "stack": [
        "Microsoft Fabric",
        "PySpark",
        "T-SQL",
        "Delta Lake",
        "Algoritmos Calendário FEBRABAN",
        "Python",
        "Pytest"
      ],
      "repoPath": "../case-studies/projeto-02-conciliacao-bancaria",
      "demoCommand": "python case-studies/projeto-02-conciliacao-bancaria/run_demo.py",
      "testCommand": "pytest case-studies/projeto-02-conciliacao-bancaria/tests/",
      "headlineMetrics": [
        "Redução do fechamento semanal de 26 dias para 3 dias",
        "100% de batimento contábil em 6.330 / 6.330 conta×dias (R$ 0,00 divergência)",
        "6.596 pares transitórios (Tipo 5/6) expurgados preservando 20 casos unilaterais",
        "2.261 validações manuais in-place descobertas (11,9 dias de atraso oculto médio)"
      ],
      "context": "O fechamento semanal de conciliação bancária das SPEs levava até 26 dias devido à necessidade de cruzar extratos bancários com milhares de lançamentos contábeis internos, onde transferências transitórias de intermediação poluíam as pendências e validações manuais sobrescreviam o primeiro snapshot do extrato.",
      "challenge": "Reconstruir independentemente o saldo bancário contábil a partir das 5 origens primárias do ERP com erro zero perante a tela nativa, eliminar ruídos de lançamentos transitórios de boleto sem apagar erros operacionais unilaterais e medir o tempo real de conciliação mesmo quando o operador validava o lançamento in-place no snapshot 1.",
      "architecture": {
        "summary": "Pipeline Medalhão no workspace ws_financeiro alimentado por 15 tabelas/views do ERP, processado por 3 notebooks PySpark especializados.",
        "nodes": [
          "ERP SQL Server (15 Tabelas/Views Financeiras)",
          "Bronze Lakehouse (Ingestão Full & Incremental por Janela)",
          "nb_silver_transforms (Recálculo 5 Pernas + Expurgo Pares Tipo 5/6)",
          "nb_gold_conciliacao (Ciclo 42 Snapshots + Detecção In-Place + ICP)",
          "nb_gold_qualidade (Sentinela Mediana 10d Úteis + Calendário Meeus/Butcher)"
        ]
      },
      "decisions": [
        {
          "title": "Recálculo Independente das 5 Pernas do Razão (SF = SI + C - D)",
          "detail": "Unificação de Extrato, RecebePgto, Depositos, EntSaiEmpAplic e VwTransfBcoExtrato, atingindo 100% de paridade matemática em 6.330 combinações conta×dia."
        },
        {
          "title": "Expurgo Seletivo de Pares Transitórios (Regra R3 — TipoControle 5 e 6)",
          "detail": "Na natureza '0071', o ERP gera pares transitórios de entrada (Tipo 5) e saída (Tipo 6) por proposta. Um filtro ingênuo ocultaria erros reais. O algoritmo casa pares estritos por (empresa, banco, conta, proposta) e expurga apenas os 6.596 pares casados, preservando 20 lançamentos unilaterais para auditoria."
        },
        {
          "title": "Auditoria de Ciclo Multi-Snapshot e Detecção de Validação In-Place",
          "detail": "Rastreando até 42 snapshots por extrato (Num_exa), descobriu-se que 2.261 lançamentos já nasciam com Status_exa = 2 no snapshot 1 porque foram validados manualmente antes do congelamento. O motor detecta essa anomalia comparando MAX(data_validacao) - MIN(data_criacao), revelando 11,9 dias de atraso médio que antes pareciam '0 dias'."
        },
        {
          "title": "Calendário FEBRABAN via Algoritmo de Meeus/Butcher e Isolamento de Aplicações no ICP",
          "detail": "Cálculo determinístico de feriados móveis bancários (Carnaval, Sexta-Feira Santa, Corpus Christi) via algoritmo astronômico de Meeus/Butcher para a Páscoa e remoção de 311 contas de aplicação/investimento do denominador diário do Índice de Conciliação no Prazo (ICP)."
        }
      ],
      "demoVsReal": {
        "real": "23 scripts SQL investigativos (00..22), 3 notebooks PySpark em produção no Microsoft Fabric auditando 132.455 lançamentos e 15.825 ciclos de vida de conciliação.",
        "demo": "Motor executável em Python (src/engine_conciliacao.py) implementando a equação contábil das 5 pernas, o casamento e expurgo seletivo Tipo 5/6, o rastreador de snapshots com detecção de overwrite in-place e o calendário FEBRABAN via Meeus/Butcher."
      },
      "quality": "Sentinela automática de cobertura de extratos baseada na mediana móvel dos últimos 10 dias úteis bancários e validação estrita de continuidade de saldos entre meses.",
      "results": "Redução comprovada do ciclo de fechamento semanal de 26 dias para 3 dias, expurgo automático de 13.192 linhas de ruído transitório e transparência total sobre o SLA real da tesouraria.",
      "lessons": "Confiar apenas no status atual ou na diferença entre o primeiro e o último snapshot esconde mutações in-place; cruzar timestamps de auditoria interna do registro é essencial para medir SLAs reais."
    },
    {
      "id": "projeto-04-marketing-crm-cloud",
      "code": "CASE 04 · CLOUD DATA ENGINEERING & DATA APPS",
      "featured": true,
      "title": "Plataforma Cloud de Marketing & CRM: Ingestão Multi-API, Lookback/MERGE, Taxonomia Regex e Data App",
      "company": "Brasil Terrenos / Buriti Empreendimentos",
      "role": "Data Engineer & Data Apps Architect",
      "categories": [
        "Data Engineering",
        "Cloud & APIs",
        "Analytics Engineering"
      ],
      "stack": [
        "Google BigQuery",
        "Python",
        "GitHub Actions",
        "Google Ads gRPC v20",
        "Meta Graph API v19",
        "GA4 API",
        "Azure OneLake",
        "Streamlit",
        "Pytest"
      ],
      "repoPath": "../case-studies/projeto-04-marketing-crm-cloud",
      "demoCommand": "python case-studies/projeto-04-marketing-crm-cloud/run_demo.py",
      "testCommand": "pytest case-studies/projeto-04-marketing-crm-cloud/tests/",
      "headlineMetrics": [],
      "context": "Os investimentos de mídia paga em dezenas de praças imobiliárias estavam fragmentados em várias plataformas externas, enquanto a atribuição de vendas e elegibilidade promocional sofriam com o atraso de compensação bancária (alguns dias úteis) e com a ausência de códigos padronizados entre campanhas de tráfego e o ERP.",
      "challenge": "Construir uma malha de ingestão serverless econômica e resiliente para o BigQuery e Azure OneLake que lidasse com janelas móveis de atribuição, paginação instável de APIs de CRM, propriedades GA4 recém-criadas com zero sessões legítimas e unificasse tudo em aplicações analíticas de resposta sub-segundo.",
      "architecture": {
        "summary": "Pipelines agendados em GitHub Actions alimentando tabelas particionadas/clusterizadas no BigQuery e Parquet no OneLake, consumidos por Data Apps Streamlit com cache sincronizado.",
        "nodes": [
          "APIs Externas (Google Ads MCC, Meta, GA4, Publya, QRFY, CRM)",
          "GitHub Actions (Cron Runners Serverless + Retry Exponencial)",
          "Staging Tables + Transactional Watermark Gate",
          "Google BigQuery (Particionamento por Data + MERGE com Janela Móvel de Lookback)",
          "taxonomia.py (@lru_cache Regex Engine: Cidade / UF / Lançamento)",
          "Streamlit Cloud & Docker Apps (Cache Sincronizado com o ETL + Menor Consumo de RAM)"
        ]
      },
      "decisions": [
        {
          "title": "Proteção Transacional da Watermark em Falhas Parciais de API",
          "detail": "Na extração incremental do CRM por MAX(DataAlteracao), se qualquer página falhar após os retries, o pipeline aborta antes do MERGE da Staging para a tabela final. Isso impede que a watermark avance com dados parciais, evitando buracos silenciosos eternos."
        },
        {
          "title": "Upsert Idempotente com Janela Móvel de Lookback e Prevenção de Dupla Contagem no Meta Ads",
          "detail": "Como redes de anúncios reatribuem conversões retroativamente, a carga extrai uma janela móvel recente e executa MERGE na chave (account_id, adset_id, date_start). Na consolidação de leads, prioriza o agregador nativo action__lead e só recorre à soma de subtipos como fallback, eliminando dupla contagem."
        },
        {
          "title": "Detector Granular de Lacunas no GA4 com Rastreio de Zero-Row",
          "detail": "Cruza todas as propriedades descobertas na Admin API contra a janela histórica no BigQuery ao nível (property_id, date) e registra explicitamente pares que retornaram zero linhas legítimas para não reconsultar a quota da API infinitamente."
        },
        {
          "title": "Motor de Taxonomia Regex com @lru_cache e Compactação de RAM",
          "detail": "Módulo determinístico com @lru_cache que extrai (cidade, uf, tipo_lancamento) de nomenclaturas livres de campanhas, combinado com conversão automática de strings de baixa cardinalidade para category no Pandas 3.0 (reduzindo o uso de RAM)."
        }
      ],
      "demoVsReal": {
        "real": "Ecossistema em produção na Brasil Terrenos / Buriti cobrindo Painel-Geral, meta_ads, ga4_extractor, gads_extractor, publya e painel_campanhas (base de contratos no OneLake + BigQuery).",
        "demo": "Pipeline completo em Python (src/marketing_pipeline.py e src/taxonomia.py) + aplicação executiva Streamlit (app/streamlit_app.py) testando proteção de watermark, MERGE lookback, prevenção de dupla contagem, taxonomia regex e compactação de memória."
      },
      "quality": "Validação de integridade transacional pré-MERGE, deduplicação determinística, cache ancorado nas janelas do ETL e suíte Pytest cobrindo cenários de falha de rede.",
      "results": "Unificação da visão executiva de CAC, ROAS e funil comercial em todas as praças com custo zero de servidores de orquestração e resgate auditado de clientes elegíveis após compensação bancária.",
      "lessons": "Em pipelines incrementais baseados em carimbo de alteração (updated_at), avançar o estado antes de confirmar a integridade de todos os lotes paginados é a principal causa de perda silenciosa de dados."
    },
    {
      "id": "projeto-05-engenharia-reversa-bi",
      "code": "CASE 05 · ENGENHARIA REVERSA & GOVERNANÇA EPISTÊMICA",
      "featured": false,
      "title": "Toolkit de Engenharia Reversa: Parser Binário QVD em NumPy Bitwise, Auditoria PBIR/TMDL e Governança Epistêmica",
      "company": "Brasil Terrenos / Buriti Empreendimentos",
      "role": "Staff Data Engineer & Governance Architect",
      "categories": [
        "Reverse Engineering & Governance",
        "Data Engineering",
        "Analytics Engineering"
      ],
      "stack": [
        "Python",
        "NumPy Bitwise",
        "PBIR / TMDL Static Analysis",
        "SQL Server Catalog Mining",
        "Obsidian Knowledge Graph",
        "Regex Anti-PII",
        "Pytest"
      ],
      "repoPath": "../case-studies/projeto-05-engenharia-reversa-bi",
      "demoCommand": "python case-studies/projeto-05-engenharia-reversa-bi/run_demo.py",
      "testCommand": "pytest case-studies/projeto-05-engenharia-reversa-bi/tests/",
      "headlineMetrics": [],
      "context": "A migração de décadas de BI legado (QlikView e dezenas de arquivos Power BI departamentais) para o Microsoft Fabric esbarrava em três bloqueios: falta de licença/ambiente QlikView para abrir grandes volumes de arquivos binários .qvd, falta de permissão VIEW DEFINITION nas views do ERP SQL Server e contradições crônicas de números entre painéis.",
      "challenge": "Extrair a lógica de negócio, o perfil estatístico e as regras de domínio diretamente dos artefatos binários (.qvd e .pbix) e dos metadados de sistema do banco de dados, documentando o conhecimento em um catálogo governado com garantia matemática contra alucinações e vazamento de PII.",
      "architecture": {
        "summary": "Três motores autorais em Python operando sobre artefatos legados para alimentar um Knowledge Graph auditado determinísticamente.",
        "nodes": [
          "Arquivos Binários .qvd + Relatórios .pbix",
          "qvd_bitstuffed_codec.py (XML Header + Symbol Table + NumPy Bitwise Unpack)",
          "pbir_dax_auditor.py (AST/Regex DAX Homônimos, Datas Inválidas e Segurança)",
          "SQL Server sys.* Miner (FKs + Decodes sem VIEW DEFINITION)",
          "Vault Markdown (Notas: Tabelas, Padrões, Métricas, Receitas)",
          "vault_epistemic_verifier.py (Validador de Lastro Numérico e Bloqueio Anti-PII)"
        ]
      },
      "decisions": [
        {
          "title": "Decodificação Vetorizada de Índices Bit-Stuffed em NumPy",
          "detail": "Arquivos .qvd armazenam valores únicos em uma Tabela de Símbolos terminada por byte nulo e comprimem as linhas em ponteiros de largura variável de bits. O parser separa o cabeçalho XML no delimitador \\r\\n\\0 e aplica shifts bitwise vetorizados em NumPy ((raw_uint >> bit_offset) & mask + bias), varrendo grandes volumes de linhas com filtro automático de colunas PII."
        },
        {
          "title": "Auditoria Estática em Lote de Modelos PBIR / TMDL",
          "detail": "Automação da conversão dos arquivos .pbix para o formato aberto PBIR/TMDL, varrendo as medidas DAX para identificar medidas com o mesmo nome mas fórmulas divergentes, literais impossíveis como DATE(2026, 9, 31) e tabelas de senhas expostas."
        },
        {
          "title": "Mineração de Domínios sem VIEW DEFINITION",
          "detail": "Com a leitura de procedures bloqueada no ERP, o extrator cruzou sys.foreign_keys (relações entre tabelas), extended_properties e mineração regex em queries legadas para catalogar os decodes de códigos numéricos."
        },
        {
          "title": "Governança Epistêmica Determinística (verifica_qlikview.py)",
          "detail": "Script de CI documental que exige tags de grau de certeza (CONFIRMADO, PROVÁVEL, HIPÓTESE), confere se cada número citado na documentação existe nos JSONs de evidência bruta e bloqueia CPFs, e-mails ou credenciais."
        }
      ],
      "demoVsReal": {
        "real": "Ferramentas em _artefatos/, Fontes/ e Vault/ que processaram os QVDs e PBIXs e geraram notas técnicas no repositório de governança.",
        "demo": "Codec binário bit-stuffed completo em NumPy (src/qvd_bitstuffed_codec.py), auditor estático PBIR/DAX (src/pbir_dax_auditor.py) e verificador epistêmico anti-PII (src/vault_epistemic_verifier.py) validados com Pytest."
      },
      "quality": "Roundtrip binário exato testado bit a bit, bloqueio determinístico de padrões sensíveis (CPF, CNPJ, senhas OLEDB) e verificação de lastro numérico.",
      "results": "Desbloqueio completo da migração do legado para o Microsoft Fabric, com descoberta prévia de conflitos de conceitos DAX e proteção de governança.",
      "lessons": "Tratar relatórios de BI e arquivos binários legados como código-fonte auditável (via parsers e análise estática) transforma migrações subjetivas em processos determinísticos de engenharia."
    },
    {
      "id": "projeto-06-maquina-estados-imobiliario",
      "code": "CASE 06 · MÁQUINA DE ESTADOS, ESTATÍSTICA & GEOESPACIAL",
      "featured": false,
      "title": "Máquina do Tempo de Estoque Imobiliário (Multi-CRM/ERP), Suavização Estatística INCC e Enriquecimento Geoespacial",
      "company": "EBM Desenvolvimento Imobiliário",
      "role": "Analytics Engineer & BI / Data Specialist",
      "categories": [
        "State Machines & Algorithms",
        "Analytics Engineering",
        "Data Engineering"
      ],
      "stack": [
        "Python",
        "Pandas",
        "NumPy",
        "Geometria Esférica / Haversine",
        "Estatística / Séries Temporais INCC",
        "Power BI",
        "Pytest"
      ],
      "repoPath": "../case-studies/projeto-06-maquina-estados-imobiliario",
      "demoCommand": "python case-studies/projeto-06-maquina-estados-imobiliario/run_demo.py",
      "testCommand": "pytest case-studies/projeto-06-maquina-estados-imobiliario/tests/",
      "headlineMetrics": [],
      "context": "Ao longo de vários anos, a incorporadora operou com múltiplos CRMs (Anapro, Microsoft Dynamics 365 e Construtor de Vendas - CV) além do ERP Sienge. Para análises de velocidade de vendas (VSO), precificação de terrenos e inteligência geográfica de compradores, era necessário reconstruir a fotografia exata do status de cada unidade imobiliária em cada mês do passado e limpar distorções severas em séries de preço/m² de mercado.",
      "challenge": "Resolver anomalias temporais onde o distrato administrativo de um contrato N era efetivado no ERP meses após a unidade já ter sido revendida em um contrato N+1 no CRM; suavizar outliers de digitação em séries de preços imobiliários sem perder a tendência inflacionária da construção civil; e plotar milhares de compradores clusterizados por CEP sem sobreposição visual de pinos nem deslocamento de bairro.",
      "architecture": {
        "summary": "Três motores algorítmicos em Python compondo a camada de inteligência comercial e territorial.",
        "nodes": [
          "Fontes Históricas (Sienge ERP + Dynamics 365 + CV CRM + Anapro + BCB OData4 INCC)",
          "state_machine_estoque.py (Reconciliação de Conflitos Cronológicos + Grade Mensal)",
          "suavizacao_estatistica_incc.py (Clusters de Área qcut + INCC defasado + Regra por Faixas)",
          "geoespacial_utils.py (Haversine + Dispersão Polar Vetorizada + Polígonos Shoelace)",
          "Camada Gold Analítica & Dashboards Executivos (Diretoria / Inteligência de Mercado)"
        ]
      },
      "decisions": [
        {
          "title": "Resolução de Conflito Temporal na Máquina do Tempo (Contrato N vs Contrato N+1)",
          "detail": "Quando Data_Cancelamento(Contrato N) > Data_Venda(Contrato N+1) na mesma unidade, uma linha do tempo ingênua sobrescreveria a nova venda como 'Distratada'. O motor detecta a inversão cronológica e trunca a vigência do contrato N para Data_Venda(N+1) - 1 dia, preservando a integridade do estoque mensal."
        },
        {
          "title": "Suavização Estatística de Preço/m² por Faixas com INCC Defasado",
          "detail": "Aplica a convenção setorial de defasagem no índice INCC, segmenta empreendimentos em clusters de metragem (qcut) e avalia o desvio perante a mediana móvel anual: desvios pequenos mantêm o valor real; desvios intermediários assumem a mediana móvel anual; desvios grandes (erros grosseiros de coleta) são reconstruídos pela curva teórica do cluster corrigida pelo INCC."
        },
        {
          "title": "Dispersão Polar Vetorizada em Anéis Concêntricos e Fórmula de Shoelace",
          "detail": "Para evitar que dezenas de clientes do mesmo CEP fiquem empilhados no mesmo ponto do mapa, o algoritmo distribui coordenadas idênticas usando trigonometria polar em anéis concêntricos (anéis de raio crescente), além de calcular distâncias reais ao estande via Haversine e áreas de terrenos via Fórmula de Gauss (Shoelace)."
        }
      ],
      "demoVsReal": {
        "real": "Scripts em produção na EBM (Novo Fechamento.py, tratamento_sintese [preco].py, Pesquisas P1..P4_V5 e kmztocsv.py) gerando bases históricas e alimentando o ecossistema de Inteligência de Mercado e Comercial.",
        "demo": "Três módulos Python independentes e vetorizados (state_machine_estoque.py, suavizacao_estatistica_incc.py e geoespacial_utils.py) com dados sintéticos e bateria completa de testes Pytest."
      },
      "quality": "Invariantes de unicidade de estado por (id_unidade, ano_mes), conservação do total físico de unidades do empreendimento em todos os meses da série e validação trigonométrica de raio máximo de dispersão.",
      "results": "Série histórica livre de distorções de duplo status por unidade, curvas de avaliação de preço/m² imunes a erros de digitação e mapas de calor comerciais de alta precisão.",
      "lessons": "Integrar múltiplos CRMs e ERPs ao longo do tempo exige modelar os dados como um log de eventos sujeito a atrasos de escrituração contábil, aplicando regras formais de precedência de negócios antes de expandir snapshots mensais."
    }
  ]
};

let portfolioProjects = FALLBACK_PORTFOLIO_DATA.projects;

// ============================================================================
// Cartões dos projetos e janela de detalhes técnicos: ver assets/js/cases.js
// ============================================================================

// ============================================================================
// 2. SIMULADOR INTERATIVO — DW FINANCEIRO (SNAPSHOTS & DIFF ENGINE)
// ============================================================================
const dwState = {
  snapshotT1Date: "2026-03-22",
  snapshotT2Date: "2026-03-29",
  dtCargaT2: "2026-03-29 22:04:12 -03:00",
  runCountT2: 1,
  t1Rows: [
    { parcela_id: "P-1001", fatia_id: "R-01", fornecedor: "FORN-801 Terraplenagem Alfa", centro_custo: "CC-401 Infraestrutura", vencimento: "2026-04-10", valor: 185000.00, status: "ABERTA" },
    { parcela_id: "P-1002", fatia_id: "R-01", fornecedor: "FORN-802 Pavimentação Beta", centro_custo: "CC-401 Infraestrutura", vencimento: "2026-04-15", valor: 92400.00, status: "ABERTA" },
    { parcela_id: "P-1003", fatia_id: "R-01", fornecedor: "FORN-803 Topografia Precisa", centro_custo: "CC-205 Projetos", vencimento: "2026-04-05", valor: 34000.00, status: "ABERTA" },
    { parcela_id: "P-1004", fatia_id: "R-01", fornecedor: "FORN-804 Saneamento Delta", centro_custo: "CC-402 Redes Água", vencimento: "2026-04-20", valor: 210000.00, status: "ABERTA" }
  ],
  t2Rows: [
    { parcela_id: "P-1001", fatia_id: "R-01", fornecedor: "FORN-801 Terraplenagem Alfa", centro_custo: "CC-401 Infraestrutura", vencimento: "2026-04-10", valor: 215500.00, status: "ABERTA" },
    { parcela_id: "P-1002", fatia_id: "R-01", fornecedor: "FORN-802 Pavimentação Beta", centro_custo: "CC-401 Infraestrutura", vencimento: "2026-05-15", valor: 92400.00, status: "ABERTA" },
    { parcela_id: "P-1003", fatia_id: "R-01", fornecedor: "FORN-803 Topografia Precisa", centro_custo: "CC-909 Urbanismo Geral", vencimento: "2026-04-05", valor: 34000.00, status: "ABERTA" },
    { parcela_id: "P-1005", fatia_id: "R-01", fornecedor: "FORN-805 Energia Solar SPE", centro_custo: "CC-403 Rede Elétrica", vencimento: "2026-04-28", valor: 68900.00, status: "ABERTA" }
  ]
};

function computeDwDiff() {
  const mapT1 = new Map(dwState.t1Rows.map(r => [`${r.parcela_id}|${r.fatia_id}`, r]));
  const mapT2 = new Map(dwState.t2Rows.map(r => [`${r.parcela_id}|${r.fatia_id}`, r]));
  const allKeys = new Set([...mapT1.keys(), ...mapT2.keys()]);
  const diffs = [];

  for (const key of allKeys) {
    const r1 = mapT1.get(key);
    const r2 = mapT2.get(key);
    if (!r1 && r2) {
      diffs.push({
        key: r2.parcela_id,
        fornecedor: r2.fornecedor,
        tipo: "INCLUIDA",
        antes: "— (Não existia em T-1)",
        depois: `R$ ${r2.valor.toLocaleString('pt-BR')} · Venc ${r2.vencimento} · ${r2.centro_custo}`
      });
    } else if (r1 && !r2) {
      diffs.push({
        key: r1.parcela_id,
        fornecedor: r1.fornecedor,
        tipo: "EXCLUIDA",
        antes: `R$ ${r1.valor.toLocaleString('pt-BR')} · Venc ${r1.vencimento}`,
        depois: "— (Removida in-place no ERP)"
      });
    } else if (r1 && r2) {
      if (r1.valor !== r2.valor) {
        diffs.push({
          key: r2.parcela_id,
          fornecedor: r2.fornecedor,
          tipo: "VALOR_ALTERADO",
          antes: `R$ ${r1.valor.toLocaleString('pt-BR')}`,
          depois: `R$ ${r2.valor.toLocaleString('pt-BR')} (Δ R$ ${(r2.valor - r1.valor).toLocaleString('pt-BR')})`
        });
      }
      if (r1.vencimento !== r2.vencimento) {
        diffs.push({
          key: r2.parcela_id,
          fornecedor: r2.fornecedor,
          tipo: "VENCIMENTO_ALTERADO",
          antes: `Venc: ${r1.vencimento}`,
          depois: `Venc: ${r2.vencimento}`
        });
      }
      if (r1.centro_custo !== r2.centro_custo) {
        diffs.push({
          key: r2.parcela_id,
          fornecedor: r2.fornecedor,
          tipo: "RECLASSIFICADA_RATEIO",
          antes: r1.centro_custo,
          depois: r2.centro_custo
        });
      }
    }
  }
  return diffs;
}

function renderDwSimulator() {
  const container = document.getElementById("simulator-Mount");
  if (!container) return;

  const diffs = computeDwDiff();
  // Cumulative suppliers in dim.fornecedor (never drops FORN-804 even though P-1004 was deleted in T2)
  const cumulativeSuppliers = new Set([
    ...dwState.t1Rows.map(r => r.fornecedor),
    ...dwState.t2Rows.map(r => r.fornecedor)
  ]);

  container.innerHTML = `
    <div class="sim-header">
      <div>
        <span class="project-code" style="color: var(--accent-emerald); background: rgba(16,185,129,0.15);">ENGINE INTERATIVO 01 · DW FINANCEIRO (CASE 03)</span>
        <h3 style="margin-top: 0.4rem;">Motor de Snapshots Semanais Idempotentes (<code>snap</code>) e Diff de Parcelas/Rateios (<code>mudanca_parcela</code>)</h3>
        <p style="font-size: 0.85rem; color: var(--text-secondary);">
          Experimente injetar mutações in-place no ERP ou reexecutar o snapshot <code>${dwState.snapshotT2Date}</code> para verificar a idempotência entre <code>data_snapshot</code> e <code>dt_carga</code>.
        </p>
      </div>
      <div style="text-align: right; font-family: var(--font-mono); font-size: 0.76rem;">
        <div>data_snapshot (Rótulo Lógico): <strong style="color: var(--accent-cyan);">${dwState.snapshotT2Date}</strong></div>
        <div>dt_carga (Extração Física BRT): <strong style="color: var(--accent-emerald);">${dwState.dtCargaT2}</strong></div>
        <div>Execuções Idempotentes T2: <strong>${dwState.runCountT2}x (Partição Única Garantida)</strong></div>
      </div>
    </div>

    <div class="sim-controls">
      <button class="btn btn-outline btn-sm" onclick="triggerIdempotentRerun()">
        ↻ Reexecutar Snapshot (${dwState.snapshotT2Date}) — Testar Idempotência
      </button>
      <button class="btn btn-outline btn-sm" onclick="mutateDwAditivo()">
        + Simular Aditivo In-Place em P-1001 (+R$ 15.000)
      </button>
      <button class="btn btn-outline btn-sm" onclick="mutateDwProrrogacao()">
        📅 Prorrogar Vencimento de P-1002
      </button>
      <button class="btn btn-outline btn-sm" onclick="resetDwSimulator()">
        ⟲ Restaurar Estado Inicial (Seed=42)
      </button>
    </div>

    <div class="sim-grid">
      <div class="sim-box">
        <div class="sim-box-title">
          <span>DELTA DETECTADO: snap.mudanca_parcela (${dwState.snapshotT1Date} → ${dwState.snapshotT2Date})</span>
          <span>${diffs.length} mutações capturadas</span>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>Parcela</th>
              <th>Tipo de Mutação</th>
              <th>Estado em T-1 (${dwState.snapshotT1Date})</th>
              <th>Estado em T (${dwState.snapshotT2Date})</th>
            </tr>
          </thead>
          <tbody>
            ${diffs.map(d => `
              <tr>
                <td><strong>${d.key}</strong><br><span style="font-size:0.68rem; color:var(--text-muted);">${d.fornecedor}</span></td>
                <td><span class="badge-diff ${d.tipo}">${d.tipo}</span></td>
                <td>${d.antes}</td>
                <td style="color: var(--text-primary); font-weight: 600;">${d.depois}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>

      <div class="sim-box">
        <div class="sim-box-title">
          <span>GOVERNANÇA DE SCHEMA & DIMENSÃO ACUMULATIVA (D-39)</span>
          <span style="color: var(--accent-emerald);">0 ÓRFÃOS</span>
        </div>
        <div style="font-size: 0.8rem; color: var(--text-secondary); display: flex; flex-direction: column; gap: 0.65rem;">
          <div style="padding: 0.65rem; background: var(--bg-card); border-radius: 6px; border: 1px solid var(--border-subtle);">
            <strong style="color: var(--accent-cyan);">1. Guarda de Contrato (sys.columns):</strong><br>
            Staging validada antes do swap atômico. <code>SELECT *</code> bloqueado por contrato explícito de colunas.
          </div>
          <div style="padding: 0.65rem; background: var(--bg-card); border-radius: 6px; border: 1px solid var(--border-subtle);">
            <strong style="color: var(--accent-emerald);">2. Dimensão Fornecedor Acumulativa (${cumulativeSuppliers.size} fornecedores):</strong><br>
            Mesmo com a parcela <code>P-1004</code> excluída in-place no ERP em T2, o fornecedor <code>FORN-804 Saneamento Delta</code> é preservado em <code>dim.fornecedor</code> para que consultas históricas em T-1 jamais gerem chave órfã.
          </div>
          <div style="padding: 0.65rem; background: var(--bg-card); border-radius: 6px; border: 1px solid var(--border-subtle);">
            <strong style="color: var(--accent-amber);">3. Proteção Anti-52x no DAX (Direct Lake):</strong><br>
            Medidas usam guarda <code>IF(HASONEVALUE(snap[data_snapshot]), ...)</code>, impedindo soma acidental de múltiplas fotos semanais.
          </div>
        </div>
      </div>
    </div>
  `;
}

function triggerIdempotentRerun() {
  dwState.runCountT2 += 1;
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  dwState.dtCargaT2 = `2026-03-29 ${hh}:${mm}:${ss} -03:00`;
  renderDwSimulator();
}

function mutateDwAditivo() {
  dwState.t2Rows[0].valor += 15000;
  renderDwSimulator();
}

function mutateDwProrrogacao() {
  dwState.t2Rows[1].vencimento = dwState.t2Rows[1].vencimento === "2026-05-15" ? "2026-06-20" : "2026-05-15";
  renderDwSimulator();
}

function resetDwSimulator() {
  dwState.runCountT2 = 1;
  dwState.dtCargaT2 = "2026-03-29 22:04:12 -03:00";
  dwState.t2Rows[0].valor = 215500.00;
  dwState.t2Rows[1].vencimento = "2026-05-15";
  renderDwSimulator();
}

// ============================================================================
// 3. SIMULADOR INTERATIVO — LAKEHOUSE RECEBÍVEIS (CASE 01) & CONCILIAÇÃO (CASE 02)
// ============================================================================
function switchSimulatorTab(tabId, btnEl) {
  document.querySelectorAll(".sim-tab").forEach(b => b.classList.remove("active"));
  if (btnEl) btnEl.classList.add("active");

  if (tabId === "dw") {
    renderDwSimulator();
  } else if (tabId === "lakehouse") {
    renderLakehouseSimulator(99.8, false);
  } else if (tabId === "conciliacao") {
    renderConciliacaoSimulator();
  }
}

function renderLakehouseSimulator(coveragePct = 99.8, isDayOneOverride = false) {
  const container = document.getElementById("simulator-Mount");
  const gatePassed = coveragePct >= 99.5 || isDayOneOverride;

  container.innerHTML = `
    <div class="sim-header">
      <div>
        <span class="project-code">ENGINE INTERATIVO 02 · LAKEHOUSE RECEBÍVEIS (CASE 01)</span>
        <h3 style="margin-top: 0.4rem;">Gate Staging-First (Cobertura ProUAU ≥ 99,5%) & Matriz de Transição Roll-Rate (M → M+1)</h3>
        <p style="font-size: 0.85rem; color: var(--text-secondary);">
          Simule o comportamento do gate transacional quando o cálculo noturno do ERP atrasa e inspecione a precedência de transição da camada Gold.
        </p>
      </div>
      <div style="text-align: right; font-family: var(--font-mono); font-size: 0.78rem;">
        <div>Cobertura Chaves Calc: <strong style="color: ${coveragePct >= 99.5 ? 'var(--accent-emerald)' : 'var(--accent-rose)'};">${coveragePct.toFixed(1)}%</strong></div>
        <div>Status Gate Bronze: <strong style="color: ${gatePassed ? 'var(--accent-emerald)' : 'var(--accent-rose)'};">${gatePassed ? 'PROMOÇÃO AUTORIZADA' : 'BLOQUEADO (PROD PRESERVADA)'}</strong></div>
      </div>
    </div>

    <div class="sim-controls">
      <button class="btn btn-outline btn-sm" onclick="renderLakehouseSimulator(99.8, false)">
        ✓ Cenário Normal: ProUAU Concluído (99,8% Cobertura)
      </button>
      <button class="btn btn-outline btn-sm" onclick="renderLakehouseSimulator(91.4, false)">
        ✕ Cenário Falha Noturna: ProUAU Incompleto (91,4% — Bloqueia Promoção)
      </button>
      <button class="btn btn-outline btn-sm" onclick="renderLakehouseSimulator(91.4, true)">
        ⚡ Cenário Dia 1 do Mês: Virada Contábil (aceitar_calc_defasada = true)
      </button>
    </div>

    <div class="sim-grid">
      <div class="sim-box">
        <div class="sim-box-title">
          <span>MATRIZ DE TRANSIÇÃO ROLL-RATE (M → M+1) · PRECEDÊNCIA DETERMINÍSTICA</span>
          <span>100% Paridade SQL × PySpark</span>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>Faixa em M (Origem)</th>
              <th>Pago (M+1)</th>
              <th>Em Aberto / Rolagem</th>
              <th>Renegociado</th>
              <th>Cedido (TipoMnt=2)</th>
              <th>Cancelado (Distrato)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>Adimplente (A Vencer)</strong></td>
              <td style="color: var(--accent-emerald);">84,2%</td>
              <td>11,5% (→ 1-30d)</td>
              <td>1,8%</td>
              <td style="color: var(--accent-cyan);">1,9% (Isolado)</td>
              <td>0,6%</td>
            </tr>
            <tr>
              <td><strong>Atraso 1 a 30 dias</strong></td>
              <td style="color: var(--accent-emerald);">58,4%</td>
              <td>31,0% (→ 31-60d)</td>
              <td>7,4%</td>
              <td style="color: var(--accent-cyan);">2,1% (Isolado)</td>
              <td>1,1%</td>
            </tr>
            <tr>
              <td><strong>Atraso 31 a 90 dias</strong></td>
              <td style="color: var(--accent-emerald);">29,1%</td>
              <td>48,2% (→ 91-180d)</td>
              <td>16,5%</td>
              <td style="color: var(--accent-cyan);">3,0% (Isolado)</td>
              <td>3,2%</td>
            </tr>
            <tr>
              <td><strong>Atraso > 180 dias</strong></td>
              <td style="color: var(--accent-emerald);">9,4%</td>
              <td>62,1% (→ >180d)</td>
              <td>14,2%</td>
              <td style="color: var(--accent-cyan);">1,8% (Isolado)</td>
              <td>12,5%</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="sim-box">
        <div class="sim-box-title">
          <span>AUDITORIA DO CONTROLE TRANSACIONAL (wh_ctl_inad)</span>
        </div>
        <div style="font-size: 0.8rem; color: var(--text-secondary); display: flex; flex-direction: column; gap: 0.65rem;">
          <div style="padding: 0.65rem; background: var(--bg-card); border-radius: 6px; border: 1px solid var(--border-subtle);">
            <strong>Decisão do Gate:</strong> ${gatePassed
              ? (isDayOneOverride
                  ? '<span style="color:var(--accent-amber);">Promoção permitida via flag de Dia 1 (aceitar_calc_defasada=true) para garantir a Foto Crua Mensal da virada com alerta registrado em ctl_rodada.</span>'
                  : '<span style="color:var(--accent-emerald);">Cobertura de chaves entre ContasReceber e ContasReceberCalc atingiu 99,8% (≥ 99,5%). Tabelas stg_* promovidas para bronze_*.</span>')
              : '<span style="color:var(--accent-rose);">ABORTADO! Cobertura de 91,4% abaixo do limiar de 99,5%. As tabelas bronze_* da rodada anterior foram preservadas intactas e o Direct Lake não sofreu corrupção.</span>'}
          </div>
          <div style="padding: 0.65rem; background: var(--bg-card); border-radius: 6px; border: 1px solid var(--border-subtle);">
            <strong>Isolamento de Cessões (TipoMnt = 2):</strong> Contratos cedidos entre SPEs ou carteiras têm status final técnico no ERP, mas a precedência <code>cedido > cancelado</code> impede que inflem a taxa de distrato comercial.
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderConciliacaoSimulator() {
  const container = document.getElementById("simulator-Mount");
  container.innerHTML = `
    <div class="sim-header">
      <div>
        <span class="project-code">ENGINE INTERATIVO 03 · CONCILIAÇÃO BANCÁRIA (CASE 02)</span>
        <h3 style="margin-top: 0.4rem;">Expurgo Seletivo de Pares Transitórios (Regra R3: Tipo 5/6) & Detecção de Validação In-Place</h3>
        <p style="font-size: 0.85rem; color: var(--text-secondary);">
          Veja como o algoritmo diferencia lançamentos transitórios casados por proposta de casos unilaterais reais e descobre atrasos ocultos no Snapshot 1.
        </p>
      </div>
      <div style="text-align: right; font-family: var(--font-mono); font-size: 0.78rem;">
        <div>Equação 5 Pernas: <strong style="color: var(--accent-emerald);">SF = SI + C - D (100% Paridade)</strong></div>
        <div>Fechamento Semanal: <strong style="color: var(--accent-cyan);">26 dias → 3 dias</strong></div>
      </div>
    </div>

    <div class="sim-grid">
      <div class="sim-box">
        <div class="sim-box-title">
          <span>AUDITORIA DE LANÇAMENTOS TRANSITÓRIOS (NATUREZA '0071')</span>
          <span>Preservação de Unilaterais</span>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>Proposta / Conta</th>
              <th>TipoControle</th>
              <th>Valor</th>
              <th>Decisão do Motor (Regra R3)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>PROP-901 · Conta 4410-X</td>
              <td>Tipo 5 (Entrada) + Tipo 6 (Saída)</td>
              <td>+R$ 4.200 / -R$ 4.200</td>
              <td><span class="badge-diff INCLUIDA">PAR CASADO EXPURGADO (Ruído Zero)</span></td>
            </tr>
            <tr>
              <td>PROP-902 · Conta 4410-X</td>
              <td>Tipo 5 (Entrada) + Tipo 6 (Saída)</td>
              <td>+R$ 8.950 / -R$ 8.950</td>
              <td><span class="badge-diff INCLUIDA">PAR CASADO EXPURGADO (Ruído Zero)</span></td>
            </tr>
            <tr>
              <td>PROP-908 · Conta 4410-X</td>
              <td>Apenas Tipo 5 (Sem Par Tipo 6)</td>
              <td>+R$ 3.150,00</td>
              <td><span class="badge-diff EXCLUIDA">UNILATERAL PRESERVADO P/ AUDITORIA</span></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="sim-box">
        <div class="sim-box-title">
          <span>DETECÇÃO DE ANOMALIA: VALIDAÇÃO MANUAL IN-PLACE NO SNAPSHOT 1</span>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>Lançamento</th>
              <th>Status no Snapshot 1</th>
              <th>Cálculo Ingênuo</th>
              <th>Motor Real (MAX(dt_val) - MIN(dt_criacao))</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>LANC-7741</td>
              <td>Status_exa = 2 (Já Validado)</td>
              <td>0 dias (Falso Imediato)</td>
              <td><span class="badge-diff VALOR_ALTERADO">12 dias reais (validado_in_place = true)</span></td>
            </tr>
            <tr>
              <td>LANC-7749</td>
              <td>Status_exa = 0 → Snap 4 = 2</td>
              <td>9 dias (Multi-Snapshot)</td>
              <td><span class="badge-diff VENCIMENTO_ALTERADO">9 dias (Transição Normal Snap 1 → 4)</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `;
}

// ============================================================================
// 4. TEMA E INICIALIZAÇÃO
// ============================================================================
function toggleTheme() {
  const root = document.documentElement;
  const current = root.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  root.setAttribute("data-theme", next);
  const btn = document.getElementById("theme-toggle-btn");
  if (btn) {
    const icon = btn.querySelector(".theme-icon");
    const text = btn.querySelector(".theme-text");
    if (icon) icon.textContent = next === "dark" ? "☀" : "☾";
    if (text) text.textContent = next === "dark" ? " Modo claro" : " Modo escuro";
  }
}

function copyContact(value, label) {
  navigator.clipboard.writeText(value).then(() => {
    const toast = document.getElementById("copy-toast");
    if (toast) {
      toast.textContent = `${label} copiado para a área de transferência!`;
      toast.style.display = "inline-block";
      setTimeout(() => { toast.style.display = "none"; }, 2800);
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  // Attempt to load external JSON, falling back cleanly if opened via file://
  fetch("assets/data/projects.json")
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (data && data.projects) {
        portfolioProjects = data.projects;
      }
      renderProjects("ALL");
      renderDwSimulator();
    })
    .catch(() => {
      renderProjects("ALL");
      renderDwSimulator();
    });

  // Close modal on backdrop click or Escape
  const modal = document.getElementById("project-modal");
  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) closeProjectModal();
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeProjectModal();
  });
});
