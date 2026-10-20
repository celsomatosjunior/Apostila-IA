/* Compatibilidade: cabeçalhos MinGW-w64 11 não declaram estes tipos do Windows 10 SDK */
#ifdef _WIN32
#include <windows.h>
#ifndef THREAD_POWER_THROTTLING_CURRENT_VERSION
#define THREAD_POWER_THROTTLING_CURRENT_VERSION 1
#define THREAD_POWER_THROTTLING_EXECUTION_SPEED 0x1
typedef struct _THREAD_POWER_THROTTLING_STATE { ULONG Version; ULONG ControlMask; ULONG StateMask; } THREAD_POWER_THROTTLING_STATE;
#endif
#endif
