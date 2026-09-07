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

**Action:** Scan `reminders.json` $\rightarrow$ Match missed event from earlier today $\rightarrow$ Dispatch Event ID 777 to Windows Task Scheduler.

| Implementation | Architecture / Type | Process Lifetime / Time to Close | Alert Handling Mechanism | Exact Memory Footprint (Committed / Working Set) |
| :--- | :--- | :--- | :--- | :--- |
| **PyInstaller (`AutoChecker.exe`)** | Self-extracting archive | ~1,519.7 ms *(~1.52 s)* | Synchronous PyInstaller extract + Tkinter bootstrap | **49,208 KB (~49.2 MB)** *(7,352 KB bootloader + 41,856 KB GUI)* |
| **Raw Python (`checker.py`)** | CPython 3.11 Runtime | ~174.9 ms | Synchronous Python GUI bootstrap | **~25,000 KB (~25 MB)** held until dismissed |
| **Pure C Standalone (`checker_ultra.exe`)** | **Standalone Win32 Process** | **9.98 ms** | **Windows Event 777 Handoff (60 µs)** | **76 KB Private Commit (Peak 496 KB) / 32 KB WS (Peak 3.0 MB)** |
| **Pure C DLL (`checker.dll`)** | **In-Process Shared Library** | **1.12 ms** *(597 µs internal)* | **Windows Event 777 Handoff (60 µs)** | **64 KB static BSS buffer (0 KB heap, 0 MB host overhead)** |

* **The 16x DLL Speedup:** When using `checker.dll`, calling `CreateProcessA` directly took **~5.8 ms** of CPU time inside the process. By instead calling `ReportEventA` with Event ID 777, the handoff completes in **60 µs**, dropping the DLL's in-memory execution time to **~0.35–0.59 ms**—a **16.4x speedup**!
* **Why Task Scheduler EventTrigger is Best:**  
  1. Windows Task Scheduler service (`Schedule` in `svchost.exe`) is already running natively in Windows at 0 extra user RAM.
  2. The checker signals Event ID 777 in **60 µs** and terminates immediately.
  3. Task Scheduler catches Event ID 777 and starts `AutoChecker.exe` asynchronously (~200 ms later).
  4. By the time the GUI renders, `checker_ultra.exe` has already been dead and closed for 190 ms, and 100% of its memory has been released to Windows.
* **Why Custom Event ID 777 Has Zero Collision:**  
  Event ID 1001 in Windows is shared with Windows Error Reporting (crash dumps). Using custom Event ID **777** with source name `SmartCalendar` guarantees that no other system event or app crash will ever collide with the reminder trigger.

---

## ⚡ Scenario 2: Quiet Bootup / No Event Detected (95%+ of System Boots)

**Action:** Scan `reminders.json` $\rightarrow$ Zero missed events $\rightarrow$ Instant silent exit & complete RAM release.

| Implementation | Architecture / Type | Total Process Lifetime (RAM Release) | Total CPU Hardware Cycles | Exact Memory Footprint (Committed / Working Set) |
| :--- | :--- | :--- | :--- | :--- |
| **PyInstaller (`AutoChecker.exe`)** | Self-extracting archive | ~1,392.5 ms *(~1.39 s)* | ~2,146,000,000 | ~45 MB held for 1.39 s |
| **Raw Python (`checker.py`)** | CPython 3.11 Runtime | ~66.1 ms | ~222,000,000 | ~25 MB held for 66 ms |
| **Pure C Binary (`checker_ultra.exe`)** | **Standalone Win32 Process** | **7.79 ms** | **~10,600,000** | **76 KB Private Commit (Peak 496 KB) / 32 KB WS (Peak 3.0 MB)** |
| **Pure C DLL (`checker.dll`)** | **In-Process Shared Library** | **0.339 ms** *(339 µs)* | **~190,000** | **64 KB static BSS buffer (0 KB heap overhead)** |

---

## 📈 Cross-Implementation Comparison Table

| Implementation | Runtime / Engine | Binary Size | Quiet Lifetime (RAM Release) | Missed Event Checker Lifetime | Total CPU Cycles (Quiet Boot) | Memory Lifecycle & Exact Footprint |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **PyInstaller (`AutoChecker.exe`)** | Self-extracting archive | 11.2 MB | ~1,392 ms *(~1.39 s)* | ~1,519 ms | ~2,146,000,000 | Holds **49,208 KB (~49.2 MB)** until dismissed |
| **Raw Python (`checker.py`)** | CPython 3.11 Runtime | 12.1 KB | ~66.1 ms | ~174.9 ms | ~222,000,000 | Holds **~25,000 KB (~25 MB)** until dismissed |
| **Pure C (`checker_ultra.exe`)** | **Standalone Win32 Process** | **7.5 KB** | **7.79 ms** | **9.98 ms** | **~10,600,000** | **Freed in 7-10 ms (76 KB Private, 32 KB WS)** |
| **Pure C (`checker.dll`)** | **In-Process Shared Library** | **7.5 KB** | **0.339 ms (339 µs)** | **1.12 ms** *(597 µs internal)* | **~190,000** | **Freed in 339 µs (64 KB static BSS buffer)** |

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
