"""
Suíte de Testes Automatizados (pytest) — Estudo de Caso 03: DW Financeiro (Snapshots & Diff Engine).

Cobre:
1. Guarda de contrato de colunas (bloqueio de schema drift em sys.columns).
2. Idempotência na dupla execução do mesmo data_snapshot.
3. Bloqueio de contaminação retroativa (tentativa de rodar data_snapshot passada).
4. Detecção exata dos 6 tipos de mutação no motor de diff (snap_mudanca_parcela e cur_mudanca_parcela).
5. Dimensões acumulativas sem órfãos (D-39), mesmo com exclusão no cadastro do ERP e resgate da tabela fato.
6. Emulação da Guarda DAX contra inflação multi-snapshot (Armadilha 3).
"""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from run_demo import (
    executar_demonstracao,
    gerar_estado_erp_domingo_1,
    gerar_estado_erp_domingo_2,
    gerar_estado_erp_domingo_3,
    gerar_estado_erp_quarta_cur,
)
from src.warehouse_snapshot_engine import (
    ContractViolationError,
    RetroactiveSnapshotError,
    auditar_orfaos_dimensoes,
    atualizar_dimensoes_cadastro,
    calcular_mudanca_parcela,
    consultar_total_desembolso_dax_guard,
    inicializar_warehouse,
    publicar_cur_diario,
    publicar_snapshot_semanal,
    verificar_contrato_colunas,
)


def test_guarda_contrato_colunas_bloqueia_schema_drift() -> None:
    conn = inicializar_warehouse(":memory:")
    lote_valido = gerar_estado_erp_domingo_1()
    assert verificar_contrato_colunas(lote_valido) is True

    # Remove uma coluna obrigatória ('insumo_cod')
    lote_faltando_coluna = copy.deepcopy(lote_valido)
    del lote_faltando_coluna[0]["insumo_cod"]
    with pytest.raises(ContractViolationError, match="Violação de contrato estrutural"):
        publicar_snapshot_semanal(
            conn,
            lote_faltando_coluna,
            data_snapshot="2026-10-04",
            dt_carga="2026-10-04T08:00:00",
        )

    # Adiciona coluna extra inesperada ('coluna_intrusa_select_star')
    lote_coluna_extra = copy.deepcopy(lote_valido)
    lote_coluna_extra[0]["coluna_intrusa_select_star"] = "ERRO"
    with pytest.raises(ContractViolationError, match="Violação de contrato estrutural"):
        publicar_snapshot_semanal(
            conn,
            lote_coluna_extra,
            data_snapshot="2026-10-04",
            dt_carga="2026-10-04T08:00:00",
        )


def test_idempotencia_dupla_execucao_mesmo_snapshot() -> None:
    conn = inicializar_warehouse(":memory:")
    lote = gerar_estado_erp_domingo_1()

    r1 = publicar_snapshot_semanal(
        conn, lote, data_snapshot="2026-10-18", dt_carga="2026-10-18T08:00:00"
    )
    assert r1["status"] == "SUCESSO_NOVA_FOTO"
    assert r1["linhas_inseridas"] == 5
    assert r1["linhas_removidas_idempotencia"] == 0

    # Segunda execução para a mesma etiqueta data_snapshot='2026-10-18'
    r2 = publicar_snapshot_semanal(
        conn, lote, data_snapshot="2026-10-18", dt_carga="2026-10-18T09:15:00"
    )
    assert r2["status"] == "SUCESSO_REPROCESSADO_IDEMPOTENTE"
    assert r2["linhas_inseridas"] == 5
    assert r2["linhas_removidas_idempotencia"] == 5

    cur = conn.cursor()
    total_linhas = cur.execute(
        "SELECT COUNT(*) FROM snap_desembolso_completo WHERE data_snapshot = '2026-10-18'"
    ).fetchone()[0]
    total_fotos = cur.execute(
        "SELECT COUNT(DISTINCT data_snapshot) FROM snap_desembolso_completo"
    ).fetchone()[0]
    assert total_linhas == 5
    assert total_fotos == 1


def test_bloqueio_contaminacao_retroativa_snapshot_passado() -> None:
    conn = inicializar_warehouse(":memory:")
    lote = gerar_estado_erp_domingo_1()

    publicar_snapshot_semanal(
        conn, lote, data_snapshot="2026-10-11", dt_carga="2026-10-11T08:00:00"
    )
    publicar_snapshot_semanal(
        conn, lote, data_snapshot="2026-10-18", dt_carga="2026-10-18T08:00:00"
    )

    # Tentar rodar hoje com etiqueta de duas semanas atrás ('2026-10-04') deve ser bloqueado
    with pytest.raises(RetroactiveSnapshotError, match="Contaminação retroativa bloqueada"):
        publicar_snapshot_semanal(
            conn, lote, data_snapshot="2026-10-04", dt_carga="2026-10-19T10:00:00"
        )


def test_motor_diff_detecta_todos_6_tipos_mutacao() -> None:
    conn = inicializar_warehouse(":memory:")
    d1 = gerar_estado_erp_domingo_1()
    d2 = gerar_estado_erp_domingo_2(d1)
    d3 = gerar_estado_erp_domingo_3(d2)
    cur_quarta = gerar_estado_erp_quarta_cur(d3)

    publicar_snapshot_semanal(conn, d1, "2026-10-04", "2026-10-04T08:00:00")
    publicar_snapshot_semanal(conn, d2, "2026-10-11", "2026-10-11T08:00:00")
    publicar_snapshot_semanal(conn, d3, "2026-10-18", "2026-10-18T08:00:00")
    publicar_cur_diario(conn, cur_quarta, "2026-10-21T07:00:00")

    diff_1_2 = calcular_mudanca_parcela(
        conn, modo="snap", data_snapshot_atual="2026-10-11", data_snapshot_anterior="2026-10-04"
    )
    diff_2_3 = calcular_mudanca_parcela(
        conn, modo="snap", data_snapshot_atual="2026-10-18", data_snapshot_anterior="2026-10-11"
    )
    diff_cur = calcular_mudanca_parcela(conn, modo="cur")

    tipos_1_2 = {d["parcela_id"]: d["tipo_mudanca"] for d in diff_1_2}
    assert tipos_1_2 == {
        "101|OBR-GO-01|5001|1": "STATUS_ALTERADO",
        "101|OBR-GO-01|5002|1": "VALOR_ALTERADO",
        "102|OBR-TO-02|6002|1": "EXCLUIDA",
    }

    tipos_2_3 = {d["parcela_id"]: d["tipo_mudanca"] for d in diff_2_3}
    assert tipos_2_3 == {
        "101|OBR-GO-01|5002|1": "VALOR_ALTERADO",
        "101|OBR-GO-01|5003|1": "VENCIMENTO_ALTERADO",
        "101|OBR-GO-01|7001|1": "INCLUIDA",
        "102|OBR-TO-02|6001|1": "RECLASSIFICADA_RATEIO",
    }
    # Garante que a parcela 5001 (inalterada entre D2 e D3) NÃO entrou no diff
    assert "101|OBR-GO-01|5001|1" not in tipos_2_3

    # Verifica cálculo exato de dias de prorrogação de vencimento na 5003
    reg_5003 = next(d for d in diff_2_3 if d["parcela_id"] == "101|OBR-GO-01|5003|1")
    assert reg_5003["dias_deslocamento_vencimento"] == 11

    tipos_cur = {d["parcela_id"]: d["tipo_mudanca"] for d in diff_cur}
    assert tipos_cur == {
        "101|OBR-GO-01|5002|1": "STATUS_ALTERADO",
        "101|OBR-GO-01|7001|1": "VALOR_ALTERADO",
    }


def test_dimensoes_acumulativas_zero_orfaos_d39() -> None:
    conn = inicializar_warehouse(":memory:")
    d1 = gerar_estado_erp_domingo_1()
    d2 = gerar_estado_erp_domingo_2(d1)
    d3 = gerar_estado_erp_domingo_3(d2)

    publicar_snapshot_semanal(conn, d1, "2026-10-04", "2026-10-04T08:00:00")
    publicar_snapshot_semanal(conn, d3, "2026-10-18", "2026-10-18T08:00:00")

    # Passa apenas 1 fornecedor ativo no cadastro; os demais devem ser preservados/resgatados do fato
    atualizar_dimensoes_cadastro(
        conn,
        cadastros_fornecedores=[
            {"fornecedor_cod": 9001, "razao_social": "TERRA FORTE S/A", "uf": "GO"}
        ],
        cadastros_obras=[],
        cadastros_insumos=[],
    )

    orfaos = auditar_orfaos_dimensoes(conn)
    assert orfaos["orfaos_fornecedor"] == 0
    assert orfaos["orfaos_obra"] == 0
    assert orfaos["orfaos_insumo"] == 0
    assert orfaos["total_orfaos"] == 0


def test_guarda_dax_emulada_evita_inflacao_multi_snapshot() -> None:
    relatorio = executar_demonstracao()
    info_dax = relatorio["armadilha_3_guarda_dax"]
    assert info_dax["soma_ingenuo_sem_guarda_inflado"] > info_dax["soma_correta_com_guarda_ultimo_snapshot"]
    assert info_dax["soma_correta_com_guarda_ultimo_snapshot"] == 360200.00
