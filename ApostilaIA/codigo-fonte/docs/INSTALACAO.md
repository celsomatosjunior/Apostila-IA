# Instalação simples

1. Dê dois cliques em **ApostilaIA-Setup-1.0.0.exe** e siga as telas (Avançar → Instalar → Concluir).
   O Windows pode mostrar "O Windows protegeu o computador" (programa sem assinatura digital):
   clique em *Mais informações* → *Executar assim mesmo*.
2. Abra o **ApostilaIA** pelo ícone. Na primeira vez ele mostra o hardware detectado e pede autorização
   para baixar os modelos de IA (uma única vez; nos seus computadores, o conjunto "Qualidade máxima",
   cerca de 22 GB, mais o CUDA opcional para placas NVIDIA). Depois funciona sem internet.
3. Adicione o(s) TXT da aula e os PDFs dos slides, escolha a pasta, escolha a extensão e clique em
   **Gerar apostila**.

Desinstalar: Configurações do Windows → Aplicativos → ApostilaIA → Desinstalar. Os modelos baixados e as
apostilas geradas não são apagados (modelos: `%LOCALAPPDATA%\ApostilaIA`, podem ser excluídos à mão).
