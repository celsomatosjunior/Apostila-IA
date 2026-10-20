# ApostilaIA 1.0.0

Transforma a transcrição de uma aula (TXT do TranscritorIA) e os PDFs dos slides em uma apostila de
estudo em PDF e DOCX — com inteligência artificial executada inteiramente neste computador.

1. Abra **ApostilaIA.exe**.
2. Clique em **Adicionar transcrição** e escolha o(s) TXT da aula (várias partes = vários arquivos).
3. Clique em **Adicionar PDFs da aula** e escolha os slides (ou arraste tudo para a janela).
4. Escolha a pasta de destino e a extensão (Compacta, **Equilibrada** ou Fiel e detalhada).
5. Clique em **Gerar apostila** e aguarde. Pode pausar, continuar ou fechar: o progresso fica salvo.

Resultado na pasta escolhida: `Apostila_Final.pdf`, `Apostila_Final.docx` (editável no Word) e
`Relatorio_de_Fidelidade.pdf` (omissões, termos ambíguos, divergências fala × slide e o mapa de quais
trechos da transcrição e quais slides originaram cada capítulo).

**Regra de fidelidade:** a apostila usa somente a transcrição e os slides. Nada é buscado na internet nem
acrescentado de livros ou do "conhecimento" do modelo. Frases sem sustentação são removidas e listadas
no relatório. Termos duvidosos são sinalizados, nunca corrigidos por suposição.

**Primeiro uso:** o programa pede autorização para baixar os modelos de IA uma única vez (de 2,7 a 22 GB,
conforme o computador; em placas NVIDIA, opcionalmente o llama.cpp CUDA). Depois funciona sem internet.
Nenhuma transcrição, PDF ou apostila sai do computador. Sem login, assinatura ou telemetria.

**Modo Turbo** usa todos os recursos. **Modo Trabalho** reduz a prioridade e deixa memória livre para
outros programas. A GPU só aparece como "em uso" quando o próprio motor confirma camadas carregadas nela.

Problemas: Configurações → Abrir logs (`apostila.log`, `llama-server.log`).
Diagnóstico pelo Prompt de Comando: `ApostilaIA-cli.exe --diagnostico`
