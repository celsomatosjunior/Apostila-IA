# Transcritor IA Local 1.0.0 — instalador (Windows 10/11, 64 bits)

1. Baixe `TranscritorIA-Setup-1.0.0.exe` e execute.
2. Se aparecer "O Windows protegeu o computador", clique em *Mais informações → Executar assim mesmo*.
3. Abra o programa, arraste as aulas, escolha a pasta e clique em **Iniciar transcrição**.

Na primeira transcrição o programa pede autorização para baixar o modelo de IA (~3 GB) e, em placas
NVIDIA, as bibliotecas CUDA (~1,3 GB). Depois funciona sem internet. Nenhum áudio sai do computador.

Conferir o download: `certutil -hashfile TranscritorIA-Setup-1.0.0.exe SHA256` e comparar com `SHA256SUMS-1.0.0.txt`.
