# Scripts de compilação (cópia de `codigo-fonte/build/windows/`)

- `build.sh` — gera `ApostilaIA-Setup-1.0.0.exe` no Linux (Python embutido + lançador C + llama.cpp + NSIS).
- `assemble.py` — monta a pasta do programa e verifica as DLLs pelos cabeçalhos PE.
- `launcher.c`, `launcher.rc`, `ApostilaIA.exe.manifest` — lançador nativo (GUI e CLI).
- `installer.nsi` — instalador em português (NSIS 3).
- `testar_instalador.sh` — instala, executa e desinstala no Wine.
Execute a partir de `codigo-fonte/` (os scripts usam caminhos relativos a ela). Detalhes: `documentacao/RECONSTRUIR.md`.
