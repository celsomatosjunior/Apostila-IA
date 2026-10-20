"""Teste de integração com modelo REAL (llama.cpp + GGUF), sem simulador.

Executa o pipeline completo — Motor (descoberta de backend, carga, verificação de GPU),
chamadas JSON com gramática, notas, plano, capítulos, auditoria com verificação pelo
modelo — usando um GGUF pequeno no lugar do Qwen (qualidade de texto NÃO é avaliada
aqui; só a integração). Uso:
  python tools/teste_integracao_llm.py <pasta-llama.cpp> <modelo.gguf> <pasta-trabalho>
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
llama_dir, gguf, work = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
os.environ["APOSTILA_LLAMA_DIR"] = str(llama_dir)
os.environ["APOSTILA_DATA_DIR"] = str(work / "dados")

import sintetico  # noqa: E402
from apostila import hardware, logs  # noqa: E402
from apostila.llm import modelos  # noqa: E402
from apostila.llm.modelos import Arquivo, Conjunto, Modelo  # noqa: E402
from apostila.llm.motor import Motor  # noqa: E402
from apostila.pipeline.orquestrador import Gerador  # noqa: E402
from apostila.settings import Settings  # noqa: E402

logs.setup(verbose=False)
work.mkdir(parents=True, exist_ok=True)
base = work / "modelos"
m = Modelo(key="teste-gguf", label=f"GGUF de teste ({gguf.name})",
           gguf=Arquivo("local", gguf.name, gguf.stat().st_size, ""), ctx_texto=8192)
(base / m.key).mkdir(parents=True, exist_ok=True)
dst = base / m.key / gguf.name
if not dst.exists():
    os.symlink(gguf, dst)
conj = Conjunto("T", "teste", m, m)
hw = hardware.detect()
st = Settings()
st.usar_visao = False
st.perfil = "compacta"
txt = sintetico.transcricao(work / "aula.txt", "Aula integração", 4, seed=42, topicos=sintetico.TOPICOS[:2])
pdf = sintetico.slides(work / "slides.pdf", "Situs fetal", "Fulana de Tal", topicos=sintetico.TOPICOS[:2],
                       ultrassons=1, tabela=False, divisoria="")
status = []
motor = Motor(hw, conj, modo="trabalho", status=status.append, models_base=base)
eventos = []
t0 = time.monotonic()
g = Gerador([txt], [pdf], work / "saida", st, motor, on_progress=eventos.append, base_dir=work / "proj",
            modelos_key="teste")
r = g.executar()
dt = time.monotonic() - t0
rel = json.loads(Path(r.relatorio_json).read_text(encoding="utf-8"))
llm = motor.llms_vistos()[0]
out = {
    "segundos": round(dt, 1), "pdf": str(r.pdf), "paginas": r.paginas, "palavras": r.palavras,
    "backend": [c.backend for c in motor.candidatos], "aceleracao": rel["execucao"]["aceleracao"],
    "gpu_verificada": motor.llms_vistos()[0].srv.gpu.verificada if motor.llms_vistos() else None,
    "chamadas": llm.stats.chamadas, "tokens_gerados": llm.stats.tokens_gerados,
    "tok_s": round(llm.stats.tok_s, 1), "prompt_tok_s": round(llm.stats.prompt_tok_s, 1),
    "removidas": len(rel["removidas"]), "parciais": len(rel["parciais"]), "status": status[:5],
}
print(json.dumps(out, ensure_ascii=False, indent=2))
(work / "resultado.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
