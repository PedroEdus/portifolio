"""
Codec binário demonstrativo da arquitetura colunar QlikView Data (.qvd).

Implementa empacotamento e desempacotamento de matrizes de índices bit-stuffed
utilizando operações bitwise vetorizadas em NumPy:
    symbol_idx = ((raw_uint >> bit_offset) & ((1 << bit_width) - 1)) + bias

Estrutura do fluxo binário QVD demonstrativo:
1. Cabeçalho XML `<QvdTableHeader>...</QvdTableHeader>` terminado por byte nulo (`\\x00`).
2. Tabela de Símbolos binária (strings terminadas em `\\x00` com prefixo de tipo `\\x04`,
   inteiros de 4 bytes little-endian com prefixo `\\x01`, ou float IEEE 754 de 8 bytes com `\\x02`).
3. Matriz de Índices Bit-Stuffed alinhada em registros de largura fixa em bytes.
"""

from __future__ import annotations

import math
import re
import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# Padrões determinísticos para bloqueio automático de colunas com PII / Credenciais
PII_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(cpf|cnpj|rg|pis|pasep|nit|cnh|titulo_eleitor)\b"),
    re.compile(r"(?i)(cpf|cnpj|senha|password|xpassword|secret|token|cartao|cvv|salario|remuneracao)"),
    re.compile(r"(?i)(email|e_mail|telefone|celular|endereco_residencial|conta_bancaria)"),
)


def is_sensitive_column(column_name: str) -> bool:
    """Verifica se o nome da coluna viola políticas anti-PII / credenciais."""
    normalized = column_name.strip()
    return any(pattern.search(normalized) for pattern in PII_PATTERNS)


@dataclass(frozen=True)
class QvdFieldMetadata:
    """Metadados de um campo individual extraídos do `<QvdFieldHeader>`."""

    field_name: str
    bit_offset: int
    bit_width: int
    bias: int
    no_of_symbols: int
    symbol_offset: int
    symbol_length: int


@dataclass
class QvdTableMetadata:
    """Metadados globais da tabela QVD extraídos do cabeçalho XML."""

    table_name: str
    no_of_records: int
    record_byte_size: int
    offset_records: int
    length_records: int
    fields: List[QvdFieldMetadata] = field(default_factory=list)


class QvdBitStuffedCodec:
    """
    Codificador e decodificador binário colunar inspirado na especificação interna `.qvd`.

    Opera 100% em Python + NumPy sem dependência de QlikView Desktop ou DLLs proprietárias.
    """

    SYMBOL_TYPE_INT = 0x01
    SYMBOL_TYPE_DOUBLE = 0x02
    SYMBOL_TYPE_STRING = 0x04

    def __init__(self, drop_pii: bool = True) -> None:
        self.drop_pii = drop_pii

    @staticmethod
    def _encode_symbol_table(symbols: Sequence[Any]) -> bytes:
        """Serializa a lista de símbolos únicos de uma coluna no formato binário QVD."""
        buf = bytearray()
        for sym in symbols:
            if isinstance(sym, (int, np.integer)) and not isinstance(sym, bool):
                buf.append(QvdBitStuffedCodec.SYMBOL_TYPE_INT)
                buf.extend(struct.pack("<i", int(sym)))
            elif isinstance(sym, (float, np.floating)):
                buf.append(QvdBitStuffedCodec.SYMBOL_TYPE_DOUBLE)
                buf.extend(struct.pack("<d", float(sym)))
            else:
                buf.append(QvdBitStuffedCodec.SYMBOL_TYPE_STRING)
                buf.extend(str(sym).encode("utf-8"))
                buf.append(0x00)
        return bytes(buf)

    @staticmethod
    def _decode_symbol_table(blob: bytes, expected_count: int) -> List[Any]:
        """Reconstrói o vetor de símbolos únicos a partir do segmento binário da coluna."""
        symbols: List[Any] = []
        pos = 0
        limit = len(blob)
        while pos < limit and len(symbols) < expected_count:
            sym_type = blob[pos]
            pos += 1
            if sym_type == QvdBitStuffedCodec.SYMBOL_TYPE_INT:
                val = struct.unpack_from("<i", blob, pos)[0]
                pos += 4
                symbols.append(int(val))
            elif sym_type == QvdBitStuffedCodec.SYMBOL_TYPE_DOUBLE:
                val = struct.unpack_from("<d", blob, pos)[0]
                pos += 8
                symbols.append(float(val))
            elif sym_type == QvdBitStuffedCodec.SYMBOL_TYPE_STRING:
                null_idx = blob.find(b"\x00", pos)
                if null_idx == -1:
                    raise ValueError("String não terminada por byte nulo na tabela de símbolos QVD.")
                val_str = blob[pos:null_idx].decode("utf-8", errors="replace")
                pos = null_idx + 1
                symbols.append(val_str)
            else:
                raise ValueError(f"Tipo de símbolo QVD desconhecido: 0x{sym_type:02x} na posição {pos - 1}.")
        return symbols

    def encode_table(
        self,
        table_name: str,
        columns: Dict[str, Sequence[Any]],
        nullable_columns: Optional[ Sequence[str] ] = None,
    ) -> bytes:
        """
        Codifica um dicionário colunar em um fluxo binário `.qvd` completo
        (Cabeçalho XML + Tabelas de Símbolos + Matriz de Índices Bit-Stuffed).

        Se `nullable_columns` contiver o nome de uma coluna (ou se houver `None` nos valores),
        aplica `Bias = -2` para reservar índices negativos para NULL, exatamente como o motor Qlik.
        """
        nullable_set = set(nullable_columns or [])
        col_names = list(columns.keys())
        if not col_names:
            raise ValueError("A tabela deve conter ao menos uma coluna.")

        n_rows = len(columns[col_names[0]])
        for name, values in columns.items():
            if len(values) != n_rows:
                raise ValueError(f"Coluna '{name}' possui {len(values)} linhas; esperado {n_rows}.")

        field_metas: List[QvdFieldMetadata] = []
        symbol_blobs: List[bytes] = []
        encoded_indices_per_col: List[np.ndarray] = []

        current_bit_offset = 0
        current_symbol_offset = 0

        for name in col_names:
            raw_vals = columns[name]
            has_null = any(v is None for v in raw_vals) or (name in nullable_set)
            bias = -2 if has_null else 0

            unique_symbols: List[Any] = []
            sym_to_idx: Dict[Any, int] = {}
            raw_pointer_codes = np.empty(n_rows, dtype=np.uint64)

            for row_idx, val in enumerate(raw_vals):
                if val is None:
                    # Com bias = -2, código armazenado 0 -> -2 + 0 = -2 (NULL no QVD)
                    raw_pointer_codes[row_idx] = 0
                else:
                    if val not in sym_to_idx:
                        sym_to_idx[val] = len(unique_symbols)
                        unique_symbols.append(val)
                    sym_idx = sym_to_idx[val]
                    # pointer_code + bias = sym_idx  =>  pointer_code = sym_idx - bias
                    raw_pointer_codes[row_idx] = sym_idx - bias

            max_code = int(raw_pointer_codes.max()) if n_rows > 0 else 0
            if len(unique_symbols) <= 1 and not has_null:
                # Coluna constante ocupa 0 bits na matriz de índices QVD
                bit_width = 0
            else:
                bit_width = max(1, int(math.floor(math.log2(max(1, max_code))) + 1))

            sym_bytes = self._encode_symbol_table(unique_symbols)
            symbol_blobs.append(sym_bytes)

            field_metas.append(
                QvdFieldMetadata(
                    field_name=name,
                    bit_offset=current_bit_offset,
                    bit_width=bit_width,
                    bias=bias,
                    no_of_symbols=len(unique_symbols),
                    symbol_offset=current_symbol_offset,
                    symbol_length=len(sym_bytes),
                )
            )

            current_bit_offset += bit_width
            current_symbol_offset += len(sym_bytes)
            encoded_indices_per_col.append(raw_pointer_codes)

        total_bits_per_row = current_bit_offset
        record_byte_size = max(1, math.ceil(total_bits_per_row / 8))
        if record_byte_size > 8:
            raise ValueError("Este codec demonstrativo suporta até 64 bits por registro (8 bytes).")

        # Empacotamento bitwise vetorizado em uint64
        packed_rows = np.zeros(n_rows, dtype=np.uint64)
        for meta, codes in zip(field_metas, encoded_indices_per_col):
            if meta.bit_width > 0:
                mask = np.uint64((1 << meta.bit_width) - 1)
                packed_rows |= (codes & mask) << np.uint64(meta.bit_offset)

        # Converte uint64 little-endian para matriz de bytes (n_rows, 8) e fatia para record_byte_size
        packed_bytes_matrix = packed_rows.view(np.uint8).reshape(n_rows, 8)[:, :record_byte_size]
        records_blob = packed_bytes_matrix.tobytes()

        all_symbols_blob = b"".join(symbol_blobs)
        xml_header = self._build_xml_header(
            table_name=table_name,
            no_of_records=n_rows,
            record_byte_size=record_byte_size,
            offset_records=len(all_symbols_blob),
            length_records=len(records_blob),
            fields=field_metas,
        )

        return xml_header + b"\r\n\x00" + all_symbols_blob + records_blob

    @staticmethod
    def _build_xml_header(
        table_name: str,
        no_of_records: int,
        record_byte_size: int,
        offset_records: int,
        length_records: int,
        fields: Sequence[QvdFieldMetadata],
    ) -> bytes:
        """Gera o cabeçalho XML `<QvdTableHeader>` compatível com a estrutura do Qlik."""
        lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            "<QvdTableHeader>",
            "  <QvBuildNo>50667</QvBuildNo>",
            f"  <TableName>{table_name}</TableName>",
            "  <Fields>",
        ]
        for f in fields:
            lines.extend(
                [
                    "    <QvdFieldHeader>",
                    f"      <FieldName>{f.field_name}</FieldName>",
                    f"      <BitOffset>{f.bit_offset}</BitOffset>",
                    f"      <BitWidth>{f.bit_width}</BitWidth>",
                    f"      <Bias>{f.bias}</Bias>",
                    f"      <NoOfSymbols>{f.no_of_symbols}</NoOfSymbols>",
                    f"      <Offset>{f.symbol_offset}</Offset>",
                    f"      <Length>{f.symbol_length}</Length>",
                    "    </QvdFieldHeader>",
                ]
            )
        lines.extend(
            [
                "  </Fields>",
                f"  <RecordByteSize>{record_byte_size}</RecordByteSize>",
                f"  <NoOfRecords>{no_of_records}</NoOfRecords>",
                f"  <Offset>{offset_records}</Offset>",
                f"  <Length>{length_records}</Length>",
                "</QvdTableHeader>",
            ]
        )
        return "\r\n".join(lines).encode("utf-8")

    @staticmethod
    def parse_header(qvd_bytes: bytes) -> Tuple[QvdTableMetadata, int]:
        """
        Localiza a tag `</QvdTableHeader>` e o terminador nulo `\\x00`, extraindo os
        metadados de offsets de bits, larguras, bias e ponteiros da tabela de símbolos.
        """
        end_tag = b"</QvdTableHeader>"
        end_idx = qvd_bytes.find(end_tag)
        if end_idx == -1:
            raise ValueError("Cabeçalho XML </QvdTableHeader> não encontrado no buffer QVD.")

        null_idx = qvd_bytes.find(b"\x00", end_idx)
        if null_idx == -1:
            raise ValueError("Byte nulo delimitador de fim de cabeçalho XML não encontrado.")

        xml_bytes = qvd_bytes[: end_idx + len(end_tag)]
        root = ET.fromstring(xml_bytes.decode("utf-8"))

        table_name = root.findtext("TableName", default="UNKNOWN")
        no_of_records = int(root.findtext("NoOfRecords", default="0"))
        record_byte_size = int(root.findtext("RecordByteSize", default="1"))
        offset_records = int(root.findtext("Offset", default="0"))
        length_records = int(root.findtext("Length", default="0"))

        fields: List[QvdFieldMetadata] = []
        fields_node = root.find("Fields")
        if fields_node is not None:
            for fh in fields_node.findall("QvdFieldHeader"):
                fields.append(
                    QvdFieldMetadata(
                        field_name=fh.findtext("FieldName", default=""),
                        bit_offset=int(fh.findtext("BitOffset", default="0")),
                        bit_width=int(fh.findtext("BitWidth", default="0")),
                        bias=int(fh.findtext("Bias", default="0")),
                        no_of_symbols=int(fh.findtext("NoOfSymbols", default="0")),
                        symbol_offset=int(fh.findtext("Offset", default="0")),
                        symbol_length=int(fh.findtext("Length", default="0")),
                    )
                )

        meta = QvdTableMetadata(
            table_name=table_name,
            no_of_records=no_of_records,
            record_byte_size=record_byte_size,
            offset_records=offset_records,
            length_records=length_records,
            fields=fields,
        )
        return meta, null_idx + 1

    def decode_table(self, qvd_bytes: bytes) -> Dict[str, Any]:
        """
        Decodifica um arquivo/fluxo `.qvd` usando operações bitwise vetorizadas em NumPy.

        Retorna um dicionário contendo:
        - `metadata`: `QvdTableMetadata`
        - `data`: `Dict[str, List[Any]]` com as colunas reconstruídas
        - `dropped_pii_columns`: lista de colunas descartadas na origem por proteção anti-PII
        """
        meta, binary_start = self.parse_header(qvd_bytes)
        symbols_region = qvd_bytes[binary_start : binary_start + meta.offset_records]
        records_region = qvd_bytes[
            binary_start + meta.offset_records : binary_start + meta.offset_records + meta.length_records
        ]

        n_rows = meta.no_of_records
        rec_size = meta.record_byte_size

        # Padding para 8 bytes (uint64 little-endian) para extração bitwise vetorizada
        if n_rows > 0:
            raw_matrix = np.frombuffer(records_region, dtype=np.uint8).reshape(n_rows, rec_size)
            padded_matrix = np.zeros((n_rows, 8), dtype=np.uint8)
            padded_matrix[:, :rec_size] = raw_matrix
            raw_uint64 = padded_matrix.view(np.uint64).ravel()
        else:
            raw_uint64 = np.zeros(0, dtype=np.uint64)

        decoded_columns: Dict[str, List[Any]] = {}
        dropped_pii_columns: List[str] = []

        for field_meta in meta.fields:
            if self.drop_pii and is_sensitive_column(field_meta.field_name):
                dropped_pii_columns.append(field_meta.field_name)
                continue

            col_sym_blob = symbols_region[
                field_meta.symbol_offset : field_meta.symbol_offset + field_meta.symbol_length
            ]
            symbols = self._decode_symbol_table(col_sym_blob, field_meta.no_of_symbols)

            if n_rows == 0:
                decoded_columns[field_meta.field_name] = []
                continue

            if field_meta.bit_width == 0:
                # Coluna constante: todos os registros apontam para o símbolo 0 (se existir)
                const_val = symbols[0] if symbols else None
                decoded_columns[field_meta.field_name] = [const_val] * n_rows
                continue

            # Fórmula fundamental do desempacotamento bit-stuffed QVD em NumPy:
            # symbol_idx = ((raw_uint >> bit_offset) & ((1 << bit_width) - 1)) + bias
            bit_offset = np.uint64(field_meta.bit_offset)
            mask = np.uint64((1 << field_meta.bit_width) - 1)
            pointer_codes = ((raw_uint64 >> bit_offset) & mask).astype(np.int64)
            symbol_indices = pointer_codes + int(field_meta.bias)

            col_values: List[Any] = [
                None if idx < 0 or idx >= len(symbols) else symbols[int(idx)]
                for idx in symbol_indices
            ]
            decoded_columns[field_meta.field_name] = col_values

        return {
            "table_name": meta.table_name,
            "no_of_records": meta.no_of_records,
            "record_byte_size": meta.record_byte_size,
            "dropped_pii_columns": dropped_pii_columns,
            "data": decoded_columns,
            "metadata": meta,
        }
