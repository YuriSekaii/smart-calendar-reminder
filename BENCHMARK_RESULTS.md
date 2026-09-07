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

| Implementation | Architecture / Type | Process Lifetime / Time to Close | Alert Handling Mechanism | Exact Memory Footprint (Committed / Working Set) |
| :--- | :--- | :--- | :--- | :--- |
| **PyInstaller (`AutoChecker.exe`)** | Self-extracting archive | ~1,575 ms *(~1.58 s)* | Synchronous PyInstaller extract + Tkinter bootstrap | **49,208 KB (~49.2 MB)** *(7,352 KB bootloader + 41,856 KB GUI)* |
| **Raw Python (`checker.py`)** | CPython 3.11 Runtime | ~172.6 ms | Synchronous Python GUI bootstrap | **~25,000 KB (~25 MB)** held until dismissed |
| **Pure C Standalone (`checker_ultra.exe`)** | **Signal Mode (`--signal`)** | **8.98 ms** | **Microsecond Exit Code Bit `1`** | **76 KB Private Commit (Peak 496 KB) / 32 KB WS (Peak 3.0 MB)** |
| **Pure C Standalone (`checker_ultra.exe`)** | **Event Log Mode (`--event`)** | **9.88 ms** | **Task Scheduler `EventTrigger`** | **76 KB Private Commit (Peak 496 KB) / 32 KB WS (Peak 3.0 MB)** |
| **Pure C Standalone (`checker_ultra.exe`)** | **Direct Spawn (Default)** | **14.31 ms** | **Autonomous async `CreateProcessA`** | **76 KB Private Commit (Peak 496 KB) / 32 KB WS (Peak 3.0 MB)** |
| **Pure C DLL (`checker.dll`)** | **In-Process Shared Library** | **6.27 ms** | **In-memory scan + async `CreateProcessA`** | **64 KB static BSS buffer (0 KB heap, 0 MB host overhead)** |

* **Zero Boot Blocking:** Rather than stalling system bootup to extract archives and initialize Tkinter, `checker_ultra.exe` hands off the GUI in milliseconds and exits immediately, returning 100% of its working set memory to Windows while the GUI dialog renders independently.
* **Why `CreateProcess` Takes ~5 ms (Not "A Few CPU Cycles"):**  
  In Windows NT, launching a process is not a simple message send—it is a heavyweight synchronous kernel operation (`NtCreateUserProcess`). The operating system must:
  1. Open and validate the target executable on NTFS (`IoCreateFile`, parse PE headers).
  2. Allocate the `EPROCESS` block, page directory tables (PML4), and new Virtual Address Space.
  3. Map the executable sections and system DLLs (`ntdll.dll`, `kernel32.dll`).
  4. Synchronously notify kernel minifilters—including **Windows Defender (`WdFilter.sys`)** via `PsSetCreateProcessNotifyRoutineEx` to inspect the executable headers and process integrity before allowing execution.
  5. Perform an inter-process ALPC round-trip with the Windows Subsystem (`csrss.exe`) to register the process and thread IDs.  
  Only after the kernel and security subsystems finish this setup does `CreateProcess` return control. This synchronous kernel pipeline consumes ~4.85 ms (~18 million CPU clock cycles).
* **The "Mark a Bit" Solution (Microsecond Signaling):**
  To bypass kernel `CreateProcess` wait times completely:
  1. **Exit Code Bit (`--signal` / `-s`):** `checker_ultra.exe` sets its process exit code to `1` in `< 1 µs` (`ExitProcess(1)`). It exits in **8.98 ms** with **0 ms extra wait for GUI**. The launcher or Task Scheduler runs the GUI only if exit code 1 is received.
  2. **Windows Event Log (`--event` / `-e`):** `checker_ultra.exe` logs Event ID 1001 to the Windows Application Log via `ReportEventA` in **~300 µs**. The checker exits in **9.88 ms**, and Windows Task Scheduler natively catches the event via `<EventTrigger>` to start `AutoChecker.exe`.

---

## ⚡ Scenario 2: Quiet Bootup / No Event Detected (95%+ of System Boots)

**Action:** Scan `reminders.json` $\rightarrow$ Zero missed events $\rightarrow$ Instant silent exit & complete RAM release.

| Implementation | Architecture / Type | Total Process Lifetime (RAM Release) | Total CPU Hardware Cycles | Exact Memory Footprint (Committed / Working Set) |
| :--- | :--- | :--- | :--- | :--- |
| **PyInstaller (`AutoChecker.exe`)** | Self-extracting archive | ~1,415.7 ms *(~1.42 s)* | ~2,145,000,000 | ~45 MB held for 1.42 s |
| **Raw Python (`checker.py`)** | CPython 3.11 Runtime | ~66.9 ms | ~224,000,000 | ~25 MB held for 67 ms |
| **Pure C Binary (`checker_ultra.exe`)** | **Standalone Win32 Process** | **7.64 ms** | **~10,500,000** | **76 KB Private Commit (Peak 496 KB) / 32 KB WS (Peak 3.0 MB)** |
| **Pure C DLL (`checker.dll`)** | **In-Process Shared Library** | **0.322 ms** *(322 µs)* | **~190,000** | **64 KB static BSS buffer (0 KB heap overhead)** |

---

## 📈 Cross-Implementation Comparison Table

| Implementation | Runtime / Engine | Binary Size | Quiet Lifetime (RAM Release) | Missed Event Checker Lifetime | Total CPU Cycles (Quiet Boot) | Memory Lifecycle & Exact Footprint |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **PyInstaller (`AutoChecker.exe`)** | Self-extracting archive | 11.2 MB | ~1,415 ms *(~1.42 s)* | ~1,575 ms | ~2,145,000,000 | Holds **49,208 KB (~49.2 MB)** until dismissed |
| **Raw Python (`checker.py`)** | CPython 3.11 Runtime | 12.1 KB | ~66.9 ms | ~172.6 ms | ~224,000,000 | Holds **~25,000 KB (~25 MB)** until dismissed |
| **Pure C (`checker_ultra.exe`)** | **Standalone Win32 (`--signal`)** | **8.5 KB** | **7.64 ms** | **8.98 ms** | **~10,500,000** | **Freed in 7-9 ms (76 KB Private, 32 KB WS)** |
| **Pure C (`checker_ultra.exe`)** | **Standalone Win32 (`--event`)** | **8.5 KB** | **7.64 ms** | **9.88 ms** | **~10,500,000** | **Freed in 7-10 ms (76 KB Private, 32 KB WS)** |
| **Pure C (`checker_ultra.exe`)** | **Standalone Win32 (Direct)** | **8.5 KB** | **7.64 ms** | **14.31 ms** | **~10,500,000** | **Freed in 7-14 ms (76 KB Private, 32 KB WS)** |
| **Pure C (`checker.dll`)** | **In-Process Shared Library** | **8.5 KB** | **0.322 ms (322 µs)** | **6.27 ms** | **~190,000** | **Freed in 322 µs (64 KB static BSS buffer)** |

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
