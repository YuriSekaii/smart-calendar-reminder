#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>

// Bare-metal Zero-CRT bootup scanner
// Stripped of all MSVCRT runtime, TLS, and heap overhead

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

static void print_float(HANDLE h, double val) {
    char buf[32];
    int whole = (int)val;
    int frac = (int)((val - (double)whole) * 1000.0);
    if (frac < 0) frac = -frac;
    
    char temp[16];
    int ti = 0;
    if (whole == 0) temp[ti++] = '0';
    else {
        int w = whole;
        while (w > 0) { temp[ti++] = '0' + (w % 10); w /= 10; }
    }
    int bi = 0;
    for (int i = ti - 1; i >= 0; i--) buf[bi++] = temp[i];
    buf[bi++] = '.';
    buf[bi++] = '0' + (frac / 100);
    buf[bi++] = '0' + ((frac / 10) % 10);
    buf[bi++] = '0' + (frac % 10);
    buf[bi] = '\0';
    print_str(h, buf);
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

// 64 KB static buffer in BSS (occupies 0 bytes in executable file on disk)
static char s_buffer[65536];

typedef BOOL (WINAPI *pfnQPCT)(HANDLE, PULONG64);

void mainCRTStartup(void) {
    LARGE_INTEGER freq, t0, t1, t2, t3, t4, t5, t6;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&t0);

    ULONG64 start_cycles = 0, end_cycles = 0;
    HMODULE hK32 = GetModuleHandleA("kernel32.dll");
    pfnQPCT pQPCT = (pfnQPCT)GetProcAddress(hK32, "QueryProcessCycleTime");
    if (pQPCT) pQPCT(GetCurrentProcess(), &start_cycles);

    // Fast check for command-line arguments
    char *cmdLine = GetCommandLineA();
    int is_profile = 0;
    for (char *c = cmdLine; *c; c++) {
        if (c[0] == '-' && c[1] == '-') {
            is_profile = 1;
            break;
        }
    }

    // Action 1: Get Current Local Time from Kernel
    SYSTEMTIME st;
    GetLocalTime(&st);
    QueryPerformanceCounter(&t1);

    // Action 2: Direct File Open (Fast Path: check current directory first)
    char base_dir[MAX_PATH];
    base_dir[0] = '\0';
    HANDLE hFile = CreateFileA("reminders.json", GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) {
        // Slow Path: resolve via GetModuleFileNameA
        GetModuleFileNameA(NULL, base_dir, MAX_PATH);
        char *last_slash = NULL;
        for (char *c = base_dir; *c; c++) if (*c == '\\') last_slash = c;
        if (last_slash) *last_slash = '\0';

        char json_path[MAX_PATH];
        char *d = json_path;
        for (char *s = base_dir; *s; s++) *d++ = *s;
        const char *suffix = "\\reminders.json";
        for (const char *s = suffix; *s; s++) *d++ = *s;
        *d = '\0';

        hFile = CreateFileA(json_path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        if (hFile == INVALID_HANDLE_VALUE) {
            ExitProcess(0);
        }
    }
    QueryPerformanceCounter(&t2);

    // Action 3: Read File Directly into Static Cache (Zero Heap Allocation)
    DWORD bytes_read = 0;
    ReadFile(hFile, s_buffer, sizeof(s_buffer) - 1, &bytes_read, NULL);
    s_buffer[bytes_read] = '\0';
    CloseHandle(hFile);
    QueryPerformanceCounter(&t3);

    // Action 4: 64-bit SWAR Scanning & Integer Date Evaluation
    int needs_alert = 0;
    const char *buf = s_buffer;
    const char *limit = buf + bytes_read - 25;
    const char *p = buf;
    const uint64_t KEY_DATETIME = 0x656d697465746164ULL; // "datetime"

    while (p <= limit) {
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

                const char *obj_start = p;
                while (obj_start > buf && *obj_start != '{') obj_start--;
                const char *obj_end = p;
                while (obj_end < (buf + bytes_read) && *obj_end != '}') obj_end++;

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
    QueryPerformanceCounter(&t4);

    // Action 5: Launch GUI Alert Popup if event detected
    if (needs_alert) {
        if (base_dir[0] == '\0') {
            GetModuleFileNameA(NULL, base_dir, MAX_PATH);
            char *last_slash = NULL;
            for (char *c = base_dir; *c; c++) if (*c == '\\') last_slash = c;
            if (last_slash) *last_slash = '\0';
        }
        char auto_cmd[MAX_PATH * 2];
        char *ac = auto_cmd;
        *ac++ = '"';
        for (char *s = base_dir; *s; s++) *ac++ = *s;
        const char *exe_suf = "\\dist\\AutoChecker.exe\"";
        for (const char *s = exe_suf; *s; s++) *ac++ = *s;
        *ac = '\0';
        WinExec(auto_cmd, SW_SHOW);
    }
    QueryPerformanceCounter(&t5);

    if (pQPCT) pQPCT(GetCurrentProcess(), &end_cycles);
    ULONG64 total_cycles = end_cycles - start_cycles;

    if (is_profile) {
        HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
        double to_us = 1000000.0 / (double)freq.QuadPart;

        print_str(hOut, "====================================================\n");
        print_str(hOut, "ACTION-BY-ACTION TIME BREAKDOWN (MICRO-PROFILED)\n");
        print_str(hOut, "====================================================\n");
        print_str(hOut, "Action 1: Kernel Time Retrieval (GetLocalTime)  : ");
        print_float(hOut, (t1.QuadPart - t0.QuadPart) * to_us);
        print_str(hOut, " us\n");

        print_str(hOut, "Action 2: File Open & Path Check (CreateFileA)  : ");
        print_float(hOut, (t2.QuadPart - t1.QuadPart) * to_us);
        print_str(hOut, " us\n");

        print_str(hOut, "Action 3: File Read into Static Cache (ReadFile): ");
        print_float(hOut, (t3.QuadPart - t2.QuadPart) * to_us);
        print_str(hOut, " us\n");

        print_str(hOut, "Action 4: 64-bit SWAR Scanning & Date Math      : ");
        print_float(hOut, (t4.QuadPart - t3.QuadPart) * to_us);
        print_str(hOut, " us\n");

        print_str(hOut, "Action 5: GUI Alert Launch (WinExec)            : ");
        print_float(hOut, (t5.QuadPart - t4.QuadPart) * to_us);
        print_str(hOut, " us ");
        print_str(hOut, needs_alert ? "[ALERT FIRED]\n" : "[SKIPPED - NO EVENT]\n");

        print_str(hOut, "----------------------------------------------------\n");
        print_str(hOut, "TOTAL INTERNAL EXECUTION TIME                   : ");
        print_float(hOut, (t5.QuadPart - t0.QuadPart) * to_us);
        print_str(hOut, " us (");
        print_float(hOut, (t5.QuadPart - t0.QuadPart) * 1000.0 / (double)freq.QuadPart);
        print_str(hOut, " ms)\n");
        print_str(hOut, "TOTAL CPU CYCLES SPENT                          : ");
        print_uint(hOut, total_cycles);
        print_str(hOut, " cycles\n");
        print_str(hOut, "====================================================\n");
    }

    ExitProcess(0);
}
