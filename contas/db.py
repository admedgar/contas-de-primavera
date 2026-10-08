"""Esquema SQLite e utilitários. Valores monetários em CENTAVOS (INTEGER). Datas em ISO (texto).
Escrito em SQL padrão (sem recursos exclusivos do SQLite) para facilitar migração a PostgreSQL."""
from __future__ import annotations

import contextlib
import sqlite3
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS entidade (
  id TEXT PRIMARY KEY, nome TEXT NOT NULL, portal TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS execucao_coleta (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entidade TEXT NOT NULL, fonte TEXT NOT NULL, exercicio INTEGER,
  inicio TEXT NOT NULL, fim TEXT, status TEXT NOT NULL,   -- 'executando' | 'ok' | 'erro'
  registros INTEGER, bytes INTEGER, url TEXT, mensagem TEXT);

CREATE TABLE IF NOT EXISTS fornecedor (
  entidade TEXT NOT NULL, codif TEXT NOT NULL, nome TEXT NOT NULL,
  documento TEXT,            -- CNPJ, ou CPF JÁ MASCARADO como vem da fonte. Nunca desmascarar.
  tipo_documento TEXT,
  PRIMARY KEY (entidade, codif));

CREATE TABLE IF NOT EXISTS orgao (
  entidade TEXT NOT NULL, codigo TEXT NOT NULL, nome TEXT NOT NULL,
  PRIMARY KEY (entidade, codigo));

CREATE TABLE IF NOT EXISTS unidade (
  entidade TEXT NOT NULL, codigo TEXT NOT NULL, orgao_codigo TEXT NOT NULL, nome TEXT NOT NULL,
  PRIMARY KEY (entidade, codigo));

CREATE TABLE IF NOT EXISTS empenho (
  entidade TEXT NOT NULL, exercicio INTEGER NOT NULL, pkemp TEXT NOT NULL,
  numero TEXT NOT NULL,                 -- número do empenho (repete entre tipos)
  tipo TEXT NOT NULL,                   -- OR ordinário, ES estimativo, GL global, AN anulação, AD/DA adiantamento e sua anulação...
  pkemp_origem TEXT,                    -- empenho original (em anulações)
  codif TEXT NOT NULL, data TEXT,
  orgao TEXT NOT NULL, unidade TEXT NOT NULL,
  funcao TEXT, subfuncao TEXT, programa TEXT, acao TEXT,
  elemento TEXT, natureza TEXT, fonte_recurso TEXT,
  modalidade_licitacao TEXT, historico TEXT,
  empenhado INTEGER NOT NULL, liquidado INTEGER NOT NULL, pago INTEGER NOT NULL,   -- JÁ líquidos (AN vem negativo)
  PRIMARY KEY (entidade, exercicio, pkemp));
CREATE INDEX IF NOT EXISTS ix_empenho_forn ON empenho (entidade, exercicio, codif);
CREATE INDEX IF NOT EXISTS ix_empenho_data ON empenho (entidade, exercicio, data);

CREATE TABLE IF NOT EXISTS mensal_fornecedor (
  entidade TEXT NOT NULL, exercicio INTEGER NOT NULL, mes INTEGER NOT NULL, codif TEXT NOT NULL,
  empenhado INTEGER NOT NULL, liquidado INTEGER NOT NULL, pago INTEGER NOT NULL,
  PRIMARY KEY (entidade, exercicio, mes, codif));

CREATE TABLE IF NOT EXISTS mensal_orgao (
  entidade TEXT NOT NULL, exercicio INTEGER NOT NULL, mes INTEGER NOT NULL, orgao TEXT NOT NULL,
  empenhado INTEGER NOT NULL, liquidado INTEGER NOT NULL, pago INTEGER NOT NULL,   -- liquidado/pago derivados da diferença de acumulados
  PRIMARY KEY (entidade, exercicio, mes, orgao));

-- Totais que o PRÓPRIO portal informa, guardados para conferir com a soma dos detalhes
CREATE TABLE IF NOT EXISTS total_portal (
  entidade TEXT NOT NULL, exercicio INTEGER NOT NULL, origem TEXT NOT NULL,  -- 'por_orgao' | 'por_fornecedor'
  empenhado INTEGER NOT NULL, liquidado INTEGER NOT NULL, pago INTEGER NOT NULL,
  dotacao_atualizada INTEGER, coletado_em TEXT NOT NULL,
  PRIMARY KEY (entidade, exercicio, origem));

CREATE TABLE IF NOT EXISTS orgao_total_portal (
  entidade TEXT NOT NULL, exercicio INTEGER NOT NULL, orgao TEXT NOT NULL,
  empenhado INTEGER NOT NULL, liquidado INTEGER NOT NULL, pago INTEGER NOT NULL, dotacao_atualizada INTEGER,
  PRIMARY KEY (entidade, exercicio, orgao));

-- Receita: árvore hierárquica COMO VEM (códigos se repetem em níveis diferentes). Totais = linhas com ordem = 1.
CREATE TABLE IF NOT EXISTS receita (
  entidade TEXT NOT NULL, exercicio INTEGER NOT NULL, linha INTEGER NOT NULL,
  ordem INTEGER NOT NULL, codigo TEXT NOT NULL, nome TEXT NOT NULL,
  previsao_inicial INTEGER, previsao_atualizada INTEGER, arrecadado INTEGER,
  PRIMARY KEY (entidade, exercicio, linha));
CREATE TABLE IF NOT EXISTS receita_mensal_topo (
  entidade TEXT NOT NULL, exercicio INTEGER NOT NULL, mes INTEGER NOT NULL, codigo TEXT NOT NULL,
  nome TEXT NOT NULL, arrecadado INTEGER NOT NULL,
  PRIMARY KEY (entidade, exercicio, mes, codigo));

CREATE TABLE IF NOT EXISTS licitacao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entidade TEXT NOT NULL, exercicio INTEGER NOT NULL, numero TEXT, processo TEXT,
  modalidade TEXT,                 -- texto do campo LICIT da fonte (DISPENSA, PREGÃO ELETRÔNICO...); vazio se a fonte não informa
  sequencial TEXT,                 -- campo LICITACAO: número sequencial dentro da modalidade
  objeto TEXT, data TEXT, data_encerramento TEXT, situacao TEXT,
  valor INTEGER, valor_complementar INTEGER, registro_preco TEXT, fundamento TEXT);
CREATE INDEX IF NOT EXISTS ix_licitacao_ent ON licitacao (entidade, exercicio);

CREATE TABLE IF NOT EXISTS contrato (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entidade TEXT NOT NULL, codigo TEXT NOT NULL, exercicio INTEGER,
  fornecedor TEXT, documento TEXT, objeto TEXT, modalidade TEXT,
  valor INTEGER, aditado INTEGER, empenhado INTEGER, liquidado INTEGER,
  data_assinatura TEXT, vigencia_inicio TEXT, vigencia_fim TEXT, vigencia_atual TEXT, encerramento TEXT, anulacao TEXT);
CREATE INDEX IF NOT EXISTS ix_contrato_ent ON contrato (entidade);

-- Folha: SOMENTE agregados (sem nomes). Grupos com menos de K servidores são reunidos em 'Outros'.
CREATE TABLE IF NOT EXISTS servidor_agregado (
  entidade TEXT NOT NULL, ref_ano INTEGER NOT NULL, ref_mes INTEGER NOT NULL,
  dimensao TEXT NOT NULL,   -- 'total' | 'cargo' | 'divisao' | 'vinculo'
  chave TEXT NOT NULL, qtd INTEGER NOT NULL, proventos INTEGER NOT NULL, descontos INTEGER NOT NULL, liquido INTEGER NOT NULL,
  PRIMARY KEY (entidade, ref_ano, ref_mes, dimensao, chave));

CREATE TABLE IF NOT EXISTS populacao (
  ano INTEGER PRIMARY KEY, habitantes INTEGER NOT NULL, fonte TEXT NOT NULL, url TEXT, coletado_em TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS validacao (
  entidade TEXT NOT NULL, exercicio INTEGER NOT NULL, checagem TEXT NOT NULL,
  status TEXT NOT NULL,   -- 'ok' | 'divergente' | 'aviso'
  esperado INTEGER, obtido INTEGER, diferenca INTEGER, detalhe TEXT, em TEXT NOT NULL,
  PRIMARY KEY (entidade, exercicio, checagem));
-- ===== Fase 3: Câmara =====
-- Repasses entre entes (consulta Transf do portal da PREFEITURA, que traz os dois sentidos: repasse ao Legislativo e devolução)
CREATE TABLE IF NOT EXISTS transferencia (
  entidade TEXT NOT NULL, exercicio INTEGER NOT NULL, linha INTEGER NOT NULL, mes INTEGER,
  pagadora TEXT, recebedora TEXT, repasse INTEGER NOT NULL, devolucao INTEGER NOT NULL, previsto INTEGER, data TEXT,
  PRIMARY KEY (entidade, exercicio, linha));

-- Vereadores: únicas pessoas identificadas pelo nome na folha (decisão do projeto). Chave de identidade = CPF mascarado + nome.
CREATE TABLE IF NOT EXISTS vereador (
  id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, nome_norm TEXT NOT NULL, cpf_mascarado TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vereador_folha (
  vereador_id INTEGER NOT NULL, ano INTEGER NOT NULL, mes INTEGER NOT NULL,
  cargo TEXT, vinculo TEXT, admissao TEXT, proventos INTEGER NOT NULL, descontos INTEGER NOT NULL, lancamentos INTEGER NOT NULL,
  PRIMARY KEY (vereador_id, ano, mes));
-- Quem (código de fornecedor/favorecido) é qual vereador. Só 'confirmado' é usado nas somas.
CREATE TABLE IF NOT EXISTS vereador_vinculo (
  codif TEXT PRIMARY KEY, vereador_id INTEGER NOT NULL,
  status TEXT NOT NULL,      -- 'confirmado' | 'sugerido' | 'rejeitado'
  origem TEXT NOT NULL,      -- 'regra' (CPF mascarado idêntico + nome idêntico ignorando acento/espaço) | 'manual' (arquivo revisado pelo cliente)
  nota TEXT);

CREATE TABLE IF NOT EXISTS diaria (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entidade TEXT NOT NULL, exercicio INTEGER NOT NULL, pkemp TEXT, empenho TEXT, liquidacao TEXT, ordem_pagamento TEXT,
  data TEXT, valor INTEGER NOT NULL, valor_anulado INTEGER NOT NULL, quantidade TEXT,
  elemento TEXT, descricao TEXT, codif TEXT, favorecido TEXT, cargo TEXT, cpf_mascarado TEXT);
CREATE INDEX IF NOT EXISTS ix_diaria ON diaria (entidade, exercicio, codif);

-- Verba indenizatória: valor recebido (origem API, elemento 93 + histórico). Derivada a cada rodada.
CREATE TABLE IF NOT EXISTS verba_indenizatoria (
  entidade TEXT NOT NULL, exercicio INTEGER NOT NULL, pkemp TEXT NOT NULL,
  vereador_id INTEGER,       -- NULL = favorecido ainda não vinculado a vereador confirmado
  codif TEXT NOT NULL, data_empenho TEXT, competencia TEXT,   -- competência só quando o histórico a informa (AAAA-MM)
  categoria TEXT NOT NULL,   -- 'verba' (histórico cita verba indenizatória) | 'reembolso' (demais empenhos do elemento 93)
  empenhado INTEGER NOT NULL, liquidado INTEGER NOT NULL, pago INTEGER NOT NULL, historico TEXT,
  PRIMARY KEY (entidade, exercicio, pkemp));
-- Pronta para a Fase 5 (detalhamento de como a verba foi gasta). NÃO é preenchida: os PDFs da Câmara não podem ser lidos
-- automaticamente até a Câmara autorizar.
CREATE TABLE IF NOT EXISTS verba_indenizatoria_item (
  id INTEGER PRIMARY KEY AUTOINCREMENT, vereador_id INTEGER NOT NULL, mes TEXT NOT NULL,   -- AAAA-MM
  categoria TEXT, fornecedor TEXT, valor INTEGER NOT NULL, documento TEXT, fonte_url TEXT, coletado_em TEXT);
-- ===== Fase 4: alertas =====
CREATE TABLE IF NOT EXISTS visto (          -- o que já foi visto pela ferramenta (base para detectar "novos")
  entidade TEXT NOT NULL, tipo TEXT NOT NULL,   -- 'empenho' | 'contrato'
  chave TEXT NOT NULL, visto_em TEXT NOT NULL,
  PRIMARY KEY (entidade, tipo, chave));
CREATE TABLE IF NOT EXISTS alerta (
  id INTEGER PRIMARY KEY AUTOINCREMENT, criado_em TEXT NOT NULL,
  entidade TEXT NOT NULL, tipo TEXT NOT NULL, chave TEXT NOT NULL,
  motivos TEXT NOT NULL,                     -- lista separada por ';' (valor_alto, dispensa, inexigibilidade)
  data_registro TEXT, valor INTEGER NOT NULL, secretaria TEXT, fornecedor TEXT, documento TEXT,
  elemento TEXT, modalidade TEXT, descricao TEXT,
  UNIQUE (entidade, tipo, chave));
-- ===== Fase 4b: receitas (entradas) =====
-- Receita do portal mês a mês, TODOS os níveis úteis (1,2,3,4 e 7; o nível 10 só repete o 7 dividido por vinculação). Só exercício corrente.
CREATE TABLE IF NOT EXISTS receita_mensal (
  entidade TEXT NOT NULL, exercicio INTEGER NOT NULL, mes INTEGER NOT NULL, codigo TEXT NOT NULL, ordem INTEGER NOT NULL,
  nome TEXT NOT NULL, arrecadado INTEGER NOT NULL,
  PRIMARY KEY (entidade, exercicio, mes, codigo, ordem));
-- Demonstrativos oficiais do Tesouro Nacional (SICONFI): DCA (anual, 'Anexo I-C') e RREO (bimestral, 'Anexo 01'). Perímetro e convenção
-- (líquido do Fundeb nas linhas do RREO; consolidado com regime próprio) diferem do portal: NUNCA somar nem comparar com o portal.
CREATE TABLE IF NOT EXISTS siconfi_receita (
  origem TEXT NOT NULL,            -- 'dca' | 'rreo'
  exercicio INTEGER NOT NULL, periodo INTEGER NOT NULL,   -- 0 na DCA; bimestre (1-6) no RREO
  coluna TEXT NOT NULL, cod_conta TEXT NOT NULL, conta TEXT NOT NULL, valor INTEGER NOT NULL, coletado_em TEXT NOT NULL,
  PRIMARY KEY (origem, exercicio, periodo, coluna, cod_conta));
-- Valores que passam pelo caixa mas NÃO são receita (retenções, consignações, cauções), agrupados por tipo. Sem nomes de pessoas.
CREATE TABLE IF NOT EXISTS ingresso_extra (
  entidade TEXT NOT NULL, exercicio INTEGER NOT NULL, grupo TEXT NOT NULL, valor INTEGER NOT NULL, lancamentos INTEGER NOT NULL,
  PRIMARY KEY (entidade, exercicio, grupo));
-- Emendas de origem FEDERAL/ESTADUAL recebidas (as municipais são despesa, não entrada).
CREATE TABLE IF NOT EXISTS emenda_recebida (
  entidade TEXT NOT NULL, numero TEXT NOT NULL, ano INTEGER, esfera TEXT, tipo TEXT, transferencia TEXT, autor TEXT,
  valor_total INTEGER, receita_ano_anterior INTEGER, receita INTEGER, empenhado INTEGER, pago INTEGER,
  PRIMARY KEY (entidade, numero));
"""


def agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def conectar(caminho: Path = None) -> sqlite3.Connection:
    caminho = Path(caminho or config.DB_PADRAO)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(caminho))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    for k, v in config.ENTIDADES.items():
        conn.execute("INSERT OR IGNORE INTO entidade VALUES (?,?,?)", (k, v["nome"], v["portal"]))
    conn.commit()
    return conn


@contextlib.contextmanager
def coleta(conn: sqlite3.Connection, entidade: str, fonte: str, exercicio=None) -> Iterator[dict]:
    """Registra início/fim/erro em execucao_coleta. O bloco recebe um dict para informar registros/bytes/url.
    Em erro: grava o status 'erro' e relança (a transação do bloco é revertida pelo chamador)."""
    cur = conn.execute(
        "INSERT INTO execucao_coleta (entidade, fonte, exercicio, inicio, status) VALUES (?,?,?,?, 'executando')",
        (entidade, fonte, exercicio, agora()))
    conn.commit()
    info = {"registros": None, "bytes": None, "url": None, "mensagem": None}
    try:
        yield info
        conn.commit()
        status, msg = "ok", info.get("mensagem")
    except BaseException as e:
        conn.rollback()
        status, msg = "erro", f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=4)}"
        raise
    finally:
        conn.execute(
            "UPDATE execucao_coleta SET fim=?, status=?, registros=?, bytes=?, url=?, mensagem=? WHERE id=?",
            (agora(), locals().get("status", "erro"), info["registros"], info["bytes"], info["url"],
             locals().get("msg"), cur.lastrowid))
        conn.commit()