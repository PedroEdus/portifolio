"""
Plataforma Lakehouse Medallion, Controle Transacional e Matriz Roll-Rate de Recebíveis.

Implementação demonstrativa executável (Python + DuckDB com fallback automático para SQLite)
que reproduz os padrões arquiteturais de produção desenvolvidos em Microsoft Fabric
(PySpark + Warehouse T-SQL `wh_ctl_inad` + Direct Lake + PBIR):

1. Controle Transacional (`ctl_rodada`, `ctl_carga_fonte`, `sp_abrir_rodada`,
   `sp_gate_consistencia`, `sp_fechar_rodada`).
2. Ingestão Staging-First Atômica (`stg_*` -> validação de contrato de schema +
   cobertura de chaves >= 99.5% entre ContasReceber e ContasReceberCalc +
   regra de dia 1 `aceitar_calc_defasada` -> promoção atômica para `bronze_*`).
3. Retenção de Foto Crua Mensal idempotente no dia 1 (`replaceWhere` por `data_foto`).
4. Camada Silver Declarativa (`snake_case` com prefixos semânticos, bloqueio de
   Schema Drift e garantia de `COUNT(Silver) == COUNT(Bronze)`).
5. Camada Gold Star Schema:
   - Atraso contratual (`dt_vencimento_original`) vs prorrogado (`dt_vencimento_atual`)
   - Separação de custas (`tipo_parcela = '1'`) vs parcelas contratuais (`tipo_parcela = '0'`)
   - Rastreio de cadeia de cessões (`TipoMnt = 2` para não inflar distratos)
   - Matriz de Transição Roll-Rate (M -> M+1) com precedência `cedido > cancelado > renegociado > pago > em_aberto`
   - Coorte de sobrevivência de renegociações
   - Prova de paridade 100% célula a célula entre query SQL pura na Bronze e tabela Gold.

AVISO DE CONFIDENCIALIDADE:
Todos os dados processados por este módulo são 100% sintéticos (`seed=42`).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import duckdb  # type: ignore

    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False


class LakehouseQualityGateError(RuntimeError):
    """Exceção disparada quando um Gate de Qualidade ou Contrato de Schema é violado."""


@dataclass
class RodadaStatus:
    id_rodada: int
    data_referencia: str
    status: str
    cobertura_calc_pct: float
    aceitar_calc_defasada: bool
    mensagem: str


class RelationalEngineAdapter:
    """
    Adaptador unificado sobre DuckDB (primário) com fallback transparente para SQLite.
    Garante execução 100% determinística em qualquer ambiente Python.
    """

    def __init__(self, prefer_duckdb: bool = True) -> None:
        self.engine_name = "duckdb" if (prefer_duckdb and HAS_DUCKDB) else "sqlite"
        if self.engine_name == "duckdb":
            self.conn = duckdb.connect(":memory:")
        else:
            self.conn = sqlite3.connect(":memory:")

    def execute(self, sql: str, params: Tuple[Any, ...] = ()) -> None:
        if self.engine_name == "duckdb":
            if params:
                self.conn.execute(sql, list(params))
            else:
                self.conn.execute(sql)
        else:
            self.conn.execute(sql, params)
            self.conn.commit()

    def register_df(self, table_name: str, df: pd.DataFrame) -> None:
        if self.engine_name == "duckdb":
            self.conn.register(f"_tmp_{table_name}", df)
            self.conn.execute(
                f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _tmp_{table_name}"
            )
            self.conn.unregister(f"_tmp_{table_name}")
        else:
            df.to_sql(table_name, self.conn, if_exists="replace", index=False)

    def query_df(self, sql: str) -> pd.DataFrame:
        if self.engine_name == "duckdb":
            return self.conn.execute(sql).df()
        return pd.read_sql_query(sql, self.conn)

    def table_exists(self, table_name: str) -> bool:
        if self.engine_name == "duckdb":
            res = self.conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                [table_name],
            ).fetchone()
            return bool(res and res[0] > 0)
        res = self.conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return bool(res and res[0] > 0)


class LakehouseRecebiveisPipeline:
    """
    Orquestrador Medallion (Staging -> Bronze -> Silver -> Gold) com controle
    transacional inspirado no Warehouse T-SQL `wh_ctl_inad`.
    """

    EXPECTED_CONTRACTS: Dict[str, List[str]] = {
        "contas_receber": [
            "DataFoto",
            "Empresa_prc",
            "Obra_prc",
            "NumVend_prc",
            "NumParc_prc",
            "ChaveParcela",
            "TipoParc_prc",
            "DtVencOrig_prc",
            "DtVencAtu_prc",
            "ValorNom_prc",
            "Status_prc",
            "DataBaixa_prc",
            "FlagReneg_prc",
            "FlagCancel_prc",
            "SafraReneg",
        ],
        "contas_receber_calc": [
            "DataFoto",
            "ChaveParcela",
            "Empresa_crc",
            "Obra_crc",
            "NumVend_crc",
            "NumParc_crc",
            "VlrPrincipal_crc",
            "VlrJuros_crc",
            "VlrTotalCalc_crc",
            "DtCalculo_crc",
        ],
        "cessoes": [
            "Empresa_mnt",
            "Obra_mnt",
            "NumVendOrig_mnt",
            "NumVendNovo_mnt",
            "TipoMnt",
            "DataCessao",
            "ChaveParcela",
        ],
        "distratos": [
            "Empresa_dis",
            "Obra_dis",
            "NumVend_dis",
            "DataDistrato",
            "Motivo_dis",
            "ValorDistratado",
        ],
    }

    SILVER_DECLARATIVE_MAPPING: Dict[str, str] = {
        "DataFoto": "dt_foto",
        "Empresa_prc": "cod_empresa",
        "Obra_prc": "cod_obra",
        "NumVend_prc": "num_venda",
        "NumParc_prc": "num_parcela",
        "ChaveParcela": "id_chave_parcela",
        "TipoParc_prc": "cod_tipo_parcela",
        "DtVencOrig_prc": "dt_vencimento_original",
        "DtVencAtu_prc": "dt_vencimento_atual",
        "ValorNom_prc": "vlr_nominal",
        "Status_prc": "desc_status_parcela",
        "DataBaixa_prc": "dt_baixa",
        "FlagReneg_prc": "flg_renegociado",
        "FlagCancel_prc": "flg_cancelado",
        "SafraReneg": "cod_safra_renegociacao",
    }

    def __init__(
        self,
        min_coverage_pct: float = 99.5,
        prefer_duckdb: bool = True,
    ) -> None:
        self.min_coverage_pct = min_coverage_pct
        self.db = RelationalEngineAdapter(prefer_duckdb=prefer_duckdb)
        self._next_rodada_id = 1
        self._init_control_tables()

    def _init_control_tables(self) -> None:
        """Inicializa as tabelas de controle transacional equivalentes ao `wh_ctl_inad`."""
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS ctl_rodada (
                id_rodada INTEGER,
                data_referencia VARCHAR,
                aceitar_calc_defasada INTEGER,
                status_rodada VARCHAR,
                cobertura_calc_pct DOUBLE,
                ts_abertura VARCHAR,
                ts_fechamento VARCHAR,
                mensagem_auditoria VARCHAR
            )
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS ctl_carga_fonte (
                id_rodada INTEGER,
                nome_tabela VARCHAR,
                camada VARCHAR,
                qtd_registros INTEGER,
                status_validacao VARCHAR,
                detalhe VARCHAR,
                ts_registro VARCHAR
            )
            """
        )

    # =========================================================================
    # a) Controle Transacional (`sp_abrir_rodada`, `sp_gate_consistencia`, `sp_fechar_rodada`)
    # =========================================================================
    def sp_abrir_rodada(
        self, data_referencia: str, aceitar_calc_defasada: Optional[bool] = None
    ) -> int:
        """
        Abre uma nova rodada de carga transacional.
        Se `aceitar_calc_defasada` não for informado explicitamente, ativa automaticamente
        no dia 1 do mês (quando a tabela de cálculo reajustado pode estar em fechamento contábil).
        """
        dt_obj = datetime.strptime(data_referencia, "%Y-%m-%d").date()
        if aceitar_calc_defasada is None:
            aceitar_calc_defasada = dt_obj.day == 1

        id_rodada = self._next_rodada_id
        self._next_rodada_id += 1
        now_iso = datetime.now(timezone.utc).isoformat()

        self.db.execute(
            """
            INSERT INTO ctl_rodada (
                id_rodada, data_referencia, aceitar_calc_defasada,
                status_rodada, cobertura_calc_pct, ts_abertura, ts_fechamento, mensagem_auditoria
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_rodada,
                data_referencia,
                1 if aceitar_calc_defasada else 0,
                "ABERTA",
                0.0,
                now_iso,
                None,
                "Rodada iniciada em modo Staging-First.",
            ),
        )
        return id_rodada

    def _log_carga_fonte(
        self,
        id_rodada: int,
        nome_tabela: str,
        camada: str,
        qtd_registros: int,
        status_validacao: str,
        detalhe: str,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """
            INSERT INTO ctl_carga_fonte (
                id_rodada, nome_tabela, camada, qtd_registros, status_validacao, detalhe, ts_registro
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_rodada,
                nome_tabela,
                camada,
                int(qtd_registros),
                status_validacao,
                detalhe,
                now_iso,
            ),
        )

    def sp_gate_consistencia(
        self, id_rodada: int, aceitar_calc_defasada: bool
    ) -> Tuple[bool, float, str]:
        """
        Executa o Gate de Consistência Transacional sobre as tabelas `stg_*`:
        - Verifica a cobertura de chaves (`ChaveParcela` + `DataFoto`) entre
          `stg_contas_receber` e `stg_contas_receber_calc`.
        - Exige cobertura >= `self.min_coverage_pct` (99.5%), exceto quando a regra
          de dia 1 (`aceitar_calc_defasada=True`) estiver explicitamente ativa e a
          defasagem for somente de data de cálculo, preservando a cobertura mínima ou
          registrando a ressalva auditada.
        """
        df_cov = self.db.query_df(
            """
            SELECT
                COUNT(*) AS total_receber,
                SUM(CASE WHEN c.ChaveParcela IS NOT NULL THEN 1 ELSE 0 END) AS total_pareado,
                SUM(
                    CASE
                        WHEN c.ChaveParcela IS NOT NULL AND c.DtCalculo_crc = r.DataFoto THEN 1
                        ELSE 0
                    END
                ) AS total_calculo_no_dia
            FROM stg_contas_receber r
            LEFT JOIN stg_contas_receber_calc c
              ON r.ChaveParcela = c.ChaveParcela
             AND r.DataFoto = c.DataFoto
            """
        )
        total_receber = int(df_cov["total_receber"].iloc[0] or 0)
        total_pareado = int(df_cov["total_pareado"].iloc[0] or 0)
        total_no_dia = int(df_cov["total_calculo_no_dia"].iloc[0] or 0)

        if total_receber == 0:
            return False, 0.0, "Tabela stg_contas_receber vazia."

        cobertura_chaves_pct = round((total_pareado / total_receber) * 100.0, 4)
        cobertura_no_dia_pct = round((total_no_dia / total_receber) * 100.0, 4)

        if cobertura_chaves_pct < self.min_coverage_pct:
            msg = (
                f"BLOQUEADO: Cobertura de chaves ContasReceber vs Calc ({cobertura_chaves_pct:.2f}%) "
                f"abaixo do mínimo exigido ({self.min_coverage_pct:.2f}%)."
            )
            return False, cobertura_chaves_pct, msg

        if cobertura_no_dia_pct < self.min_coverage_pct and not aceitar_calc_defasada:
            msg = (
                f"BLOQUEADO: Cobertura de cálculo atualizado no dia ({cobertura_no_dia_pct:.2f}%) "
                f"abaixo de {self.min_coverage_pct:.2f}% e aceitar_calc_defasada=False."
            )
            return False, cobertura_no_dia_pct, msg

        msg = (
            f"APROVADO: Cobertura de chaves={cobertura_chaves_pct:.2f}% "
            f"(cálculo no dia={cobertura_no_dia_pct:.2f}%, aceitar_calc_defasada={aceitar_calc_defasada})."
        )
        return True, cobertura_chaves_pct, msg

    def sp_fechar_rodada(
        self, id_rodada: int, aprovado: bool, cobertura_pct: float, mensagem: str
    ) -> RodadaStatus:
        now_iso = datetime.now(timezone.utc).isoformat()
        novo_status = "PUBLICADA" if aprovado else "ABORTADA_QUARENTENA"
        self.db.execute(
            """
            UPDATE ctl_rodada
               SET status_rodada = ?,
                   cobertura_calc_pct = ?,
                   ts_fechamento = ?,
                   mensagem_auditoria = ?
             WHERE id_rodada = ?
            """,
            (novo_status, float(cobertura_pct), now_iso, mensagem, id_rodada),
        )
        df_r = self.db.query_df(
            f"SELECT * FROM ctl_rodada WHERE id_rodada = {int(id_rodada)}"
        )
        row = df_r.iloc[0]
        return RodadaStatus(
            id_rodada=int(row["id_rodada"]),
            data_referencia=str(row["data_referencia"]),
            status=str(row["status_rodada"]),
            cobertura_calc_pct=float(row["cobertura_calc_pct"]),
            aceitar_calc_defasada=bool(row["aceitar_calc_defasada"]),
            mensagem=str(row["mensagem_auditoria"]),
        )

    # =========================================================================
    # b) Ingestão Staging-First Atômica + c) Foto Crua Mensal Idempotente (Dia 1)
    # =========================================================================
    def validate_schema_contract(
        self, table_key: str, df: pd.DataFrame, id_rodada: int
    ) -> None:
        expected = self.EXPECTED_CONTRACTS[table_key]
        actual = list(df.columns)
        missing = [c for c in expected if c not in actual]
        unexpected = [c for c in actual if c not in expected]
        if missing or unexpected:
            detalhe = f"Schema Drift detectado em '{table_key}': ausentes={missing}, inesperadas={unexpected}"
            self._log_carga_fonte(
                id_rodada,
                f"stg_{table_key}",
                "STAGING",
                len(df),
                "FALHA_SCHEMA_DRIFT",
                detalhe,
            )
            self.sp_fechar_rodada(id_rodada, False, 0.0, detalhe)
            raise LakehouseQualityGateError(detalhe)

    def ingest_staging_and_promote_to_bronze(
        self,
        datasets: Dict[str, pd.DataFrame],
        data_referencia: str,
        aceitar_calc_defasada: Optional[bool] = None,
    ) -> RodadaStatus:
        """
        Carrega os DataFrames em tabelas `stg_*`, valida o contrato de colunas (bloqueando
        Schema Drift), executa `sp_gate_consistencia` e, somente se aprovado, promove
        atomicamente para `bronze_*`. Se a rodada falhar, `bronze_*` permanece intacta.
        """
        dt_obj = datetime.strptime(data_referencia, "%Y-%m-%d").date()
        if aceitar_calc_defasada is None:
            aceitar_calc_defasada = dt_obj.day == 1

        id_rodada = self.sp_abrir_rodada(
            data_referencia=data_referencia,
            aceitar_calc_defasada=aceitar_calc_defasada,
        )

        # 1. Validar contrato de schema e gravar em stg_*
        for key in ("contas_receber", "contas_receber_calc", "cessoes", "distratos"):
            if key not in datasets:
                raise LakehouseQualityGateError(f"Fonte obrigatória ausente: {key}")
            df_src = datasets[key]
            self.validate_schema_contract(key, df_src, id_rodada)
            self.db.register_df(f"stg_{key}", df_src)
            self._log_carga_fonte(
                id_rodada,
                f"stg_{key}",
                "STAGING",
                len(df_src),
                "VALIDADO",
                "Contrato de schema 100% aderente.",
            )

        # 2. Gate de Consistência Transacional
        aprovado, cobertura_pct, msg = self.sp_gate_consistencia(
            id_rodada, aceitar_calc_defasada=bool(aceitar_calc_defasada)
        )
        if not aprovado:
            self.sp_fechar_rodada(id_rodada, False, cobertura_pct, msg)
            raise LakehouseQualityGateError(msg)

        # 3. Promoção Atômica para Bronze
        for key in ("contas_receber", "contas_receber_calc", "cessoes", "distratos"):
            df_stg = self.db.query_df(f"SELECT * FROM stg_{key}")
            self.db.register_df(f"bronze_{key}", df_stg)
            self._log_carga_fonte(
                id_rodada,
                f"bronze_{key}",
                "BRONZE",
                len(df_stg),
                "PROMOVIDO",
                "Promoção atômica Staging -> Bronze concluída.",
            )

        # 4. Se for dia 1 do mês, reter Foto Crua Mensal com semântica idempotente `replaceWhere` por `data_foto`
        if dt_obj.day == 1:
            self.retain_monthly_snapshot_idempotent(data_foto=data_referencia)

        return self.sp_fechar_rodada(id_rodada, True, cobertura_pct, msg)

    def retain_monthly_snapshot_idempotent(self, data_foto: str) -> int:
        """
        Retém a foto crua mensal do dia 1 (`bronze_foto_mensal_recebiveis`) aplicando
        semântica idempotente de `replaceWhere` pela partição `DataFoto = data_foto`.
        Reexecuções para a mesma `data_foto` substituem a partição sem duplicar linhas.
        """
        df_partition = self.db.query_df(
            f"SELECT * FROM bronze_contas_receber WHERE DataFoto = '{data_foto}'"
        )
        if not self.db.table_exists("bronze_foto_mensal_recebiveis"):
            self.db.register_df("bronze_foto_mensal_recebiveis", df_partition)
        else:
            # Emula Delta Lake `.option("replaceWhere", f"DataFoto = '{data_foto}'")`
            self.db.execute(
                "DELETE FROM bronze_foto_mensal_recebiveis WHERE DataFoto = ?",
                (data_foto,),
            )
            df_existing = self.db.query_df("SELECT * FROM bronze_foto_mensal_recebiveis")
            df_combined = pd.concat([df_existing, df_partition], ignore_index=True)
            self.db.register_df("bronze_foto_mensal_recebiveis", df_combined)

        df_count = self.db.query_df(
            f"SELECT COUNT(*) AS cnt FROM bronze_foto_mensal_recebiveis WHERE DataFoto = '{data_foto}'"
        )
        return int(df_count["cnt"].iloc[0])

    # =========================================================================
    # d) Camada Silver Declarativa (`snake_case` + bloqueio de Drift + `COUNT(Silver) == COUNT(Bronze)`)
    # =========================================================================
    def build_silver_layer(self) -> Dict[str, int]:
        """
        Constrói as tabelas da camada Silver a partir da Bronze com mapeamento declarativo
        `snake_case`, prefixos semânticos (`cod_`, `num_`, `dt_`, `vlr_`, `flg_`) e
        verificação estrita de conservação de cardinalidade (`COUNT(Silver) == COUNT(Bronze)`).
        """
        df_bronze_cr = self.db.query_df("SELECT * FROM bronze_contas_receber")
        for src_col in self.SILVER_DECLARATIVE_MAPPING:
            if src_col not in df_bronze_cr.columns:
                raise LakehouseQualityGateError(
                    f"Coluna esperada ausente na Bronze para Silver declarativa: {src_col}"
                )

        df_silver_cr = df_bronze_cr.rename(columns=self.SILVER_DECLARATIVE_MAPPING).copy()
        df_silver_cr["flg_custa"] = (
            df_silver_cr["cod_tipo_parcela"].astype(str) == "1"
        ).astype(int)

        # Enriquecimento com valores calculados da Bronze Calc sem perda de linhas
        df_bronze_calc = self.db.query_df(
            """
            SELECT
                DataFoto AS dt_foto,
                ChaveParcela AS id_chave_parcela,
                VlrPrincipal_crc AS vlr_principal_calc,
                VlrJuros_crc AS vlr_juros_calc,
                VlrTotalCalc_crc AS vlr_total_corrigido,
                DtCalculo_crc AS dt_calculo_ref
            FROM bronze_contas_receber_calc
            """
        )
        df_silver_cr = df_silver_cr.merge(
            df_bronze_calc,
            on=["dt_foto", "id_chave_parcela"],
            how="left",
        )
        df_silver_cr["vlr_total_corrigido"] = df_silver_cr[
            "vlr_total_corrigido"
        ].fillna(df_silver_cr["vlr_nominal"])

        # Cessões e Distratos na Silver
        df_silver_cessoes = self.db.query_df(
            """
            SELECT
                Empresa_mnt AS cod_empresa,
                Obra_mnt AS cod_obra,
                NumVendOrig_mnt AS num_venda_origem,
                NumVendNovo_mnt AS num_venda_destino,
                TipoMnt AS cod_tipo_manutencao,
                DataCessao AS dt_cessao,
                ChaveParcela AS id_chave_parcela
            FROM bronze_cessoes
            """
        )

        df_silver_distratos = self.db.query_df(
            """
            SELECT
                Empresa_dis AS cod_empresa,
                Obra_dis AS cod_obra,
                NumVend_dis AS num_venda,
                DataDistrato AS dt_distrato,
                Motivo_dis AS desc_motivo_distrato,
                ValorDistratado AS vlr_distratado
            FROM bronze_distratos
            """
        )

        self.db.register_df("silver_contas_receber", df_silver_cr)
        self.db.register_df("silver_cessoes", df_silver_cessoes)
        self.db.register_df("silver_distratos", df_silver_distratos)

        # Gate de conservação de registros Bronze -> Silver
        cnt_bronze = len(df_bronze_cr)
        cnt_silver = len(
            self.db.query_df("SELECT * FROM silver_contas_receber")
        )
        if cnt_silver != cnt_bronze:
            raise LakehouseQualityGateError(
                f"Violação de cardinalidade Silver vs Bronze: Silver={cnt_silver} != Bronze={cnt_bronze}"
            )

        return {
            "silver_contas_receber": cnt_silver,
            "silver_cessoes": len(df_silver_cessoes),
            "silver_distratos": len(df_silver_distratos),
        }

    # =========================================================================
    # e) Camada Gold Star Schema: Atraso Contratual vs Prorrogado, Custas, Cessões,
    #    Matriz Roll-Rate (M -> M+1) e Coorte de Sobrevivência de Renegociações
    # =========================================================================
    @staticmethod
    def _classify_aging_bucket(dias_atraso: int) -> str:
        if dias_atraso <= 0:
            return "00_A_VENCER"
        if dias_atraso <= 30:
            return "01_001_030"
        if dias_atraso <= 60:
            return "02_031_060"
        if dias_atraso <= 90:
            return "03_061_090"
        if dias_atraso <= 180:
            return "04_091_180"
        return "05_MAIOR_180"

    def build_gold_layer(
        self, data_foto_m: str = "2026-01-01", data_foto_m1: str = "2026-02-01"
    ) -> Dict[str, pd.DataFrame]:
        """
        Constrói as tabelas analíticas do Gold Star Schema:
        1. `gold_fato_carteira_recebiveis`: cálculo duplo de aging (contratual vs prorrogado),
           separação de custas (`flg_custa = 1`) e marcação de cessões (`TipoMnt = 2`).
        2. `gold_fato_distratos_auditados`: expurga transferências de titularidade/cessões
           (`TipoMnt = 2`) para não inflar o indicador de distratos reais.
        3. `gold_matriz_roll_rate`: matriz de transição M -> M+1 com precedência determinística
           `cedido > cancelado > renegociado > pago > em_aberto`.
        4. `gold_coorte_renegociacao`: análise de sobrevivência das safras renegociadas.
        """
        df_silver = self.db.query_df("SELECT * FROM silver_contas_receber")
        df_cessoes = self.db.query_df(
            "SELECT DISTINCT id_chave_parcela, num_venda_origem, cod_empresa, cod_obra "
            "FROM silver_cessoes WHERE cod_tipo_manutencao = 2"
        )
        chaves_cedidas = set(df_cessoes["id_chave_parcela"].unique())
        vendas_cedidas = set(
            zip(
                df_cessoes["cod_empresa"],
                df_cessoes["cod_obra"],
                df_cessoes["num_venda_origem"],
            )
        )

        # 1. Fato Carteira de Recebíveis (Gold)
        dt_foto_series = pd.to_datetime(df_silver["dt_foto"])
        dt_venc_orig = pd.to_datetime(df_silver["dt_vencimento_original"])
        dt_venc_atu = pd.to_datetime(df_silver["dt_vencimento_atual"])

        df_gold_carteira = df_silver.copy()
        df_gold_carteira["dias_atraso_contratual"] = (
            dt_foto_series - dt_venc_orig
        ).dt.days.astype(int)
        df_gold_carteira["dias_atraso_prorrogado"] = (
            dt_foto_series - dt_venc_atu
        ).dt.days.astype(int)

        df_gold_carteira["faixa_atraso_contratual"] = df_gold_carteira[
            "dias_atraso_contratual"
        ].apply(self._classify_aging_bucket)
        df_gold_carteira["faixa_atraso_prorrogado"] = df_gold_carteira[
            "dias_atraso_prorrogado"
        ].apply(self._classify_aging_bucket)

        df_gold_carteira["flg_cedido"] = (
            df_gold_carteira["id_chave_parcela"].isin(chaves_cedidas).astype(int)
        )

        # Precedência canônica de status: cedido > cancelado > renegociado > pago > em_aberto
        def resolve_canonical_status(row: pd.Series) -> str:
            if int(row["flg_cedido"]) == 1:
                return "cedido"
            if (
                int(row["flg_cancelado"]) == 1
                or str(row["desc_status_parcela"]).upper() == "CANCELADO"
            ):
                return "cancelado"
            if (
                int(row["flg_renegociado"]) == 1
                or str(row["desc_status_parcela"]).upper() == "RENEGOCIADO"
            ):
                return "renegociado"
            if str(row["desc_status_parcela"]).upper() == "PAGO":
                return "pago"
            return "em_aberto"

        df_gold_carteira["status_canonico"] = df_gold_carteira.apply(
            resolve_canonical_status, axis=1
        )
        self.db.register_df("gold_fato_carteira_recebiveis", df_gold_carteira)

        # 2. Fato Distratos Auditados (Gold) - Exclui vendas com TipoMnt = 2 (Cessão de Direitos)
        df_distratos = self.db.query_df("SELECT * FROM silver_distratos")
        df_distratos["flg_excluido_por_cessao"] = df_distratos.apply(
            lambda r: 1
            if (r["cod_empresa"], r["cod_obra"], r["num_venda"]) in vendas_cedidas
            else 0,
            axis=1,
        )
        df_gold_distratos = df_distratos[
            df_distratos["flg_excluido_por_cessao"] == 0
        ].copy()
        self.db.register_df("gold_fato_distratos_auditados", df_gold_distratos)

        # 3. Matriz de Transição Roll-Rate (M -> M+1) para parcelas contratuais (flg_custa = 0)
        df_m = df_gold_carteira[
            (df_gold_carteira["dt_foto"] == data_foto_m)
            & (df_gold_carteira["flg_custa"] == 0)
            & (df_gold_carteira["status_canonico"] == "em_aberto")
        ][
            [
                "id_chave_parcela",
                "cod_empresa",
                "faixa_atraso_contratual",
                "vlr_total_corrigido",
            ]
        ].rename(
            columns={
                "faixa_atraso_contratual": "faixa_origem_m",
                "vlr_total_corrigido": "vlr_saldo_m",
            }
        )

        df_m1 = df_gold_carteira[
            (df_gold_carteira["dt_foto"] == data_foto_m1)
            & (df_gold_carteira["flg_custa"] == 0)
        ][
            [
                "id_chave_parcela",
                "status_canonico",
                "faixa_atraso_contratual",
                "vlr_total_corrigido",
            ]
        ].rename(
            columns={
                "status_canonico": "status_destino_m1",
                "faixa_atraso_contratual": "faixa_destino_m1",
                "vlr_total_corrigido": "vlr_saldo_m1",
            }
        )

        df_trans = df_m.merge(df_m1, on="id_chave_parcela", how="inner")
        df_trans["estado_destino_roll_rate"] = np.where(
            df_trans["status_destino_m1"] == "em_aberto",
            "em_aberto:" + df_trans["faixa_destino_m1"],
            df_trans["status_destino_m1"],
        )

        df_roll_rate = (
            df_trans.groupby(
                ["faixa_origem_m", "status_destino_m1", "estado_destino_roll_rate"],
                as_index=False,
            )
            .agg(
                qtd_parcelas=("id_chave_parcela", "count"),
                vlr_base_origem_m=("vlr_saldo_m", "sum"),
                vlr_remanescente_m1=("vlr_saldo_m1", "sum"),
            )
            .sort_values(
                ["faixa_origem_m", "status_destino_m1", "estado_destino_roll_rate"]
            )
            .reset_index(drop=True)
        )
        df_roll_rate["vlr_base_origem_m"] = df_roll_rate["vlr_base_origem_m"].round(2)
        df_roll_rate["vlr_remanescente_m1"] = df_roll_rate[
            "vlr_remanescente_m1"
        ].round(2)

        totais_faixa = df_roll_rate.groupby("faixa_origem_m")["qtd_parcelas"].transform(
            "sum"
        )
        df_roll_rate["taxa_transicao_qtd_pct"] = (
            (df_roll_rate["qtd_parcelas"] / totais_faixa) * 100.0
        ).round(2)

        self.db.register_df("gold_matriz_roll_rate", df_roll_rate)

        # 4. Coorte de Sobrevivência de Renegociações
        df_coorte_base = df_gold_carteira[
            (df_gold_carteira["dt_foto"] == data_foto_m1)
            & (df_gold_carteira["cod_safra_renegociacao"].notna())
            & (df_gold_carteira["flg_custa"] == 0)
        ].copy()
        df_coorte = (
            df_coorte_base.groupby("cod_safra_renegociacao", as_index=False)
            .agg(
                total_parcelas_safra=("id_chave_parcela", "count"),
                parcelas_adimplentes_ou_pagas=(
                    "status_canonico",
                    lambda s: int(
                        sum(
                            (s == "pago")
                            | (
                                (s == "em_aberto")
                                & (
                                    df_coorte_base.loc[
                                        s.index, "dias_atraso_contratual"
                                    ]
                                    <= 30
                                )
                            )
                        )
                    ),
                ),
                vlr_total_safra=("vlr_nominal", "sum"),
            )
            .sort_values("cod_safra_renegociacao")
            .reset_index(drop=True)
        )
        df_coorte["vlr_total_safra"] = df_coorte["vlr_total_safra"].round(2)
        df_coorte["taxa_sobrevivencia_pct"] = (
            (
                df_coorte["parcelas_adimplentes_ou_pagas"]
                / df_coorte["total_parcelas_safra"]
            )
            * 100.0
        ).round(2)
        self.db.register_df("gold_coorte_renegociacao", df_coorte)

        return {
            "gold_fato_carteira_recebiveis": df_gold_carteira,
            "gold_fato_distratos_auditados": df_gold_distratos,
            "gold_matriz_roll_rate": df_roll_rate,
            "gold_coorte_renegociacao": df_coorte,
        }

    # =========================================================================
    # Prova de Paridade 100% Célula a Célula: Query SQL Pura sobre Bronze vs Gold
    # =========================================================================
    def verify_bronze_to_gold_parity(
        self, data_foto_m: str = "2026-01-01", data_foto_m1: str = "2026-02-01"
    ) -> Tuple[bool, pd.DataFrame, pd.DataFrame]:
        """
        Executa uma consulta SQL pura diretamente sobre as tabelas `bronze_*` para
        recalcular a Matriz de Transição Roll-Rate e confronta célula a célula contra
        a tabela `gold_matriz_roll_rate`.
        """
        if self.db.engine_name == "duckdb":
            date_diff_expr_m = " CAST(r.DataFoto AS DATE) - CAST(r.DtVencOrig_prc AS DATE) "
            date_diff_expr_m1 = " CAST(r1.DataFoto AS DATE) - CAST(r1.DtVencOrig_prc AS DATE) "
        else:
            date_diff_expr_m = " CAST(julianday(r.DataFoto) - julianday(r.DtVencOrig_prc) AS INTEGER) "
            date_diff_expr_m1 = " CAST(julianday(r1.DataFoto) - julianday(r1.DtVencOrig_prc) AS INTEGER) "

        pure_bronze_sql = f"""
        WITH cessoes_ativas AS (
            SELECT DISTINCT ChaveParcela
            FROM bronze_cessoes
            WHERE TipoMnt = 2
        ),
        base_m AS (
            SELECT
                r.ChaveParcela AS id_chave_parcela,
                COALESCE(c.VlrTotalCalc_crc, r.ValorNom_prc) AS vlr_saldo_m,
                CASE
                    WHEN ({date_diff_expr_m}) <= 0 THEN '00_A_VENCER'
                    WHEN ({date_diff_expr_m}) <= 30 THEN '01_001_030'
                    WHEN ({date_diff_expr_m}) <= 60 THEN '02_031_060'
                    WHEN ({date_diff_expr_m}) <= 90 THEN '03_061_090'
                    WHEN ({date_diff_expr_m}) <= 180 THEN '04_091_180'
                    ELSE '05_MAIOR_180'
                END AS faixa_origem_m
            FROM bronze_contas_receber r
            LEFT JOIN bronze_contas_receber_calc c
              ON r.ChaveParcela = c.ChaveParcela
             AND r.DataFoto = c.DataFoto
            LEFT JOIN cessoes_ativas cs
              ON r.ChaveParcela = cs.ChaveParcela
            WHERE r.DataFoto = '{data_foto_m}'
              AND CAST(r.TipoParc_prc AS VARCHAR) != '1'
              AND cs.ChaveParcela IS NULL
              AND r.FlagCancel_prc = 0
              AND r.FlagReneg_prc = 0
              AND UPPER(r.Status_prc) = 'EM_ABERTO'
        ),
        base_m1 AS (
            SELECT
                r1.ChaveParcela AS id_chave_parcela,
                COALESCE(c1.VlrTotalCalc_crc, r1.ValorNom_prc) AS vlr_saldo_m1,
                CASE
                    WHEN cs1.ChaveParcela IS NOT NULL THEN 'cedido'
                    WHEN r1.FlagCancel_prc = 1 OR UPPER(r1.Status_prc) = 'CANCELADO' THEN 'cancelado'
                    WHEN r1.FlagReneg_prc = 1 OR UPPER(r1.Status_prc) = 'RENEGOCIADO' THEN 'renegociado'
                    WHEN UPPER(r1.Status_prc) = 'PAGO' THEN 'pago'
                    ELSE 'em_aberto'
                END AS status_destino_m1,
                CASE
                    WHEN ({date_diff_expr_m1}) <= 0 THEN '00_A_VENCER'
                    WHEN ({date_diff_expr_m1}) <= 30 THEN '01_001_030'
                    WHEN ({date_diff_expr_m1}) <= 60 THEN '02_031_060'
                    WHEN ({date_diff_expr_m1}) <= 90 THEN '03_061_090'
                    WHEN ({date_diff_expr_m1}) <= 180 THEN '04_091_180'
                    ELSE '05_MAIOR_180'
                END AS faixa_destino_m1
            FROM bronze_contas_receber r1
            LEFT JOIN bronze_contas_receber_calc c1
              ON r1.ChaveParcela = c1.ChaveParcela
             AND r1.DataFoto = c1.DataFoto
            LEFT JOIN cessoes_ativas cs1
              ON r1.ChaveParcela = cs1.ChaveParcela
            WHERE r1.DataFoto = '{data_foto_m1}'
              AND CAST(r1.TipoParc_prc AS VARCHAR) != '1'
        ),
        joined AS (
            SELECT
                m.faixa_origem_m,
                m1.status_destino_m1,
                CASE
                    WHEN m1.status_destino_m1 = 'em_aberto' THEN 'em_aberto:' || m1.faixa_destino_m1
                    ELSE m1.status_destino_m1
                END AS estado_destino_roll_rate,
                m.id_chave_parcela,
                m.vlr_saldo_m,
                m1.vlr_saldo_m1
            FROM base_m m
            INNER JOIN base_m1 m1
              ON m.id_chave_parcela = m1.id_chave_parcela
        )
        SELECT
            faixa_origem_m,
            status_destino_m1,
            estado_destino_roll_rate,
            COUNT(id_chave_parcela) AS qtd_parcelas,
            ROUND(SUM(vlr_saldo_m), 2) AS vlr_base_origem_m,
            ROUND(SUM(vlr_saldo_m1), 2) AS vlr_remanescente_m1
        FROM joined
        GROUP BY
            faixa_origem_m,
            status_destino_m1,
            estado_destino_roll_rate
        ORDER BY
            faixa_origem_m,
            status_destino_m1,
            estado_destino_roll_rate
        """

        df_sql_bronze = self.db.query_df(pure_bronze_sql)
        totais_sql = df_sql_bronze.groupby("faixa_origem_m")["qtd_parcelas"].transform(
            "sum"
        )
        df_sql_bronze["taxa_transicao_qtd_pct"] = (
            (df_sql_bronze["qtd_parcelas"] / totais_sql) * 100.0
        ).round(2)

        df_gold = (
            self.db.query_df("SELECT * FROM gold_matriz_roll_rate")
            .sort_values(
                ["faixa_origem_m", "status_destino_m1", "estado_destino_roll_rate"]
            )
            .reset_index(drop=True)
        )
        df_sql_bronze = df_sql_bronze.sort_values(
            ["faixa_origem_m", "status_destino_m1", "estado_destino_roll_rate"]
        ).reset_index(drop=True)

        # Compara 100% célula a célula
        try:
            pd.testing.assert_frame_equal(
                df_sql_bronze,
                df_gold,
                check_dtype=False,
                check_exact=False,
                rtol=1e-5,
                atol=1e-2,
            )
            is_equal = True
        except AssertionError:
            is_equal = False

        return is_equal, df_sql_bronze, df_gold
