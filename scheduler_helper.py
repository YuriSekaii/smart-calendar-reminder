import os
import sys
import json
import uuid
import subprocess
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_SCHTASKS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)

def parse_dt_fast(dt_str):
    """Fast parse of 'YYYY-MM-DD HH:MM' string, falling back to strptime if needed."""
    if not dt_str or not isinstance(dt_str, str):
        return None
    try:
        if len(dt_str) == 16 and dt_str[4] == '-' and dt_str[7] == '-' and dt_str[10] == ' ' and dt_str[13] == ':':
            return datetime(int(dt_str[:4]), int(dt_str[5:7]), int(dt_str[8:10]), int(dt_str[11:13]), int(dt_str[14:16]))
    except Exception:
        pass
    try:
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    except Exception:
        return None

def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

DATA_FILE = os.path.join(get_app_dir(), "reminders.json")
ACTIVE_ALERTS_FILE = os.path.join(get_app_dir(), "active_alerts.json")
DISMISSED_FILE = os.path.join(get_app_dir(), "dismissed_today.json")
PID_FILE = os.path.join(get_app_dir(), "notify.pid")
TASK_MANIFEST_FILE = os.path.join(get_app_dir(), "scheduled_tasks.json")

# --- 12-HOUR / 24-HOUR TIME HELPERS ---

def to_12h_str(time_24h):
    """Converts '14:30' -> '02:30 PM'"""
    try:
        h, m = map(int, time_24h.split(":"))
        am_pm = "AM" if h < 12 else "PM"
        h12 = h % 12
        if h12 == 0:
            h12 = 12
        return f"{h12:02d}:{m:02d} {am_pm}"
    except Exception:
        return str(time_24h)

def to_12h_parts(time_24h):
    """Converts '14:30' -> ('02', '30', 'PM')"""
    try:
        h, m = map(int, time_24h.split(":"))
        am_pm = "AM" if h < 12 else "PM"
        h12 = h % 12
        if h12 == 0:
            h12 = 12
        return f"{h12:02d}", f"{m:02d}", am_pm
    except Exception:
        return "09", "00", "AM"

def to_24h_str(hour_12, minute, am_pm):
    """Converts ('02', '30', 'PM') -> '14:30'"""
    try:
        h = int(hour_12) % 12
        if str(am_pm).upper() == "PM":
            h += 12
        return f"{h:02d}:{int(minute):02d}"
    except Exception:
        return "09:00"

def format_time_period(start_24h, end_24h=None, has_end_time=False):
    """Formats '18:00' and '20:00' -> '06:00 PM - 08:00 PM', overnight -> '10:00 PM - 02:00 AM (+1d)'"""
    start_str = to_12h_str(start_24h)
    if has_end_time and end_24h:
        end_str = to_12h_str(end_24h)
        if end_24h < start_24h:
            return f"{start_str} - {end_str} (+1d)"
        return f"{start_str} - {end_str}"
    return start_str

def get_checker_executable_path():
    app_dir = get_app_dir()
    exe_candidate = os.path.join(app_dir, "AutoChecker.exe")
    if os.path.exists(exe_candidate):
        return exe_candidate
    dist_candidate = os.path.join(app_dir, "dist", "AutoChecker.exe")
    if os.path.exists(dist_candidate):
        return dist_candidate
    py_candidate = os.path.join(app_dir, "checker.py")
    if os.path.exists(py_candidate):
        return f'"{sys.executable}" "{py_candidate}"'
    return exe_candidate

def load_reminders(file_path=DATA_FILE):
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    modified = False
    cleaned_data = []
    for item in data:
        if not item.get("id"):
            item["id"] = "rem_" + uuid.uuid4().hex[:8]
            modified = True

        repeat = item.get("repeat", "none")
        if item.get("is_annual", False):
            repeat = "annual"
            item["repeat"] = "annual"

        if "type" not in item:
            item["type"] = repeat if repeat in ["daily", "weekly", "annual"] else "once"
            modified = True

        if "has_end_time" not in item:
            item["has_end_time"] = False
            item["end_time"] = None
            modified = True

        if "time" not in item and "datetime" in item:
            try:
                dt = parse_dt_fast(item["datetime"])
                if dt:
                    item["time"] = dt.strftime("%H:%M")
                    if item["type"] == "weekly" and "weekday" not in item:
                        item["weekday"] = dt.weekday()
                        item["day_name"] = WEEKDAY_SHORT[dt.weekday()]
                    modified = True
            except Exception:
                pass

        if item["type"] == "weekly":
            if "weekday" not in item:
                item["weekday"] = 0
                item["day_name"] = "Mon"
                modified = True
            elif "day_name" not in item:
                item["day_name"] = WEEKDAY_SHORT[item["weekday"] % 7]
                modified = True
            elif len(item["day_name"]) > 3:
                idx = item["weekday"] % 7
                item["day_name"] = WEEKDAY_SHORT[idx]
                modified = True

        cleaned_data.append(item)

    if modified:
        save_reminders(cleaned_data, file_path)

    return cleaned_data

def save_reminders(reminders, file_path=DATA_FILE):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(reminders, f, indent=4, ensure_ascii=False)
    except Exception:
        pass

# --- DISMISSED & ACTIVE ALERTS STATE ---

def get_dismissed_today():
    today_str = datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(DISMISSED_FILE):
        return set()
    try:
        with open(DISMISSED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("date") == today_str:
                return set(data.get("dismissed_ids", []))
    except Exception:
        pass
    return set()

def record_dismissed_today(reminder_ids):
    today_str = datetime.now().strftime("%Y-%m-%d")
    current = get_dismissed_today()
    for rid in reminder_ids:
        current.add(rid)
    try:
        with open(DISMISSED_FILE, "w", encoding="utf-8") as f:
            json.dump({"date": today_str, "dismissed_ids": list(current)}, f, indent=4)
    except Exception:
        pass

    clear_active_alerts(reminder_ids)

def get_active_alerts():
    if not os.path.exists(ACTIVE_ALERTS_FILE):
        return []
    try:
        with open(ACTIVE_ALERTS_FILE, "r", encoding="utf-8") as f:
            alerts = json.load(f)
            today_str = datetime.now().strftime("%Y-%m-%d")
            return [a for a in alerts if a.get("date") == today_str]
    except Exception:
        return []

def add_active_alert(reminder):
    alerts = get_active_alerts()
    today_str = datetime.now().strftime("%Y-%m-%d")
    existing_ids = {a["id"] for a in alerts}
    if reminder["id"] not in existing_ids:
        time_period = format_time_period(reminder.get("time", "09:00"),
                                          reminder.get("end_time"),
                                          reminder.get("has_end_time", False))
        alerts.append({
            "id": reminder["id"],
            "time": reminder.get("time", "09:00"),
            "end_time": reminder.get("end_time"),
            "has_end_time": reminder.get("has_end_time", False),
            "time_display": time_period,
            "note": reminder.get("note", ""),
            "type": reminder.get("type", "once"),
            "date": today_str,
            "triggered_at": datetime.now().isoformat()
        })
        try:
            with open(ACTIVE_ALERTS_FILE, "w", encoding="utf-8") as f:
                json.dump(alerts, f, indent=4)
        except Exception:
            pass

def clear_active_alerts(reminder_ids=None):
    if not os.path.exists(ACTIVE_ALERTS_FILE):
        return
    try:
        if reminder_ids is None:
            with open(ACTIVE_ALERTS_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
        else:
            remove_set = set(reminder_ids)
            alerts = get_active_alerts()
            remaining = [a for a in alerts if a["id"] not in remove_set]
            with open(ACTIVE_ALERTS_FILE, "w", encoding="utf-8") as f:
                json.dump(remaining, f, indent=4)
    except Exception:
        pass

# --- PID MANAGEMENT ---

def write_notify_pid():
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

def close_previous_notify():
    if not os.path.exists(PID_FILE):
        return
    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            old_pid = int(f.read().strip())
        if old_pid != os.getpid():
            PROCESS_TERMINATE = 0x0001
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, old_pid)
            if handle:
                ctypes.windll.kernel32.TerminateProcess(handle, 0)
                ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        pass
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except Exception:
        pass

# --- TASKBAR GLOWING YELLOW NOTIFICATION ---

class FLASHWINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.UINT),
        ('hwnd', wintypes.HWND),
        ('dwFlags', wintypes.DWORD),
        ('uCount', wintypes.UINT),
        ('dwTimeout', wintypes.DWORD)
    ]

def flash_window_glow(root):
    try:
        root.update_idletasks()
        child_hwnd = root.winfo_id()
        parent_hwnd = ctypes.windll.user32.GetParent(child_hwnd)
        hwnd = parent_hwnd if parent_hwnd != 0 else child_hwnd
        info = FLASHWINFO()
        info.cbSize = ctypes.sizeof(FLASHWINFO)
        info.hwnd = hwnd
        info.dwFlags = 3 | 12  # FLASHW_ALL | FLASHW_TIMERNOFG
        info.uCount = 0
        info.dwTimeout = 0
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass

def get_event_occurrence_on_date(item, target_date):
    """
    Returns (applies, start_dt, end_dt, is_overnight) for an event starting on target_date.
    """
    rtype = item.get("type", item.get("repeat", "once"))
    applies = False

    if rtype == "daily":
        applies = True
    elif rtype == "weekly":
        wday = item.get("weekday", 0)
        if wday == target_date.weekday():
            applies = True
    elif rtype == "annual":
        dt = parse_dt_fast(item.get("datetime"))
        if dt and dt.month == target_date.month and dt.day == target_date.day:
            applies = True
    elif rtype == "once":
        dt = parse_dt_fast(item.get("datetime"))
        if dt and dt.date() == target_date:
            applies = True

    if not applies:
        return False, None, None, False

    time_str = item.get("time", "09:00")
    has_end_time = item.get("has_end_time", False)
    end_time_str = item.get("end_time")

    try:
        h, m = map(int, time_str.split(":"))
        start_dt = datetime(target_date.year, target_date.month, target_date.day, h, m)
    except Exception:
        return False, None, None, False

    end_dt = None
    is_overnight = False
    if has_end_time and end_time_str:
        try:
            eh, em = map(int, end_time_str.split(":"))
            end_dt = datetime(target_date.year, target_date.month, target_date.day, eh, em)
            if end_dt < start_dt:
                end_dt += timedelta(days=1)
                is_overnight = True
        except Exception:
            pass

    return True, start_dt, end_dt, is_overnight

# --- MISSED EVENTS FROM EARLIER TODAY ---

def get_missed_events_today(reminders=None, now=None):
    """
    Finds events from earlier TODAY or overnight events that should notify at bootup.
    Rules:
    - For daily/weekly, if the PC boots up after the END TIME, DO NOT notify.
    - If the PC boots up during an ongoing event (including overnight), DO notify with ONGOING badge.
    - If a specific date/annual event passed, DO notify.
    """
    if reminders is None:
        reminders = load_reminders()

    if now is None:
        now = datetime.now()
    today = now.date()
    yesterday = today - timedelta(days=1)
    dismissed_ids = get_dismissed_today()

    missed = []
    seen_ids = set()

    for item in reminders:
        rid = item.get("id")
        if not rid or rid in dismissed_ids:
            continue

        rtype = item.get("type", item.get("repeat", "once"))
        dname = item.get("day_name", "Mon")[:3]
        type_label = "Daily" if rtype == "daily" else (f"Weekly ({dname})" if rtype == "weekly" else ("Yearly" if rtype == "annual" else "Once"))
        time_str = item.get("time", "09:00")
        has_end_time = item.get("has_end_time", False)
        end_time_str = item.get("end_time")
        time_display = format_time_period(time_str, end_time_str, has_end_time)

        # 1. Check overnight occurrence that started YESTERDAY
        y_applies, y_start, y_end, y_overnight = get_event_occurrence_on_date(item, yesterday)
        if y_applies and y_overnight and y_end:
            if y_start <= now <= y_end:
                missed.append({
                    "id": rid,
                    "time": time_str,
                    "end_time": end_time_str,
                    "has_end_time": has_end_time,
                    "is_overnight": True,
                    "time_display": time_display,
                    "datetime": y_start,
                    "type": rtype,
                    "type_label": type_label,
                    "status_badge": "ONGOING OVERNIGHT EVENT",
                    "note": item.get("note", "")
                })
                seen_ids.add(rid)
                continue
            elif now > y_end:
                if rtype in ["once", "annual"]:
                    missed.append({
                        "id": rid,
                        "time": time_str,
                        "end_time": end_time_str,
                        "has_end_time": has_end_time,
                        "is_overnight": True,
                        "time_display": time_display,
                        "datetime": y_start,
                        "type": rtype,
                        "type_label": type_label,
                        "status_badge": "MISSED OVERNIGHT EVENT",
                        "note": item.get("note", "")
                    })
                    seen_ids.add(rid)
                    continue

        # 2. Check occurrence starting TODAY
        t_applies, start_dt, end_dt, is_overnight = get_event_occurrence_on_date(item, today)
        if t_applies and rid not in seen_ids:
            if rtype in ["daily", "weekly"] and end_dt and now > end_dt:
                continue

            if start_dt <= now:
                is_ongoing = end_dt and start_dt <= now <= end_dt
                if is_ongoing:
                    status_badge = "ONGOING OVERNIGHT EVENT" if is_overnight else "ONGOING EVENT TODAY"
                else:
                    status_badge = "MISSED EARLIER TODAY"

                missed.append({
                    "id": rid,
                    "time": time_str,
                    "end_time": end_time_str,
                    "has_end_time": has_end_time,
                    "is_overnight": is_overnight,
                    "time_display": time_display,
                    "datetime": start_dt,
                    "type": rtype,
                    "type_label": type_label,
                    "status_badge": status_badge,
                    "note": item.get("note", "")
                })
                seen_ids.add(rid)

    missed.sort(key=lambda x: x["datetime"])
    return missed

# --- CHRONOLOGICAL TIMELINE RESOLVER ---

def get_today_timeline(reminders, current_trigger_id=None, now=None):
    if now is None:
        now = datetime.now()
    today = now.date()
    yesterday = today - timedelta(days=1)
    dismissed_ids = get_dismissed_today()

    events_for_today = []
    seen_ids = set()

    for item in reminders:
        rid = item["id"]
        rtype = item.get("type", item.get("repeat", "once"))
        time_str = item.get("time", "09:00")
        has_end_time = item.get("has_end_time", False)
        end_time_str = item.get("end_time")
        note = item.get("note", "")
        time_display = format_time_period(time_str, end_time_str, has_end_time)

        # Yesterday overnight ongoing
        y_applies, y_start, y_end, y_overnight = get_event_occurrence_on_date(item, yesterday)
        if y_applies and y_overnight and y_end and (y_start <= now <= y_end):
            is_dismissed = rid in dismissed_ids
            if not (is_dismissed and rid != current_trigger_id):
                events_for_today.append({
                    "id": rid,
                    "time": time_str,
                    "end_time": end_time_str,
                    "has_end_time": has_end_time,
                    "is_overnight": True,
                    "time_12h": time_display,
                    "datetime": y_start,
                    "note": note,
                    "type": rtype,
                    "status": "ongoing",
                    "is_highlight": True
                })
                seen_ids.add(rid)

        # Today's occurrence
        t_applies, start_dt, end_dt, is_overnight = get_event_occurrence_on_date(item, today)
        if t_applies and rid not in seen_ids:
            is_passed = now > start_dt
            is_dismissed = rid in dismissed_ids

            if is_passed and is_dismissed and rid != current_trigger_id:
                continue

            status = "upcoming"
            is_highlight = False

            if rid == current_trigger_id:
                is_highlight = True
                status = "triggering"
            elif is_passed and not is_dismissed:
                if end_dt and start_dt <= now <= end_dt:
                    status = "ongoing"
                    is_highlight = True
                else:
                    status = "unclosed"
            elif abs((start_dt - now).total_seconds()) <= 360:
                is_highlight = True
                status = "triggering"

            events_for_today.append({
                "id": rid,
                "time": time_str,
                "end_time": end_time_str,
                "has_end_time": has_end_time,
                "is_overnight": is_overnight,
                "time_12h": time_display,
                "datetime": start_dt,
                "note": note,
                "type": rtype,
                "status": status,
                "is_highlight": is_highlight
            })
            seen_ids.add(rid)

    events_for_today.sort(key=lambda x: x["datetime"])
    return events_for_today

# --- WINDOWS TASK SCHEDULER (schtasks) ---

def get_registered_manifest():
    if not os.path.exists(TASK_MANIFEST_FILE):
        return {}
    try:
        with open(TASK_MANIFEST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return {t: "" for t in data}
            elif isinstance(data, dict):
                return data
            return {}
    except Exception:
        return {}

def save_registered_manifest(manifest):
    try:
        with open(TASK_MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=4)
    except Exception:
        pass

def delete_scheduled_task(task_name):
    try:
        subprocess.run(['schtasks', '/Delete', '/TN', task_name, '/F'],
                       capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass

def sync_all_tasks(reminders=None):
    if reminders is None:
        reminders = load_reminders()

    checker_exe = get_checker_executable_path()
    now = datetime.now()

    old_manifest = get_registered_manifest()
    new_manifest = {}

    for item in reminders:
        rid = item.get("id")
        if not rid:
            continue

        clean_id = "".join(c for c in rid if c.isalnum() or c == "_")
        task_name = f"MyCalendar_{clean_id}"
        time_str = item.get("time", "09:00")
        rtype = item.get("type", item.get("repeat", "once"))

        try:
            hour, minute = map(int, time_str.split(":"))
        except Exception:
            continue

        dummy_dt = datetime(2026, 1, 1, hour, minute) - timedelta(minutes=5)
        st_time = dummy_dt.strftime("%H:%M")

        if checker_exe.startswith('"'):
            tr_cmd = f'{checker_exe} --alert {rid}'
        else:
            tr_cmd = f'"{checker_exe}" --alert {rid}'

        create_cmd = None
        task_sig = ""

        if rtype == "daily":
            task_sig = f"DAILY|{st_time}|{tr_cmd}"
            create_cmd = [
                'schtasks', '/Create', '/SC', 'DAILY',
                '/TN', task_name,
                '/TR', tr_cmd,
                '/ST', st_time,
                '/F'
            ]

        elif rtype == "weekly":
            wday = item.get("weekday", 0) % 7
            day_sch = WEEKDAY_SCHTASKS[wday]
            task_sig = f"WEEKLY|{day_sch}|{st_time}|{tr_cmd}"
            create_cmd = [
                'schtasks', '/Create', '/SC', 'WEEKLY',
                '/D', day_sch,
                '/TN', task_name,
                '/TR', tr_cmd,
                '/ST', st_time,
                '/F'
            ]

        elif rtype in ["once", "annual"]:
            event_dt = parse_dt_fast(item.get("datetime"))
            if not event_dt:
                continue

            target_dt = event_dt - timedelta(minutes=5)

            if rtype == "annual":
                try:
                    target_dt = target_dt.replace(year=now.year)
                except ValueError:
                    target_dt = target_dt.replace(year=now.year, month=3, day=1)

                if target_dt < now:
                    try:
                        target_dt = target_dt.replace(year=now.year + 1)
                    except ValueError:
                        target_dt = target_dt.replace(year=now.year + 1, month=3, day=1)

            elif rtype == "once":
                if target_dt < now:
                    continue

            sd_date = target_dt.strftime("%m/%d/%Y")
            st_time = target_dt.strftime("%H:%M")
            task_sig = f"ONCE|{sd_date}|{st_time}|{tr_cmd}"

            create_cmd = [
                'schtasks', '/Create', '/SC', 'ONCE',
                '/TN', task_name,
                '/TR', tr_cmd,
                '/SD', sd_date,
                '/ST', st_time,
                '/F'
            ]

        if create_cmd and task_sig:
            # Check if task is already configured with the exact same parameters
            if task_name in old_manifest and old_manifest[task_name] == task_sig:
                new_manifest[task_name] = task_sig
            else:
                res = subprocess.run(create_cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
                if res.returncode == 0:
                    new_manifest[task_name] = task_sig

    # Automatically register Windows Task Scheduler Event Trigger for SmartCalendar Event ID 777
    event_task_name = "MyCalendar_EventAlert"
    event_sig = f"ONEVENT|777|{checker_exe}"
    if event_task_name in old_manifest and old_manifest[event_task_name] == event_sig:
        new_manifest[event_task_name] = event_sig
    else:
        event_cmd = [
            'schtasks', '/Create',
            '/TN', event_task_name,
            '/TR', checker_exe if checker_exe.startswith('"') else f'"{checker_exe}"',
            '/SC', 'ONEVENT',
            '/EC', 'Application',
            '/MO', "*[System[Provider[@Name='SmartCalendar'] and (EventID=777)]]",
            '/F'
        ]
        res = subprocess.run(event_cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        if res.returncode == 0:
            new_manifest[event_task_name] = event_sig

    # Clean up obsolete or deleted tasks
    for old_t in old_manifest:
        if old_t not in new_manifest:
            delete_scheduled_task(old_t)

    save_registered_manifest(new_manifest)
    return len(new_manifest)
