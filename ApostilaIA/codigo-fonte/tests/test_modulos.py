"""Testes unitários dos módulos (complementam os 16 obrigatórios)."""
from __future__ import annotations

import json
from pathlib import Path

from apostila.fontes import transcricao
from apostila.llm.cliente import parse_json_tolerante, reparar_json_truncado
from apostila.pipeline import alinhamento, numeros, termos
from apostila.pipeline.texto import limpar_oralidade
from apostila.util import load_json, save_json


def test_transcricao_formatos(tmp_path):
    a = tmp_path / "Parte 10.txt"
    b = tmp_path / "Parte 2.txt"
    a.write_text("AULA: X\n\nDuração original: 00:10:00\n\nTRANSCRIÇÃO COM MARCAÇÕES DE TEMPO\n\n"
                 "[00:00:05] Primeiro parágrafo da parte dez.\n\n[00:01:00] Segundo.\n\n" + "—" * 40 + "\nrodapé\n",
                 encoding="utf-8")
    b.write_bytes("Texto simples sem cabeçalho, em cp1252: ação.\n\nOutro parágrafo.".encode("cp1252"))
    t = transcricao.ler_transcricoes([a, b])
    assert [p.arquivo for p in t.partes] == ["Parte 2.txt", "Parte 10.txt"]   # ordem natural
    assert t.partes[0].paragrafos[0].texto.endswith("ação.")
    assert t.partes[1].paragrafos[0].inicio == 5 and t.partes[1].duracao_s == 600
    assert all("rodapé" not in p.texto for p in t.paragrafos)
    assert t.partes[1].paragrafos[0].id == "P2.1"


def test_paragrafo_gigante_dividido(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("Frase número um da aula. " * 800, encoding="utf-8")
    t = transcricao.ler_transcricoes([f])
    assert len(t.paragrafos) > 5 and max(p.tokens for p in t.paragrafos) < 600


def test_json_tolerante_e_truncado():
    assert parse_json_tolerante('```json\n{"a": [1, 2,],}\n```') == {"a": [1, 2]}
    assert reparar_json_truncado('{"itens": [{"x": 1}, {"x": 2}, {"x": "inc') == {"itens": [{"x": 1}, {"x": 2}]}


def test_checkpoint_integridade(tmp_path):
    p = tmp_path / "c.json"
    save_json(p, {"a": 1})
    assert load_json(p) == {"a": 1}
    d = json.loads(p.read_text(encoding="utf-8"))
    d["body"]["a"] = 2
    p.write_text(json.dumps(d), encoding="utf-8")
    assert load_json(p) is None and not p.exists()


def test_alinhamento_nao_forca():
    slides = [{"id": "A1-p2", "deck": 1, "num": 2, "texto": "Situs solitus arranjo habitual estômago esquerda"},
              {"id": "A1-p3", "deck": 1, "num": 3, "texto": "Isomerismo esquerdo poliesplenia veia ázigos"}]
    falas = ["O situs solitus é o arranjo habitual, com o estômago à esquerda.",
             "Hoje o almoço vai atrasar e o intervalo será às três horas da tarde.",
             "No isomerismo esquerdo há poliesplenia e continuação pela veia ázigos."]
    a = alinhamento.alinhar(falas, slides)
    assert a.janelas[0].ancora == "A1-p2"
    assert a.janelas[1].ancora is None and a.janelas[1].confianca == "nenhuma"
    assert a.janelas[2].ancora == "A1-p3"


def test_termos_so_com_slide():
    t = termos.construir(["O RASC foi feito.", "O sítios solitus está normal.", "No sítios solitus o estômago fica à esquerda."], ["Situs solitus"])
    assert [(c.de, c.para) for c in t.correcoes] == [("sítios", "situs")]
    assert not any(c.de.lower() == "rasc" for c in t.correcoes)     # sem a forma no slide: não corrige


def test_numeros():
    assert numeros.valores("noventa por cento e 36,7%") >= {"90", "36.7"}
    assert numeros.numeros_sem_fonte("Ocorre em 97% dos casos.", {"90"}) == ["97%"]


def test_oralidade():
    assert limpar_oralidade("então assim, né, a gente vê vê o coração, tá?") .startswith("A gente vê o coração")
