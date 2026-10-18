"""
Motor de Historização por Snapshots Semanais/Diários e Diff Engine de Parcelas/Rateios.
Reconstrução executável em Python + SQLite (emulando T-SQL do wh_dw_financeiro no Microsoft Fabric).

AVISO: Todos os dados e schemas manipulados por este módulo são 100% sintéticos.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

CONTRATO_COLUNAS_PADRAO: Tuple[str, ...] = (
    "empresa_cod",
    "obra_cod",
    "processo_num",
    "parcela_num",
    "item_num",
    "cap_cod",
    "insumo_cod",
    "fornecedor_cod",
    "valor_fatia",
    "data_vencimento",
    "status_parcela",
    "descricao_item",
)


class ContractViolationError(RuntimeError):
    """Exceção disparada quando o schema da fonte diverge do contrato esperado (Armadilha 5)."""


class RetroactiveSnapshotError(RuntimeError):
    """Exceção disparada ao tentar gravar o estado atual do ERP em uma data_snapshot passada."""


def inicializar_warehouse(db_path: str = ":memory:") -> sqlite3.Connection:
    """
    Inicializa o banco relacional emulando os 5 schemas do wh_dw_financeiro:
    - ctl  (ctl_log_carga)
    - stg  (stg_desembolso_completo)
    - snap (snap_desembolso_completo, snap_mudanca_parcela)
    - cur  (cur_desembolso_atual, cur_mudanca_parcela)
    - dim  (dim_fornecedor, dim_obra, dim_insumo)
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS ctl_log_carga (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo_operacao TEXT NOT NULL,
            data_snapshot TEXT,
            dt_carga TEXT NOT NULL,
            linhas_inseridas INTEGER NOT NULL,
            linhas_removidas_idempotencia INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            mensagem TEXT
        );

        CREATE TABLE IF NOT EXISTS stg_desembolso_completo (
            empresa_cod INTEGER NOT NULL,
            obra_cod TEXT NOT NULL,
            processo_num INTEGER NOT NULL,
            parcela_num INTEGER NOT NULL,
            item_num INTEGER NOT NULL,
            cap_cod TEXT NOT NULL,
            insumo_cod TEXT NOT NULL,
            fornecedor_cod INTEGER NOT NULL,
            valor_fatia REAL NOT NULL,
            data_vencimento TEXT NOT NULL,
            status_parcela TEXT NOT NULL,
            descricao_item TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS snap_desembolso_completo (
            data_snapshot TEXT NOT NULL,
            dt_carga TEXT NOT NULL,
            parcela_id TEXT NOT NULL,
            fatia_rateio_id TEXT NOT NULL,
            chave_obra TEXT NOT NULL,
            empresa_cod INTEGER NOT NULL,
            obra_cod TEXT NOT NULL,
            processo_num INTEGER NOT NULL,
            parcela_num INTEGER NOT NULL,
            item_num INTEGER NOT NULL,
            cap_cod TEXT NOT NULL,
            insumo_cod TEXT NOT NULL,
            fornecedor_cod INTEGER NOT NULL,
            valor_fatia REAL NOT NULL,
            data_vencimento TEXT NOT NULL,
            status_parcela TEXT NOT NULL,
            descricao_item TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_snap_data_fatia
            ON snap_desembolso_completo (data_snapshot, fatia_rateio_id);

        CREATE TABLE IF NOT EXISTS cur_desembolso_atual (
            dt_carga TEXT NOT NULL,
            parcela_id TEXT NOT NULL,
            fatia_rateio_id TEXT NOT NULL,
            chave_obra TEXT NOT NULL,
            empresa_cod INTEGER NOT NULL,
            obra_cod TEXT NOT NULL,
            processo_num INTEGER NOT NULL,
            parcela_num INTEGER NOT NULL,
            item_num INTEGER NOT NULL,
            cap_cod TEXT NOT NULL,
            insumo_cod TEXT NOT NULL,
            fornecedor_cod INTEGER NOT NULL,
            valor_fatia REAL NOT NULL,
            data_vencimento TEXT NOT NULL,
            status_parcela TEXT NOT NULL,
            descricao_item TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS snap_mudanca_parcela (
            data_snapshot_anterior TEXT NOT NULL,
            data_snapshot_atual TEXT NOT NULL,
            dt_calculo TEXT NOT NULL,
            parcela_id TEXT NOT NULL,
            fatia_rateio_id TEXT NOT NULL,
            chave_obra TEXT NOT NULL,
            fornecedor_cod INTEGER NOT NULL,
            tipo_mudanca TEXT NOT NULL,
            valor_anterior REAL,
            valor_atual REAL,
            delta_valor REAL NOT NULL,
            vencimento_anterior TEXT,
            vencimento_atual TEXT,
            dias_deslocamento_vencimento INTEGER,
            status_anterior TEXT,
            status_atual TEXT,
            cap_anterior TEXT,
            cap_atual TEXT,
            insumo_anterior TEXT,
            insumo_atual TEXT
        );

        CREATE TABLE IF NOT EXISTS cur_mudanca_parcela (
            data_snapshot_referencia TEXT NOT NULL,
            dt_carga_atual TEXT NOT NULL,
            parcela_id TEXT NOT NULL,
            fatia_rateio_id TEXT NOT NULL,
            chave_obra TEXT NOT NULL,
            fornecedor_cod INTEGER NOT NULL,
            tipo_mudanca TEXT NOT NULL,
            valor_anterior REAL,
            valor_atual REAL,
            delta_valor REAL NOT NULL,
            vencimento_anterior TEXT,
            vencimento_atual TEXT,
            dias_deslocamento_vencimento INTEGER,
            status_anterior TEXT,
            status_atual TEXT,
            cap_anterior TEXT,
            cap_atual TEXT,
            insumo_anterior TEXT,
            insumo_atual TEXT
        );

        CREATE TABLE IF NOT EXISTS dim_fornecedor (
            fornecedor_cod INTEGER PRIMARY KEY,
            razao_social TEXT NOT NULL,
            uf TEXT NOT NULL,
            origem_registro TEXT NOT NULL,
            dt_primeira_carga TEXT NOT NULL,
            dt_ultima_atualizacao TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dim_obra (
            chave_obra TEXT PRIMARY KEY,
            empresa_cod INTEGER NOT NULL,
            obra_cod TEXT NOT NULL,
            nome_obra TEXT NOT NULL,
            cidade TEXT NOT NULL,
            uf TEXT NOT NULL,
            origem_registro TEXT NOT NULL,
            dt_ultima_atualizacao TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dim_insumo (
            insumo_cod TEXT PRIMARY KEY,
            descricao_insumo TEXT NOT NULL,
            grupo_insumo TEXT NOT NULL,
            origem_registro TEXT NOT NULL,
            dt_ultima_atualizacao TEXT NOT NULL
        );
        """
    )
    conn.commit()
    return conn


def _extrair_nomes_colunas(
    df_ou_registros: Union[Sequence[Dict[str, Any]], Any]
) -> Tuple[str, ...]:
    """Extrai a tupla ordenada de colunas de uma lista de dicts ou DataFrame."""
    if hasattr(df_ou_registros, "columns"):
        return tuple(str(c) for c in df_ou_registros.columns)
    if isinstance(df_ou_registros, Sequence) and len(df_ou_registros) > 0:
        primeiro = df_ou_registros[0]
        if isinstance(primeiro, dict):
            return tuple(primeiro.keys())
    if isinstance(df_ou_registros, Sequence) and len(df_ou_registros) == 0:
        return CONTRATO_COLUNAS_PADRAO
    raise ContractViolationError("Formato de lote inválido para verificação de contrato.")


def _converter_para_registros(
    df_ou_registros: Union[Sequence[Dict[str, Any]], Any]
) -> List[Dict[str, Any]]:
    """Normaliza entrada (DataFrame ou lista de dicionários) para lista de dicts."""
    if hasattr(df_ou_registros, "to_dict"):
        return list(df_ou_registros.to_dict(orient="records"))
    return [dict(r) for r in df_ou_registros]


def verificar_contrato_colunas(
    df_ou_registros: Union[Sequence[Dict[str, Any]], Any],
    colunas_esperadas: Sequence[str] = CONTRATO_COLUNAS_PADRAO,
) -> bool:
    """
    Guarda de Contrato de Colunas (emulando inspeção em sys.columns — D-11 / Armadilha 5).
    Bloqueia a carga caso o número de colunas ou seus nomes divirjam do contrato esperado.
    """
    colunas_recebidas = _extrair_nomes_colunas(df_ou_registros)
    esperadas_set = set(colunas_esperadas)
    recebidas_set = set(colunas_recebidas)

    faltantes = sorted(esperadas_set - recebidas_set)
    extras = sorted(recebidas_set - esperadas_set)

    if len(colunas_recebidas) != len(colunas_esperadas) or faltantes or extras:
        raise ContractViolationError(
            f"Violação de contrato estrutural na staging! "
            f"Esperadas={len(colunas_esperadas)}, Recebidas={len(colunas_recebidas)}. "
            f"Faltantes={faltantes}, Extras={extras}."
        )
    return True


def construir_chaves_compostas(reg: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Calcula as chaves canônicas do DW Financeiro:
    - parcela_id:      empresa_cod|obra_cod|processo_num|parcela_num
    - fatia_rateio_id: empresa_cod|obra_cod|processo_num|parcela_num|item_num
    - chave_obra:      empresa_cod|obra_cod
    """
    empresa = int(reg["empresa_cod"])
    obra = str(reg["obra_cod"]).strip().upper()
    processo = int(reg["processo_num"])
    parcela = int(reg["parcela_num"])
    item = int(reg["item_num"])

    chave_obra = f"{empresa}|{obra}"
    parcela_id = f"{empresa}|{obra}|{processo}|{parcela}"
    fatia_rateio_id = f"{parcela_id}|{item}"
    return parcela_id, fatia_rateio_id, chave_obra


def publicar_snapshot_semanal(
    conn: sqlite3.Connection,
    df_erp: Union[Sequence[Dict[str, Any]], Any],
    data_snapshot: str,
    dt_carga: str,
    permitir_reprocessamento_ultimo: bool = True,
) -> Dict[str, Any]:
    """
    Publica de forma atômica e idempotente uma fotografia semanal em snap_desembolso_completo.

    Garantias de engenharia:
    1. Guarda de contrato de colunas antes de qualquer escrita.
    2. Bloqueio de contaminação retroativa: impede gravar o estado de hoje do ERP
       com uma etiqueta data_snapshot anterior ao último snapshot já consolidado.
    3. Idempotência: se executada 2x para a mesma data_snapshot, remove a foto anterior
       daquela etiqueta e grava a nova dentro da mesma transação, mantendo 1 única foto.
    4. Normalização Case-Insensitive / UTF-8 de domínios textuais (Armadilha 1).
    """
    verificar_contrato_colunas(df_erp)
    registros = _converter_para_registros(df_erp)

    cur = conn.cursor()
    row_max = cur.execute(
        "SELECT MAX(data_snapshot) AS max_snap FROM snap_desembolso_completo"
    ).fetchone()
    max_snap = row_max["max_snap"] if row_max else None

    if max_snap is not None:
        if data_snapshot < max_snap:
            cur.execute(
                """
                INSERT INTO ctl_log_carga
                (tipo_operacao, data_snapshot, dt_carga, linhas_inseridas, linhas_removidas_idempotencia, status, mensagem)
                VALUES (?, ?, ?, 0, 0, 'BLOQUEADO_RETROATIVO', ?)
                """,
                (
                    "SNAPSHOT_SEMANAL",
                    data_snapshot,
                    dt_carga,
                    f"Tentativa bloqueada de gravar snapshot retroativo ({data_snapshot} < {max_snap}).",
                ),
            )
            conn.commit()
            raise RetroactiveSnapshotError(
                f"Contaminação retroativa bloqueada: data_snapshot '{data_snapshot}' é anterior "
                f"ao último snapshot consolidado '{max_snap}'. O ERP é mutável in-place."
            )
        if data_snapshot == max_snap and not permitir_reprocessamento_ultimo:
            raise RetroactiveSnapshotError(
                f"Snapshot '{data_snapshot}' já existe e reprocessamento está desabilitado."
            )

    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("DELETE FROM stg_desembolso_completo")

        linhas_stg = []
        linhas_snap = []
        for r in registros:
            parcela_id, fatia_rateio_id, chave_obra = construir_chaves_compostas(r)
            obra_norm = str(r["obra_cod"]).strip().upper()
            cap_norm = str(r["cap_cod"]).strip().upper()
            insumo_norm = str(r["insumo_cod"]).strip().upper()
            status_norm = str(r["status_parcela"]).strip().upper()
            desc_norm = str(r["descricao_item"]).strip()

            linhas_stg.append(
                (
                    int(r["empresa_cod"]),
                    obra_norm,
                    int(r["processo_num"]),
                    int(r["parcela_num"]),
                    int(r["item_num"]),
                    cap_norm,
                    insumo_norm,
                    int(r["fornecedor_cod"]),
                    round(float(r["valor_fatia"]), 2),
                    str(r["data_vencimento"]).strip(),
                    status_norm,
                    desc_norm,
                )
            )
            linhas_snap.append(
                (
                    data_snapshot,
                    dt_carga,
                    parcela_id,
                    fatia_rateio_id,
                    chave_obra,
                    int(r["empresa_cod"]),
                    obra_norm,
                    int(r["processo_num"]),
                    int(r["parcela_num"]),
                    int(r["item_num"]),
                    cap_norm,
                    insumo_norm,
                    int(r["fornecedor_cod"]),
                    round(float(r["valor_fatia"]), 2),
                    str(r["data_vencimento"]).strip(),
                    status_norm,
                    desc_norm,
                )
            )

        cur.executemany(
            """
            INSERT INTO stg_desembolso_completo (
                empresa_cod, obra_cod, processo_num, parcela_num, item_num,
                cap_cod, insumo_cod, fornecedor_cod, valor_fatia,
                data_vencimento, status_parcela, descricao_item
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            linhas_stg,
        )

        # Limpeza atômica para idempotência na mesma etiqueta data_snapshot
        cur.execute(
            "DELETE FROM snap_desembolso_completo WHERE data_snapshot = ?",
            (data_snapshot,),
        )
        removidas = cur.rowcount

        cur.executemany(
            """
            INSERT INTO snap_desembolso_completo (
                data_snapshot, dt_carga, parcela_id, fatia_rateio_id, chave_obra,
                empresa_cod, obra_cod, processo_num, parcela_num, item_num,
                cap_cod, insumo_cod, fornecedor_cod, valor_fatia,
                data_vencimento, status_parcela, descricao_item
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            linhas_snap,
        )

        status_msg = (
            "SUCESSO_REPROCESSADO_IDEMPOTENTE" if removidas > 0 else "SUCESSO_NOVA_FOTO"
        )
        cur.execute(
            """
            INSERT INTO ctl_log_carga (
                tipo_operacao, data_snapshot, dt_carga,
                linhas_inseridas, linhas_removidas_idempotencia, status, mensagem
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SNAPSHOT_SEMANAL",
                data_snapshot,
                dt_carga,
                len(linhas_snap),
                removidas,
                status_msg,
                f"Snapshot {data_snapshot} publicado com {len(linhas_snap)} linhas (removidas={removidas}).",
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "data_snapshot": data_snapshot,
        "dt_carga": dt_carga,
        "linhas_inseridas": len(linhas_snap),
        "linhas_removidas_idempotencia": removidas,
        "status": status_msg,
    }


def publicar_cur_diario(
    conn: sqlite3.Connection,
    df_erp: Union[Sequence[Dict[str, Any]], Any],
    dt_carga: str,
) -> Dict[str, Any]:
    """
    Atualiza de forma atômica a camada operacional corrente (cur_desembolso_atual).
    """
    verificar_contrato_colunas(df_erp)
    registros = _converter_para_registros(df_erp)

    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("DELETE FROM cur_desembolso_atual")
        removidas = cur.rowcount

        linhas_cur = []
        for r in registros:
            parcela_id, fatia_rateio_id, chave_obra = construir_chaves_compostas(r)
            linhas_cur.append(
                (
                    dt_carga,
                    parcela_id,
                    fatia_rateio_id,
                    chave_obra,
                    int(r["empresa_cod"]),
                    str(r["obra_cod"]).strip().upper(),
                    int(r["processo_num"]),
                    int(r["parcela_num"]),
                    int(r["item_num"]),
                    str(r["cap_cod"]).strip().upper(),
                    str(r["insumo_cod"]).strip().upper(),
                    int(r["fornecedor_cod"]),
                    round(float(r["valor_fatia"]), 2),
                    str(r["data_vencimento"]).strip(),
                    str(r["status_parcela"]).strip().upper(),
                    str(r["descricao_item"]).strip(),
                )
            )

        cur.executemany(
            """
            INSERT INTO cur_desembolso_atual (
                dt_carga, parcela_id, fatia_rateio_id, chave_obra,
                empresa_cod, obra_cod, processo_num, parcela_num, item_num,
                cap_cod, insumo_cod, fornecedor_cod, valor_fatia,
                data_vencimento, status_parcela, descricao_item
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            linhas_cur,
        )

        cur.execute(
            """
            INSERT INTO ctl_log_carga (
                tipo_operacao, data_snapshot, dt_carga,
                linhas_inseridas, linhas_removidas_idempotencia, status, mensagem
            ) VALUES ('CUR_DIARIO', NULL, ?, ?, ?, 'SUCESSO_CUR', ?)
            """,
            (
                dt_carga,
                len(linhas_cur),
                removidas,
                f"Camada cur atualizada com {len(linhas_cur)} linhas.",
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "dt_carga": dt_carga,
        "linhas_inseridas": len(linhas_cur),
        "status": "SUCESSO_CUR",
    }


def atualizar_dimensoes_cadastro(
    conn: sqlite3.Connection,
    cadastros_fornecedores: Optional[Sequence[Dict[str, Any]]] = None,
    cadastros_obras: Optional[Sequence[Dict[str, Any]]] = None,
    cadastros_insumos: Optional[Sequence[Dict[str, Any]]] = None,
    dt_atualizacao: str = "2026-10-18T08:00:00",
) -> Dict[str, int]:
    """
    Atualiza as dimensões de cadastro de forma acumulativa (Decisão D-39: Zero Órfãos):
    1. Faz UPSERT dos cadastros ativos enviados pelo ERP sem jamais apagar códigos históricos.
    2. Varre snap_desembolso_completo e cur_desembolso_atual em busca de chaves órfãs
       (fornecedores, obras ou insumos presentes no fato mas ausentes no cadastro)
       e insere membros de resgate ('RESGATE_FATO') para garantir integridade referencial de 100%.
    """
    cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    try:
        for f in cadastros_fornecedores or []:
            cur.execute(
                """
                INSERT INTO dim_fornecedor (
                    fornecedor_cod, razao_social, uf, origem_registro,
                    dt_primeira_carga, dt_ultima_atualizacao
                ) VALUES (?, ?, ?, 'CADASTRO_ERP', ?, ?)
                ON CONFLICT(fornecedor_cod) DO UPDATE SET
                    razao_social = excluded.razao_social,
                    uf = excluded.uf,
                    origem_registro = 'CADASTRO_ERP',
                    dt_ultima_atualizacao = excluded.dt_ultima_atualizacao
                """,
                (
                    int(f["fornecedor_cod"]),
                    str(f["razao_social"]).strip(),
                    str(f.get("uf", "GO")).strip().upper(),
                    dt_atualizacao,
                    dt_atualizacao,
                ),
            )

        for o in cadastros_obras or []:
            empresa = int(o["empresa_cod"])
            obra = str(o["obra_cod"]).strip().upper()
            chave_obra = f"{empresa}|{obra}"
            cur.execute(
                """
                INSERT INTO dim_obra (
                    chave_obra, empresa_cod, obra_cod, nome_obra, cidade, uf,
                    origem_registro, dt_ultima_atualizacao
                ) VALUES (?, ?, ?, ?, ?, ?, 'CADASTRO_ERP', ?)
                ON CONFLICT(chave_obra) DO UPDATE SET
                    nome_obra = excluded.nome_obra,
                    cidade = excluded.cidade,
                    uf = excluded.uf,
                    origem_registro = 'CADASTRO_ERP',
                    dt_ultima_atualizacao = excluded.dt_ultima_atualizacao
                """,
                (
                    chave_obra,
                    empresa,
                    obra,
                    str(o["nome_obra"]).strip(),
                    str(o.get("cidade", "Goiânia")).strip(),
                    str(o.get("uf", "GO")).strip().upper(),
                    dt_atualizacao,
                ),
            )

        for ins in cadastros_insumos or []:
            ins_cod = str(ins["insumo_cod"]).strip().upper()
            cur.execute(
                """
                INSERT INTO dim_insumo (
                    insumo_cod, descricao_insumo, grupo_insumo,
                    origem_registro, dt_ultima_atualizacao
                ) VALUES (?, ?, ?, 'CADASTRO_ERP', ?)
                ON CONFLICT(insumo_cod) DO UPDATE SET
                    descricao_insumo = excluded.descricao_insumo,
                    grupo_insumo = excluded.grupo_insumo,
                    origem_registro = 'CADASTRO_ERP',
                    dt_ultima_atualizacao = excluded.dt_ultima_atualizacao
                """,
                (
                    ins_cod,
                    str(ins["descricao_insumo"]).strip(),
                    str(ins.get("grupo_insumo", "GERAL")).strip().upper(),
                    dt_atualizacao,
                ),
            )

        # Resgate automático de fornecedores referenciados em snap ou cur mas ausentes em dim_fornecedor
        cur.execute(
            """
            INSERT INTO dim_fornecedor (
                fornecedor_cod, razao_social, uf, origem_registro,
                dt_primeira_carga, dt_ultima_atualizacao
            )
            SELECT DISTINCT
                f.fornecedor_cod,
                'FORNECEDOR HISTORICO #' || CAST(f.fornecedor_cod AS TEXT),
                'ND',
                'RESGATE_FATO',
                ?,
                ?
            FROM (
                SELECT fornecedor_cod FROM snap_desembolso_completo
                UNION
                SELECT fornecedor_cod FROM cur_desembolso_atual
            ) f
            LEFT JOIN dim_fornecedor d ON d.fornecedor_cod = f.fornecedor_cod
            WHERE d.fornecedor_cod IS NULL
            """,
            (dt_atualizacao, dt_atualizacao),
        )

        # Resgate automático de obras referenciadas em snap ou cur mas ausentes em dim_obra
        cur.execute(
            """
            INSERT INTO dim_obra (
                chave_obra, empresa_cod, obra_cod, nome_obra, cidade, uf,
                origem_registro, dt_ultima_atualizacao
            )
            SELECT DISTINCT
                f.chave_obra,
                f.empresa_cod,
                f.obra_cod,
                'OBRA HISTORICA ' || f.chave_obra,
                'NAO INFORMADA',
                'ND',
                'RESGATE_FATO',
                ?
            FROM (
                SELECT chave_obra, empresa_cod, obra_cod FROM snap_desembolso_completo
                UNION
                SELECT chave_obra, empresa_cod, obra_cod FROM cur_desembolso_atual
            ) f
            LEFT JOIN dim_obra d ON d.chave_obra = f.chave_obra
            WHERE d.chave_obra IS NULL
            """,
            (dt_atualizacao,),
        )

        # Resgate automático de insumos referenciados em snap ou cur mas ausentes em dim_insumo
        cur.execute(
            """
            INSERT INTO dim_insumo (
                insumo_cod, descricao_insumo, grupo_insumo,
                origem_registro, dt_ultima_atualizacao
            )
            SELECT DISTINCT
                f.insumo_cod,
                'INSUMO HISTORICO ' || f.insumo_cod,
                'HISTORICO_RESGATADO',
                'RESGATE_FATO',
                ?
            FROM (
                SELECT insumo_cod FROM snap_desembolso_completo
                UNION
                SELECT insumo_cod FROM cur_desembolso_atual
            ) f
            LEFT JOIN dim_insumo d ON d.insumo_cod = f.insumo_cod
            WHERE d.insumo_cod IS NULL
            """,
            (dt_atualizacao,),
        )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    tot_forn = cur.execute("SELECT COUNT(*) FROM dim_fornecedor").fetchone()[0]
    tot_obra = cur.execute("SELECT COUNT(*) FROM dim_obra").fetchone()[0]
    tot_ins = cur.execute("SELECT COUNT(*) FROM dim_insumo").fetchone()[0]

    return {
        "dim_fornecedor": tot_forn,
        "dim_obra": tot_obra,
        "dim_insumo": tot_ins,
    }


def auditar_orfaos_dimensoes(conn: sqlite3.Connection) -> Dict[str, int]:
    """
    Audita a quantidade de registros em snap_desembolso_completo e cur_desembolso_atual
    sem correspondência nas tabelas dim_fornecedor, dim_obra e dim_insumo.
    Deve retornar 0 em todas as dimensões (D-39).
    """
    cur = conn.cursor()
    orfaos_fornecedor = cur.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT fornecedor_cod FROM snap_desembolso_completo
            UNION ALL
            SELECT fornecedor_cod FROM cur_desembolso_atual
        ) f
        LEFT JOIN dim_fornecedor d ON d.fornecedor_cod = f.fornecedor_cod
        WHERE d.fornecedor_cod IS NULL
        """
    ).fetchone()[0]

    orfaos_obra = cur.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT chave_obra FROM snap_desembolso_completo
            UNION ALL
            SELECT chave_obra FROM cur_desembolso_atual
        ) f
        LEFT JOIN dim_obra d ON d.chave_obra = f.chave_obra
        WHERE d.chave_obra IS NULL
        """
    ).fetchone()[0]

    orfaos_insumo = cur.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT insumo_cod FROM snap_desembolso_completo
            UNION ALL
            SELECT insumo_cod FROM cur_desembolso_atual
        ) f
        LEFT JOIN dim_insumo d ON d.insumo_cod = f.insumo_cod
        WHERE d.insumo_cod IS NULL
        """
    ).fetchone()[0]

    return {
        "orfaos_fornecedor": int(orfaos_fornecedor),
        "orfaos_obra": int(orfaos_obra),
        "orfaos_insumo": int(orfaos_insumo),
        "total_orfaos": int(orfaos_fornecedor + orfaos_obra + orfaos_insumo),
    }


def _dias_entre(data_ant: Optional[str], data_atu: Optional[str]) -> Optional[int]:
    if not data_ant or not data_atu:
        return None
    d1 = datetime.strptime(data_ant, "%Y-%m-%d").date()
    d2 = datetime.strptime(data_atu, "%Y-%m-%d").date()
    return (d2 - d1).days


def _classificar_mudanca_registro(
    ant: Optional[Dict[str, Any]], atu: Optional[Dict[str, Any]]
) -> Optional[str]:
    """
    Classifica a mutação sofrida por uma fatia de rateio de parcela entre duas fotos:
    - INCLUIDA
    - EXCLUIDA
    - STATUS_ALTERADO
    - RECLASSIFICADA_RATEIO
    - VALOR_ALTERADO
    - VENCIMENTO_ALTERADO
    Retorna None caso o registro esteja idêntico nas duas fotos.
    """
    if ant is None and atu is not None:
        return "INCLUIDA"
    if ant is not None and atu is None:
        return "EXCLUIDA"
    assert ant is not None and atu is not None

    mudou_status = ant["status_parcela"] != atu["status_parcela"]
    mudou_rateio = (
        ant["cap_cod"] != atu["cap_cod"] or ant["insumo_cod"] != atu["insumo_cod"]
    )
    mudou_valor = round(float(ant["valor_fatia"]), 2) != round(
        float(atu["valor_fatia"]), 2
    )
    mudou_venc = ant["data_vencimento"] != atu["data_vencimento"]

    if not (mudou_status or mudou_rateio or mudou_valor or mudou_venc):
        return None

    # Ordem determinística de precedência analítica da Controladoria
    if mudou_status:
        return "STATUS_ALTERADO"
    if mudou_rateio:
        return "RECLASSIFICADA_RATEIO"
    if mudou_valor:
        return "VALOR_ALTERADO"
    return "VENCIMENTO_ALTERADO"


def calcular_mudanca_parcela(
    conn: sqlite3.Connection,
    modo: str = "snap",
    data_snapshot_atual: Optional[str] = None,
    data_snapshot_anterior: Optional[str] = None,
    dt_calculo: str = "2026-10-18T08:05:00",
) -> List[Dict[str, Any]]:
    """
    Motor de Diff de Parcelas e Fatias de Rateio (snap.mudanca_parcela e cur.mudanca_parcela).

    - modo='snap': Compara a foto T (data_snapshot_atual) contra T-1 (data_snapshot_anterior)
      e persiste os deltas em snap_mudanca_parcela.
    - modo='cur': Compara a camada operacional diária (cur_desembolso_atual) contra o
      último snapshot semanal consolidado em snap_desembolso_completo, persistindo em cur_mudanca_parcela.
    """
    cur = conn.cursor()

    if modo == "snap":
        fotos = [
            r[0]
            for r in cur.execute(
                "SELECT DISTINCT data_snapshot FROM snap_desembolso_completo ORDER BY data_snapshot ASC"
            ).fetchall()
        ]
        if len(fotos) < 2:
            return []

        if data_snapshot_atual is None:
            data_snapshot_atual = fotos[-1]
        if data_snapshot_anterior is None:
            idx = fotos.index(data_snapshot_atual)
            if idx == 0:
                return []
            data_snapshot_anterior = fotos[idx - 1]

        rows_ant = cur.execute(
            "SELECT * FROM snap_desembolso_completo WHERE data_snapshot = ?",
            (data_snapshot_anterior,),
        ).fetchall()
        rows_atu = cur.execute(
            "SELECT * FROM snap_desembolso_completo WHERE data_snapshot = ?",
            (data_snapshot_atual,),
        ).fetchall()
    elif modo == "cur":
        row_ult = cur.execute(
            "SELECT MAX(data_snapshot) AS max_snap FROM snap_desembolso_completo"
        ).fetchone()
        if not row_ult or not row_ult["max_snap"]:
            return []
        data_snapshot_anterior = row_ult["max_snap"]

        rows_ant = cur.execute(
            "SELECT * FROM snap_desembolso_completo WHERE data_snapshot = ?",
            (data_snapshot_anterior,),
        ).fetchall()
        rows_atu = cur.execute("SELECT * FROM cur_desembolso_atual").fetchall()
        data_snapshot_atual = (
            rows_atu[0]["dt_carga"] if rows_atu else dt_calculo
        )
    else:
        raise ValueError(f"Modo inválido para calcular_mudanca_parcela: {modo}")

    mapa_ant = {r["fatia_rateio_id"]: dict(r) for r in rows_ant}
    mapa_atu = {r["fatia_rateio_id"]: dict(r) for r in rows_atu}

    todas_fatias = sorted(set(mapa_ant.keys()) | set(mapa_atu.keys()))
    deltas: List[Dict[str, Any]] = []

    for fatia_id in todas_fatias:
        ant = mapa_ant.get(fatia_id)
        atu = mapa_atu.get(fatia_id)
        tipo = _classificar_mudanca_registro(ant, atu)
        if tipo is None:
            continue

        ref = atu if atu is not None else ant
        assert ref is not None

        val_ant = round(float(ant["valor_fatia"]), 2) if ant else None
        val_atu = round(float(atu["valor_fatia"]), 2) if atu else None
        delta_val = round((val_atu or 0.0) - (val_ant or 0.0), 2)

        venc_ant = ant["data_vencimento"] if ant else None
        venc_atu = atu["data_vencimento"] if atu else None
        dias_desl = _dias_entre(venc_ant, venc_atu)

        deltas.append(
            {
                "data_snapshot_anterior": data_snapshot_anterior,
                "data_snapshot_atual": data_snapshot_atual,
                "dt_calculo": dt_calculo,
                "parcela_id": ref["parcela_id"],
                "fatia_rateio_id": fatia_id,
                "chave_obra": ref["chave_obra"],
                "fornecedor_cod": int(ref["fornecedor_cod"]),
                "tipo_mudanca": tipo,
                "valor_anterior": val_ant,
                "valor_atual": val_atu,
                "delta_valor": delta_val,
                "vencimento_anterior": venc_ant,
                "vencimento_atual": venc_atu,
                "dias_deslocamento_vencimento": dias_desl,
                "status_anterior": ant["status_parcela"] if ant else None,
                "status_atual": atu["status_parcela"] if atu else None,
                "cap_anterior": ant["cap_cod"] if ant else None,
                "cap_atual": atu["cap_cod"] if atu else None,
                "insumo_anterior": ant["insumo_cod"] if ant else None,
                "insumo_atual": atu["insumo_cod"] if atu else None,
            }
        )

    cur.execute("BEGIN IMMEDIATE")
    try:
        if modo == "snap":
            cur.execute(
                """
                DELETE FROM snap_mudanca_parcela
                WHERE data_snapshot_anterior = ? AND data_snapshot_atual = ?
                """,
                (data_snapshot_anterior, data_snapshot_atual),
            )
            cur.executemany(
                """
                INSERT INTO snap_mudanca_parcela (
                    data_snapshot_anterior, data_snapshot_atual, dt_calculo,
                    parcela_id, fatia_rateio_id, chave_obra, fornecedor_cod,
                    tipo_mudanca, valor_anterior, valor_atual, delta_valor,
                    vencimento_anterior, vencimento_atual, dias_deslocamento_vencimento,
                    status_anterior, status_atual, cap_anterior, cap_atual,
                    insumo_anterior, insumo_atual
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        d["data_snapshot_anterior"],
                        d["data_snapshot_atual"],
                        d["dt_calculo"],
                        d["parcela_id"],
                        d["fatia_rateio_id"],
                        d["chave_obra"],
                        d["fornecedor_cod"],
                        d["tipo_mudanca"],
                        d["valor_anterior"],
                        d["valor_atual"],
                        d["delta_valor"],
                        d["vencimento_anterior"],
                        d["vencimento_atual"],
                        d["dias_deslocamento_vencimento"],
                        d["status_anterior"],
                        d["status_atual"],
                        d["cap_anterior"],
                        d["cap_atual"],
                        d["insumo_anterior"],
                        d["insumo_atual"],
                    )
                    for d in deltas
                ],
            )
        else:
            cur.execute("DELETE FROM cur_mudanca_parcela")
            cur.executemany(
                """
                INSERT INTO cur_mudanca_parcela (
                    data_snapshot_referencia, dt_carga_atual,
                    parcela_id, fatia_rateio_id, chave_obra, fornecedor_cod,
                    tipo_mudanca, valor_anterior, valor_atual, delta_valor,
                    vencimento_anterior, vencimento_atual, dias_deslocamento_vencimento,
                    status_anterior, status_atual, cap_anterior, cap_atual,
                    insumo_anterior, insumo_atual
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        d["data_snapshot_anterior"],
                        d["data_snapshot_atual"],
                        d["parcela_id"],
                        d["fatia_rateio_id"],
                        d["chave_obra"],
                        d["fornecedor_cod"],
                        d["tipo_mudanca"],
                        d["valor_anterior"],
                        d["valor_atual"],
                        d["delta_valor"],
                        d["vencimento_anterior"],
                        d["vencimento_atual"],
                        d["dias_deslocamento_vencimento"],
                        d["status_anterior"],
                        d["status_atual"],
                        d["cap_anterior"],
                        d["cap_atual"],
                        d["insumo_anterior"],
                        d["insumo_atual"],
                    )
                    for d in deltas
                ],
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return deltas


def consultar_total_desembolso_dax_guard(
    conn: sqlite3.Connection,
    data_snapshot: Optional[str] = None,
    usar_guarda: bool = True,
) -> float:
    """
    Emula o comportamento da Guarda de Snapshot nas medidas DAX (Armadilha 3 / Decisão D-21).
    - Se usar_guarda=False e data_snapshot=None, soma todas as fotos da tabela (inflando em N vezes).
    - Se usar_guarda=True e data_snapshot=None, fixa automaticamente na última foto MAX(data_snapshot).
    """
    cur = conn.cursor()
    if not usar_guarda and data_snapshot is None:
        row = cur.execute(
            "SELECT COALESCE(SUM(valor_fatia), 0.0) FROM snap_desembolso_completo"
        ).fetchone()
        return round(float(row[0]), 2)

    if data_snapshot is None:
        row_max = cur.execute(
            "SELECT MAX(data_snapshot) FROM snap_desembolso_completo"
        ).fetchone()
        data_snapshot = row_max[0] if row_max else None

    if not data_snapshot:
        return 0.0

    row = cur.execute(
        "SELECT COALESCE(SUM(valor_fatia), 0.0) FROM snap_desembolso_completo WHERE data_snapshot = ?",
        (data_snapshot,),
    ).fetchone()
    return round(float(row[0]), 2)
