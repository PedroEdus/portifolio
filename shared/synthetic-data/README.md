# Gerador Unificado de Dados Sintéticos (`shared/synthetic-data`)

> [!IMPORTANT]
> **AVISO DE CONFIDENCIALIDADE E SIGILO CORPORATIVO**  
> Todos os conjuntos de dados, códigos de empresas (SPEs), números de contratos, contas bancárias, valores financeiros, lançamentos contábeis e campanhas gerados por este módulo são **100% sintéticos e determinísticos** (`numpy.random.default_rng(42)`).  
> Nenhuma informação real de clientes, parceiros ou instituições financeiras foi utilizada ou exposta. Este gerador existe exclusivamente para preservar o sigilo corporativo e permitir a **reprodutibilidade integral dos algoritmos e métodos de engenharia de dados** demonstrados neste portfólio.

---

## Objetivo

Fornecer massas de dados sintéticas realistas, determinísticas e com casos de borda controlados (*edge cases*) para validar pipelines de engenharia de dados, motores de reconciliação contábil e suítes de testes automatizados (`pytest`).

## Entidades Sintéticas Geradas

1. **Catálogo de SPEs (`spes.json` / `spes.csv`)**:
   - Empreendimentos imobiliários fictícios (`SPE-101 Horizonte`, `SPE-102 Parque das Águas`, `SPE-103 Reserva do Sol`, `SPE-104 Jardim Imperial`, `SPE-105 Vila Verde`).
2. **Recebíveis e Histórico de Snapshots (`recebiveis_*.csv` / `recebiveis_sample.json`)**:
   - Tabelas espelho sintéticas de `ContasReceber`, `ContasReceberCalc`, `Cessoes` (`TipoMnt = 2`) e `Distratos` para múltiplas datas de foto (`2026-01-01`, `2026-02-01`, `2026-03-01`).
   - Inclui parcelas contratuais vs. prorrogadas, custas (`tipo_parcela = '1'`), cadeias de cessão de direitos, distratos reais e transições completas entre faixas de atraso para cálculo da **Matriz Roll-Rate ($M \to M+1$)** e **Coorte de Sobrevivência de Renegociações**.
3. **Conciliação Bancária e Razão ERP de 5 Pernas (`conciliacao_*.csv` / `conciliacao_sample.json`)**:
   - Contas bancárias fictícias (Contas Correntes operacionais e Contas de Aplicação Financeira).
   - Movimentações das 5 pernas do razão ERP (`Extrato`, `RecebePgto`, `Depositos`, `EntSaiEmpAplic`, `VwTransfBcoExtrato`) confrontadas com o extrato bancário oficial (`SF = SI + C - D`).
   - Casos sintéticos da regra `R3`: pares casados de intermediação transitória `(TipoControle = 5, TipoControle = 6)` na natureza `'0071'` e lançamentos unilaterais órfãos que devem ser preservados.
   - Histórico de snapshots de conciliação (`Num_exa = 1..N`) incluindo a anomalia de sobrescrita *in-place* (`Status_exa = 2` já no `Num_exa = 1` com `data_validacao > data_criacao`).
4. **Campanhas Digitais e Captação (`campanhas.csv` / `campanhas.json`)**:
   - Séries temporais sintéticas de mídia paga, leads e conversões por empreendimento.

## Como Executar

```bash
python shared/synthetic-data/generate_all.py
```

Os arquivos gerados são salvos automaticamente em `shared/synthetic-data/output/`.
