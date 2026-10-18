# Portfolio Workspace — Engenharia de Dados, Analytics Engineering & BI

Este repositório contém as demonstrações públicas executáveis (com dados 100% sintéticos) e o site do portfólio técnico de **Pedro Eduardo Carneiro Moura**.

---

## Estrutura do Repositório

```text
portifolio/
├── shared/
│   └── synthetic-data/                   # Geradores determinísticos de dados sintéticos (seed=42)
├── case-studies/
│   ├── projeto-01-lakehouse-recebiveis/          # Arquitetura Medallion, Gate Transacional, Roll-Rate & Paridade
│   ├── projeto-02-conciliacao-bancaria/          # Recálculo de 5 Pernas, Expurgo Intermediação, Ciclo & FEBRABAN
│   ├── projeto-03-dw-snapshots-diff/             # Historização de ERP Mutável & Diff Engine por Parcela/Rateio
│   ├── projeto-04-marketing-crm-cloud/           # Ingestão Multi-API, Watermark/MERGE, Taxonomia & Data App
│   ├── projeto-05-engenharia-reversa-bi/         # Parser Binário QVD (NumPy), Auditoria DAX/PBIR & Scanner PII
│   └── projeto-06-maquina-estados-imobiliario/   # Fotografia Mensal Multi-CRM/ERP, INCC Cluster & Geoespacial
├── portfolio-site/                       # Interface web técnica responsiva publicada via GitHub Pages
├── verify_portfolio.py                   # Verificador unificado (testes dos 6 cases + varredura anti-segredos)
└── README.md
```

---

## Princípios de Engenharia e Segurança Adotados

1. **Somente-Leitura sobre as Fontes Reais:** Nenhum arquivo dos sistemas e repositórios corporativos de origem foi copiado, modificado, movido ou exposto; todo o código aqui é uma reconstrução original.
2. **Separação Visível entre Produção Real e Demonstração Reconstruída:** Cada estudo de caso documenta a arquitetura real em produção (Microsoft Fabric, BigQuery, SQL Server, PySpark, Direct Lake, PBIR) e fornece uma implementação pública original e 100% executável localmente sobre dados sintéticos.
3. **Zero Vazamento de Propriedade Intelectual ou PII:** Todos os dados de demonstração são gerados sinteticamente (`seed=42`) e validados por scanner determinístico anti-PII.
