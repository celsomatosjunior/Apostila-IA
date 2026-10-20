"""Ponto de entrada: duplo clique abre a interface; argumentos ativam o modo linha de comando.

Usado tanto pelo lançador nativo (TranscritorIA.exe + Python embutido, executado com -I)
quanto em desenvolvimento (python TranscritorIA.py).
"""
import multiprocessing
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CLI_FLAGS = ("--cli", "--diagnostico", "--desempenho", "--autoteste", "--help", "-h", "--recalibrar", "--analisar")


def _fatal(msg: str) -> None:
    """Mostra o erro mesmo que a interface (Qt) não consiga carregar."""
    try:
        base = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "TranscritorIA")
        os.makedirs(base, exist_ok=True)
        with open(os.path.join(base, "erro-inicializacao.log"), "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass
    if sys.platform == "win32" and not any(a in CLI_FLAGS for a in sys.argv[1:]):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, "O Transcritor IA Local não conseguiu iniciar.\n\n" + msg[-1500:] +
                "\n\nSe o problema continuar, reinstale o programa.", "Transcritor IA Local", 0x10)
            return
        except Exception:  # noqa: BLE001
            pass
    if sys.stderr:
        sys.stderr.write(msg)


def main() -> int:
    multiprocessing.freeze_support()
    if any(a in CLI_FLAGS for a in sys.argv[1:]):
        from transcritor.cli import main as cli_main

        return cli_main(sys.argv[1:])
    from transcritor.gui.app import run

    return run(sys.argv[1:])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001
        _fatal(traceback.format_exc())
        sys.exit(1)
