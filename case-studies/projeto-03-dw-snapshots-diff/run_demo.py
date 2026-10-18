"""
Script de Demonstração Executável — Estudo de Caso 03 (DW Financeiro: Snapshots & Diff Engine).

Simula:
1. 3 domingos consecutivos de snapshots (2026-10-04, 2026-10-11, 2026-10-18) sobre um ERP sintético mutável.
2. Dupla execução idempotente do Domingo 3 (2026-10-18) para comprovar ausência de duplicação.
3. Tentativa bloqueada de contaminação retroativa (rodar data_snapshot passada).
4. Carga operacional diária (cur_desembolso_atual) na quarta-feira (2026-10-21).
5. Dimensões acumulativas sem órfãos (D-39), mesmo quando fornecedor antigo é removido do cadastro do ERP.
6. Cálculo do Diff Semanal (snap_mudanca_parcela) e Diff Diário (cur_mudanca_parcela) cobrindo todos os 6 tipos de mutação.
7. Exportação de evidências estruturadas em examples/sample_output.json.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List

from src.warehouse_snapshot_engine import (
    RetroactiveSnapshotError,
    auditar_orfaos_dimensoes,
    atualizar_dimensoes_cadastro,
    calcular_mudanca_parcela,
    consultar_total_desembolso_dax_guard,
    inicializar_warehouse,
    publicar_cur_diario,
    publicar_snapshot_semanal,
)


def gerar_estado_erp_domingo_1() -> List[Dict[str, Any]]:
    """Foto inicial do ERP sintético no Domingo 1 (2026-10-04)."""
    return [
        {
            "empresa_cod": 101,
            "obra_cod": "OBR-GO-01",
            "processo_num": 5001,
            "parcela_num": 1,
            "item_num": 1,
            "cap_cod": "CAP-TERRAPLENAGEM",
            "insumo_cod": "INS-OLEO-DIESEL",
            "fornecedor_cod": 9001,
            "valor_fatia": 45000.00,
            "data_vencimento": "2026-10-15",
            "status_parcela": "ABERTO",
            "descricao_item": "Locação de patrulha mecanizada e óleo diesel",
        },
        {
            "empresa_cod": 101,
            "obra_cod": "OBR-GO-01",
            "processo_num": 5002,
            "parcela_num": 1,
            "item_num": 1,
            "cap_cod": "CAP-DRENAGEM",
            "insumo_cod": "INS-TUBO-CONCRETO",
            "fornecedor_cod": 9002,
            "valor_fatia": 82000.00,
            "data_vencimento": "2026-10-20",
            "status_parcela": "ABERTO",
            "descricao_item": "Tubos de concreto armado PA-2 DN 800mm",
        },
        {
            "empresa_cod": 101,
            "obra_cod": "OBR-GO-01",
            "processo_num": 5003,
            "parcela_num": 1,
            "item_num": 1,
            "cap_cod": "CAP-PAVIMENTACAO",
            "insumo_cod": "INS-CBUQ",
            "fornecedor_cod": 9003,
            "valor_fatia": 120000.00,
            "data_vencimento": "2026-10-25",
            "status_parcela": "ABERTO",
            "descricao_item": "Massa asfáltica CBUQ faixa C",
        },
        {
            "empresa_cod": 102,
            "obra_cod": "OBR-TO-02",
            "processo_num": 6001,
            "parcela_num": 1,
            "item_num": 1,
            "cap_cod": "CAP-REDE-ELETRICA",
            "insumo_cod": "INS-CABO-ALUMINIO",
            "fornecedor_cod": 9004,
            "valor_fatia": 64000.00,
            "data_vencimento": "2026-10-28",
            "status_parcela": "ABERTO",
            "descricao_item": "Cabos de alumínio multiplexados média tensão",
        },
        {
            "empresa_cod": 102,
            "obra_cod": "OBR-TO-02",
            "processo_num": 6002,
            "parcela_num": 1,
            "item_num": 1,
            "cap_cod": "CAP-TOPOGRAFIA",
            "insumo_cod": "INS-MARCO-CONCRETO",
            "fornecedor_cod": 9005,
            "valor_fatia": 18500.00,
            "data_vencimento": "2026-10-12",
            "status_parcela": "ABERTO",
            "descricao_item": "Serviços topográficos e piqueteamento de quadras",
        },
    ]


def gerar_estado_erp_domingo_2(base_d1: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Mutações in-place ocorridas no ERP entre Domingo 1 (2026-10-04) e Domingo 2 (2026-10-11):
    - Processo 5001: STATUS_ALTERADO ('ABERTO' -> 'PAGO')
    - Processo 5002: VALOR_ALTERADO (82.000 -> 89.500 por aditivo de frete)
    - Processo 6002: EXCLUIDA fisicamente do ERP
    """
    d2 = copy.deepcopy(base_d1)
    d2[0]["status_parcela"] = "PAGO"
    d2[1]["valor_fatia"] = 89500.00
    # Remove processo 6002 (índice 4) simulando deleção in-place sem log no ERP
    d2 = [r for r in d2 if r["processo_num"] != 6002]
    return d2


def gerar_estado_erp_domingo_3(base_d2: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Mutações in-place ocorridas no ERP entre Domingo 2 (2026-10-11) e Domingo 3 (2026-10-18):
    - Processo 5002: VALOR_ALTERADO (89.500 -> 91.000)
    - Processo 5003: VENCIMENTO_ALTERADO ('2026-10-25' -> '2026-11-10', +16 dias)
    - Processo 6001: RECLASSIFICADA_RATEIO (cap_cod 'CAP-REDE-ELETRICA' -> 'CAP-ILUMINACAO-PUBLICA')
    - Processo 5002: STATUS_ALTERADO ('ABERTO' -> 'PAGO') -> faremos isso num processo separado ou no 5001
    Vamos aplicar mutações ortogonais para demonstrar todos os 6 tipos no Domingo 3 vs Domingo 2:
    - Processo 5001 (já PAGO): permanece inalterado (prova que inalterados não entram no diff!)
    - Processo 5002: VALOR_ALTERADO (89.500 -> 94.000)
    - Processo 5003: VENCIMENTO_ALTERADO ('2026-10-25' -> '2026-11-05')
    - Processo 6001: RECLASSIFICADA_RATEIO (insumo_cod 'INS-CABO-ALUMINIO' -> 'INS-LUMINARIA-LED')
    - Processo 7001: INCLUIDA (nova parcela inserida na semana)
    """
    d3 = copy.deepcopy(base_d2)
    for r in d3:
        if r["processo_num"] == 5002:
            r["valor_fatia"] = 94000.00
        elif r["processo_num"] == 5003:
            r["data_vencimento"] = "2026-11-05"
        elif r["processo_num"] == 6001:
            r["cap_cod"] = "CAP-ILUMINACAO-LED"
            r["insumo_cod"] = "INS-LUMINARIA-LED"

    # Nova parcela incluída no Domingo 3 (com um fornecedor 9099 ainda não cadastrado na tabela de fornecedores!)
    d3.append(
        {
            "empresa_cod": 101,
            "obra_cod": "OBR-GO-01",
            "processo_num": 7001,
            "parcela_num": 1,
            "item_num": 1,
            "cap_cod": "CAP-PAISAGISMO",
            "insumo_cod": "INS-GRAMA-ESMERALDA",
            "fornecedor_cod": 9099,
            "valor_fatia": 37200.00,
            "data_vencimento": "2026-11-15",
            "status_parcela": "ABERTO",
            "descricao_item": "Plantio de grama esmeralda em áreas verdes",
        }
    )
    return d3


def gerar_estado_erp_quarta_cur(base_d3: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Estado operacional diário na Quarta-feira (2026-10-21) comparado ao Domingo 3 (2026-10-18):
    - Processo 5002: STATUS_ALTERADO ('ABERTO' -> 'PAGO')
    - Processo 7001: VALOR_ALTERADO (37.200 -> 39.000)
    """
    cur_data = copy.deepcopy(base_d3)
    for r in cur_data:
        if r["processo_num"] == 5002:
            r["status_parcela"] = "PAGO"
        elif r["processo_num"] == 7001:
            r["valor_fatia"] = 39000.00
    return cur_data


def executar_demonstracao() -> Dict[str, Any]:
    conn = inicializar_warehouse(":memory:")

    # Cadastros iniciais do ERP no Domingo 1
    fornecedores_d1 = [
        {"fornecedor_cod": 9001, "razao_social": "TERRA FORTE LOCACOES S/A", "uf": "GO"},
        {"fornecedor_cod": 9002, "razao_social": "PREMOLDADOS CENTRAL LTDA", "uf": "GO"},
        {"fornecedor_cod": 9003, "razao_social": "USINA ASFALTO PLANALTO LTDA", "uf": "DF"},
        {"fornecedor_cod": 9004, "razao_social": "ELETRO REDES NORTE S/A", "uf": "TO"},
        {"fornecedor_cod": 9005, "razao_social": "PRECISAO TOPOGRAFIA S/S", "uf": "TO"},
    ]
    obras_d1 = [
        {"empresa_cod": 101, "obra_cod": "OBR-GO-01", "nome_obra": "Jardins do Cerrado I", "cidade": "Aparecida de Goiânia", "uf": "GO"},
        {"empresa_cod": 102, "obra_cod": "OBR-TO-02", "nome_obra": "Parque das Águas Sul", "cidade": "Palmas", "uf": "TO"},
    ]
    insumos_d1 = [
        {"insumo_cod": "INS-OLEO-DIESEL", "descricao_insumo": "Óleo Diesel S10", "grupo_insumo": "COMBUSTIVEIS"},
        {"insumo_cod": "INS-TUBO-CONCRETO", "descricao_insumo": "Tubo Concreto PA-2", "grupo_insumo": "DRENAGEM"},
        {"insumo_cod": "INS-CBUQ", "descricao_insumo": "Concreto Betuminoso Usinado a Quente", "grupo_insumo": "PAVIMENTACAO"},
        {"insumo_cod": "INS-CABO-ALUMINIO", "descricao_insumo": "Cabo Multiplexado Alumínio", "grupo_insumo": "ELETRICA"},
        {"insumo_cod": "INS-MARCO-CONCRETO", "descricao_insumo": "Marco Topográfico de Concreto", "grupo_insumo": "TOPOGRAFIA"},
    ]

    # 1. Domingo 1 (2026-10-04)
    erp_d1 = gerar_estado_erp_domingo_1()
    res_d1 = publicar_snapshot_semanal(
        conn, erp_d1, data_snapshot="2026-10-04", dt_carga="2026-10-04T08:00:12"
    )
    atualizar_dimensoes_cadastro(
        conn, fornecedores_d1, obras_d1, insumos_d1, dt_atualizacao="2026-10-04T08:01:00"
    )

    # 2. Domingo 2 (2026-10-11)
    erp_d2 = gerar_estado_erp_domingo_2(erp_d1)
    res_d2 = publicar_snapshot_semanal(
        conn, erp_d2, data_snapshot="2026-10-11", dt_carga="2026-10-11T08:00:09"
    )
    diff_d1_d2 = calcular_mudanca_parcela(
        conn,
        modo="snap",
        data_snapshot_atual="2026-10-11",
        data_snapshot_anterior="2026-10-04",
        dt_calculo="2026-10-11T08:02:00",
    )

    # 3. Domingo 3 (2026-10-18) — Primeira execução
    erp_d3 = gerar_estado_erp_domingo_3(erp_d2)
    res_d3_1 = publicar_snapshot_semanal(
        conn, erp_d3, data_snapshot="2026-10-18", dt_carga="2026-10-18T08:00:15"
    )
    # 3b. Domingo 3 (2026-10-18) — Segunda execução no mesmo dia (Teste de Idempotência)
    res_d3_2 = publicar_snapshot_semanal(
        conn, erp_d3, data_snapshot="2026-10-18", dt_carga="2026-10-18T10:30:00"
    )

    # Simula que no Domingo 3 o fornecedor 9005 foi excluído do cadastro do ERP
    # e o fornecedor 9099 ainda não foi cadastrado na tabela de fornecedores
    fornecedores_d3_parcial = [f for f in fornecedores_d1 if f["fornecedor_cod"] != 9005]
    dim_stats = atualizar_dimensoes_cadastro(
        conn,
        fornecedores_d3_parcial,
        obras_d1,
        insumos_d1,
        dt_atualizacao="2026-10-18T10:31:00",
    )

    diff_d2_d3 = calcular_mudanca_parcela(
        conn,
        modo="snap",
        data_snapshot_atual="2026-10-18",
        data_snapshot_anterior="2026-10-11",
        dt_calculo="2026-10-18T10:32:00",
    )

    # 4. Teste de Bloqueio de Contaminação Retroativa
    bloqueio_retroativo_ok = False
    msg_bloqueio = ""
    try:
        publicar_snapshot_semanal(
            conn, erp_d3, data_snapshot="2026-10-04", dt_carga="2026-10-19T09:00:00"
        )
    except RetroactiveSnapshotError as exc:
        bloqueio_retroativo_ok = True
        msg_bloqueio = str(exc)

    # 5. Quarta-feira (2026-10-21) — Camada Operacional Diária (cur) e Diff Diário
    erp_cur = gerar_estado_erp_quarta_cur(erp_d3)
    res_cur = publicar_cur_diario(conn, erp_cur, dt_carga="2026-10-21T07:00:05")
    diff_cur = calcular_mudanca_parcela(
        conn, modo="cur", dt_calculo="2026-10-21T07:02:00"
    )

    # 6. Auditoria de Zero Órfãos (D-39) e Guarda DAX (Armadilha 3)
    auditoria_orfaos = auditar_orfaos_dimensoes(conn)
    soma_sem_guarda = consultar_total_desembolso_dax_guard(conn, usar_guarda=False)
    soma_com_guarda = consultar_total_desembolso_dax_guard(conn, usar_guarda=True)

    cur = conn.cursor()
    fotos_distintas = [
        r[0]
        for r in cur.execute(
            "SELECT DISTINCT data_snapshot FROM snap_desembolso_completo ORDER BY data_snapshot"
        ).fetchall()
    ]
    total_linhas_snap = cur.execute(
        "SELECT COUNT(*) FROM snap_desembolso_completo"
    ).fetchone()[0]

    relatorio = {
        "projeto": "case-03-dw-snapshots-diff",
        "aviso_dados_sinteticos": "100% sinteticos (seed=42) - Nenhuma informacao corporativa real exposta.",
        "resumo_snapshots": {
            "fotos_consolidada_serie": fotos_distintas,
            "quantidade_fotos": len(fotos_distintas),
            "total_linhas_snap_acumuladas": total_linhas_snap,
            "execucao_domingo_1": res_d1,
            "execucao_domingo_2": res_d2,
            "execucao_domingo_3_primeira": res_d3_1,
            "execucao_domingo_3_reprocessada_idempotente": res_d3_2,
            "execucao_cur_quarta": res_cur,
        },
        "protecao_contaminacao_retroativa": {
            "tentativa_bloqueada": bloqueio_retroativo_ok,
            "mensagem": msg_bloqueio,
        },
        "dimensoes_acumulativas_d39": {
            "totais_dimensoes": dim_stats,
            "auditoria_orfaos": auditoria_orfaos,
        },
        "armadilha_3_guarda_dax": {
            "soma_ingenuo_sem_guarda_inflado": soma_sem_guarda,
            "soma_correta_com_guarda_ultimo_snapshot": soma_com_guarda,
            "fator_inflacao_evitado": round(soma_sem_guarda / soma_com_guarda, 2),
        },
        "diff_semanal_d1_para_d2": diff_d1_d2,
        "diff_semanal_d2_para_d3": diff_d2_d3,
        "diff_diario_d3_para_cur": diff_cur,
    }

    output_path = Path(__file__).resolve().parent / "examples" / "sample_output.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return relatorio


if __name__ == "__main__":
    resultado = executar_demonstracao()
    print("=== DEMONSTRACAO DW FINANCEIRO (SNAPSHOTS & DIFF ENGINE) CONCLUIDA ===")
    print(f"Fotos na serie: {resultado['resumo_snapshots']['fotos_consolidada_serie']}")
    print(
        f"Idempotencia Domingo 3: status={resultado['resumo_snapshots']['execucao_domingo_3_reprocessada_idempotente']['status']}"
    )
    print(
        f"Zero Orfaos D-39: total_orfaos={resultado['dimensoes_acumulativas_d39']['auditoria_orfaos']['total_orfaos']}"
    )
    print(
        f"Deltas D1->D2: {len(resultado['diff_semanal_d1_para_d2'])} | "
        f"Deltas D2->D3: {len(resultado['diff_semanal_d2_para_d3'])} | "
        f"Deltas D3->CUR: {len(resultado['diff_diario_d3_para_cur'])}"
    )
