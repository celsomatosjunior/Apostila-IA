"""Chamadas ao modelo local.

Texto estruturado: POST /apply-template (prompt no formato do próprio modelo) e
POST /completion com "json_schema" — a gramática do llama.cpp garante JSON válido
no esquema pedido. Respostas em streaming, para que Pausar/Cancelar interrompam
a geração imediatamente.

Visão: POST /v1/chat/completions com a imagem do slide (base64, local) e o mesmo
esquema JSON; se o servidor recusar a gramática, repete sem ela e lê o JSON de
forma tolerante.
"""
from __future__ import annotations

import base64
import json
import re
import threading
import time
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from .. import logs
from .servidor import LlamaServer

log = logs.get("llm")
MEDIA_MARKER = "<__media__>"  # marcador padrão do libmtmd (llama.cpp)


class LLMCancelado(Exception):
    """Cancelado pelo usuário."""


class LLMInterrompido(Exception):
    """Pausa solicitada: a chamada será refeita ao continuar."""


class LLMErro(RuntimeError):
    pass


class ContextoExcedido(LLMErro):
    pass


@dataclass
class Controle:
    cancel: threading.Event = field(default_factory=threading.Event)
    pause: threading.Event = field(default_factory=threading.Event)

    def check(self):
        if self.cancel.is_set():
            raise LLMCancelado()
        if self.pause.is_set():
            raise LLMInterrompido()


@dataclass
class Estatisticas:
    chamadas: int = 0
    tokens_prompt: int = 0
    tokens_gerados: int = 0
    seg_prompt: float = 0.0
    seg_geracao: float = 0.0

    @property
    def tok_s(self) -> float:
        return self.tokens_gerados / self.seg_geracao if self.seg_geracao > 0 else 0.0

    @property
    def prompt_tok_s(self) -> float:
        return self.tokens_prompt / self.seg_prompt if self.seg_prompt > 0 else 0.0


def parse_json_tolerante(txt: str):
    txt = txt.strip()
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt)
    try:
        return json.loads(txt)
    except Exception:  # noqa: BLE001
        pass
    start = txt.find("{")
    if start < 0:
        raise LLMErro("resposta sem JSON")
    depth, instr, esc = 0, False, False
    for i in range(start, len(txt)):
        ch = txt[i]
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                instr = False
            continue
        if ch == '"':
            instr = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                frag = re.sub(r",\s*([}\]])", r"\1", txt[start:i + 1])
                return json.loads(frag)
    raise LLMErro("JSON incompleto na resposta")


def reparar_json_truncado(txt: str):
    """Resposta cortada pelo limite de tokens: fecha o JSON no último elemento completo."""
    start = txt.find("{")
    if start < 0:
        return None
    pilha, instr, esc = [], False, False
    cortes = []  # (posição após um valor completo, pilha naquele ponto)
    for i in range(start, len(txt)):
        ch = txt[i]
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                instr = False
            continue
        if ch == '"':
            instr = True
        elif ch in "{[":
            pilha.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if pilha:
                pilha.pop()
            cortes.append((i + 1, list(pilha)))
    for pos, pl in reversed(cortes[-200:]):
        cand = re.sub(r",\s*$", "", txt[start:pos]) + "".join(reversed(pl))
        try:
            return json.loads(cand)
        except Exception:  # noqa: BLE001
            continue
    return None


class LLMBase:
    """Interface usada pelo pipeline (implementada pelo modelo real e pelo simulador)."""
    nome = "base"
    suporta_visao = False
    descricao_aceleracao = "CPU"
    n_ctx = 8192

    def json(self, tarefa: str, sistema: str, usuario: str, schema: dict, max_tokens: int,
             temperatura: float = 0.2, ctx: Optional[dict] = None, controle: Optional[Controle] = None,
             on_token: Optional[Callable[[int], None]] = None) -> dict:
        raise NotImplementedError

    def visao(self, tarefa: str, sistema: str, usuario: str, imagem: Path, schema: dict, max_tokens: int,
              ctx: Optional[dict] = None, controle: Optional[Controle] = None) -> dict:
        raise NotImplementedError

    def contar_tokens(self, texto: str) -> int:
        from ..util import est_tokens
        return est_tokens(texto)


class LlamaLLM(LLMBase):
    def __init__(self, server: LlamaServer, nome: str, suporta_visao: bool):
        self.srv = server
        self.nome = nome
        self.suporta_visao = suporta_visao
        self.stats = Estatisticas()
        self.n_ctx = server.n_ctx

    @property
    def descricao_aceleracao(self) -> str:
        return self.srv.gpu.descricao()

    def contar_tokens(self, texto: str) -> int:
        try:
            with self.srv.post("/tokenize", {"content": texto}, timeout=60) as r:
                return len(json.loads(r.read().decode("utf-8")).get("tokens", []))
        except Exception:  # noqa: BLE001
            return super().contar_tokens(texto)

    # --------------------------------------------------------------- streaming
    def _stream(self, path: str, body: dict, controle: Optional[Controle], chat: bool,
                on_token: Optional[Callable[[int], None]]) -> str:
        body = dict(body, stream=True)
        try:
            resp = self.srv.post(path, body, timeout=3600)
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:800]
            if "exceed" in msg.lower() and "context" in msg.lower():
                raise ContextoExcedido(msg) from e
            raise LLMErro(f"HTTP {e.code}: {msg}") from e
        except (urllib.error.URLError, OSError) as e:
            raise LLMErro(f"servidor indisponível: {e}") from e
        out: List[str] = []
        n = 0
        t0 = time.monotonic()
        timings = {}
        try:
            for raw in resp:
                if controle:
                    controle.check()
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    ev = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if "error" in ev:
                    raise LLMErro(str(ev["error"])[:500])
                if chat:
                    for ch in ev.get("choices", []):
                        piece = (ch.get("delta") or {}).get("content") or ""
                        if piece:
                            out.append(piece)
                            n += 1
                else:
                    piece = ev.get("content", "")
                    if piece:
                        out.append(piece)
                        n += 1
                if ev.get("timings"):
                    timings = ev["timings"]
                if on_token and n % 16 == 0:
                    on_token(n)
                if (not chat and ev.get("stop")):
                    break
        finally:
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass
        self.stats.chamadas += 1
        if timings:
            self.stats.tokens_prompt += int(timings.get("prompt_n", 0))
            self.stats.seg_prompt += float(timings.get("prompt_ms", 0)) / 1000
            self.stats.tokens_gerados += int(timings.get("predicted_n", n))
            self.stats.seg_geracao += float(timings.get("predicted_ms", 0)) / 1000
        else:
            self.stats.tokens_gerados += n
            self.stats.seg_geracao += time.monotonic() - t0
        return "".join(out)

    def _template(self, sistema: str, usuario: str) -> str:
        msgs = [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]
        with self.srv.post("/apply-template", {"messages": msgs}, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))["prompt"]

    def json(self, tarefa, sistema, usuario, schema, max_tokens, temperatura=0.2, ctx=None,
             controle=None, on_token=None):
        prompt = self._template(sistema, usuario)
        n_prompt = self.contar_tokens(prompt)
        if n_prompt + max_tokens > self.n_ctx:
            raise ContextoExcedido(f"{tarefa}: {n_prompt}+{max_tokens} tokens > contexto {self.n_ctx}")
        body = {"prompt": prompt, "json_schema": schema, "n_predict": max_tokens,
                "temperature": temperatura, "top_p": 0.9, "top_k": 40, "min_p": 0.05,
                "repeat_penalty": 1.05, "cache_prompt": True}
        last_err = None
        for tentativa in range(2):
            txt = self._stream("/completion", body, controle, chat=False, on_token=on_token)
            try:
                return parse_json_tolerante(txt)
            except Exception as e:  # noqa: BLE001
                last_err = e
                rep = reparar_json_truncado(txt) if tentativa == 1 else None
                if isinstance(rep, dict):
                    log.warning("%s: resposta truncada; aproveitados os elementos completos", tarefa)
                    rep["_truncado"] = True
                    return rep
                log.warning("%s: JSON inválido (tentativa %d): %s | %s", tarefa, tentativa + 1, e, txt[-300:])
                body["n_predict"] = int(max_tokens * 1.5)
                if n_prompt + body["n_predict"] > self.n_ctx:
                    body["n_predict"] = max(256, self.n_ctx - n_prompt - 16)
        raise LLMErro(f"{tarefa}: o modelo não produziu JSON válido ({last_err})")

    def visao(self, tarefa, sistema, usuario, imagem, schema, max_tokens, ctx=None, controle=None):
        if not self.suporta_visao:
            raise LLMErro("modelo carregado não tem visão")
        b64 = base64.b64encode(Path(imagem).read_bytes()).decode("ascii")
        mime = "image/png" if str(imagem).lower().endswith(".png") else "image/jpeg"
        # 1) /completion multimodal: marcador de mídia no prompt + gramática JSON
        try:
            prompt = self._template(sistema, MEDIA_MARKER + "\n" + usuario)
            body = {"prompt": {"prompt_string": prompt, "multimodal_data": [b64]},
                    "json_schema": schema, "n_predict": max_tokens, "temperature": 0.1,
                    "top_p": 0.9, "repeat_penalty": 1.05, "cache_prompt": False}
            txt = self._stream("/completion", body, controle, chat=False, on_token=None)
            return parse_json_tolerante(txt)
        except (LLMCancelado, LLMInterrompido, ContextoExcedido):
            raise
        except LLMErro as e:
            log.warning("Visão via /completion falhou (%s); usando /v1/chat/completions", e)
        # 2) API de chat (sem gramática) com leitura tolerante do JSON
        msgs = [{"role": "system", "content": sistema},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": usuario + "\nResponda somente com o objeto JSON."}]}]
        body = {"messages": msgs, "max_tokens": max_tokens, "temperature": 0.1, "top_p": 0.9}
        txt = self._stream("/v1/chat/completions", body, controle, chat=True, on_token=None)
        return parse_json_tolerante(txt)
