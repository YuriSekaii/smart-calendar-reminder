#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![windows_subsystem = "windows"]

extern crate checker;
use core::ffi::c_void;

const STD_OUTPUT_HANDLE: u32 = (-11i32) as u32;
const ATTACH_PARENT_PROCESS: u32 = 0xFFFF_FFFF;
const INVALID_HANDLE_VALUE: *mut c_void = (-1isize) as *mut c_void;

#[link(name = "kernel32")]
extern "system" {
    fn GetCommandLineA() -> *const u8;
    fn ExitProcess(uExitCode: u32) -> !;
    fn QueryPerformanceFrequency(lpFrequency: *mut i64) -> i32;
    fn QueryPerformanceCounter(lpPerformanceCount: *mut i64) -> i32;
    fn QueryProcessCycleTime(ProcessHandle: *mut c_void, CycleTime: *mut u64) -> i32;
    fn GetCurrentProcess() -> *mut c_void;
    fn GetStdHandle(nStdHandle: u32) -> *mut c_void;
    fn AttachConsole(dwProcessId: u32) -> i32;
    fn WriteFile(
        hFile: *mut c_void,
        lpBuffer: *const u8,
        nNumberOfBytesToWrite: u32,
        lpNumberOfBytesWritten: *mut u32,
        lpOverlapped: *mut c_void,
    ) -> i32;
}

unsafe fn write_bytes(h: *mut c_void, s: &[u8]) {
    if !h.is_null() && h != INVALID_HANDLE_VALUE {
        let mut w = 0u32;
        WriteFile(h, s.as_ptr(), s.len() as u32, &mut w, core::ptr::null_mut());
    }
}

unsafe fn write_u64(h: *mut c_void, mut v: u64) {
    let mut buf = [0u8; 24];
    let mut i = buf.len();
    if v == 0 {
        i -= 1;
        buf[i] = b'0';
    } else {
        while v > 0 {
            i -= 1;
            buf[i] = b'0' + (v % 10) as u8;
            v /= 10;
        }
    }
    write_bytes(h, &buf[i..]);
}

unsafe fn write_f64_3(h: *mut c_void, val: f64) {
    let whole = val as u64;
    let frac = (((val - (whole as f64)) * 1000.0) as i64).abs() as u64;
    write_u64(h, whole);
    let f = [
        b'.',
        b'0' + ((frac / 100) % 10) as u8,
        b'0' + ((frac / 10) % 10) as u8,
        b'0' + (frac % 10) as u8,
    ];
    write_bytes(h, &f);
}

#[cfg(not(test))]
#[no_mangle]
pub extern "system" fn WinMain(_: *mut c_void, _: *mut c_void, _: *const u8, _: i32) -> i32 {
    0
}

#[cfg(not(test))]
#[no_mangle]
pub extern "system" fn checker_entry() -> ! {
    unsafe {
        let mut p = GetCommandLineA();
        let mut is_profile = false;
        while !p.is_null() && *p != 0 {
            if *p == b'-' && *p.add(1) == b'-' {
                is_profile = true;
                break;
            }
            p = p.add(1);
        }

        if !is_profile {
            let res = checker::check_missed_events();
            ExitProcess(if res != 0 { 1 } else { 0 });
        }

        let mut freq: i64 = 1;
        let mut t0: i64 = 0;
        let mut t1: i64 = 0;
        let mut c0: u64 = 0;
        let mut c1: u64 = 0;
        QueryPerformanceFrequency(&mut freq);
        QueryPerformanceCounter(&mut t0);
        QueryProcessCycleTime(GetCurrentProcess(), &mut c0);

        let res = checker::check_missed_events();

        QueryPerformanceCounter(&mut t1);
        QueryProcessCycleTime(GetCurrentProcess(), &mut c1);

        let mut h_out = GetStdHandle(STD_OUTPUT_HANDLE);
        if h_out.is_null() || h_out == INVALID_HANDLE_VALUE {
            AttachConsole(ATTACH_PARENT_PROCESS);
            h_out = GetStdHandle(STD_OUTPUT_HANDLE);
        }

        let elapsed_us = ((t1 - t0) as f64) * 1_000_000.0 / (freq as f64);
        write_bytes(h_out, b"====================================================\n");
        write_bytes(h_out, b"INTERNAL CODE EXECUTION (RUST ZERO-CRT)\n");
        write_bytes(h_out, b"====================================================\n");
        write_bytes(h_out, b"Total Internal Time   : ");
        write_f64_3(h_out, elapsed_us);
        write_bytes(h_out, b" us (");
        write_f64_3(h_out, elapsed_us / 1000.0);
        write_bytes(h_out, b" ms)\nTotal CPU Cycles      : ");
        write_u64(h_out, c1.saturating_sub(c0));
        write_bytes(h_out, b" cycles\nAlert Result          : ");
        if res != 0 {
            write_bytes(h_out, b"YES (Event 777 Dispatched, Exit Code 1)\n");
        } else {
            write_bytes(h_out, b"NO (Quiet State, Exit Code 0)\n");
        }
        write_bytes(h_out, b"====================================================\n");

        ExitProcess(if res != 0 { 1 } else { 0 });
    }
}
