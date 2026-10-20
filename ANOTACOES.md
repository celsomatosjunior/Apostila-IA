# Anotações do projeto

Registro de trabalho: o que foi feito, por quê, o que se aprendeu e o que falta.
Datas no fuso de Brasília/Bahia.

## Objetivo

Pegar as aulas gravadas (áudio ou vídeo) da pós-graduação, transcrever fielmente e, a partir do texto fiel
mais os PDFs dos slides (o "roteiro" da aula), produzir apostilas melhores que as feitas à mão ou por IA
genérica. A apostila deve ser fiel à professora, sem nada externo, com figuras dos slides e boa diagramação.

## Histórico

| Data | Marco |
|---|---|
| 18/10/2026 | **TranscritorIA 1.0.0**: transcrição de MP3 com Whisper local (CUDA, Vulkan ou CPU), instalador NSIS pelo método do Capture Pro |
| 18/10/2026 | **TranscritorIA 2.0.0**: vídeos (só o áudio, FFmpeg LGPL), escolha de trilha, interface atualizada |
| 18/10/2026 | Análise de duas apostilas de referência e de três PDFs de slides de uma aula de ecocardiografia fetal (material privado, **não** versionado) |
| 19/10/2026 | **ApostilaIA 1.0.0**: programa completo, 16 testes obrigatórios, instalador testado no Wine |
| 20/10/2026 | Criação deste repositório próprio (`Apostila-IA`) com os dois programas, separado do arquivo geral de códigos |

## O que a análise das apostilas de referência ensinou (aplicado no ApostilaIA)

1. **Os slides são, em grande parte, imagens.** Num dos PDFs analisados só havia 14 palavras extraíveis.
   Sem um modelo de visão a apostila perde o conteúdo visual. Por isso cada página é renderizada e lida pelo
   Qwen3-VL.
2. **As apostilas de referência não usavam as imagens dos slides nem as referências bibliográficas.** O ApostilaIA
   inclui figuras dos slides visuais (ultrassonografias, esquemas) e o apêndice "Referências citadas nos slides".
3. **Havia conteúdo só dos slides que ficou de fora:** tabelas, estatísticas, classificações. Esse conteúdo
   entra marcado como "do slide", sem ser atribuído à fala da professora.
4. **Erros de transcrição recorrentes:**
   - termo latino ouvido como palavra portuguesa ("sítios" no lugar de "situs");
   - grafia trocada ("destro-" × "dextro-");
   - siglas e epônimos deturpados;
   - nome da professora com outra letra.

   Solução: só corrigir quando a forma certa está impressa no slide. O resto vai para "Termos e pontos a
   conferir".
5. **Divergências numéricas** entre o que foi dito e o que estava no slide, e até dentro da mesma apostila:
   - nunca escolher um valor;
   - registrar no relatório e no apêndice.
6. Uma apostila tinha **blocos duplicados** e a outra tinha **numeração de listas quebrada**. A auditoria remove
   duplicatas, e a composição numera as listas corretamente.
7. A seção "Pontos incertos" de uma das referências era boa e foi mantida como o apêndice
   "Termos e pontos a conferir".

## Decisões técnicas

- **Motor:** llama.cpp (b11435) como `llama-server` local, em 127.0.0.1 com porta e chave aleatórias.
  - Saída estruturada: `/apply-template` + `/completion` com `json_schema`; a gramática garante JSON válido.
  - O caminho `/v1/chat/completions` com `response_format` falhou nos testes ("Failed to initialize samplers").
- **Modelos:** Qwen3-30B-A3B-Instruct-2507 (MoE: só 3B ativos por token, rápido mesmo com parte na RAM) para
  texto, e Qwen3-VL-8B para visão.
  - Os dois são carregados em sequência, nunca juntos.
  - `--fit` do llama.cpp distribui as camadas entre GPU e RAM conforme a VRAM livre, com margem de 1 GB no
    Turbo e 2,5 GB no Trabalho.
- **GPU:** o programa só declara uso quando o log do llama.cpp mostra camadas e buffers na GPU.
- **PDF da apostila:** Typst (embutido, rápido, sem dependências).
  - Os dados vão em JSON e nenhum texto é interpretado como marcação.
  - Fontes IBM Plex (OFL), convertidas de WOFF2 para TTF.
- **DOCX:** python-docx com estilos nativos de título, campo de sumário e quadros como tabelas sombreadas.
- **Sem numpy no ApostilaIA:** evita o problema do `ucrtbase.crealf` no Wine e deixa o instalador menor (67 MB).
- **Checkpoints:** leitura dos slides, segmentação e notas ficam num cache compartilhado; mudar o perfil não
  refaz esse trabalho.
- **Contingência extrativa:** se o modelo falhar de forma persistente num trecho, esse trecho é montado direto
  da fonte (fiel) e registrado no relatório, para não perder horas de processamento.

## Aprendizados (erros encontrados e corrigidos)

- `.gitignore` com `engines/` sem âncora ignorou `transcritor/engines/`. Solução: usar padrões ancorados (`/engines/`).
- O NSIS é 32 bits e precisa de `wine32:i386` com um wineprefix novo. Arquivos com acento precisam de `LANG=C.UTF-8`.
- No Wine, redirecionar a saída de um executável de console direto para um arquivo invalida os handles.
  Solução: usar um pipe (`| cat > arquivo`).
- O corretor de termos começou agressivo demais: no material real, 24 correções propostas, a maioria falsas,
  como "vias"→"veias". Regras atuais:
  - flexões da mesma palavra são ignoradas;
  - o termo do slide precisa estar (quase) ausente da fala;
  - a semelhança mínima é 0,72;
  - são necessárias pelo menos 2 ocorrências em contexto.
- Respostas cortadas pelo limite de tokens: o JSON é reparado e os elementos completos são aproveitados.
- O alinhamento por z-score não funciona com poucos slides; com menos de 8 slides vale só o limiar absoluto.
- Aulas longas com um único PDF geravam um capítulo só. Agora capítulos com mais de cerca de 12 mil tokens de
  fala são divididos.

## Pendências

- [ ] **Testar o ApostilaIA com os modelos Qwen reais.** No ambiente de compilação o Hugging Face estava
      bloqueado, então a qualidade da redação e da leitura visual ainda não foi medida.
- [ ] Medir o uso real da GPU (RTX 3070, RTX 4090M, RTX 5070 Ti, RX 9070 XT) no Windows.
- [ ] Rodar com as transcrições reais do Módulo 2, Dia 1 (TXT do TranscritorIA) e comparar com as apostilas de
      referência. Fazer isso fora do repositório.
- [ ] Conferir a interface do ApostilaIA no Windows real: arrastar e soltar, janela de download.
- [ ] Abrir o DOCX no Microsoft Word e conferir a atualização do sumário.
- [ ] Assinatura digital dos instaladores (opcional; evita o aviso do SmartScreen).
- [ ] Criar as tags/releases no GitHub, se desejado. No ambiente de compilação a criação de tags foi bloqueada.

## Observações

- O código do ApostilaIA neste repositório difere do que está compilado no instalador 1.0.0 só em um
  comentário e num teste: nomes reais foram trocados por fictícios antes da publicação.
- **Licenças:**
  - PyMuPDF é AGPL-3.0 e o código-fonte completo está publicado aqui junto com o instalador.
  - FFmpeg (TranscritorIA) é LGPL, com o código correspondente indicado na documentação do TranscritorIA.
  - Os modelos Qwen são Apache-2.0 e são baixados pelo usuário, não redistribuídos aqui.
