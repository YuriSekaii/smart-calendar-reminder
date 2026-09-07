# Smart Calendar & Reminder App

> **A set-and-forget Windows reminder app that never runs in your background. Reliably pops up 5 minutes before daily, weekly, annual, or custom date events using Windows Task Scheduler.**

---

![Smart Calendar UI Preview](assets/preview.png)

---

## 💡 Overview

Most desktop reminder utilities run continuous background processes or infinite `while` loops, needlessly consuming system memory (RAM) and CPU cycles. 

**Smart Calendar & Reminder App** solves this problem by using a **native OS-level architecture**:
- When you schedule or update an event, the app automatically configures a scheduled job using **Windows Task Scheduler (`schtasks`)**.
- The GUI application closes completely—**0% background CPU and 0 MB RAM footprint**.
- Exactly **5 minutes before your scheduled event**, Windows wakes a lightweight checker that alerts you with sound and a popup dialog.

---

## ✨ Features

- **Zero Background Overhead:** Doesn't stay resident in system memory. Windows handles execution natively.
- **5-Minute Pre-Event Notifications:** Always triggers 5 minutes prior to give you time to prepare.
- **Flexible Recurrence Patterns:**
  - **One-time:** Specific date and time.
  - **Daily:** Recurring at a designated hour every day.
  - **Weekly:** Customizable days of the week (e.g., Monday, Wednesday, Friday).
  - **Annual:** Year-over-year milestones and anniversaries with 7-day advance notice.
- **Bootup Missed Event Check:** On computer startup, it intelligently scans if you missed any event while your PC was powered off.
- **Clean Tkinter GUI:**
  - Built-in monthly calendar picker (`tkcalendar`).
  - 1-click AM/PM time toggle.
  - Duration/end-time support.
  - Easy event search, editing, and deletion.
- **Audio & Visual Prompts:** Uses Windows audio cues (`winsound`) with non-intrusive interactive popups.

---

## 🛠️ Architecture

```
Calendar/
├── editor.py            # Main GUI management interface (Tkinter + tkcalendar)
├── checker.py           # Python notification trigger & alert dialog
├── checker_ultra.c      # Dual-target Zero-CRT C checker (standalone .exe + 58 µs in-memory .dll)
├── scheduler_helper.py  # Backend engine (JSON persistence, recurrence logic, Windows API / schtasks)
├── benchmark.py         # Automated reproducible benchmark test suite
├── BENCHMARK_RESULTS.md # Detailed run-by-run benchmark report & methodology
├── requirements.txt     # Python dependencies
└── reminders.json.example # Sample event structure
```

---

## ⚡ High-Performance Native C Checker (`checker_ultra.c`)

To eliminate interpreted runtime overhead during Windows startup, the project includes an ultra-fast **pure Win32 C implementation** (`checker_ultra.c`) that can be compiled as a **standalone executable (`checker_ultra.exe`)** for Windows Task Scheduler or as an **in-process shared library (`checker.dll`)**.

### Why Pure C & Zero CRT?
- **Zero C Runtime (`-nostdlib`):** No Python VM, no .NET runtime, and **zero `msvcrt.dll` CRT dependencies**. Links exclusively against `KERNEL32.dll` directly.
- **Microscopic Footprint:** Binary size is only **~8 KB**!
- **Asynchronous GUI Handoff:** Uses Win32 `CreateProcessA` for non-blocking asynchronous dispatch of the GUI popup dialog without stalling.
- **64-bit SWAR String Matching:** Scans JSON keys 8 bytes at a time in a single 64-bit ALU register operation (`0x656d697465746164ULL`).
- **Two-Tier Architecture:** 
  - On **system boot with no missed events (95%+ of boots)**: Scans JSON in microseconds and exits silently with zero popups.
  - If a missed event is found: Instantly dispatches the interactive alert window without blocking.

### 📊 Real-World Bootup Benchmarks (AMD Ryzen 5 5600X @ 3.7 GHz)

> 💡 **Why Process Lifetime & CPU Cycles Matter:**  
> A background checker occupies system RAM and CPU resources for the entire duration it remains open. While internal code logic may run quickly in memory, runtime bootstrap, module loading, and process teardown dictate real-world OS bootup impact. **The faster the process exits and closes, the faster 100% of its RAM and handles are released back to Windows.**

#### Scenario 1: Missed Event Detected (Popup Triggered)
*Action: Scan `reminders.json` $\rightarrow$ Match missed event $\rightarrow$ Asynchronously dispatch GUI alert popup.*

| Implementation | Type | Total Time Before Close (RAM Release) | Alert Handling | Peak RAM Overhead |
| :--- | :--- | :--- | :--- | :--- |
| **PyInstaller (`AutoChecker.exe`)** | Self-extracting archive | ~1,630 ms *(~1.63 s)* | Synchronous Python GUI bootstrap | ~45 MB (held in RAM) |
| **Raw Python (`checker.py`)** | CPython 3.11 VM | ~171.2 ms | Python VM initialization + GUI spawn | ~25 MB (held in RAM) |
| **Pure C Binary (`checker_ultra.exe`)** | **Standalone Win32 Process** | **13.90 ms** | **Non-blocking async `CreateProcessA`** | **< 1 MB (released in 13.9 ms)** |
| **Pure C DLL (`checker.dll`)** | **In-Process Shared Library** | **6.33 ms** | **In-memory scan + async `CreateProcessA`** | **0 MB extra (released in 6.3 ms)** |

#### Scenario 2: Quiet Bootup / No Event Detected (95%+ of System Boots)
*Action: Scan `reminders.json` $\rightarrow$ Zero missed events $\rightarrow$ Instant silent termination and RAM release.*

| Implementation | Type | Total Process Lifetime (RAM Release Time) | Total CPU Cycles Consumed | RAM Residency Impact |
| :--- | :--- | :--- | :--- | :--- |
| **PyInstaller (`AutoChecker.exe`)** | Self-extracting archive | ~1,558.9 ms *(~1.56 s)* | ~2,171,000,000 | ~45 MB held for 1.56 s |
| **Raw Python (`checker.py`)** | CPython 3.11 VM | ~67.8 ms | ~228,000,000 | ~25 MB held for 68 ms |
| **Pure C Binary (`checker_ultra.exe`)** | **Standalone Win32 Process** | **6.27 ms** | **~5,831,000** | **< 1 MB released in 6.27 ms** |
| **Pure C DLL (`checker.dll`)** | **In-Process Shared Library** | **0.318 ms** *(318 µs)* | **~190,000** | **0 MB extra released in 318 µs** |

> 🚀 **Key Performance Takeaways:**
> - **Immediate RAM Release on Quiet Boot:** The pure C executable (`checker_ultra.exe`) checks and exits cleanly in **6.27 ms** (**318 µs for DLL**), immediately returning 100% of allocated memory back to Windows. This is **~248x faster memory release** than PyInstaller while saving over **2.1 billion CPU clock cycles**.
> - **Zero-Blocking Alert Boot:** When a missed event is found, `checker_ultra.exe` hands off the popup dialog asynchronously via Win32 `CreateProcessA` and exits immediately in **13.90 ms**, allowing system startup to finish with zero delay while the GUI renders independently.

### Compiling the C Checker

Both the standalone `.exe` and the in-process `.dll` are built from the single source file [`checker_ultra.c`](checker_ultra.c):

```bash
# 1. Standalone Startup Binary (.EXE) - GUI subsystem, 64KB stack, no console flashing:
gcc -O3 -s -nostdlib -e mainCRTStartup -mwindows -fno-asynchronous-unwind-tables -fno-exceptions -fno-ident -fno-stack-protector -Wl,--subsystem,windows -Wl,--stack,65536 checker_ultra.c -lkernel32 -o checker_ultra.exe

# 2. In-Memory Shared Library (.DLL) - Ultra-fast 58 µs in-process check:
gcc -O3 -shared -s -nostdlib -e DllMain -fno-ident -fno-asynchronous-unwind-tables checker_ultra.c -lkernel32 -o checker.dll
```

### 🧪 Reproducing the Benchmarks

You can execute the automated benchmark suite directly on your machine:

```bash
python benchmark.py
```

*For complete run-by-run tables, QPC CPU hardware cycle analysis, and testing methodology, see [`BENCHMARK_RESULTS.md`](BENCHMARK_RESULTS.md).*

---

## 🚀 Getting Started

### Prerequisites
* Windows 10 / 11
* Python 3.9+

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/YuriSekaii/smart-calendar-reminder.git
   cd smart-calendar-reminder
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Launch the Calendar Editor:
   ```bash
   python editor.py
   ```

---

## 📦 Building Standalone Executables (Optional)

If you want to package the app into standalone Windows executables without requiring a Python environment:

```bash
pip install pyinstaller

# Build the GUI Editor
pyinstaller --noconsole --onefile editor.py -n MyCalendarApp

# Build the Background Checker
pyinstaller --noconsole --onefile checker.py -n AutoChecker
```

---

## 📄 License

This project is licensed under the MIT License.
