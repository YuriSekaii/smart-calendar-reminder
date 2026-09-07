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
├── checker.py           # Lightweight notification trigger invoked by Windows Task Scheduler
├── scheduler_helper.py  # Backend engine (JSON persistence, recurrence logic, Windows API / schtasks)
├── requirements.txt     # Python dependencies
└── reminders.json.example # Sample event structure
```

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
