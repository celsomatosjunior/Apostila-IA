/*
 * Lançador nativo do Transcritor IA Local (mesmo método do Capture Pro).
 *
 * Carrega o Python embutido (python312.dll, na mesma pasta) dentro do próprio
 * processo e executa app\TranscritorIA.py. Compilado duas vezes:
 *   TranscritorIA.exe      -> interface gráfica, sem janela de console (-mwindows)
 *   TranscritorIA-cli.exe  -> linha de comando (-DCONSOLE_APP -mconsole)
 */
#define WIN32_LEAN_AND_MEAN
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <shellapi.h>
#include <stdlib.h>
#include <wchar.h>
#include <stdio.h>

typedef int (*Py_MainFn)(int, wchar_t **);

static void fail(const wchar_t *msg)
{
#ifdef CONSOLE_APP
    fwprintf(stderr, L"%ls\n", msg);
#else
    MessageBoxW(NULL, msg, L"Transcritor IA Local", MB_OK | MB_ICONERROR);
#endif
}

static int run(void)
{
    static wchar_t exe[32768], dir[32768], dll[32768], script[32768];

    DWORD n = GetModuleFileNameW(NULL, exe, 32768);
    if (n == 0 || n >= 32768) { fail(L"Não foi possível localizar o executável."); return 1; }
    wcscpy(dir, exe);
    wchar_t *slash = wcsrchr(dir, L'\\');
    if (slash) *slash = 0;

    /* ambiente limpo: nenhuma instalação de Python do computador interfere */
    SetEnvironmentVariableW(L"PYTHONHOME", NULL);
    SetEnvironmentVariableW(L"PYTHONPATH", NULL);
    SetEnvironmentVariableW(L"PYTHONSTARTUP", NULL);
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    SetEnvironmentVariableW(L"TRANSCRITOR_EXE", exe);
    SetEnvironmentVariableW(L"TRANSCRITOR_APPDIR", dir);

    _snwprintf(dll, 32768, L"%ls\\python312.dll", dir);
    _snwprintf(script, 32768, L"%ls\\app\\TranscritorIA.py", dir);

    if (GetFileAttributesW(script) == INVALID_FILE_ATTRIBUTES) {
        fail(L"Arquivos do programa ausentes (app\\TranscritorIA.py).\nReinstale o Transcritor IA Local.");
        return 1;
    }

    SetDllDirectoryW(dir);
    HMODULE py = LoadLibraryExW(dll, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!py) {
        fail(L"Não foi possível carregar o componente Python (python312.dll).\nReinstale o Transcritor IA Local.");
        return 1;
    }
    Py_MainFn py_main = (Py_MainFn)GetProcAddress(py, "Py_Main");
    if (!py_main) { fail(L"Componente Python inválido."); return 1; }

    int argc_in = 0;
    wchar_t **argv_in = CommandLineToArgvW(GetCommandLineW(), &argc_in);
    int extra = argc_in > 1 ? argc_in - 1 : 0;
    wchar_t **argv = (wchar_t **)calloc((size_t)(5 + extra), sizeof(wchar_t *));
    if (!argv) return 1;
    int k = 0;
    argv[k++] = exe;
    argv[k++] = L"-I";   /* isolado: ignora variáveis e site do usuário */
    argv[k++] = L"-B";   /* não grava .pyc (pasta de programas é somente leitura) */
    argv[k++] = script;
    for (int i = 1; i < argc_in; i++) argv[k++] = argv_in[i];

    int rc = py_main(k, argv);
    free(argv);
    if (argv_in) LocalFree(argv_in);
    return rc;
}

#ifdef CONSOLE_APP
int wmain(void) { return run(); }
#else
int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, PWSTR cmdLine, int nShow)
{
    (void)hInst; (void)hPrev; (void)cmdLine; (void)nShow;
    return run();
}
#endif
