import tkinter as tk
from tkinter import ttk
import os
import sys
from datetime import datetime, timedelta
import winsound
import scheduler_helper

def check_bootup_reminders():
    reminders = scheduler_helper.load_reminders()

    # 1. Check for missed/ongoing events from EARLIER TODAY
    # (Daily/Weekly past their end time are filtered out!)
    missed_today = scheduler_helper.get_missed_events_today(reminders)

    # 2. Check 7-day advance notice for Specific Date & Yearly events (Daily/Weekly excluded)
    upcoming_7days = []
    now = datetime.now()
    range_limit = now + timedelta(days=7)

    for item in reminders:
        rtype = item.get("type", item.get("repeat", "once"))
        if rtype in ["daily", "weekly"]:
            continue

        event_time = scheduler_helper.parse_dt_fast(item.get('datetime'))
        if not event_time:
            continue
        try:
            is_annual = rtype == "annual" or item.get("repeat") == "annual" or item.get("is_annual", False)

            if is_annual:
                try:
                    target_event = event_time.replace(year=now.year)
                except ValueError:
                    target_event = event_time.replace(year=now.year, month=3, day=1)

                if target_event < now:
                    try:
                        target_event = event_time.replace(year=now.year + 1)
                    except ValueError:
                        target_event = event_time.replace(year=now.year + 1, month=3, day=1)
            else:
                target_event = event_time

            # Advance notice: only future events in the next 7 days
            if now < target_event <= range_limit:
                time_left = target_event - now
                days = time_left.days
                hours = time_left.seconds // 3600
                note = item.get('note', '')
                if is_annual:
                    note += " (Yearly Event 🎂)"

                time_12h = target_event.strftime("%Y-%m-%d %I:%M %p")
                if item.get("has_end_time") and item.get("end_time"):
                    time_12h += f" - {scheduler_helper.to_12h_str(item['end_time'])}"

                upcoming_7days.append({
                    "id": item.get("id"),
                    "time_str": time_12h,
                    "remaining": f"{days} Days, {hours} Hours",
                    "note": note
                })
        except Exception:
            continue

    return missed_today, upcoming_7days

def show_bootup_notification(missed_today, upcoming_7days):
    root = tk.Tk()
    root.title("Calendar Reminders & Alerts")
    root.geometry("540x480")
    root.minsize(480, 400)

    root.attributes('-topmost', True)
    scheduler_helper.flash_window_glow(root)

    # Play alert chime
    try:
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        pass

    # Header
    if missed_today:
        hdr_bg = "#D32F2F"
        hdr_text = "⚠️ You Have Events From Today!"
    else:
        hdr_bg = "#1976D2"
        hdr_text = "📅 Upcoming Events Reminder"

    hdr = tk.Frame(root, bg=hdr_bg, pady=8)
    hdr.pack(fill=tk.X)
    tk.Label(hdr, text=hdr_text, font=("Arial", 12, "bold"), fg="white", bg=hdr_bg).pack()

    # Scrollable frame for cards
    container = tk.Frame(root)
    container.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

    canvas = tk.Canvas(container, highlightthickness=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def on_mousewheel(event):
        try:
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        except Exception:
            pass
    canvas.bind_all("<MouseWheel>", on_mousewheel)

    # 1. Render Missed/Ongoing Events from Today
    if missed_today:
        sec1 = tk.Frame(scrollable_frame)
        sec1.pack(fill=tk.X, pady=(4, 2))
        tk.Label(sec1, text="⚠️ Events from Today (Started while PC was Off):", font=("Arial", 10, "bold"), fg="#D32F2F").pack(anchor=tk.W)

        for m in missed_today:
            card = tk.Frame(scrollable_frame, bg="#FFEBEE", bd=2, relief=tk.SOLID, padx=8, pady=6)
            card.pack(fill=tk.X, expand=True, pady=3, padx=2)

            top = tk.Frame(card, bg="#FFEBEE")
            top.pack(fill=tk.X)
            tk.Label(top, text=f"Time: {m['time_display']} ({m['type_label']})", font=("Arial", 10, "bold"), bg="#FFEBEE", fg="#B71C1C").pack(side=tk.LEFT)
            badge = m.get("status_badge", "MISSED EARLIER TODAY")
            badge_fg = "#E65100" if "ONGOING" in badge else "#C62828"
            tk.Label(top, text=badge, font=("Arial", 8, "bold"), bg="#FFEBEE", fg=badge_fg).pack(side=tk.RIGHT)

            tk.Label(card, text=m['note'], font=("Arial", 9), bg="#FFEBEE", fg="#333333",
                     wraplength=460, justify=tk.LEFT).pack(anchor=tk.W, pady=(4, 0))

    # 2. Render Upcoming 7-day Advance Notice
    if upcoming_7days:
        sec2 = tk.Frame(scrollable_frame)
        sec2.pack(fill=tk.X, pady=(10, 2))
        tk.Label(sec2, text="📅 Upcoming in the Next 7 Days:", font=("Arial", 10, "bold"), fg="#1565C0").pack(anchor=tk.W)

        for u in upcoming_7days:
            card = tk.Frame(scrollable_frame, bg="#E3F2FD", bd=1, relief=tk.SOLID, padx=8, pady=6)
            card.pack(fill=tk.X, expand=True, pady=3, padx=2)

            top = tk.Frame(card, bg="#E3F2FD")
            top.pack(fill=tk.X)
            tk.Label(top, text=f"Date: {u['time_str']}", font=("Arial", 10, "bold"), bg="#E3F2FD", fg="#0D47A1").pack(side=tk.LEFT)
            tk.Label(top, text=f"In: {u['remaining']}", font=("Arial", 8, "bold"), bg="#E3F2FD", fg="#1565C0").pack(side=tk.RIGHT)

            tk.Label(card, text=u['note'], font=("Arial", 9), bg="#E3F2FD", fg="#333333",
                     wraplength=460, justify=tk.LEFT).pack(anchor=tk.W, pady=(4, 0))

    def on_dismiss(event=None):
        try:
            canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        try:
            if missed_today:
                scheduler_helper.record_dismissed_today([m["id"] for m in missed_today])
        except Exception:
            pass
        try:
            if os.path.exists(scheduler_helper.PID_FILE):
                os.remove(scheduler_helper.PID_FILE)
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass

    root.protocol("WM_DELETE_WINDOW", on_dismiss)

    btn_frame = tk.Frame(root, pady=8)
    btn_frame.pack(fill=tk.X)
    tk.Button(btn_frame, text="Dismiss / OK", bg="#4CAF50", fg="white", font=("Arial", 10, "bold"),
              width=18, pady=4, command=on_dismiss, cursor="hand2").pack()

    root.mainloop()

def show_5min_alert(trigger_id=None):
    scheduler_helper.close_previous_notify()
    scheduler_helper.write_notify_pid()

    try:
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        pass

    reminders = scheduler_helper.load_reminders()

    if trigger_id:
        for r in reminders:
            if r.get("id") == trigger_id:
                scheduler_helper.add_active_alert(r)
                break

    events = scheduler_helper.get_today_timeline(reminders, current_trigger_id=trigger_id)

    shown_ids = [e["id"] for e in events if e.get("status") in ["triggering", "unclosed"]]
    if trigger_id and trigger_id not in shown_ids:
        shown_ids.append(trigger_id)

    root = tk.Tk()
    root.title("⏰ Reminder Alert (In 5 Minutes!)")
    root.geometry("520x490")
    root.minsize(460, 410)

    root.attributes('-topmost', True)
    scheduler_helper.flash_window_glow(root)

    header_frame = tk.Frame(root, bg="#FF9800", pady=8)
    header_frame.pack(fill=tk.X)
    tk.Label(header_frame, text="🔔 UPCOMING REMINDER (Starting in 5 Minutes!)",
             font=("Arial", 12, "bold"), fg="white", bg="#FF9800").pack()

    container = tk.Frame(root)
    container.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

    canvas = tk.Canvas(container, highlightthickness=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def on_mousewheel(event):
        try:
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        except Exception:
            pass
    canvas.bind_all("<MouseWheel>", on_mousewheel)

    if not events:
        tk.Label(scrollable_frame, text="Event alert triggered.", font=("Arial", 10)).pack(pady=20)
    else:
        for evt in events:
            is_hl = evt.get("is_highlight", False)
            status = evt.get("status", "upcoming")
            time_display = evt.get("time_12h", scheduler_helper.to_12h_str(evt.get("time", "09:00")))
            note_val = evt.get("note", "").strip()
            etype = evt.get("type", "once").capitalize()

            if is_hl or status == "triggering":
                card_bg = "#FFF8E1"
                border_col = "#FFA000"
                badge_text = "⚠️ STARTING IN 5 MINUTES"
                badge_fg = "#E65100"
                title_font = ("Arial", 11, "bold")
            elif status == "unclosed":
                card_bg = "#FFEBEE"
                border_col = "#E53935"
                badge_text = "📌 UNCLOSED FROM EARLIER"
                badge_fg = "#C62828"
                title_font = ("Arial", 10, "bold")
            else:
                card_bg = "#F5F5F5"
                border_col = "#BDBDBD"
                badge_text = "📅 LATER TODAY"
                badge_fg = "#616161"
                title_font = ("Arial", 10)

            card = tk.Frame(scrollable_frame, bg=card_bg, bd=2, relief=tk.SOLID, padx=8, pady=6)
            card.pack(fill=tk.X, expand=True, pady=4, padx=2)

            card_top = tk.Frame(card, bg=card_bg)
            card_top.pack(fill=tk.X)

            tk.Label(card_top, text=f"Time: {time_display} ({etype})", font=title_font, bg=card_bg, fg="#212121").pack(side=tk.LEFT)
            tk.Label(card_top, text=badge_text, font=("Arial", 8, "bold"), fg=badge_fg, bg=card_bg).pack(side=tk.RIGHT)

            tk.Label(card, text=note_val, font=("Arial", 9), bg=card_bg, fg="#333333",
                     wraplength=440, justify=tk.LEFT).pack(anchor=tk.W, pady=(4, 0))

    def on_dismiss(event=None):
        try:
            canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        try:
            if shown_ids:
                scheduler_helper.record_dismissed_today(shown_ids)
        except Exception:
            pass
        try:
            if os.path.exists(scheduler_helper.PID_FILE):
                os.remove(scheduler_helper.PID_FILE)
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass

    root.protocol("WM_DELETE_WINDOW", on_dismiss)

    btn_frame = tk.Frame(root, pady=8)
    btn_frame.pack(fill=tk.X)
    tk.Button(btn_frame, text="Dismiss / OK", bg="#4CAF50", fg="white", font=("Arial", 10, "bold"),
              width=18, pady=4, command=on_dismiss, cursor="hand2").pack()

    root.mainloop()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--alert":
        trigger_id = sys.argv[2] if len(sys.argv) > 2 else None
        show_5min_alert(trigger_id)
    else:
        scheduler_helper.sync_all_tasks()
        missed_today, upcoming_7days = check_bootup_reminders()
        if missed_today or upcoming_7days:
            show_bootup_notification(missed_today, upcoming_7days)
        else:
            sys.exit(0)
