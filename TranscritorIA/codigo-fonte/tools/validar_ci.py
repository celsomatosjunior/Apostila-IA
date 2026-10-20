"""Validação real no Windows (GitHub Actions), usando o EXECUTÁVEL compilado.

1. Transcreve a aula sintética de 5 min com o modelo informado (motor real, CPU do runner).
2. Compara o TXT com o texto falado (WER) e confere ordem/integridade.
3. Lê os relatórios dos autotestes e escreve um resumo em Markdown.

Critérios de reprovação (falha "dura"): executável não roda, TXT ausente, texto vazio
ou WER acima de 0,60 (indica lixo/perda de trechos). A voz sintética (eSpeak) é
robótica, então o WER absoluto aqui NÃO representa a precisão em aulas reais.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from transcritor.metrics import wer  # noqa: E402


def main(exe: str, model: str, motor: str, out_md: str) -> int:
    aula = ROOT / "tests" / "_gerados" / "aula_5min.mp3"
    script = json.loads(aula.with_suffix(".json").read_text(encoding="utf-8"))
    ref = " ".join(w for _, _, w in script)
    out = ROOT / "ci-saida" / motor
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    r = subprocess.run([exe, "--cli", str(aula), "--saida", str(out), "--modelo", model, "--motor", motor,
                        "--baixar", "--relatorio", str(out / "relatorio.json")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    el = time.time() - t0
    print(r.stdout[-4000:])
    print(r.stderr[-4000:], file=sys.stderr)
    txts = list(out.glob("*.txt"))
    ok = r.returncode == 0 and len(txts) == 1
    w = None
    info = {}
    if txts:
        body = txts[0].read_text(encoding="utf-8").split("TRANSCRIÇÃO", 1)[-1].split("—" * 40)[0]
        w = wer(ref, body)
        ok = ok and bool(body.strip()) and w <= 0.60
    rep = out / "relatorio.json"
    if rep.exists():
        info = json.loads(rep.read_text(encoding="utf-8")).get("motor", {})
    lines = [f"### Transcrição real — motor `{motor}`, modelo `{model}`", "",
             f"- Resultado: **{'APROVADO' if ok else 'REPROVADO'}** (código {r.returncode})",
             f"- Aula sintética: 5 min · tempo total (inclui carregar modelo): {el:.0f} s",
             f"- WER contra o texto falado: {w:.1%}" if w is not None else "- WER: sem texto",
             f"- Acelerador relatado pelo programa: {info.get('aceleracao', '?')} · GPU: {info.get('gpu', '?')}", ""]
    for name in ("autoteste_ct2.json", "autoteste_wcpp.json"):
        p = ROOT / name
        if p.exists():
            a = json.loads(p.read_text(encoding="utf-8")).get("autoteste", {})
            lines.append(f"- {name}: WER {a.get('wer')} · motor {a.get('motor', {}).get('aceleracao')} · "
                         f"{a.get('segundos')} s")
    md = "\n".join(lines) + "\n"
    with open(out_md, "a", encoding="utf-8") as f:
        f.write(md)
    print(md)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3], os.environ.get("GITHUB_STEP_SUMMARY", "resumo.md")))
