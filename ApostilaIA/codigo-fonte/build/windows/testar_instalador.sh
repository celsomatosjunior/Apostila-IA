#!/usr/bin/env bash
# Teste do instalador no Wine (Linux): instalação silenciosa, execução do programa instalado
# (diagnóstico, geração completa com o simulador, llama-server.exe real com um GGUF pequeno)
# e desinstalação. Não substitui um teste em Windows real (ver RELATORIO_DE_TESTES.md).
#
# Uso: build/windows/testar_instalador.sh <ApostilaIA-Setup.exe> <pasta-de-trabalho> [modelo.gguf]
set -uo pipefail
SETUP=$(readlink -f "$1"); T=$(readlink -f "$2"); GGUF=${3:-}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
export WINEPREFIX=$T/wineprefix WINEDEBUG=-all LANG=C.UTF-8
rm -rf "$T" && mkdir -p "$T/aula"
ok() { echo "  [OK] $*"; }; falha() { echo "  [FALHA] $*"; FALHAS=$((FALHAS+1)); }
FALHAS=0
wineboot -i >/dev/null 2>&1

echo "== Instalação silenciosa"
wine "$SETUP" /S; sleep 2
DIR="$WINEPREFIX/drive_c/Program Files/ApostilaIA"
for f in ApostilaIA.exe ApostilaIA-cli.exe python312.dll app/ApostilaIA.py llama/vulkan/llama-server.exe \
         llama/cpu/llama-server.exe Desinstalar.exe app/assets/fonts/IBMPlexSerif-Regular.ttf; do
  [ -f "$DIR/$f" ] && ok "$f" || falha "ausente: $f"
done
wine reg query 'HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\ApostilaIA' /v DisplayVersion /reg:64 2>/dev/null \
  | grep -q 1.0.0 && ok "registro de desinstalação (versão 1.0.0)" || falha "registro de desinstalação"
LNK="$WINEPREFIX/drive_c/ProgramData/Microsoft/Windows/Start Menu/Programs/ApostilaIA/ApostilaIA.lnk"
[ -f "$LNK" ] && ok "atalho no Menu Iniciar" || falha "atalho no Menu Iniciar"

echo "== Diagnóstico (programa instalado)"
# (no Wine, a saída precisa ir por um pipe: redirecionar direto para arquivo invalida os handles do console)
wine "$DIR/ApostilaIA-cli.exe" --diagnostico 2>&1 | cat > "$T/diag.txt"
cat "$T/diag.txt" | sed 's/^/     /'
grep -q "ApostilaIA 1.0.0" "$T/diag.txt" && ok "executável abre e detecta o hardware" || falha "diagnóstico"

echo "== Geração completa no Windows Python (simulador extrativo, sem modelo)"
python3 - "$T/aula" <<'EOF'
import sys; sys.path.insert(0, "tests")
from pathlib import Path
import sintetico
w = Path(sys.argv[1])
sintetico.transcricao(w / "Aula teste.txt", "Aula teste", 25, seed=7)
sintetico.slides(w / "AULA 01 - Situs.pdf", "Situs fetal", "Fulana de Tal", achatar=(1,), ultrassons=2)
EOF
( cd "$ROOT" && true )
wine "$DIR/ApostilaIA-cli.exe" --simulador --txt "Z:$T/aula/Aula teste.txt" --pdf "Z:$T/aula/AULA 01 - Situs.pdf" \
  --destino "Z:$T/saida" 2>&1 | cat > "$T/gerar.txt"
tail -5 "$T/gerar.txt" | sed 's/^/     /'
for f in Apostila_Final.pdf Apostila_Final.docx Relatorio_de_Fidelidade.pdf; do
  [ -s "$T/saida/$f" ] && ok "$f gerado no Windows Python" || falha "$f não gerado"
done
python3 - "$T/saida" <<'EOF' && ok "PDF/DOCX válidos" || { echo "  [FALHA] PDF/DOCX inválidos"; }
import sys, pymupdf, docx
from pathlib import Path
d = pymupdf.open(str(Path(sys.argv[1]) / "Apostila_Final.pdf")); assert d.page_count >= 3 and d.get_toc()
docx.Document(str(Path(sys.argv[1]) / "Apostila_Final.docx"))
print("     PDF:", d.page_count, "páginas;", len(d.get_toc()), "marcadores")
EOF

if [ -n "$GGUF" ] && [ -f "$GGUF" ]; then
  echo "== llama-server.exe (Windows, CPU) com modelo GGUF real"
  cp "$GGUF" "$T/teste.gguf"
  ( cd "$DIR/llama/cpu" && wine llama-server.exe -m "Z:$T/teste.gguf" --host 127.0.0.1 --port 18765 -c 2048 \
      -np 1 --no-webui -dev none -ngl 0 -t 2 > "$T/llama-win.log" 2>&1 & echo $! > "$T/llama.pid" )
  for i in $(seq 1 120); do curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18765/health 2>/dev/null | grep -q 200 && break; sleep 1; done
  R=$(curl -s http://127.0.0.1:18765/completion -H 'Content-Type: application/json' \
      -d '{"prompt":"Lista:","n_predict":96,"temperature":0,"json_schema":{"type":"object","properties":{"itens":{"type":"array","items":{"type":"string"},"maxItems":2}},"required":["itens"]}}')
  echo "     resposta: ${R:0:200}"
  echo "$R" | python3 -c "import sys,json; c=json.loads(sys.stdin.read())['content']; json.loads(c)" \
    && ok "llama-server.exe gerou JSON válido (gramática) no Windows/Wine" || falha "llama-server.exe"
  wineserver -k >/dev/null 2>&1 || true
fi

echo "== Desinstalação silenciosa"
wine "$DIR/Desinstalar.exe" /S _?="$DIR"; wineserver -w 2>/dev/null; sleep 3
[ ! -f "$DIR/ApostilaIA.exe" ] && ok "arquivos do programa removidos" || falha "programa não removido"
wine reg query 'HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\ApostilaIA' /reg:64 >/dev/null 2>&1 \
  && falha "registro não removido" || ok "registro removido"
[ ! -f "$LNK" ] && ok "atalho removido" || falha "atalho não removido"
[ -s "$T/saida/Apostila_Final.pdf" ] && ok "apostilas do usuário preservadas" || falha "apostilas apagadas"
echo "== Resultado: $FALHAS falha(s)"
exit $FALHAS
