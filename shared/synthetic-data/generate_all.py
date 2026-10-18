"""
Gerador Unificado de Dados Sintéticos Determinísticos (seed=42).

AVISO DE CONFIDENCIALIDADE:
Todos os dados gerados por este módulo (empresas/SPEs, contratos, contas bancárias,
valores financeiros, lançamentos contábeis e campanhas) são 100% sintéticos.
Nenhum dado real corporativo ou de clientes é utilizado. O objetivo exclusivo é
demonstrar e validar os métodos de engenharia de dados com reprodutibilidade.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

DEFAULT_SEED = 42
CONFIDENTIALITY_NOTICE = (
    "CONFIDENTIALITY NOTICE: 100% synthetic data generated with numpy.random.default_rng(42). "
    "No real corporate, financial, or customer data is used or exposed."
)


def generate_spe_catalog(seed: int = DEFAULT_SEED) -> pd.DataFrame:
    """Gera catálogo sintético de SPEs (Sociedades de Propósito Específico)."""
    _ = np.random.default_rng(seed)
    spes = [
        {
            "cod_empresa": 101,
            "nome_spe": "SPE-101 Horizonte",
            "uf": "GO",
            "cidade": "Goiânia",
            "total_lotes": 850,
            "status_empreendimento": "Em Carteira Ativa",
        },
        {
            "cod_empresa": 102,
            "nome_spe": "SPE-102 Parque das Águas",
            "uf": "TO",
            "cidade": "Palmas",
            "total_lotes": 1200,
            "status_empreendimento": "Em Carteira Ativa",
        },
        {
            "cod_empresa": 103,
            "nome_spe": "SPE-103 Reserva do Sol",
            "uf": "PA",
            "cidade": "Marabá",
            "total_lotes": 640,
            "status_empreendimento": "Em Carteira Ativa",
        },
        {
            "cod_empresa": 104,
            "nome_spe": "SPE-104 Jardim Imperial",
            "uf": "MG",
            "cidade": "Uberlândia",
            "total_lotes": 920,
            "status_empreendimento": "Em Carteira Ativa",
        },
        {
            "cod_empresa": 105,
            "nome_spe": "SPE-105 Vila Verde",
            "uf": "BA",
            "cidade": "Barreiras",
            "total_lotes": 510,
            "status_empreendimento": "Em Lançamento",
        },
    ]
    return pd.DataFrame(spes)


def generate_receivables_dataset(seed: int = DEFAULT_SEED) -> Dict[str, pd.DataFrame]:
    """
    Gera conjunto de dados sintéticos para a Plataforma Lakehouse de Recebíveis (Projeto 01).

    Inclui:
    - ContasReceber (M e M+1) com datas de vencimento original vs atual (prorrogada),
      parcelas normais ('0') e custas ('1'), status de pagamento, renegociação, cancelamento e cessão.
    - ContasReceberCalc (cálculo reajustado com cobertura controlada >= 99.5% em operação normal).
    - Cessoes (TipoMnt = 2) para testar isolamento de distratos vs transferências de titularidade.
    - Distratos (rescisões contratuais reais vs registros gerados por cessão).
    - Coortes de Renegociação (acompanhamento de sobrevivência por safra).
    """
    rng = np.random.default_rng(seed)
    spes = [101, 102, 103, 104]

    contas_receber_rows: List[Dict[str, Any]] = []
    contas_receber_calc_rows: List[Dict[str, Any]] = []
    cessoes_rows: List[Dict[str, Any]] = []
    distratos_rows: List[Dict[str, Any]] = []

    # Snapshots mensais: M = 2026-01-01 e M+1 = 2026-02-01
    data_foto_m = "2026-01-01"
    data_foto_m1 = "2026-02-01"

    num_parcelas = 240
    for idx in range(1, num_parcelas + 1):
        cod_empresa = int(spes[idx % len(spes)])
        cod_obra = f"OBR-{cod_empresa}"
        num_venda = 10000 + (idx // 2)
        num_parcela = (idx % 12) + 1
        chave_parcela = f"{cod_empresa}-{cod_obra}-{num_venda}-{num_parcela}"

        # Define tipo de parcela: 10% são custas ('1'), 90% são parcelas contratuais ('0')
        tipo_parcela = "1" if idx % 10 == 0 else "0"

        # Definindo faixas de vencimento no mês M (referência 2026-01-01)
        bucket_selector = idx % 6
        if bucket_selector == 0:
            # A vencer
            dias_atraso_orig_m = -int(rng.integers(5, 60))
        elif bucket_selector == 1:
            # 1-30 dias
            dias_atraso_orig_m = int(rng.integers(1, 30))
        elif bucket_selector == 2:
            # 31-60 dias
            dias_atraso_orig_m = int(rng.integers(31, 60))
        elif bucket_selector == 3:
            # 61-90 dias
            dias_atraso_orig_m = int(rng.integers(61, 90))
        elif bucket_selector == 4:
            # 91-180 dias
            dias_atraso_orig_m = int(rng.integers(91, 180))
        else:
            # >180 dias
            dias_atraso_orig_m = int(rng.integers(181, 360))

        dt_ref_m = date(2026, 1, 1)
        dt_ref_m1 = date(2026, 2, 1)
        dt_venc_original = dt_ref_m - timedelta(days=dias_atraso_orig_m)

        # Em 15% dos casos em atraso, houve prorrogação administrativa do vencimento atual
        prorrogado = (dias_atraso_orig_m > 30) and (idx % 7 == 0)
        dt_venc_atual_m = (
            dt_ref_m + timedelta(days=25) if prorrogado else dt_venc_original
        )

        valor_nominal = round(float(rng.uniform(650.0, 4200.0)), 2)
        valor_corrigido_m = round(
            valor_nominal * (1.0 + max(0, dias_atraso_orig_m) * 0.0008), 2
        )

        # Registro no snapshot M (todos começam em_aberto para compor a base de transição M -> M+1)
        contas_receber_rows.append(
            {
                "DataFoto": data_foto_m,
                "Empresa_prc": cod_empresa,
                "Obra_prc": cod_obra,
                "NumVend_prc": num_venda,
                "NumParc_prc": num_parcela,
                "ChaveParcela": chave_parcela,
                "TipoParc_prc": tipo_parcela,
                "DtVencOrig_prc": dt_venc_original.isoformat(),
                "DtVencAtu_prc": dt_venc_atual_m.isoformat(),
                "ValorNom_prc": valor_nominal,
                "Status_prc": "EM_ABERTO",
                "DataBaixa_prc": None,
                "FlagReneg_prc": 0,
                "FlagCancel_prc": 0,
                "SafraReneg": f"2025-Q{(idx % 4) + 1}" if idx % 5 == 0 else None,
            }
        )
        contas_receber_calc_rows.append(
            {
                "DataFoto": data_foto_m,
                "ChaveParcela": chave_parcela,
                "Empresa_crc": cod_empresa,
                "Obra_crc": cod_obra,
                "NumVend_crc": num_venda,
                "NumParc_crc": num_parcela,
                "VlrPrincipal_crc": valor_nominal,
                "VlrJuros_crc": round(valor_corrigido_m - valor_nominal, 2),
                "VlrTotalCalc_crc": valor_corrigido_m,
                "DtCalculo_crc": data_foto_m,
            }
        )

        # Determina o destino da parcela em M+1 (2026-02-01)
        # Precedência de estados exigida: cedido > cancelado > renegociado > pago > em_aberto
        transition_mod = idx % 20
        if transition_mod == 0:
            # Cedido (e também marcado como cancelado no legado para testar precedência cedido > cancelado!)
            status_m1 = "CANCELADO"
            flag_cancel_m1 = 1
            flag_reneg_m1 = 0
            dt_baixa_m1 = "2026-01-18"
            cessoes_rows.append(
                {
                    "Empresa_mnt": cod_empresa,
                    "Obra_mnt": cod_obra,
                    "NumVendOrig_mnt": num_venda,
                    "NumVendNovo_mnt": num_venda + 50000,
                    "TipoMnt": 2,  # 2 = Cessão de Direitos
                    "DataCessao": "2026-01-18",
                    "ChaveParcela": chave_parcela,
                }
            )
            # Registro na tabela de distratos bruta que deve ser expurgado por ser TipoMnt=2
            distratos_rows.append(
                {
                    "Empresa_dis": cod_empresa,
                    "Obra_dis": cod_obra,
                    "NumVend_dis": num_venda,
                    "DataDistrato": "2026-01-18",
                    "Motivo_dis": "Baixa por transferencia/cessao",
                    "ValorDistratado": valor_corrigido_m,
                }
            )
        elif transition_mod == 1:
            # Cancelado / Distrato real (sem cessão)
            status_m1 = "CANCELADO"
            flag_cancel_m1 = 1
            flag_reneg_m1 = 0
            dt_baixa_m1 = "2026-01-22"
            distratos_rows.append(
                {
                    "Empresa_dis": cod_empresa,
                    "Obra_dis": cod_obra,
                    "NumVend_dis": num_venda,
                    "DataDistrato": "2026-01-22",
                    "Motivo_dis": "Rescisao Contratual Inadimplencia",
                    "ValorDistratado": valor_corrigido_m,
                }
            )
        elif transition_mod in (2, 3):
            # Renegociado
            status_m1 = "RENEGOCIADO"
            flag_cancel_m1 = 0
            flag_reneg_m1 = 1
            dt_baixa_m1 = "2026-01-25"
        elif transition_mod in (4, 5, 6, 7, 8):
            # Pago no mês
            status_m1 = "PAGO"
            flag_cancel_m1 = 0
            flag_reneg_m1 = 0
            dt_baixa_m1 = "2026-01-15"
        else:
            # Permanece em aberto (rola para a próxima faixa de atraso em M+1)
            status_m1 = "EM_ABERTO"
            flag_cancel_m1 = 0
            flag_reneg_m1 = 0
            dt_baixa_m1 = None

        dias_atraso_orig_m1 = (dt_ref_m1 - dt_venc_original).days
        valor_corrigido_m1 = (
            0.0
            if status_m1 in ("PAGO", "CANCELADO", "RENEGOCIADO")
            else round(valor_nominal * (1.0 + max(0, dias_atraso_orig_m1) * 0.0008), 2)
        )

        contas_receber_rows.append(
            {
                "DataFoto": data_foto_m1,
                "Empresa_prc": cod_empresa,
                "Obra_prc": cod_obra,
                "NumVend_prc": num_venda,
                "NumParc_prc": num_parcela,
                "ChaveParcela": chave_parcela,
                "TipoParc_prc": tipo_parcela,
                "DtVencOrig_prc": dt_venc_original.isoformat(),
                "DtVencAtu_prc": dt_venc_atual_m.isoformat(),
                "ValorNom_prc": valor_nominal,
                "Status_prc": status_m1,
                "DataBaixa_prc": dt_baixa_m1,
                "FlagReneg_prc": flag_reneg_m1,
                "FlagCancel_prc": flag_cancel_m1,
                "SafraReneg": f"2025-Q{(idx % 4) + 1}" if idx % 5 == 0 else None,
            }
        )
        contas_receber_calc_rows.append(
            {
                "DataFoto": data_foto_m1,
                "ChaveParcela": chave_parcela,
                "Empresa_crc": cod_empresa,
                "Obra_crc": cod_obra,
                "NumVend_crc": num_venda,
                "NumParc_crc": num_parcela,
                "VlrPrincipal_crc": valor_nominal,
                "VlrJuros_crc": round(max(0.0, valor_corrigido_m1 - valor_nominal), 2),
                "VlrTotalCalc_crc": valor_corrigido_m1,
                "DtCalculo_crc": data_foto_m1,
            }
        )

    return {
        "contas_receber": pd.DataFrame(contas_receber_rows),
        "contas_receber_calc": pd.DataFrame(contas_receber_calc_rows),
        "cessoes": pd.DataFrame(cessoes_rows),
        "distratos": pd.DataFrame(distratos_rows),
    }


def generate_reconciliation_dataset(seed: int = DEFAULT_SEED) -> Dict[str, pd.DataFrame]:
    """
    Gera conjunto de dados sintéticos para o Motor de Conciliação Bancária (Projeto 02).

    Inclui:
    - Catalogo de Contas Bancárias (Contas Correntes vs Contas de Aplicação).
    - As 5 pernas do razão ERP (`Extrato`, `RecebePgto`, `Depositos`, `EntSaiEmpAplic`, `VwTransfBcoExtrato`).
    - Pares transitórios de intermediação casados `(TipoControle=5, TipoControle=6)` na natureza `'0071'`
      e lançamento unilateral órfão na natureza `'0071'` que deve ser preservado.
    - Extrato bancário oficial com equação de saldo `SF = SI + C - D` 100% consistente após expurgo R3.
    - Histórico de snapshots `Num_exa 1..N` incluindo conciliação padrão, pendências abertas e
      a anomalia de `validacao_in_place` (`Status_exa = 2` já no `Num_exa = 1` com `data_validacao > data_criacao`).
    """
    rng = np.random.default_rng(seed)

    contas = [
        {
            "cod_empresa": 101,
            "nome_spe": "SPE-101 Horizonte",
            "cod_banco": 341,
            "conta_bancaria": "CC-101-001",
            "tipo_conta": "CONTA_CORRENTE",
            "saldo_inicial_base": 150000.00,
        },
        {
            "cod_empresa": 102,
            "nome_spe": "SPE-102 Parque das Águas",
            "cod_banco": 1,
            "conta_bancaria": "CC-102-001",
            "tipo_conta": "CONTA_CORRENTE",
            "saldo_inicial_base": 280000.00,
        },
        {
            "cod_empresa": 103,
            "nome_spe": "SPE-103 Reserva do Sol",
            "cod_banco": 237,
            "conta_bancaria": "CC-103-001",
            "tipo_conta": "CONTA_CORRENTE",
            "saldo_inicial_base": 95000.00,
        },
        {
            "cod_empresa": 101,
            "nome_spe": "SPE-101 Horizonte",
            "cod_banco": 341,
            "conta_bancaria": "CDB-101-999",
            "tipo_conta": "CONTA_APLICACAO",
            "saldo_inicial_base": 1250000.00,
        },
    ]
    df_contas = pd.DataFrame(contas)

    # Datas de simulação em Abril/2026 (inclui Sexta-Feira Santa 2026-04-03 e Tiradentes 2026-04-21)
    start_dt = date(2026, 4, 1)
    days_count = 15

    leg_extrato: List[Dict[str, Any]] = []
    leg_recebepgto: List[Dict[str, Any]] = []
    leg_depositos: List[Dict[str, Any]] = []
    leg_entsai_aplic: List[Dict[str, Any]] = []
    leg_transf: List[Dict[str, Any]] = []
    extrato_oficial: List[Dict[str, Any]] = []

    lanc_id = 1000
    for c in contas:
        emp = c["cod_empresa"]
        bco = c["cod_banco"]
        cta = c["conta_bancaria"]
        saldo_corrente = float(c["saldo_inicial_base"])

        for d_idx in range(days_count):
            dt_mov = start_dt + timedelta(days=d_idx)
            # Pular finais de semana e feriados nacionais de Abril/2026 (2026-04-03 é Sexta-Feira Santa)
            if dt_mov.weekday() >= 5 or dt_mov == date(2026, 4, 3):
                continue

            dt_str = dt_mov.isoformat()
            saldo_ini_dia = round(saldo_corrente, 2)

            # 1. Perna Extrato (Tarifas e lançamentos diretos)
            vlr_tarifa = round(float(rng.uniform(45.0, 180.0)), 2)
            lanc_id += 1
            leg_extrato.append(
                {
                    "id_lancamento": f"EXT-{lanc_id}",
                    "cod_empresa": emp,
                    "cod_banco": bco,
                    "conta_bancaria": cta,
                    "data_movimento": dt_str,
                    "natureza": "0102",
                    "tipo_controle": 1,
                    "proposta": None,
                    "natureza_dc": "D",
                    "valor": vlr_tarifa,
                    "origem_perna": "Extrato",
                }
            )

            # 2. Perna RecebePgto (Recebimentos de boletos/PIX e pagamentos de fornecedores)
            vlr_rec = round(float(rng.uniform(2500.0, 12000.0)), 2)
            lanc_id += 1
            leg_recebepgto.append(
                {
                    "id_lancamento": f"REC-{lanc_id}",
                    "cod_empresa": emp,
                    "cod_banco": bco,
                    "conta_bancaria": cta,
                    "data_movimento": dt_str,
                    "natureza": "0010",
                    "tipo_controle": 2,
                    "proposta": f"PROP-{emp}-{d_idx}A",
                    "natureza_dc": "C",
                    "valor": vlr_rec,
                    "origem_perna": "RecebePgto",
                }
            )

            # Inserir pares transitórios de intermediação (Regra R3: natureza '0071', TipoControle 5 e 6)
            # Esses pares somam Crédito e Débito artificiais no ERP, mas NÃO existem no extrato bancário real!
            vlr_intermed = round(float(rng.uniform(1500.0, 4000.0)), 2)
            proposta_casada = f"PROP-INT-{emp}-{d_idx}"
            lanc_id += 1
            leg_recebepgto.append(
                {
                    "id_lancamento": f"R3C-{lanc_id}",
                    "cod_empresa": emp,
                    "cod_banco": bco,
                    "conta_bancaria": cta,
                    "data_movimento": dt_str,
                    "natureza": "0071",
                    "tipo_controle": 5,
                    "proposta": proposta_casada,
                    "natureza_dc": "C",
                    "valor": vlr_intermed,
                    "origem_perna": "RecebePgto",
                }
            )
            lanc_id += 1
            leg_recebepgto.append(
                {
                    "id_lancamento": f"R3D-{lanc_id}",
                    "cod_empresa": emp,
                    "cod_banco": bco,
                    "conta_bancaria": cta,
                    "data_movimento": dt_str,
                    "natureza": "0071",
                    "tipo_controle": 6,
                    "proposta": proposta_casada,
                    "natureza_dc": "D",
                    "valor": vlr_intermed,
                    "origem_perna": "RecebePgto",
                }
            )

            # Em um dia específico da conta CC-101-001, inserir um lançamento '0071' UNILATERAL (órfão)
            # que é uma movimentação real e NÃO deve ser expurgada!
            vlr_orfao_c = 0.0
            if cta == "CC-101-001" and d_idx == 1:
                vlr_orfao_c = 850.00
                lanc_id += 1
                leg_recebepgto.append(
                    {
                        "id_lancamento": f"R3-ORFAO-{lanc_id}",
                        "cod_empresa": emp,
                        "cod_banco": bco,
                        "conta_bancaria": cta,
                        "data_movimento": dt_str,
                        "natureza": "0071",
                        "tipo_controle": 5,
                        "proposta": "PROP-UNILATERAL-999",
                        "natureza_dc": "C",
                        "valor": vlr_orfao_c,
                        "origem_perna": "RecebePgto",
                    }
                )

            # 3. Perna Depositos
            vlr_dep = round(float(rng.uniform(500.0, 3200.0)), 2)
            lanc_id += 1
            leg_depositos.append(
                {
                    "id_lancamento": f"DEP-{lanc_id}",
                    "cod_empresa": emp,
                    "cod_banco": bco,
                    "conta_bancaria": cta,
                    "data_movimento": dt_str,
                    "natureza": "0020",
                    "tipo_controle": 1,
                    "proposta": None,
                    "natureza_dc": "C",
                    "valor": vlr_dep,
                    "origem_perna": "Depositos",
                }
            )

            # 4. Perna EntSaiEmpAplic (Resgates/Aplicações)
            vlr_aplic = round(float(rng.uniform(300.0, 1500.0)), 2)
            lanc_id += 1
            leg_entsai_aplic.append(
                {
                    "id_lancamento": f"APL-{lanc_id}",
                    "cod_empresa": emp,
                    "cod_banco": bco,
                    "conta_bancaria": cta,
                    "data_movimento": dt_str,
                    "natureza": "0050",
                    "tipo_controle": 1,
                    "proposta": None,
                    "natureza_dc": "D",
                    "valor": vlr_aplic,
                    "origem_perna": "EntSaiEmpAplic",
                }
            )

            # 5. Perna VwTransfBcoExtrato (Transferências interbancárias)
            vlr_transf = round(float(rng.uniform(200.0, 900.0)), 2)
            lanc_id += 1
            leg_transf.append(
                {
                    "id_lancamento": f"TRF-{lanc_id}",
                    "cod_empresa": emp,
                    "cod_banco": bco,
                    "conta_bancaria": cta,
                    "data_movimento": dt_str,
                    "natureza": "0080",
                    "tipo_controle": 1,
                    "proposta": None,
                    "natureza_dc": "D",
                    "valor": vlr_transf,
                    "origem_perna": "VwTransfBcoExtrato",
                }
            )

            # Créditos e débitos reais (sem o par transitório casado R3)
            creditos_reais = round(vlr_rec + vlr_dep + vlr_orfao_c, 2)
            debitos_reais = round(vlr_tarifa + vlr_aplic + vlr_transf, 2)
            saldo_fim_dia = round(saldo_ini_dia + creditos_reais - debitos_reais, 2)
            saldo_corrente = saldo_fim_dia

            # Simular que a conta de aplicação (CDB-101-999) só envia extrato em alguns dias
            # (justificando sua exclusão do denominador diário do ICP de Contas Correntes)
            if c["tipo_conta"] == "CONTA_APLICACAO" and d_idx % 3 != 0:
                continue

            extrato_oficial.append(
                {
                    "cod_empresa": emp,
                    "cod_banco": bco,
                    "conta_bancaria": cta,
                    "tipo_conta": c["tipo_conta"],
                    "data_movimento": dt_str,
                    "saldo_inicial": saldo_ini_dia,
                    "creditos_extrato": creditos_reais,
                    "debitos_extrato": debitos_reais,
                    "saldo_final": saldo_fim_dia,
                }
            )

    # Histórico de Snapshots de Conciliação (Num_exa 1..N)
    # Status_exa: 0 = Aberto/Pendente, 2 = Conciliado/Validado
    snapshots_ciclo: List[Dict[str, Any]] = [
        # Caso 1: Ciclo normal em 3 snapshots (criado em D0 com Status=0, conciliado em D+3 no Num_exa=3)
        {
            "id_item_extrato": "ITEM-1001",
            "cod_empresa": 101,
            "conta_bancaria": "CC-101-001",
            "num_exa": 1,
            "status_exa": 0,
            "data_criacao": "2026-04-01",
            "data_validacao": None,
        },
        {
            "id_item_extrato": "ITEM-1001",
            "cod_empresa": 101,
            "conta_bancaria": "CC-101-001",
            "num_exa": 2,
            "status_exa": 0,
            "data_criacao": "2026-04-01",
            "data_validacao": None,
        },
        {
            "id_item_extrato": "ITEM-1001",
            "cod_empresa": 101,
            "conta_bancaria": "CC-101-001",
            "num_exa": 3,
            "status_exa": 2,
            "data_criacao": "2026-04-01",
            "data_validacao": "2026-04-04",
        },
        # Caso 2: Anomalia de validação in-place!
        # O ERP sobrescreveu Status_exa = 2 direto no Num_exa = 1 dias após a criação
        {
            "id_item_extrato": "ITEM-1002",
            "cod_empresa": 101,
            "conta_bancaria": "CC-101-001",
            "num_exa": 1,
            "status_exa": 2,
            "data_criacao": "2026-04-02",
            "data_validacao": "2026-04-07",
        },
        {
            "id_item_extrato": "ITEM-1002",
            "cod_empresa": 101,
            "conta_bancaria": "CC-101-001",
            "num_exa": 2,
            "status_exa": 2,
            "data_criacao": "2026-04-02",
            "data_validacao": "2026-04-09",
        },
        # Caso 3: Item ainda pendente de conciliação
        {
            "id_item_extrato": "ITEM-1003",
            "cod_empresa": 102,
            "conta_bancaria": "CC-102-001",
            "num_exa": 1,
            "status_exa": 0,
            "data_criacao": "2026-04-06",
            "data_validacao": None,
        },
        {
            "id_item_extrato": "ITEM-1003",
            "cod_empresa": 102,
            "conta_bancaria": "CC-102-001",
            "num_exa": 2,
            "status_exa": 0,
            "data_criacao": "2026-04-06",
            "data_validacao": None,
        },
        # Caso 4: Conciliação rápida em D+1
        {
            "id_item_extrato": "ITEM-1004",
            "cod_empresa": 103,
            "conta_bancaria": "CC-103-001",
            "num_exa": 1,
            "status_exa": 0,
            "data_criacao": "2026-04-08",
            "data_validacao": None,
        },
        {
            "id_item_extrato": "ITEM-1004",
            "cod_empresa": 103,
            "conta_bancaria": "CC-103-001",
            "num_exa": 2,
            "status_exa": 2,
            "data_criacao": "2026-04-08",
            "data_validacao": "2026-04-09",
        },
    ]

    return {
        "contas_bancarias": df_contas,
        "extrato_bancario": pd.DataFrame(extrato_oficial),
        "perna_extrato": pd.DataFrame(leg_extrato),
        "perna_recebepgto": pd.DataFrame(leg_recebepgto),
        "perna_depositos": pd.DataFrame(leg_depositos),
        "perna_entsai_aplic": pd.DataFrame(leg_entsai_aplic),
        "perna_transf": pd.DataFrame(leg_transf),
        "snapshots_ciclo": pd.DataFrame(snapshots_ciclo),
    }


def generate_campaigns_dataset(seed: int = DEFAULT_SEED) -> pd.DataFrame:
    """Gera dados sintéticos de campanhas de mídia digital por empreendimento."""
    rng = np.random.default_rng(seed)
    canais = ["Meta Ads", "Google Search", "TikTok Ads", "Portal Imobiliário"]
    campanhas = [
        ("CMP-2026-01", "Feirão Lote Novo Horizonte", 101),
        ("CMP-2026-02", "Lançamento Parque das Águas", 102),
        ("CMP-2026-03", "Campanha Investidor Reserva do Sol", 103),
        ("CMP-2026-04", "Plantão Digital Jardim Imperial", 104),
    ]
    rows: List[Dict[str, Any]] = []
    for cod_cmp, nome_cmp, cod_emp in campanhas:
        for canal in canais:
            investimento = round(float(rng.uniform(4500.0, 28000.0)), 2)
            impressoes = int(rng.integers(45000, 320000))
            cliques = int(impressoes * rng.uniform(0.015, 0.045))
            leads = int(cliques * rng.uniform(0.06, 0.18))
            vendas = int(max(1, leads * rng.uniform(0.03, 0.09)))
            rows.append(
                {
                    "id_campanha": cod_cmp,
                    "nome_campanha": nome_cmp,
                    "cod_empresa": cod_emp,
                    "canal": canal,
                    "investimento_brl": investimento,
                    "impressoes": impressoes,
                    "cliques": cliques,
                    "leads_gerados": leads,
                    "contratos_fechados": vendas,
                }
            )
    return pd.DataFrame(rows)


def generate_all_datasets(
    output_dir: Path | str | None = None, seed: int = DEFAULT_SEED
) -> Dict[str, Any]:
    """Gera e persiste todos os conjuntos de dados sintéticos em CSV e JSON."""
    if output_dir is None:
        output_dir = Path(__file__).resolve().parent / "output"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    df_spes = generate_spe_catalog(seed=seed)
    recebiveis = generate_receivables_dataset(seed=seed)
    conciliacao = generate_reconciliation_dataset(seed=seed)
    df_campanhas = generate_campaigns_dataset(seed=seed)

    # Salvar CSVs
    df_spes.to_csv(output_dir / "spes.csv", index=False)
    recebiveis["contas_receber"].to_csv(
        output_dir / "recebiveis_contas_receber.csv", index=False
    )
    recebiveis["contas_receber_calc"].to_csv(
        output_dir / "recebiveis_contas_receber_calc.csv", index=False
    )
    recebiveis["cessoes"].to_csv(output_dir / "recebiveis_cessoes.csv", index=False)
    recebiveis["distratos"].to_csv(output_dir / "recebiveis_distratos.csv", index=False)

    conciliacao["contas_bancarias"].to_csv(
        output_dir / "conciliacao_contas_bancarias.csv", index=False
    )
    conciliacao["extrato_bancario"].to_csv(
        output_dir / "conciliacao_extrato_bancario.csv", index=False
    )
    conciliacao["snapshots_ciclo"].to_csv(
        output_dir / "conciliacao_snapshots_ciclo.csv", index=False
    )
    df_campanhas.to_csv(output_dir / "campanhas_marketing.csv", index=False)

    # Salvar resumo JSON com amostras e metadados de confidencialidade
    summary_payload = {
        "metadata": {
            "seed": seed,
            "generator": "numpy.random.default_rng(42)",
            "confidentiality_notice": CONFIDENTIALITY_NOTICE,
        },
        "counts": {
            "spes": len(df_spes),
            "contas_receber": len(recebiveis["contas_receber"]),
            "contas_receber_calc": len(recebiveis["contas_receber_calc"]),
            "cessoes": len(recebiveis["cessoes"]),
            "distratos": len(recebiveis["distratos"]),
            "contas_bancarias": len(conciliacao["contas_bancarias"]),
            "extrato_bancario": len(conciliacao["extrato_bancario"]),
            "perna_recebepgto": len(conciliacao["perna_recebepgto"]),
            "snapshots_ciclo": len(conciliacao["snapshots_ciclo"]),
            "campanhas_marketing": len(df_campanhas),
        },
        "samples": {
            "spes": df_spes.head(3).to_dict(orient="records"),
            "contas_receber": recebiveis["contas_receber"]
            .head(3)
            .to_dict(orient="records"),
            "extrato_bancario": conciliacao["extrato_bancario"]
            .head(3)
            .to_dict(orient="records"),
            "campanhas_marketing": df_campanhas.head(3).to_dict(orient="records"),
        },
    }

    with open(output_dir / "synthetic_data_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, ensure_ascii=False, indent=2)

    return summary_payload


if __name__ == "__main__":
    summary = generate_all_datasets()
    print("=" * 76)
    print(CONFIDENTIALITY_NOTICE)
    print("=" * 76)
    print("Dados sintéticos gerados com sucesso em shared/synthetic-data/output/:")
    for k, v in summary["counts"].items():
        print(f"  - {k}: {v} registros")
