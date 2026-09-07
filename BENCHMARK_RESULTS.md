# 📊 Bootup Checker Benchmark Results

Authoritative performance benchmarks comparing the native Zero-CRT Win32 Bootup Checker against traditional CPython and PyInstaller implementations.

**Hardware Environment:**
* **CPU:** AMD Ryzen 5 5600X 6-Core Processor @ 3.70 GHz (Max Boost 4.65 GHz)
* **OS:** Windows 11 Pro 64-bit
* **Compiler:** MinGW-w64 GCC 16.2.0 (`-O3 -s -nostdlib`)
* **Timing Mechanism:** High-precision Win32 QueryPerformanceCounter (QPC) CPU hardware registers (Resolution: < 100 ns)

---

## 🎯 Executive Summary & Methodology

A background checker utility consumes system resources for the entire duration it remains active. Measuring only internal microsecond execution time ignores process creation overhead, runtime bootstrap, module loading, and process teardown.

What actually matters to system bootup and OS responsiveness is:
1. **Total Process Lifetime (Time to Exit & Free RAM):** The faster a process closes, the faster 100% of its working set memory, thread pool, and OS handles are released back to Windows.
2. **Total CPU Hardware Cycles Consumed:** The exact number of CPU clock cycles burned from process invocation to termination.

---

## 🔬 Scenario 1: Missed Event Detected (Popup Triggered)

**Action:** Scan `reminders.json` $\rightarrow$ Match missed event from earlier today $\rightarrow$ Dispatch interactive GUI alert popup.

| Implementation | Architecture / Type | Process Lifetime / Time to Close | Alert Handling Mechanism | RAM Working Set Footprint |
| :--- | :--- | :--- | :--- | :--- |
| **PyInstaller (`AutoChecker.exe`)** | Self-extracting archive | ~1,550 ms *(~1.55 s)* | Synchronous PyInstaller extract + Tkinter bootstrap | ~45 MB (held until dismissed) |
| **Raw Python (`checker.py`)** | CPython 3.11 Runtime | ~172.2 ms | Synchronous Python GUI bootstrap | ~25 MB (held until dismissed) |
| **Pure C Binary (`checker_ultra.exe`)** | **Standalone Win32 Process** | **14.06 ms** | **Non-blocking async `CreateProcessA`** | **< 1 MB (freed in 14 ms)** |
| **Pure C DLL (`checker.dll`)** | **In-Process Shared Library** | **6.42 ms** | **In-memory scan + async `CreateProcessA`** | **~64 KB (freed in 6.4 ms)** |

* **Zero Boot Blocking:** Rather than stalling system bootup to extract archives and initialize Tkinter, `checker_ultra.exe` uses non-blocking asynchronous `CreateProcessA`. It dispatches the alert in **~14.0 ms** (or **~6.4 ms** for DLL) and exits immediately, returning 100% of its working set memory to Windows while the GUI dialog renders independently.
* **Why Alert Dispatch Takes ~6 ms (Not "A Few CPU Cycles"):**  
  In Windows NT, launching a process is not a simple message send—it is a heavyweight synchronous kernel operation (`NtCreateUserProcess`). The operating system must:
  1. Open and validate the target executable on NTFS (`IoCreateFile`, parse PE headers).
  2. Allocate the `EPROCESS` block, page directory tables, and new Virtual Address Space.
  3. Map the executable sections and system DLLs (`ntdll.dll`, `kernel32.dll`).
  4. Synchronously notify kernel minifilters—including **Windows Defender (`WdFilter.sys`)** via `PsSetCreateProcessNotifyRoutineEx` to inspect the executable and process integrity.
  5. Perform an inter-process ALPC round-trip with the Windows Subsystem (`csrss.exe`) to register the process and thread IDs.  
  Only after the kernel and security subsystems finish this setup does `CreateProcess` return control.

---

## ⚡ Scenario 2: Quiet Bootup / No Event Detected (95%+ of System Boots)

**Action:** Scan `reminders.json` $\rightarrow$ Zero missed events $\rightarrow$ Instant silent exit & complete RAM release.

| Implementation | Architecture / Type | Total Process Lifetime (RAM Release) | Total CPU Hardware Cycles | Peak RAM Working Set |
| :--- | :--- | :--- | :--- | :--- |
| **PyInstaller (`AutoChecker.exe`)** | Self-extracting archive | ~1,458.0 ms *(~1.46 s)* | ~2,187,000,000 | ~45 MB held for 1.46 s |
| **Raw Python (`checker.py`)** | CPython 3.11 Runtime | ~65.9 ms | ~222,000,000 | ~25 MB held for 66 ms |
| **Pure C Binary (`checker_ultra.exe`)** | **Standalone Win32 Process** | **5.98 ms** | **~5,700,000** | **< 1 MB freed in 5.98 ms** |
| **Pure C DLL (`checker.dll`)** | **In-Process Shared Library** | **0.318 ms** *(318 µs)* | **~190,000** | **~64 KB freed in 318 µs** |

---

## 📈 Cross-Implementation Comparison Table

| Implementation | Runtime / Engine | Binary Size | Quiet Process Lifetime (RAM Release) | Missed Event Checker Lifetime | Total CPU Cycles (Quiet Boot) | Memory Lifecycle |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **PyInstaller (`AutoChecker.exe`)** | Self-extracting archive | 11.2 MB | ~1,458 ms *(~1.46 s)* | ~1,550 ms | ~2,187,000,000 | Holds ~45 MB for > 1.4 s |
| **Raw Python (`checker.py`)** | CPython 3.11 Runtime | 12.1 KB | ~65.9 ms | ~172.2 ms | ~222,000,000 | Holds ~25 MB for 66 ms |
| **Pure C (`checker_ultra.exe`)** | **Bare-Metal Win32 (Zero CRT)** | **8.0 KB** | **5.98 ms** | **14.06 ms** | **~5,700,000** | **Freed in 5.98 ms (< 1 MB)** |
| **Pure C (`checker.dll`)** | **In-Process Shared Library** | **8.0 KB** | **0.318 ms (318 µs)** | **6.42 ms** | **~190,000** | **Freed in 318 µs (~64 KB)** |

---

## 🛠️ How to Reproduce

You can reproduce all benchmarks directly on your Windows PC by running the automated benchmark suite included in the repository:

```bash
python benchmark.py
```

The script automatically:
1. Backs up your `reminders.json` safely.
2. Checks for `checker_ultra.exe` and `checker.dll` (recompiling via GCC if needed).
3. Executes 5 runs for each scenario.
4. Cleans up temporary processes and restores your exact personal reminders database.
