#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef BOOL (WINAPI *pfnQPCT)(HANDLE, PULONG64);

static inline int parse_2d(const char *p) {
    return (p[0] - '0') * 10 + (p[1] - '0');
}

static inline int parse_4d(const char *p) {
    return (p[0] - '0') * 1000 + (p[1] - '0') * 100 + (p[2] - '0') * 10 + (p[3] - '0');
}

int main(int argc, char *argv[]) {
    LARGE_INTEGER qpc_start, qpc_end, qpc_freq;
    QueryPerformanceFrequency(&qpc_freq);
    QueryPerformanceCounter(&qpc_start);

    ULONG64 start_cycles = 0, end_cycles = 0;
    HMODULE hK32 = GetModuleHandleA("kernel32.dll");
    pfnQPCT pQPCT = (pfnQPCT)GetProcAddress(hK32, "QueryProcessCycleTime");
    if (pQPCT) pQPCT(GetCurrentProcess(), &start_cycles);

    SYSTEMTIME st;
    GetLocalTime(&st);

    char base_dir[MAX_PATH];
    GetModuleFileNameA(NULL, base_dir, MAX_PATH);
    char *last_slash = strrchr(base_dir, '\\');
    if (last_slash) *last_slash = '\0';

    char json_path[MAX_PATH];
    snprintf(json_path, MAX_PATH, "%s\\reminders.json", base_dir);

    HANDLE hFile = CreateFileA(json_path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) {
        snprintf(json_path, MAX_PATH, "%s\\dist\\reminders.json", base_dir);
        hFile = CreateFileA(json_path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        if (hFile == INVALID_HANDLE_VALUE) {
            return 0;
        }
    }

    DWORD file_size = GetFileSize(hFile, NULL);
    if (file_size == 0 || file_size > 10 * 1024 * 1024) {
        CloseHandle(hFile);
        return 0;
    }

    char *buf = (char *)malloc(file_size + 1);
    if (!buf) {
        CloseHandle(hFile);
        return 0;
    }

    DWORD bytes_read = 0;
    ReadFile(hFile, buf, file_size, &bytes_read, NULL);
    CloseHandle(hFile);
    buf[bytes_read] = '\0';

    int needs_alert = 0;
    char *p = buf;

    while ((p = strstr(p, "\"datetime\"")) != NULL) {
        char *dt_val = strchr(p, ':');
        if (!dt_val) break;
        dt_val = strchr(dt_val, '"');
        if (!dt_val) break;
        dt_val++;

        if (dt_val[4] == '-' && dt_val[7] == '-' && dt_val[10] == ' ' && dt_val[13] == ':') {
            int ev_year  = parse_4d(dt_val);
            int ev_month = parse_2d(dt_val + 5);
            int ev_day   = parse_2d(dt_val + 8);
            int ev_hour  = parse_2d(dt_val + 11);
            int ev_min   = parse_2d(dt_val + 14);

            char *obj_start = p;
            while (obj_start > buf && *obj_start != '{') obj_start--;
            char *obj_end = strchr(p, '}');

            int is_annual = 0;
            int is_daily_or_weekly = 0;
            if (obj_end) {
                size_t obj_len = obj_end - obj_start;
                char temp[1024];
                if (obj_len < sizeof(temp)) {
                    memcpy(temp, obj_start, obj_len);
                    temp[obj_len] = '\0';
                    if (strstr(temp, "\"annual\"")) is_annual = 1;
                    if (strstr(temp, "\"daily\"") || strstr(temp, "\"weekly\"")) is_daily_or_weekly = 1;
                }
            }

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
        p += 10;
    }

    free(buf);

    QueryPerformanceCounter(&qpc_end);
    if (pQPCT) pQPCT(GetCurrentProcess(), &end_cycles);

    double elapsed_ms = (double)(qpc_end.QuadPart - qpc_start.QuadPart) * 1000.0 / (double)qpc_freq.QuadPart;
    ULONG64 total_cycles = end_cycles - start_cycles;

    if (argc > 1 && strcmp(argv[1], "--benchmark") == 0) {
        printf("NeedsAlert: %s\n", needs_alert ? "True" : "False");
        printf("Internal Execution Time: %.3f ms (%.1f microseconds)\n", elapsed_ms, elapsed_ms * 1000.0);
        printf("CPU Cycles: %llu cycles\n", total_cycles);
        return 0;
    }

    if (needs_alert) {
        char auto_cmd[MAX_PATH * 2];
        snprintf(auto_cmd, sizeof(auto_cmd), "\"%s\\dist\\AutoChecker.exe\"", base_dir);
        WinExec(auto_cmd, SW_SHOW);
    }

    return 0;
}
