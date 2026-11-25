#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>

// Bare-metal Zero-CRT bootup scanner (Fixed & Optimized C parity with Rust)
// Stripped of MSVCRT runtime; supports once/daily/weekly/annual/overnight,
// dismissed_today.json (lazy-loaded), and exact civil-days calendar math.

#define MAX_STATIC_JSON 65536

static HMODULE s_dll_module = NULL;
static char s_rem_buf[MAX_STATIC_JSON];
static char s_dis_buf[8192];

size_t strlen(const char *s) {
    size_t len = 0;
    while (s[len]) len++;
    return len;
}

static inline int is_digit_c(char c) { return c >= '0' && c <= '9'; }
static inline int is_ws_c(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }

static inline int parse_2d(const char *p) {
    if (!is_digit_c(p[0]) || !is_digit_c(p[1])) return -1;
    return (p[0] - '0') * 10 + (p[1] - '0');
}

static inline int parse_4d(const char *p) {
    for (int i = 0; i < 4; i++) if (!is_digit_c(p[i])) return -1;
    return (p[0] - '0') * 1000 + (p[1] - '0') * 100 + (p[2] - '0') * 10 + (p[3] - '0');
}

static inline int is_leap_year(int y) {
    return (y % 4 == 0 && y % 100 != 0) || (y % 400 == 0);
}

static int64_t days_from_civil(int y, int m, int d) {
    y -= (m <= 2);
    int era = (y >= 0 ? y : y - 399) / 400;
    int yoe = y - era * 400;
    int doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
    int doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return (int64_t)era * 146097 + (int64_t)doe - 719468;
}

static void civil_from_days(int64_t z, int *out_y, int *out_m, int *out_d) {
    z += 719468;
    int64_t era = (z >= 0 ? z : z - 146096) / 146097;
    int64_t doe = z - era * 146097;
    int64_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    int64_t y = yoe + era * 400;
    int64_t doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    int64_t mp = (5 * doy + 2) / 153;
    int d = (int)(doy - (153 * mp + 2) / 5 + 1);
    int m = (int)(mp + (mp < 10 ? 3 : -9));
    *out_y = (int)(y + (m <= 2));
    *out_m = m;
    *out_d = d;
}

static int parse_hm(const char *s, size_t len) {
    if (len < 5 || s[2] != ':') return -1;
    int h = parse_2d(s);
    int m = parse_2d(s + 3);
    if (h < 0 || h >= 24 || m < 0 || m >= 60) return -1;
    return h * 60 + m;
}

static int parse_datetime(const char *s, size_t len, int *y, int *mo, int *d, int *hm) {
    if (len < 16 || s[4] != '-' || s[7] != '-' || s[10] != ' ' || s[13] != ':') return 0;
    int yy = parse_4d(s), mm = parse_2d(s + 5), dd = parse_2d(s + 8), hhmm = parse_hm(s + 11, len - 11);
    if (yy < 0 || mm < 1 || mm > 12 || dd < 1 || dd > 31 || hhmm < 0) return 0;
    *y = yy; *mo = mm; *d = dd; *hm = hhmm;
    return 1;
}

static size_t skip_ws(const char *b, size_t len, size_t i) {
    while (i < len && is_ws_c(b[i])) i++;
    return i;
}

static int parse_json_str(const char *b, size_t len, size_t i, const char **out_s, size_t *out_slen, size_t *out_next) {
    if (i >= len || b[i] != '"') return 0;
    i++;
    size_t start = i;
    while (i < len) {
        if (b[i] == '\\') { i += 2; continue; }
        if (b[i] == '"') {
            *out_s = b + start;
            *out_slen = i - start;
            *out_next = i + 1;
            return 1;
        }
        i++;
    }
    return 0;
}

static size_t skip_json_val(const char *b, size_t len, size_t i) {
    i = skip_ws(b, len, i);
    if (i >= len) return len;
    if (b[i] == '"') {
        const char *s; size_t sl, nxt;
        return parse_json_str(b, len, i, &s, &sl, &nxt) ? nxt : len;
    }
    if (b[i] == '{' || b[i] == '[') {
        int depth = 0;
        while (i < len) {
            if (b[i] == '"') {
                const char *s; size_t sl, nxt;
                if (parse_json_str(b, len, i, &s, &sl, &nxt)) { i = nxt; continue; }
                return len;
            }
            if (b[i] == '{' || b[i] == '[') depth++;
            else if (b[i] == '}' || b[i] == ']') {
                depth--;
                if (depth == 0) return i + 1;
            }
            i++;
        }
        return len;
    }
    while (i < len && b[i] != ',' && b[i] != '}' && b[i] != ']' && !is_ws_c(b[i])) i++;
    return i;
}

static int slice_eq(const char *a, size_t alen, const char *lit, size_t llen) {
    if (alen != llen) return 0;
    for (size_t i = 0; i < alen; i++) if (a[i] != lit[i]) return 0;
    return 1;
}

static size_t read_file_fast(const WCHAR *path, char *static_buf, size_t static_cap, char **heap_ptr) {
    *heap_ptr = NULL;
    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return 0;

    DWORD rd = 0;
    if (!ReadFile(h, static_buf, (DWORD)static_cap, &rd, NULL)) {
        CloseHandle(h);
        return 0;
    }
    if ((size_t)rd < static_cap) {
        CloseHandle(h);
        return (size_t)rd;
    }

    LARGE_INTEGER fsz;
    if (!GetFileSizeEx(h, &fsz) || fsz.QuadPart <= (LONGLONG)static_cap) {
        CloseHandle(h);
        return (size_t)rd;
    }
    size_t size = (size_t)fsz.QuadPart;
    char *mem = (char *)HeapAlloc(GetProcessHeap(), 0, size);
    if (!mem) {
        CloseHandle(h);
        return (size_t)rd;
    }
    *heap_ptr = mem;
    for (size_t k = 0; k < (size_t)rd; k++) mem[k] = static_buf[k];

    size_t total = (size_t)rd;
    while (total < size) {
        DWORD r2 = 0;
        DWORD chunk = (DWORD)((size - total) > 0x7FFFFFFF ? 0x7FFFFFFF : (size - total));
        if (!ReadFile(h, mem + total, chunk, &r2, NULL) || r2 == 0) break;
        total += r2;
    }
    CloseHandle(h);
    return total;
}

static size_t get_module_dir_w(WCHAR *out, size_t cap) {
    DWORD len = GetModuleFileNameW(s_dll_module, out, (DWORD)cap);
    if (len == 0 || len >= cap) return 0;
    size_t last = 0;
    for (size_t i = 0; i < len; i++) if (out[i] == L'\\') last = i;
    return last;
}

static void append_ascii_w(WCHAR *dst, size_t *pos, size_t cap, const char *s) {
    while (*s && *pos + 1 < cap) {
        dst[(*pos)++] = (WCHAR)(unsigned char)*s++;
    }
    dst[*pos] = L'\0';
}

static size_t load_dismissed_file(const char **out_buf, char **heap_ptr) {
    WCHAR path_w[320];
    DWORD elen = GetEnvironmentVariableW(L"LOCALAPPDATA", path_w, 240);
    if (elen > 0 && elen < 240) {
        size_t pos = elen;
        append_ascii_w(path_w, &pos, 320, "\\SmartCalendar\\dismissed_today.json");
        size_t n = read_file_fast(path_w, s_dis_buf, sizeof(s_dis_buf), heap_ptr);
        if (n > 0) {
            *out_buf = *heap_ptr ? *heap_ptr : s_dis_buf;
            return n;
        }
    }
    size_t dlen = get_module_dir_w(path_w, 320);
    if (dlen > 0) {
        size_t pos = dlen;
        append_ascii_w(path_w, &pos, 320, "\\dismissed_today.json");
        size_t n = read_file_fast(path_w, s_dis_buf, sizeof(s_dis_buf), heap_ptr);
        if (n > 0) {
            *out_buf = *heap_ptr ? *heap_ptr : s_dis_buf;
            return n;
        }
    }
    *out_buf = NULL;
    return 0;
}

static int is_id_dismissed(const char *b, size_t len, const char *id, size_t id_len, const char *today_ymd) {
    if (!b || len == 0 || id_len == 0) return 0;
    size_t i = skip_ws(b, len, 0);
    if (i >= len || b[i] != '{') return 0;
    i++;
    int date_ok = 0;
    size_t arr_start = 0, arr_end = 0;

    while (i < len) {
        i = skip_ws(b, len, i);
        if (i >= len || b[i] == '}') break;
        if (b[i] == ',') { i++; continue; }
        const char *k; size_t kl, ak;
        if (!parse_json_str(b, len, i, &k, &kl, &ak)) break;
        i = skip_ws(b, len, ak);
        if (i >= len || b[i] != ':') break;
        i = skip_ws(b, len, i + 1);
        if (slice_eq(k, kl, "date", 4)) {
            const char *v; size_t vl, nxt;
            if (parse_json_str(b, len, i, &v, &vl, &nxt)) {
                date_ok = slice_eq(v, vl, today_ymd, 10);
                i = nxt;
            } else i = skip_json_val(b, len, i);
        } else if (slice_eq(k, kl, "dismissed_ids", 13) && i < len && b[i] == '[') {
            arr_start = i;
            arr_end = skip_json_val(b, len, i);
            i = arr_end;
        } else {
            i = skip_json_val(b, len, i);
        }
    }
    if (!date_ok || arr_end <= arr_start + 1) return 0;
    size_t j = arr_start + 1;
    while (j < arr_end) {
        j = skip_ws(b, arr_end, j);
        if (j >= arr_end || b[j] == ']') break;
        if (b[j] == ',') { j++; continue; }
        const char *v; size_t vl, nxt;
        if (!parse_json_str(b, arr_end, j, &v, &vl, &nxt)) break;
        if (slice_eq(v, vl, id, id_len)) return 1;
        j = nxt;
    }
    return 0;
}

enum { RT_NONE = 0, RT_ONCE = 1, RT_DAILY = 2, RT_WEEKLY = 3, RT_ANNUAL = 4 };

static int parse_rtype(const char *s, size_t len) {
    if (slice_eq(s, len, "once", 4)) return RT_ONCE;
    if (slice_eq(s, len, "daily", 5)) return RT_DAILY;
    if (slice_eq(s, len, "weekly", 6)) return RT_WEEKLY;
    if (slice_eq(s, len, "annual", 6)) return RT_ANNUAL;
    return RT_NONE;
}

static void TriggerAlert(void) {
    HANDLE h = RegisterEventSourceA(NULL, "SmartCalendar");
    if (h) {
        ReportEventA(h, 4, 0, 777, NULL, 0, 0, NULL, NULL);
        DeregisterEventSource(h);
    }
}

__declspec(dllexport) int CheckMissedEvents(void) {
    SYSTEMTIME st;
    GetLocalTime(&st);

    char *rem_heap = NULL;
    size_t rlen = read_file_fast(L"reminders.json", s_rem_buf, sizeof(s_rem_buf), &rem_heap);
    if (rlen == 0) {
        WCHAR path_w[320];
        size_t dlen = get_module_dir_w(path_w, 320);
        if (dlen > 0) {
            size_t pos = dlen;
            append_ascii_w(path_w, &pos, 320, "\\reminders.json");
            rlen = read_file_fast(path_w, s_rem_buf, sizeof(s_rem_buf), &rem_heap);
        }
    }
    if (rlen == 0) return 0;

    const char *buf = rem_heap ? rem_heap : s_rem_buf;
    int today_wd = (st.wDayOfWeek + 6) % 7;
    int y_wd = (today_wd + 6) % 7;
    int64_t now_days = days_from_civil(st.wYear, st.wMonth, st.wDay);
    int now_min = (int)st.wHour * 60 + (int)st.wMinute;
    int y_y, y_m, y_d;
    civil_from_days(now_days - 1, &y_y, &y_m, &y_d);

    char today_ymd[11];
    today_ymd[0] = '0' + (st.wYear / 1000) % 10;
    today_ymd[1] = '0' + (st.wYear / 100) % 10;
    today_ymd[2] = '0' + (st.wYear / 10) % 10;
    today_ymd[3] = '0' + (st.wYear % 10);
    today_ymd[4] = '-';
    today_ymd[5] = '0' + (st.wMonth / 10) % 10;
    today_ymd[6] = '0' + (st.wMonth % 10);
    today_ymd[7] = '-';
    today_ymd[8] = '0' + (st.wDay / 10) % 10;
    today_ymd[9] = '0' + (st.wDay % 10);
    today_ymd[10] = '\0';

    int dis_loaded = 0;
    const char *dis_buf = NULL;
    size_t dis_len = 0;
    char *dis_heap = NULL;
    int needs_alert = 0;

    size_t i = skip_ws(buf, rlen, 0);
    if (i < rlen && buf[i] == '[') {
        i++;
        while (i < rlen) {
            i = skip_ws(buf, rlen, i);
            if (i >= rlen || buf[i] == ']') break;
            if (buf[i] == ',') { i++; continue; }
            if (buf[i] != '{') { i = skip_json_val(buf, rlen, i); continue; }
            i++;

            const char *id = ""; size_t id_len = 0;
            int rtype_f = RT_NONE, repeat_f = RT_NONE, is_annual_f = 0, important = 1;
            int has_dt = 0, dt_y = 0, dt_m = 0, dt_d = 0, dt_hm = 0;
            int time_min = -1, has_end = 0, end_min = -1, weekday = -1;

            while (i < rlen) {
                i = skip_ws(buf, rlen, i);
                if (i >= rlen) break;
                if (buf[i] == '}') { i++; break; }
                if (buf[i] == ',') { i++; continue; }
                const char *k; size_t kl, ak;
                if (!parse_json_str(buf, rlen, i, &k, &kl, &ak)) break;
                i = skip_ws(buf, rlen, ak);
                if (i >= rlen || buf[i] != ':') break;
                i = skip_ws(buf, rlen, i + 1);

                if (slice_eq(k, kl, "id", 2)) {
                    const char *v; size_t vl, nxt;
                    if (parse_json_str(buf, rlen, i, &v, &vl, &nxt)) { id = v; id_len = vl; i = nxt; continue; }
                } else if (slice_eq(k, kl, "type", 4)) {
                    const char *v; size_t vl, nxt;
                    if (parse_json_str(buf, rlen, i, &v, &vl, &nxt)) { rtype_f = parse_rtype(v, vl); i = nxt; continue; }
                } else if (slice_eq(k, kl, "repeat", 6)) {
                    const char *v; size_t vl, nxt;
                    if (parse_json_str(buf, rlen, i, &v, &vl, &nxt)) { repeat_f = parse_rtype(v, vl); i = nxt; continue; }
                } else if (slice_eq(k, kl, "datetime", 8)) {
                    const char *v; size_t vl, nxt;
                    if (parse_json_str(buf, rlen, i, &v, &vl, &nxt)) { has_dt = parse_datetime(v, vl, &dt_y, &dt_m, &dt_d, &dt_hm); i = nxt; continue; }
                } else if (slice_eq(k, kl, "time", 4)) {
                    const char *v; size_t vl, nxt;
                    if (parse_json_str(buf, rlen, i, &v, &vl, &nxt)) { time_min = parse_hm(v, vl); i = nxt; continue; }
                } else if (slice_eq(k, kl, "end_time", 8)) {
                    const char *v; size_t vl, nxt;
                    if (parse_json_str(buf, rlen, i, &v, &vl, &nxt)) { end_min = parse_hm(v, vl); i = nxt; continue; }
                } else if (slice_eq(k, kl, "has_end_time", 12)) {
                    if (i + 4 <= rlen && slice_eq(buf + i, 4, "true", 4)) { has_end = 1; i += 4; continue; }
                    if (i + 5 <= rlen && slice_eq(buf + i, 5, "false", 5)) { has_end = 0; i += 5; continue; }
                } else if (slice_eq(k, kl, "important", 9)) {
                    if (i + 5 <= rlen && slice_eq(buf + i, 5, "false", 5)) { important = 0; i += 5; continue; }
                    if (i + 4 <= rlen && slice_eq(buf + i, 4, "true", 4)) { important = 1; i += 4; continue; }
                } else if (slice_eq(k, kl, "is_annual", 9)) {
                    if (i + 4 <= rlen && slice_eq(buf + i, 4, "true", 4)) { is_annual_f = 1; i += 4; continue; }
                    if (i + 5 <= rlen && slice_eq(buf + i, 5, "false", 5)) { is_annual_f = 0; i += 5; continue; }
                } else if (slice_eq(k, kl, "weekday", 7) && i < rlen && is_digit_c(buf[i])) {
                    int d = buf[i] - '0';
                    if (d < 7) weekday = d;
                }
                i = skip_json_val(buf, rlen, i);
            }

            int rtype = (is_annual_f || rtype_f == RT_ANNUAL || repeat_f == RT_ANNUAL) ? RT_ANNUAL
                        : (rtype_f ? rtype_f : (repeat_f ? repeat_f : RT_ONCE));
            int start_min = (time_min >= 0) ? time_min : (has_dt ? dt_hm : 9 * 60);
            int is_overnight = has_end && end_min >= 0 && end_min < start_min;

            int cand = 0;
            if (is_overnight) {
                int y_applies = (rtype == RT_DAILY) ||
                                (rtype == RT_WEEKLY && weekday == y_wd) ||
                                (rtype == RT_ANNUAL && has_dt && dt_m == y_m && dt_d == y_d) ||
                                (rtype == RT_ONCE && has_dt && days_from_civil(dt_y, dt_m, dt_d) == now_days - 1);
                if (y_applies && (now_min <= end_min || rtype == RT_ONCE || rtype == RT_ANNUAL)) {
                    cand = 1;
                }
            }
            if (!cand) {
                int t_applies = (rtype == RT_DAILY) ||
                                (rtype == RT_WEEKLY && weekday == today_wd) ||
                                (rtype == RT_ANNUAL && has_dt && dt_m == st.wMonth && dt_d == st.wDay) ||
                                (rtype == RT_ONCE && has_dt && days_from_civil(dt_y, dt_m, dt_d) == now_days);
                int ended_today = (rtype == RT_DAILY || rtype == RT_WEEKLY) && has_end && !is_overnight && end_min >= 0 && now_min > end_min;
                if (t_applies && !ended_today && start_min <= now_min) {
                    cand = 1;
                }
            }
            if (cand) {
                if (!dis_loaded) {
                    dis_len = load_dismissed_file(&dis_buf, &dis_heap);
                    dis_loaded = 1;
                }
                if (!is_id_dismissed(dis_buf, dis_len, id, id_len, today_ymd)) {
                    needs_alert = 1;
                    break;
                }
            }

            if (important && (rtype == RT_ONCE || rtype == RT_ANNUAL) && has_dt) {
                int64_t tdays;
                if (rtype == RT_ANNUAL) {
                    int m = dt_m, d = dt_d;
                    if (m == 2 && d == 29 && !is_leap_year(st.wYear)) { m = 3; d = 1; }
                    tdays = days_from_civil(st.wYear, m, d);
                    if (tdays < now_days || (tdays == now_days && dt_hm < now_min)) {
                        int nm = dt_m, nd = dt_d;
                        if (nm == 2 && nd == 29 && !is_leap_year(st.wYear + 1)) { nm = 3; nd = 1; }
                        tdays = days_from_civil(st.wYear + 1, nm, nd);
                    }
                } else {
                    tdays = days_from_civil(dt_y, dt_m, dt_d);
                }
                int64_t delta_min = (tdays - now_days) * 1440 + (int64_t)(dt_hm - now_min);
                if (delta_min > 0 && delta_min <= 7 * 1440) {
                    needs_alert = 1;
                    break;
                }
            }
        }
    }

    HANDLE heap = GetProcessHeap();
    if (rem_heap) HeapFree(heap, 0, rem_heap);
    if (dis_heap) HeapFree(heap, 0, dis_heap);

    if (needs_alert) TriggerAlert();
    return needs_alert;
}

__declspec(dllexport) void CALLBACK RunCheckMissedEvents(HWND hwnd, HINSTANCE hinst, LPSTR lpszCmdLine, int nCmdShow) {
    (void)hwnd; (void)hinst; (void)lpszCmdLine; (void)nCmdShow;
    CheckMissedEvents();
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    (void)lpvReserved;
    if (fdwReason == 1) s_dll_module = hinstDLL;
    return TRUE;
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
    else { int w = whole; while (w > 0) { temp[ti++] = '0' + (w % 10); w /= 10; } }
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
    if (val == 0) buf[idx--] = '0';
    else { while (val > 0) { buf[idx--] = '0' + (val % 10); val /= 10; } }
    print_str(h, &buf[idx + 1]);
}

typedef BOOL (WINAPI *pfnQPCT)(HANDLE, PULONG64);

void mainCRTStartup(void) {
    char *cmdLine = GetCommandLineA();
    int is_profile = 0;
    for (char *c = cmdLine; *c; c++) {
        if (c[0] == '-' && c[1] == '-') { is_profile = 1; break; }
    }
    if (!is_profile) {
        int alert_result = CheckMissedEvents();
        ExitProcess(alert_result ? 1 : 0);
    }

    LARGE_INTEGER freq, t0, t5;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&t0);
    ULONG64 start_cycles = 0, end_cycles = 0;
    HMODULE hK32 = GetModuleHandleA("kernel32.dll");
    pfnQPCT pQPCT = (pfnQPCT)GetProcAddress(hK32, "QueryProcessCycleTime");
    if (pQPCT) pQPCT(GetCurrentProcess(), &start_cycles);

    int alert_result = CheckMissedEvents();

    QueryPerformanceCounter(&t5);
    if (pQPCT) pQPCT(GetCurrentProcess(), &end_cycles);

    HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
    if (hOut == NULL || hOut == INVALID_HANDLE_VALUE) {
        AttachConsole(ATTACH_PARENT_PROCESS);
        hOut = GetStdHandle(STD_OUTPUT_HANDLE);
    }
    double elapsed_us = (t5.QuadPart - t0.QuadPart) * 1000000.0 / (double)freq.QuadPart;
    print_str(hOut, "====================================================\n");
    print_str(hOut, "INTERNAL CODE EXECUTION (FIXED C ZERO-CRT)\n");
    print_str(hOut, "====================================================\n");
    print_str(hOut, "Total Internal Time   : ");
    print_float(hOut, elapsed_us);
    print_str(hOut, " us (");
    print_float(hOut, elapsed_us / 1000.0);
    print_str(hOut, " ms)\nTotal CPU Cycles      : ");
    print_uint(hOut, end_cycles - start_cycles);
    print_str(hOut, " cycles\nAlert Result          : ");
    print_str(hOut, alert_result ? "YES (Event 777 Dispatched, Exit Code 1)\n" : "NO (Quiet State, Exit Code 0)\n");
    print_str(hOut, "====================================================\n");
    ExitProcess(alert_result ? 1 : 0);
}
