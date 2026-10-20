# Índice — versões, instaladores e backups

| Programa | Versão | Data | Instalador | SHA-256 do instalador | Backup |
|---|---|---|---|---|---|
| TranscritorIA | 2.0.0 (atual) | 18/10/2026 | [TranscritorIA-Setup-2.0.0.exe](TranscritorIA/instaladores/v2.0.0/TranscritorIA-Setup-2.0.0.exe) | `0d6fee66fde84dfbf4a69bf652a85c0d217489e342e4c464445268cbe9855358` | [backups/TranscritorIA/v2.0.0](backups/TranscritorIA/v2.0.0/) |
| TranscritorIA | 1.0.0 | 18/10/2026 | [TranscritorIA-Setup-1.0.0.exe](TranscritorIA/instaladores/v1.0.0/TranscritorIA-Setup-1.0.0.exe) | `d97145b9e0878cbd02659803e5b8517b64d466718eaff30637c66a3471a01acd` | [backups/TranscritorIA/v1.0.0](backups/TranscritorIA/v1.0.0/) |
| ApostilaIA | 1.0.0 (atual) | 19/10/2026 | [ApostilaIA-Setup-1.0.0.exe](ApostilaIA/instaladores/v1.0.0/ApostilaIA-Setup-1.0.0.exe) | `cea18100faeaa3e1d6eaca8f00cb3dcf6b3de167be7a8ca738a4c20fd0d96ffc` | [backups/ApostilaIA/v1.0.0](backups/ApostilaIA/v1.0.0/) |

## Recuperação rápida

- **Reinstalar:** baixe o instalador pela tabela (arquivo → *Download raw*) e confira o SHA-256 com
  `certutil -hashfile <arquivo> SHA256`.
- **Código de uma versão:** a versão atual de cada programa está em `<Programa>/codigo-fonte/`. As versões
  anteriores ficam no ZIP da pasta `backups/` correspondente. Cada ZIP funciona sozinho, sem o Git.
- **Integridade dos backups:** cada pasta de backup tem um `SHA256SUMS.txt`. Confira com `sha256sum -c SHA256SUMS.txt`.
- **Recompilar:** veja "Como compilar" no [README](README.md).

## Modelos de IA (não ficam no repositório)

- TranscritorIA: Whisper large-v3 / large-v3-turbo / medium (CTranslate2 ou GGML), baixados no primeiro uso.
- ApostilaIA: Qwen3-30B-A3B-Instruct-2507, Qwen3-VL-8B e Qwen3-VL-4B (GGUF), baixados no primeiro uso.
  Tamanhos e SHA-256: [ApostilaIA/configuracoes/catalogo_modelos.json](ApostilaIA/configuracoes/catalogo_modelos.json).
