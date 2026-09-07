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

| Implementation | Architecture / Type | Process Lifetime / Time to Close | Alert Handling Mechanism | RAM Overhead & Footprint |
| :--- | :--- | :--- | :--- | :--- |
| **PyInstaller (`AutoChecker.exe`)** | Self-extracting archive | ~1,630 ms *(~1.63 s)* | Synchronous PyInstaller extract + Tkinter bootstrap | ~45 MB (held in RAM) |
| **Raw Python (`checker.py`)** | CPython 3.11 Runtime | ~171.2 ms | Synchronous Python GUI bootstrap | ~25 MB (held in RAM) |
| **Pure C Binary (`checker_ultra.exe`)** | **Standalone Win32 Process** | **13.90 ms** | **Non-blocking async `CreateProcessA`** | **< 1 MB (released in 13.9 ms)** |
| **Pure C DLL (`checker.dll`)** | **In-Process Shared Library** | **6.33 ms** | **In-memory scan + async `CreateProcessA`** | **0 MB extra (released in 6.3 ms)** |

* **Key Alert Advantage:** Rather than blocking the boot sequence to extract archives and initialize Tkinter, `checker_ultra.exe` uses non-blocking asynchronous `CreateProcessA`. It dispatches the alert in **~13.9 ms** and exits immediately, returning 100% of its memory to Windows while the GUI dialog renders independently.

---

## ⚡ Scenario 2: Quiet Bootup / No Event Detected (95%+ of System Boots)

**Action:** Scan `reminders.json` $\rightarrow$ Zero missed events $\rightarrow$ Instant silent exit & complete RAM release.

| Implementation | Architecture / Type | Total Process Lifetime (RAM Release) | Total CPU Hardware Cycles | Memory Impact on Startup |
| :--- | :--- | :--- | :--- | :--- |
| **PyInstaller (`AutoChecker.exe`)** | Self-extracting archive | ~1,558.9 ms *(~1.56 s)* | ~2,171,000,000 | ~45 MB held for 1.56 s |
| **Raw Python (`checker.py`)** | CPython 3.11 Runtime | ~67.8 ms | ~228,000,000 | ~25 MB held for 68 ms |
| **Pure C Binary (`checker_ultra.exe`)** | **Standalone Win32 Process** | **6.27 ms** | **~5,831,000** | **< 1 MB released in 6.27 ms** |
| **Pure C DLL (`checker.dll`)** | **In-Process Shared Library** | **0.318 ms** *(318 µs)* | **~190,000** | **0 MB extra released in 318 µs** |

---

## 📈 Cross-Implementation Comparison Table

| Implementation | Runtime / Engine | Binary Size | Quiet Process Lifetime (RAM Release) | Missed Event Checker Lifetime | Total CPU Cycles (Quiet Boot) | Memory Lifecycle |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **PyInstaller (`AutoChecker.exe`)** | Self-extracting archive | 11.2 MB | ~1,559 ms *(~1.56 s)* | ~1,630 ms | ~2,171,000,000 | Holds ~45 MB for > 1.5 s |
| **Raw Python (`checker.py`)** | CPython 3.11 Runtime | 12.1 KB | ~67.8 ms | ~171.2 ms | ~228,000,000 | Holds ~25 MB for 68 ms |
| **Pure C (`checker_ultra.exe`)** | **Bare-Metal Win32 (Zero CRT)** | **8.0 KB** | **6.27 ms** | **13.90 ms** | **~5,831,000** | **Freed in 6.27 ms (< 1 MB)** |
| **Pure C (`checker.dll`)** | **In-Process Shared Library** | **8.0 KB** | **0.318 ms (318 µs)** | **6.33 ms** | **~190,000** | **Freed in 318 µs (0 MB)** |

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
