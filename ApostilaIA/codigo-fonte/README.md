# ApostilaIA 1.0.0

Programa Windows 10/11 (64 bits) que transforma a **transcrição integral de uma aula** (TXT do TranscritorIA)
e os **PDFs dos slides** em uma **apostila de estudo** em PDF e DOCX, com inteligência artificial executada
**localmente** (llama.cpp + modelos Qwen3 / Qwen3-VL), sem internet depois da preparação inicial.

- Fontes exclusivas: transcrição e slides. Nada de conhecimento externo; frases sem sustentação são removidas
  e listadas no **Relatório de Fidelidade**.
- Leitura completa dos PDFs (texto, tabelas, imagens, páginas renderizadas lidas por modelo de visão).
- Cruzamento fala × slides, capítulos planejados, redação capítulo a capítulo, auditoria de 10 itens.
- Quadros: Observação da professora, Dica clínica, Ponto de atenção, Exemplo discutido, Passo a passo —
  só quando há conteúdo real.
- Perfis: Compacta, **Equilibrada** (padrão), Fiel e detalhada.
- GPU via CUDA (NVIDIA) ou Vulkan (NVIDIA/AMD/Intel), com fallback para CPU; o uso da GPU só é exibido quando
  confirmado pelo motor. Modos Turbo e Trabalho. Checkpoints por etapa, por slide, por trecho e por capítulo.

Estrutura:

```
apostila/          código do programa (fontes, llm, pipeline, render, gui)
assets/            ícone, fontes IBM Plex (OFL), modelos Typst
ApostilaIA.py      ponto de entrada (interface; argumentos = linha de comando)
build/windows/     lançador C, montagem, NSIS, script de teste no Wine
tests/             16 testes obrigatórios + testes de módulos (dados sintéticos)
tools/             teste de integração com modelo GGUF real
docs/              arquitetura, instalação, reconstrução, licenças
configuracoes/     configuração padrão e catálogo de modelos (SHA-256)
```

Uso em desenvolvimento: `pip install -r requirements.txt` e `python ApostilaIA.py`.
Linha de comando: `python ApostilaIA.py --diagnostico` · `--preparar --sim` · `--txt aula.txt --pdf slides.pdf --destino pasta`.
