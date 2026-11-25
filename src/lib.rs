#![cfg_attr(not(test), no_std)]

use core::ffi::c_void;
use core::sync::atomic::{AtomicPtr, Ordering};

const MAX_STATIC_JSON: usize = 65536;
const GENERIC_READ: u32 = 0x8000_0000;
const FILE_SHARE_READ: u32 = 0x01;
const OPEN_EXISTING: u32 = 3;
const FILE_ATTRIBUTE_NORMAL: u32 = 0x80;
const INVALID_HANDLE_VALUE: *mut c_void = (-1isize) as *mut c_void;
const EVENTLOG_INFORMATION_TYPE: u16 = 4;

static DLL_MODULE: AtomicPtr<c_void> = AtomicPtr::new(core::ptr::null_mut());
static mut STATIC_REMINDERS_BUF: [u8; MAX_STATIC_JSON] = [0u8; MAX_STATIC_JSON];
static mut STATIC_DISMISSED_BUF: [u8; 8192] = [0u8; 8192];

#[repr(C)]
pub struct SystemTime {
    pub w_year: u16,
    pub w_month: u16,
    pub w_day_of_week: u16,
    pub w_day: u16,
    pub w_hour: u16,
    pub w_minute: u16,
    pub w_second: u16,
    pub w_milliseconds: u16,
}

#[link(name = "kernel32")]
extern "system" {
    pub fn GetLocalTime(lpSystemTime: *mut SystemTime);
    fn CreateFileW(
        lpFileName: *const u16,
        dwDesiredAccess: u32,
        dwShareMode: u32,
        lpSecurityAttributes: *mut c_void,
        dwCreationDisposition: u32,
        dwFlagsAndAttributes: u32,
        hTemplateFile: *mut c_void,
    ) -> *mut c_void;
    fn GetFileSizeEx(hFile: *mut c_void, lpFileSize: *mut i64) -> i32;
    fn ReadFile(
        hFile: *mut c_void,
        lpBuffer: *mut u8,
        nNumberOfBytesToRead: u32,
        lpNumberOfBytesRead: *mut u32,
        lpOverlapped: *mut c_void,
    ) -> i32;
    fn CloseHandle(hObject: *mut c_void) -> i32;
    fn GetModuleFileNameW(hModule: *mut c_void, lpFilename: *mut u16, nSize: u32) -> u32;
    fn GetEnvironmentVariableW(lpName: *const u16, lpBuffer: *mut u16, nSize: u32) -> u32;
    fn GetProcessHeap() -> *mut c_void;
    fn HeapAlloc(hHeap: *mut c_void, dwFlags: u32, dwBytes: usize) -> *mut u8;
    fn HeapFree(hHeap: *mut c_void, dwFlags: u32, lpMem: *mut c_void) -> i32;
}

#[link(name = "advapi32")]
extern "system" {
    fn RegisterEventSourceA(lpUNCServerName: *const u8, lpSourceName: *const u8) -> *mut c_void;
    fn ReportEventA(
        hEventLog: *mut c_void,
        wType: u16,
        wCategory: u16,
        dwEventID: u32,
        lpUserSid: *mut c_void,
        wNumStrings: u16,
        dwDataSize: u32,
        lpStrings: *const *const u8,
        lpRawData: *mut c_void,
    ) -> i32;
    fn DeregisterEventSource(hEventLog: *mut c_void) -> i32;
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {
        core::hint::spin_loop();
    }
}

#[cfg(not(test))]
#[no_mangle]
pub extern "C" fn rust_eh_personality() {}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct LocalDateTime {
    pub year: i32,
    pub month: u8,
    pub day: u8,
    pub weekday: u8, // 0=Mon..6=Sun
    pub hour: u8,
    pub minute: u8,
}

#[inline]
pub const fn is_leap_year(y: i32) -> bool {
    (y % 4 == 0 && y % 100 != 0) || (y % 400 == 0)
}

#[inline]
pub fn days_from_civil(y: i32, m: i32, d: i32) -> i64 {
    let y = y - if m <= 2 { 1 } else { 0 };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400;
    let doy = (153 * (m + if m > 2 { -3 } else { 9 }) + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    (era as i64) * 146097 + (doe as i64) - 719468
}

pub fn civil_from_days(z: i64) -> (i32, u8, u8) {
    let z = z + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = mp + if mp < 10 { 3 } else { -9 };
    let year = y + if m <= 2 { 1 } else { 0 };
    (year as i32, m as u8, d as u8)
}

#[inline]
fn parse_2d(b: &[u8]) -> Option<u8> {
    let a = *b.first()?;
    let c = *b.get(1)?;
    if !a.is_ascii_digit() || !c.is_ascii_digit() {
        return None;
    }
    Some((a - b'0') * 10 + (c - b'0'))
}

#[inline]
fn parse_4d(b: &[u8]) -> Option<i32> {
    if b.len() < 4 {
        return None;
    }
    let b0 = b[0];
    let b1 = b[1];
    let b2 = b[2];
    let b3 = b[3];
    if !(b0.is_ascii_digit() && b1.is_ascii_digit() && b2.is_ascii_digit() && b3.is_ascii_digit()) {
        return None;
    }
    Some(
        ((b0 - b'0') as i32) * 1000
            + ((b1 - b'0') as i32) * 100
            + ((b2 - b'0') as i32) * 10
            + ((b3 - b'0') as i32),
    )
}

#[inline]
fn parse_hm(s: &[u8]) -> Option<i32> {
    if s.len() < 5 || *s.get(2)? != b':' {
        return None;
    }
    let h = parse_2d(s)? as i32;
    let m = parse_2d(s.get(3..)?)? as i32;
    if h >= 24 || m >= 60 {
        return None;
    }
    Some(h * 60 + m)
}

#[inline]
fn parse_datetime(s: &[u8]) -> Option<(i32, u8, u8, i32)> {
    if s.len() < 16 || s[4] != b'-' || s[7] != b'-' || s[10] != b' ' || s[13] != b':' {
        return None;
    }
    let y = parse_4d(s)?;
    let mo = parse_2d(s.get(5..)?)?;
    let d = parse_2d(s.get(8..)?)?;
    let hm = parse_hm(s.get(11..)?)?;
    if !(1..=12).contains(&mo) || !(1..=31).contains(&d) {
        return None;
    }
    Some((y, mo, d, hm))
}

#[inline]
fn skip_ws(b: &[u8], mut i: usize) -> usize {
    while let Some(&ch) = b.get(i) {
        if !matches!(ch, b' ' | b'\t' | b'\r' | b'\n') {
            break;
        }
        i += 1;
    }
    i
}

#[inline]
fn parse_json_string(b: &[u8], mut i: usize) -> Option<(&[u8], usize)> {
    if *b.get(i)? != b'"' {
        return None;
    }
    i += 1;
    let start = i;
    while let Some(&ch) = b.get(i) {
        if ch == b'\\' {
            i += 2;
            continue;
        }
        if ch == b'"' {
            return b.get(start..i).map(|s| (s, i + 1));
        }
        i += 1;
    }
    None
}

fn skip_json_value(b: &[u8], mut i: usize) -> usize {
    i = skip_ws(b, i);
    let Some(&first) = b.get(i) else {
        return b.len();
    };
    match first {
        b'"' => parse_json_string(b, i).map(|x| x.1).unwrap_or(b.len()),
        b'{' | b'[' => {
            let mut depth = 0i32;
            while let Some(&ch) = b.get(i) {
                match ch {
                    b'"' => {
                        if let Some((_, next)) = parse_json_string(b, i) {
                            i = next;
                            continue;
                        }
                        return b.len();
                    }
                    b'{' | b'[' => depth += 1,
                    b'}' | b']' => {
                        depth -= 1;
                        if depth == 0 {
                            return i + 1;
                        }
                    }
                    _ => {}
                }
                i += 1;
            }
            b.len()
        }
        _ => {
            while let Some(&ch) = b.get(i) {
                if matches!(ch, b',' | b'}' | b']' | b' ' | b'\t' | b'\r' | b'\n') {
                    break;
                }
                i += 1;
            }
            i
        }
    }
}

fn is_id_dismissed(dismissed_json: Option<&[u8]>, id: &[u8], today_ymd: &[u8; 10]) -> bool {
    let Some(b) = dismissed_json else {
        return false;
    };
    if id.is_empty() {
        return false;
    }
    let mut i = skip_ws(b, 0);
    if b.get(i) != Some(&b'{') {
        return false;
    }
    i += 1;
    let mut date_matches = false;
    let mut ids_slice: Option<&[u8]> = None;

    while let Some(&ch) = b.get(i) {
        i = skip_ws(b, i);
        let Some(&c) = b.get(i) else { break };
        if c == b'}' {
            break;
        }
        if c == b',' {
            i += 1;
            continue;
        }
        let _ = ch;
        let Some((key, after_k)) = parse_json_string(b, i) else {
            break;
        };
        i = skip_ws(b, after_k);
        if b.get(i) != Some(&b':') {
            break;
        }
        i = skip_ws(b, i + 1);
        if key == b"date" {
            if let Some((val, next)) = parse_json_string(b, i) {
                date_matches = val == today_ymd;
                i = next;
            } else {
                i = skip_json_value(b, i);
            }
        } else if key == b"dismissed_ids" && b.get(i) == Some(&b'[') {
            let end = skip_json_value(b, i);
            ids_slice = b.get(i..end);
            i = end;
        } else {
            i = skip_json_value(b, i);
        }
    }

    if !date_matches {
        return false;
    }
    let Some(arr) = ids_slice else {
        return false;
    };
    let mut j = 1;
    while j < arr.len() {
        j = skip_ws(arr, j);
        let Some(&c) = arr.get(j) else { break };
        if c == b']' {
            break;
        }
        if c == b',' {
            j += 1;
            continue;
        }
        if let Some((val, next)) = parse_json_string(arr, j) {
            if val == id {
                return true;
            }
            j = next;
        } else {
            break;
        }
    }
    false
}

#[derive(Clone, Copy)]
enum RType {
    Once,
    Daily,
    Weekly,
    Annual,
}

#[inline]
fn parse_rtype(s: &[u8]) -> Option<RType> {
    match s {
        b"once" => Some(RType::Once),
        b"daily" => Some(RType::Daily),
        b"weekly" => Some(RType::Weekly),
        b"annual" => Some(RType::Annual),
        _ => None,
    }
}

#[inline]
fn fmt_ymd(y: i32, m: u8, d: u8) -> [u8; 10] {
    [
        b'0' + ((y / 1000) % 10) as u8,
        b'0' + ((y / 100) % 10) as u8,
        b'0' + ((y / 10) % 10) as u8,
        b'0' + (y % 10) as u8,
        b'-',
        b'0' + (m / 10) % 10,
        b'0' + (m % 10),
        b'-',
        b'0' + (d / 10) % 10,
        b'0' + (d % 10),
    ]
}

pub fn evaluate_reminders_lazy<'a, F>(reminders_json: &[u8], mut load_dismissed: F, now: LocalDateTime) -> bool
where
    F: FnMut() -> Option<&'a [u8]>,
{
    let today_ymd = fmt_ymd(now.year, now.month, now.day);
    let now_days = days_from_civil(now.year, now.month as i32, now.day as i32);
    let now_min = (now.hour as i32) * 60 + (now.minute as i32);
    let (_, y_mo, y_day) = civil_from_days(now_days - 1);
    let y_weekday = (now.weekday + 6) % 7;

    let mut dismissed_cache: Option<Option<&'a [u8]>> = None;

    let mut i = skip_ws(reminders_json, 0);
    if reminders_json.get(i) != Some(&b'[') {
        return false;
    }
    i += 1;

    while i < reminders_json.len() {
        i = skip_ws(reminders_json, i);
        let Some(&ch) = reminders_json.get(i) else {
            break;
        };
        if ch == b']' {
            break;
        }
        if ch == b',' {
            i += 1;
            continue;
        }
        if ch != b'{' {
            i = skip_json_value(reminders_json, i);
            continue;
        }
        i += 1;

        let mut id: &[u8] = b"";
        let mut rtype_field: Option<RType> = None;
        let mut repeat_field: Option<RType> = None;
        let mut is_annual_flag = false;
        let mut important = true;
        let mut dt: Option<(i32, u8, u8, i32)> = None;
        let mut time_min: Option<i32> = None;
        let mut has_end_time = false;
        let mut end_min: Option<i32> = None;
        let mut weekday: Option<u8> = None;

        while i < reminders_json.len() {
            i = skip_ws(reminders_json, i);
            let Some(&c) = reminders_json.get(i) else {
                break;
            };
            if c == b'}' {
                i += 1;
                break;
            }
            if c == b',' {
                i += 1;
                continue;
            }
            let Some((key, after_k)) = parse_json_string(reminders_json, i) else {
                break;
            };
            i = skip_ws(reminders_json, after_k);
            if reminders_json.get(i) != Some(&b':') {
                break;
            }
            i = skip_ws(reminders_json, i + 1);

            if key == b"id" {
                if let Some((v, next)) = parse_json_string(reminders_json, i) {
                    id = v;
                    i = next;
                    continue;
                }
            } else if key == b"type" {
                if let Some((v, next)) = parse_json_string(reminders_json, i) {
                    rtype_field = parse_rtype(v);
                    i = next;
                    continue;
                }
            } else if key == b"repeat" {
                if let Some((v, next)) = parse_json_string(reminders_json, i) {
                    repeat_field = parse_rtype(v);
                    i = next;
                    continue;
                }
            } else if key == b"datetime" {
                if let Some((v, next)) = parse_json_string(reminders_json, i) {
                    dt = parse_datetime(v);
                    i = next;
                    continue;
                }
            } else if key == b"time" {
                if let Some((v, next)) = parse_json_string(reminders_json, i) {
                    time_min = parse_hm(v);
                    i = next;
                    continue;
                }
            } else if key == b"end_time" {
                if let Some((v, next)) = parse_json_string(reminders_json, i) {
                    end_min = parse_hm(v);
                    i = next;
                    continue;
                }
            } else if key == b"has_end_time" {
                let rest = reminders_json.get(i..).unwrap_or(b"");
                if rest.starts_with(b"true") {
                    has_end_time = true;
                    i += 4;
                    continue;
                } else if rest.starts_with(b"false") {
                    has_end_time = false;
                    i += 5;
                    continue;
                }
            } else if key == b"important" {
                let rest = reminders_json.get(i..).unwrap_or(b"");
                if rest.starts_with(b"false") {
                    important = false;
                    i += 5;
                    continue;
                } else if rest.starts_with(b"true") {
                    important = true;
                    i += 4;
                    continue;
                }
            } else if key == b"is_annual" {
                let rest = reminders_json.get(i..).unwrap_or(b"");
                if rest.starts_with(b"true") {
                    is_annual_flag = true;
                    i += 4;
                    continue;
                } else if rest.starts_with(b"false") {
                    is_annual_flag = false;
                    i += 5;
                    continue;
                }
            } else if key == b"weekday" {
                if let Some(&d_ch) = reminders_json.get(i) {
                    if d_ch.is_ascii_digit() {
                        let d = d_ch - b'0';
                        if d < 7 {
                            weekday = Some(d);
                        }
                    }
                }
            }
            i = skip_json_value(reminders_json, i);
        }

        let rtype = if is_annual_flag
            || matches!(rtype_field, Some(RType::Annual))
            || matches!(repeat_field, Some(RType::Annual))
        {
            RType::Annual
        } else {
            rtype_field.or(repeat_field).unwrap_or(RType::Once)
        };

        let start_min = time_min.or_else(|| dt.map(|x| x.3)).unwrap_or(9 * 60);
        let is_overnight = has_end_time && end_min.map(|e| e < start_min).unwrap_or(false);

        let applies_on = |target_days: i64, t_mo: u8, t_day: u8, t_wd: u8| -> bool {
            match rtype {
                RType::Daily => true,
                RType::Weekly => weekday == Some(t_wd),
                RType::Annual => dt.map(|(_, m, d, _)| m == t_mo && d == t_day).unwrap_or(false),
                RType::Once => dt
                    .map(|(y, m, d, _)| days_from_civil(y, m as i32, d as i32) == target_days)
                    .unwrap_or(false),
            }
        };

        let mut candidate_missed = false;
        if is_overnight {
            if let Some(emin) = end_min {
                if applies_on(now_days - 1, y_mo, y_day, y_weekday)
                    && (now_min <= emin || matches!(rtype, RType::Once | RType::Annual))
                {
                    candidate_missed = true;
                }
            }
        }
        if !candidate_missed && applies_on(now_days, now.month, now.day, now.weekday) {
            let ended_today = matches!(rtype, RType::Daily | RType::Weekly)
                && has_end_time
                && !is_overnight
                && end_min.map(|e| now_min > e).unwrap_or(false);
            if !ended_today && start_min <= now_min {
                candidate_missed = true;
            }
        }

        if candidate_missed {
            let dis = match dismissed_cache {
                Some(v) => v,
                None => {
                    let v = load_dismissed();
                    dismissed_cache = Some(v);
                    v
                }
            };
            if !is_id_dismissed(dis, id, &today_ymd) {
                return true;
            }
        }

        // 7-day advance notice for important once/annual events
        if important && matches!(rtype, RType::Once | RType::Annual) {
            if let Some((ev_y, ev_m, ev_d, ev_hm)) = dt {
                let target_days = match rtype {
                    RType::Annual => {
                        let (mut m, mut d) = (ev_m, ev_d);
                        if m == 2 && d == 29 && !is_leap_year(now.year) {
                            m = 3;
                            d = 1;
                        }
                        let mut td = days_from_civil(now.year, m as i32, d as i32);
                        if td < now_days || (td == now_days && ev_hm < now_min) {
                            let (mut nm, mut nd) = (ev_m, ev_d);
                            if nm == 2 && nd == 29 && !is_leap_year(now.year + 1) {
                                nm = 3;
                                nd = 1;
                            }
                            td = days_from_civil(now.year + 1, nm as i32, nd as i32);
                        }
                        td
                    }
                    _ => days_from_civil(ev_y, ev_m as i32, ev_d as i32),
                };
                let delta_min = (target_days - now_days) * 1440 + (ev_hm - now_min) as i64;
                if delta_min > 0 && delta_min <= 7 * 1440 {
                    return true;
                }
            }
        }
    }

    false
}

unsafe fn read_file_fast(path_w: &[u16], static_buf: &mut [u8], heap_out: &mut (*mut u8, usize)) -> Option<usize> {
    let h = CreateFileW(
        path_w.as_ptr(),
        GENERIC_READ,
        FILE_SHARE_READ,
        core::ptr::null_mut(),
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        core::ptr::null_mut(),
    );
    if h.is_null() || h == INVALID_HANDLE_VALUE {
        return None;
    }

    let mut rd = 0u32;
    if ReadFile(h, static_buf.as_mut_ptr(), static_buf.len() as u32, &mut rd, core::ptr::null_mut()) == 0 {
        CloseHandle(h);
        return None;
    }

    if (rd as usize) < static_buf.len() {
        CloseHandle(h);
        return if rd > 0 { Some(rd as usize) } else { None };
    }

    // Rare > static_buf.len() fallback
    let mut fsize: i64 = 0;
    if GetFileSizeEx(h, &mut fsize) == 0 || fsize <= static_buf.len() as i64 {
        CloseHandle(h);
        return Some(rd as usize);
    }
    let size = fsize as usize;
    let heap = GetProcessHeap();
    let mem = HeapAlloc(heap, 0, size);
    if mem.is_null() {
        CloseHandle(h);
        return Some(rd as usize);
    }
    *heap_out = (mem, size);
    core::ptr::copy_nonoverlapping(static_buf.as_ptr(), mem, rd as usize);

    let mut total = rd as usize;
    while total < size {
        let mut r2 = 0u32;
        let chunk = (size - total).min(0x7FFF_FFFF) as u32;
        if ReadFile(h, mem.add(total), chunk, &mut r2, core::ptr::null_mut()) == 0 || r2 == 0 {
            break;
        }
        total += r2 as usize;
    }
    CloseHandle(h);
    Some(total)
}

unsafe fn push_ascii_to_w(dst: &mut [u16], pos: &mut usize, ascii: &[u8]) {
    for &b in ascii {
        if *pos + 1 < dst.len() {
            dst[*pos] = b as u16;
            *pos += 1;
        }
    }
}

unsafe fn get_module_dir_w(out: &mut [u16]) -> usize {
    let hmod = DLL_MODULE.load(Ordering::Relaxed);
    let len = GetModuleFileNameW(hmod, out.as_mut_ptr(), out.len() as u32) as usize;
    if len == 0 || len >= out.len() {
        return 0;
    }
    let mut last_slash = 0;
    for i in 0..len {
        if out[i] == b'\\' as u16 {
            last_slash = i;
        }
    }
    last_slash
}

unsafe fn read_reminders_file(heap_out: &mut (*mut u8, usize)) -> Option<&'static [u8]> {
    let rel: [u16; 15] = [
        b'r' as u16, b'e' as u16, b'm' as u16, b'i' as u16, b'n' as u16, b'd' as u16, b'e' as u16,
        b'r' as u16, b's' as u16, b'.' as u16, b'j' as u16, b's' as u16, b'o' as u16, b'n' as u16, 0,
    ];
    let static_ref = &mut *core::ptr::addr_of_mut!(STATIC_REMINDERS_BUF);
    if let Some(len) = read_file_fast(&rel, static_ref, heap_out) {
        let ptr = if heap_out.0.is_null() { static_ref.as_ptr() } else { heap_out.0 };
        return Some(core::slice::from_raw_parts(ptr, len));
    }

    let mut path_w = [0u16; 320];
    let dir_len = get_module_dir_w(&mut path_w);
    if dir_len == 0 {
        return None;
    }
    let mut pos = dir_len;
    push_ascii_to_w(&mut path_w, &mut pos, b"\\reminders.json");
    path_w[pos] = 0;

    if let Some(len) = read_file_fast(&path_w[..=pos], static_ref, heap_out) {
        let ptr = if heap_out.0.is_null() { static_ref.as_ptr() } else { heap_out.0 };
        return Some(core::slice::from_raw_parts(ptr, len));
    }
    None
}

unsafe fn read_dismissed_file(heap_out: &mut (*mut u8, usize)) -> Option<&'static [u8]> {
    let mut path_w = [0u16; 320];
    let env_name: [u16; 13] = [
        b'L' as u16, b'O' as u16, b'C' as u16, b'A' as u16, b'L' as u16, b'A' as u16, b'P' as u16,
        b'P' as u16, b'D' as u16, b'A' as u16, b'T' as u16, b'A' as u16, 0,
    ];
    let static_ref = &mut *core::ptr::addr_of_mut!(STATIC_DISMISSED_BUF);
    let elen = GetEnvironmentVariableW(env_name.as_ptr(), path_w.as_mut_ptr(), 240) as usize;
    if elen > 0 && elen < 240 {
        let mut pos = elen;
        push_ascii_to_w(&mut path_w, &mut pos, b"\\SmartCalendar\\dismissed_today.json");
        path_w[pos] = 0;
        if let Some(len) = read_file_fast(&path_w[..=pos], static_ref, heap_out) {
            let ptr = if heap_out.0.is_null() { static_ref.as_ptr() } else { heap_out.0 };
            return Some(core::slice::from_raw_parts(ptr, len));
        }
    }

    let dir_len = get_module_dir_w(&mut path_w);
    if dir_len > 0 {
        let mut pos = dir_len;
        push_ascii_to_w(&mut path_w, &mut pos, b"\\dismissed_today.json");
        path_w[pos] = 0;
        if let Some(len) = read_file_fast(&path_w[..=pos], static_ref, heap_out) {
            let ptr = if heap_out.0.is_null() { static_ref.as_ptr() } else { heap_out.0 };
            return Some(core::slice::from_raw_parts(ptr, len));
        }
    }
    None
}

unsafe fn trigger_alert() {
    let h = RegisterEventSourceA(core::ptr::null(), b"SmartCalendar\0".as_ptr());
    if !h.is_null() {
        ReportEventA(
            h,
            EVENTLOG_INFORMATION_TYPE,
            0,
            777,
            core::ptr::null_mut(),
            0,
            0,
            core::ptr::null(),
            core::ptr::null_mut(),
        );
        DeregisterEventSource(h);
    }
}

pub fn check_missed_events() -> i32 {
    unsafe {
        let mut st = SystemTime {
            w_year: 0,
            w_month: 0,
            w_day_of_week: 0,
            w_day: 0,
            w_hour: 0,
            w_minute: 0,
            w_second: 0,
            w_milliseconds: 0,
        };
        GetLocalTime(&mut st);

        let mut rem_heap: (*mut u8, usize) = (core::ptr::null_mut(), 0);
        let mut dis_heap: (*mut u8, usize) = (core::ptr::null_mut(), 0);

        let alert = if let Some(rem) = read_reminders_file(&mut rem_heap) {
            let now = LocalDateTime {
                year: st.w_year as i32,
                month: st.w_month as u8,
                day: st.w_day as u8,
                weekday: ((st.w_day_of_week + 6) % 7) as u8,
                hour: st.w_hour as u8,
                minute: st.w_minute as u8,
            };
            evaluate_reminders_lazy(rem, || read_dismissed_file(&mut dis_heap), now)
        } else {
            false
        };

        let heap = GetProcessHeap();
        if !rem_heap.0.is_null() {
            HeapFree(heap, 0, rem_heap.0 as *mut c_void);
        }
        if !dis_heap.0.is_null() {
            HeapFree(heap, 0, dis_heap.0 as *mut c_void);
        }

        if alert {
            trigger_alert();
            1
        } else {
            0
        }
    }
}

#[no_mangle]
pub extern "C" fn CheckMissedEvents() -> i32 {
    check_missed_events()
}

#[no_mangle]
pub extern "system" fn RunCheckMissedEvents(_hwnd: *mut c_void, _hinst: *mut c_void, _cmd: *const u8, _show: i32) {
    let _ = check_missed_events();
}

#[no_mangle]
pub extern "system" fn DllMain(hinst_dll: *mut c_void, fdw_reason: u32, _reserved: *mut c_void) -> i32 {
    if fdw_reason == 1 {
        DLL_MODULE.store(hinst_dll, Ordering::Relaxed);
    }
    1
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dt(y: i32, mo: u8, d: u8, wd: u8, h: u8, mi: u8) -> LocalDateTime {
        LocalDateTime {
            year: y,
            month: mo,
            day: d,
            weekday: wd,
            hour: h,
            minute: mi,
        }
    }

    #[test]
    fn lazy_dismissed_not_loaded_on_quiet_boot() {
        let non_imp = br#"[{"id":"e1","datetime":"2026-12-31 23:59","time":"23:59","type":"once"}]"#;
        let mut called = 0u32;
        let res = evaluate_reminders_lazy(
            non_imp,
            || {
                called += 1;
                None
            },
            dt(2026, 11, 25, 2, 14, 0),
        );
        assert!(!res);
        assert_eq!(called, 0);
    }

    #[test]
    fn once_future_vs_missed_and_dismissed() {
        let json = br#"[{"id":"e1","datetime":"2026-11-25 09:00","time":"09:00","type":"once","note":"test {braces}"}]"#;
        assert!(evaluate_reminders_lazy(json, || None, dt(2026, 11, 24, 1, 8, 0)));
        assert!(evaluate_reminders_lazy(json, || None, dt(2026, 11, 25, 2, 10, 0)));
        let dis_today = br#"{"date":"2026-11-25","dismissed_ids":["e1"]}"#;
        assert!(!evaluate_reminders_lazy(json, || Some(dis_today), dt(2026, 11, 25, 2, 10, 0)));
        let dis_old = br#"{"date":"2026-11-24","dismissed_ids":["e1"]}"#;
        assert!(evaluate_reminders_lazy(json, || Some(dis_old), dt(2026, 11, 25, 2, 10, 0)));
    }

    #[test]
    fn daily_weekly_and_overnight() {
        let json = br#"[
            {"id":"w1","type":"weekly","weekday":4,"time":"22:00","has_end_time":true,"end_time":"22:35"},
            {"id":"d1","type":"daily","time":"08:00","has_end_time":true,"end_time":"09:00"},
            {"id":"ov","type":"daily","time":"23:00","has_end_time":true,"end_time":"02:00"}
        ]"#;
        assert!(evaluate_reminders_lazy(json, || None, dt(2026, 11, 27, 4, 22, 15)));
        assert!(!evaluate_reminders_lazy(json, || None, dt(2026, 11, 27, 4, 22, 40)));
        assert!(evaluate_reminders_lazy(json, || None, dt(2026, 11, 25, 2, 1, 30)));
        assert!(!evaluate_reminders_lazy(json, || None, dt(2026, 11, 25, 2, 10, 0)));
    }

    #[test]
    fn exact_month_and_year_boundary_advance_notice() {
        let feb1 = br#"[{"id":"f1","type":"once","datetime":"2026-02-01 09:00","time":"09:00"}]"#;
        assert!(evaluate_reminders_lazy(feb1, || None, dt(2026, 1, 31, 5, 10, 0)));

        let jan2 = br#"[{"id":"j2","type":"annual","datetime":"2020-01-02 09:00","time":"09:00"}]"#;
        assert!(evaluate_reminders_lazy(jan2, || None, dt(2026, 12, 28, 0, 10, 0)));

        let unimp = br#"[{"id":"u1","type":"once","datetime":"2026-02-01 09:00","time":"09:00","important":false}]"#;
        assert!(!evaluate_reminders_lazy(unimp, || None, dt(2026, 1, 31, 5, 10, 0)));
    }
}
