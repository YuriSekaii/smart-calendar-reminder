#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>

// Zero CRT - Zero allocation - Memory Mapped I/O
// Fastest possible pure Win32 implementation

size_t strlen(const char *s) {
    size_t len = 0;
    while (s[len]) len++;
    return len;
}

static inline int parse_2d(const char *p) {
    return (p[0] - '0') * 10 + (p[1] - '0');
}

static inline int parse_4d(const char *p) {
    return (p[0] - '0') * 1000 + (p[1] - '0') * 100 + (p[2] - '0') * 10 + (p[3] - '0');
}

static inline char *my_strrchr(char *s, char c) {
    char *last = NULL;
    while (*s) {
        if (*s == c) last = s;
        s++;
    }
    return last;
}

static inline void my_strcpy(char *dst, const char *src) {
    while ((*dst++ = *src++));
}

static inline void my_strcat(char *dst, const char *src) {
    while (*dst) dst++;
    while ((*dst++ = *src++));
}

static inline int mem_contains(const char *start, const char *end, const char *target, size_t tlen) {
    if (end - start < (ptrdiff_t)tlen) return 0;
    const char *limit = end - tlen;
    for (const char *p = start; p <= limit; p++) {
        if (*p == *target) {
            size_t k = 1;
            while (k < tlen && p[k] == target[k]) k++;
            if (k == tlen) return 1;
        }
    }
    return 0;
}

static void print_str(HANDLE h, const char *str) {
    DWORD written;
    WriteFile(h, str, (DWORD)strlen(str), &written, NULL);
}

static void print_uint(HANDLE h, unsigned long long val) {
    char buf[32];
    int idx = 30;
    buf[31] = '\0';
    if (val == 0) {
        buf[idx--] = '0';
    } else {
        while (val > 0) {
            buf[idx--] = '0' + (val % 10);
            val /= 10;
        }
    }
    print_str(h, &buf[idx + 1]);
}

typedef BOOL (WINAPI *pfnQPCT)(HANDLE, PULONG64);

void mainCRTStartup(void) {
    LARGE_INTEGER qpc_start, qpc_end, qpc_freq;
    QueryPerformanceFrequency(&qpc_freq);
    QueryPerformanceCounter(&qpc_start);

    ULONG64 start_cycles = 0, end_cycles = 0;
    HMODULE hK32 = GetModuleHandleA("kernel32.dll");
    pfnQPCT pQPCT = (pfnQPCT)GetProcAddress(hK32, "QueryProcessCycleTime");
    if (pQPCT) pQPCT(GetCurrentProcess(), &start_cycles);

    char *cmdLine = GetCommandLineA();
    int is_benchmark = 0;
    for (char *c = cmdLine; *c; c++) {
        if (c[0] == '-' && c[1] == '-' && c[2] == 'b') {
            is_benchmark = 1;
            break;
        }
    }

    SYSTEMTIME st;
    GetLocalTime(&st);

    char base_dir[MAX_PATH];
    GetModuleFileNameA(NULL, base_dir, MAX_PATH);
    char *last_slash = my_strrchr(base_dir, '\\');
    if (last_slash) *last_slash = '\0';

    char json_path[MAX_PATH];
    my_strcpy(json_path, base_dir);
    my_strcat(json_path, "\\reminders.json");

    HANDLE hFile = CreateFileA(json_path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) {
        my_strcpy(json_path, base_dir);
        my_strcat(json_path, "\\dist\\reminders.json");
        hFile = CreateFileA(json_path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        if (hFile == INVALID_HANDLE_VALUE) {
            ExitProcess(0);
        }
    }

    DWORD file_size = GetFileSize(hFile, NULL);
    if (file_size == 0 || file_size > 10 * 1024 * 1024) {
        CloseHandle(hFile);
        ExitProcess(0);
    }

    // Memory Mapped File: Zero heap allocation, zero userspace buffer copying
    HANDLE hMapping = CreateFileMappingA(hFile, NULL, PAGE_READONLY, 0, 0, NULL);
    if (!hMapping) {
        CloseHandle(hFile);
        ExitProcess(0);
    }

    const char *buf = (const char *)MapViewOfFile(hMapping, FILE_MAP_READ, 0, 0, 0);
    if (!buf) {
        CloseHandle(hMapping);
        CloseHandle(hFile);
        ExitProcess(0);
    }

    int needs_alert = 0;
    const char *limit = buf + file_size - 25; // Ensure safe lookahead
    const char *p = buf;

    // 64-bit SWAR key for "datetime"
    // 'd' | ('a'<<8) | ('t'<<16) | ('e'<<24) | ('t'<<32) | ('i'<<40) | ('m'<<48) | ('e'<<56)
    const uint64_t KEY_DATETIME = 0x656d697465746164ULL;

    while (p <= limit) {
        // Fast search for "datetime"
        if (*(const uint64_t *)p == KEY_DATETIME && *(p - 1) == '"' && *(p + 8) == '"') {
            const char *dt_val = p + 9;
            while (*dt_val == ' ' || *dt_val == ':' || *dt_val == '\t') dt_val++;
            if (*dt_val == '"') dt_val++;

            if (dt_val[4] == '-' && dt_val[7] == '-' && dt_val[10] == ' ' && dt_val[13] == ':') {
                int ev_year  = parse_4d(dt_val);
                int ev_month = parse_2d(dt_val + 5);
                int ev_day   = parse_2d(dt_val + 8);
                int ev_hour  = parse_2d(dt_val + 11);
                int ev_min   = parse_2d(dt_val + 14);

                // Locate enclosing object bounds in-place (no allocation, no copying)
                const char *obj_start = p;
                while (obj_start > buf && *obj_start != '{') obj_start--;
                const char *obj_end = p;
                while (obj_end < (buf + file_size) && *obj_end != '}') obj_end++;

                int is_annual = mem_contains(obj_start, obj_end, "\"annual\"", 8);
                int is_daily_or_weekly = mem_contains(obj_start, obj_end, "\"daily\"", 7) ||
                                         mem_contains(obj_start, obj_end, "\"weekly\"", 8);

                if (is_annual) {
                    ev_year = st.wYear;
                    if (ev_month < st.wMonth || (ev_month == st.wMonth && ev_day < st.wDay)) {
                        ev_year++;
                    }
                }

                // Check 1: Missed earlier today
                if (ev_year == st.wYear && ev_month == st.wMonth && ev_day == st.wDay) {
                    if (ev_hour < st.wHour || (ev_hour == st.wHour && ev_min <= st.wMinute)) {
                        needs_alert = 1;
                        break;
                    }
                }

                // Check 2: Upcoming in next 7 days
                if (!is_daily_or_weekly) {
                    int day_diff = (ev_year - st.wYear) * 365 + (ev_month - st.wMonth) * 30 + (ev_day - st.wDay);
                    if (day_diff > 0 && day_diff <= 7) {
                        needs_alert = 1;
                        break;
                    }
                }
            }
            p += 25;
        } else {
            p++;
        }
    }

    UnmapViewOfFile(buf);
    CloseHandle(hMapping);
    CloseHandle(hFile);

    QueryPerformanceCounter(&qpc_end);
    if (pQPCT) pQPCT(GetCurrentProcess(), &end_cycles);

    double elapsed_us = (double)(qpc_end.QuadPart - qpc_start.QuadPart) * 1000000.0 / (double)qpc_freq.QuadPart;
    ULONG64 total_cycles = end_cycles - start_cycles;

    if (is_benchmark) {
        HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
        print_str(hOut, "NeedsAlert: ");
        print_str(hOut, needs_alert ? "True\n" : "False\n");
        print_str(hOut, "Internal Execution Time: ");
        print_uint(hOut, (unsigned long long)elapsed_us);
        print_str(hOut, " microseconds (");
        print_uint(hOut, (unsigned long long)(elapsed_us / 1000.0));
        print_str(hOut, " ms)\nCPU Cycles: ");
        print_uint(hOut, total_cycles);
        print_str(hOut, " cycles\n");
        ExitProcess(0);
    }

    if (needs_alert) {
        char auto_cmd[MAX_PATH * 2];
        my_strcpy(auto_cmd, "\"");
        my_strcat(auto_cmd, base_dir);
        my_strcat(auto_cmd, "\\dist\\AutoChecker.exe\"");
        WinExec(auto_cmd, SW_SHOW);
    }

    ExitProcess(0);
}
