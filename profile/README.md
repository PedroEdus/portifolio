<p align="center">
  <img src="./Do%20Dado%20Bruto%20%C3%A0%20Decis%C3%A3o.png" alt="Pedro Eduardo C. Moura — Analytics Engineering e Data Engineering" width="100%" />
</p>

# Pedro Eduardo
### Engenharia de Dados · Analytics Engineering · Data Platforms

Desenvolvo soluções de dados que conectam sistemas operacionais a ambientes analíticos. Trabalho com integração de APIs e ERPs, construção de pipelines ETL/ELT, modelagem e disponibilização de dados para diferentes áreas do negócio.

Minha trajetória começou em Business Intelligence e evoluiu para a engenharia por trás dos produtos analíticos: entender as fontes, estruturar a ingestão, definir granularidade e chaves, construir transformações confiáveis e preparar os dados para consumo.

[Portfólio ↗](https://pedroedus.github.io/portifolio/) · [Repositórios ↗](https://github.com/PedroEdus?tab=repositories)

---

## Áreas em que atuo

| Engenharia de dados | Analytics Engineering | Produtos de dados |
| :--- | :--- | :--- |
| Integração de APIs e ERPs, pipelines em Python e automação de cargas. | Modelagem analítica, SQL, regras de negócio, qualidade e organização em camadas. | Preparação de dados para dashboards, aplicações e indicadores usados por equipes de negócio. |

Gosto especialmente dos problemas que não são resolvidos apenas com um dashboard: descobrir como sistemas se relacionam, identificar chaves e granularidade, corrigir inconsistências e tornar cargas incrementais e reprocessamentos previsíveis.

## Projetos em destaque

### 01 — Plataforma de dados para Marketing Analytics
**Integração multiorigem · Pipelines ETL/ELT · Automação**

Integração de dados de **Meta Ads, Google Ads, GA4 e Publya** para centralizar informações de aquisição e desempenho de marketing em um ambiente analítico.

**Desafios e implementação**
- Integração com APIs de diferentes estruturas, autenticações e granularidades.
- Desenvolvimento de extrações e transformações em **Python**.
- Armazenamento e consolidação dos dados no **BigQuery**.
- Estratégias de carga incremental, recuperação de períodos e tratamento de duplicidades.
- Agendamento de rotinas por **GitHub Actions** e disponibilização dos dados para aplicações em **Streamlit**.

**Stack:** Python · APIs REST · BigQuery · SQL · GitHub Actions · Streamlit

**Implementações relacionadas:** [Extração Meta Ads ↗](https://github.com/PedroEdus/meta_ads) · [Aplicação analítica ↗](https://github.com/PedroEdus/Painel-Geral)

---

### 02 — Engenharia de dados para Conciliação Financeira
**Investigação de fontes · Relacionamento de dados · Regras de negócio**

Trabalho de descoberta e estruturação das fontes de um **ERP corporativo** para apoiar uma solução analítica de conciliação financeira, voltada à identificação de contas e movimentos que exigem atenção dos analistas.

**Desafios e trabalho realizado**
- Inspeção de tabelas do ERP para compreender a origem e o significado dos registros.
- Investigação de chaves, relacionamentos e diferentes granularidades.
- Mapeamento de vínculos entre movimentações financeiras e regras de expurgo.
- Tradução das descobertas em requisitos para a consolidação e a futura modelagem analítica.

**Competências:** SQL · Data Discovery · Modelagem de Dados · Qualidade de Dados · Análise de Regras de Negócio

*Estudo de caso em documentação. A investigação técnica não deve ser confundida com um pipeline de produção concluído.*

---

### 03 — Arquitetura de dados para Análise de Inadimplência
**Microsoft Fabric · Lakehouse · Modelagem histórica**

Estruturação de uma solução de dados para análise de inadimplência a partir de informações do **ERP UAU**, com foco na confiabilidade das fontes, na evolução histórica dos indicadores e na preparação de uma base consistente para consumo analítico.

**Desafios e abordagem técnica**
- Descoberta e validação das fontes operacionais e de suas regras de negócio.
- Definição de granularidade, identificadores e relacionamentos entre entidades.
- Planejamento da organização dos dados em camadas **Bronze, Silver e Gold**.
- Estruturação de estratégias de historização e snapshots para análises temporais.
- Modelagem da camada de consumo para indicadores e relatórios no **Power BI**.

**Stack e arquitetura:** Microsoft Fabric · Data Pipelines · Lakehouse · SQL · Power BI

*Projeto em evolução. Os itens acima descrevem o trabalho de arquitetura e estruturação, não uma alegação de implantação integral em produção.*

---

## Stack técnica

**Ingestão e orquestração**  
Python · pandas · APIs REST · GitHub Actions · Microsoft Fabric Data Pipelines

**Armazenamento e processamento**  
BigQuery · Microsoft Fabric · Lakehouse · SQL Server · SQL

**Modelagem e confiabilidade**  
ETL/ELT · Modelagem dimensional · Cargas incrementais · Deduplicação · MERGE/UPSERT · Snapshots · Arquitetura Bronze/Silver/Gold

**Consumo analítico e desenvolvimento**  
Power BI · DAX · Streamlit · Git

## Como abordo um problema de dados

1. **Investigo a origem:** sistemas, tabelas, APIs, significado dos campos e restrições.
2. **Defino o contrato analítico:** granularidade, chaves, relacionamentos, regras de negócio e critérios de qualidade.
3. **Estruturo o fluxo:** extração, armazenamento, transformações, atualização e possibilidades de reprocessamento.
4. **Preparo o consumo:** modelos e camadas que simplificam o uso dos dados pelas equipes.
5. **Documento as decisões:** o que foi implementado, as limitações encontradas e o que ainda precisa evoluir.

---

**Engenharia de Dados, para mim, é construir uma base confiável entre a origem da informação e a decisão que depende dela.**

> **Sobre os cases:** projetos corporativos são apresentados em nível de arquitetura e experiência profissional. Implementações públicas devem usar código autorizado ou reconstruções independentes com dados sintéticos.
