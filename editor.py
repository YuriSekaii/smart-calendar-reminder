import tkinter as tk
from tkinter import ttk, messagebox
from tkcalendar import Calendar
import os
import sys
from datetime import datetime
import scheduler_helper

WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

class AMPMToggle:
    """A 1-click toggle button between AM and PM"""
    def __init__(self, parent, initial="AM", on_change=None, can_toggle=None):
        self.value = initial.upper() if initial else "AM"
        self.on_change = on_change
        self.can_toggle = can_toggle
        self.state = "normal"
        self.btn = tk.Button(parent, text=self.value, font=("Arial", 9, "bold"),
                             width=4, cursor="hand2", padx=2, pady=1,
                             command=self.toggle)
        self.update_style()

    def toggle(self):
        if self.state == "disabled":
            return
        new_val = "PM" if self.value == "AM" else "AM"
        if self.can_toggle and not self.can_toggle(new_val):
            return
        self.value = new_val
        self.update_style()
        if self.on_change:
            self.on_change(self.value)

    def get(self):
        return self.value

    def set(self, val):
        self.value = val.upper() if val else "AM"
        self.update_style()

    def set_state(self, state):
        self.state = state
        self.btn.config(state=state)
        self.update_style()

    def update_style(self):
        self.btn.config(text=self.value)
        if self.state == "disabled":
            self.btn.config(bg="#E0E0E0", fg="#9E9E9E", relief=tk.FLAT)
        elif self.value == "AM":
            self.btn.config(bg="#E3F2FD", fg="#0D47A1", activebackground="#BBDEFB", relief=tk.RAISED)
        else:
            self.btn.config(bg="#FFF3E0", fg="#E65100", activebackground="#FFE0B2", relief=tk.RAISED)

class ReminderEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Calendar Note & Reminders")
        self.root.geometry("1120x750")
        self.root.minsize(1050, 700)

        self.reminders = []
        self.selected_cal_event_id = None
        self.selected_rec_event_id = None
        self.active_timetable_day = "Daily"
        self._updating_form = False

        main_container = tk.Frame(root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self.left_frame = tk.LabelFrame(main_container, text=" Date-Specific & Yearly Events ", font=("Arial", 11, "bold"), padx=8, pady=6)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))

        self.right_frame = tk.LabelFrame(main_container, text=" Daily & Weekly Reminders ", font=("Arial", 11, "bold"), padx=8, pady=6)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(4, 0))

        # Bottom Status Bar
        self.status_var = tk.StringVar(value="Ready")
        self.status_bar = tk.Label(root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W, font=("Arial", 9), bg="#F5F5F5")
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.setup_left_panel()
        self.setup_right_panel()

        self.load_all_data()

    # =========================================================================
    # LEFT PANEL: Date & Yearly Events
    # =========================================================================
    def setup_left_panel(self):
        top_bar = tk.Frame(self.left_frame)
        top_bar.pack(fill=tk.X, pady=(0, 2))

        tk.Label(top_bar, text="Select Date:", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        btn_today = tk.Button(top_bar, text="📅 Go to Today / Current Month", font=("Arial", 9, "bold"),
                              bg="#E3F2FD", fg="#0D47A1", activebackground="#BBDEFB",
                              command=self.go_to_today, cursor="hand2", padx=6, pady=1)
        btn_today.pack(side=tk.RIGHT)

        now = datetime.now()
        self.cal = Calendar(self.left_frame, selectmode='day', date_pattern='y-mm-dd',
                            showothermonthdays=True,
                            year=now.year, month=now.month, day=now.day)
        self.cal.pack(pady=2)
        self.cal.bind("<<CalendarSelected>>", self.on_date_click)

        self.cal.tag_config('has_note', background='#E53935', foreground='white')
        self.cal.tag_config('is_today', background='#FFE082', foreground='#000000')
        self.cal.tag_config('today_has_note', background='#B71C1C', foreground='#FFEB3B')

        legend = tk.Frame(self.left_frame)
        legend.pack(fill=tk.X, pady=(1, 2))
        tk.Label(legend, text="■ Today", fg="#FFA000", font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=3)
        tk.Label(legend, text="■ Has Event", fg="#E53935", font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=3)
        tk.Label(legend, text="■ Today + Event", fg="#B71C1C", font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=3)

        date_hdr = tk.Frame(self.left_frame)
        date_hdr.pack(fill=tk.X, pady=(2, 2))

        self.cal_date_label = tk.Label(date_hdr, text="Events for: YYYY-MM-DD", font=("Arial", 10, "bold"), fg="#1565C0")
        self.cal_date_label.pack(side=tk.LEFT)

        btn_new_cal_evt = tk.Button(date_hdr, text="＋ New Event on this Date", font=("Arial", 8, "bold"),
                                    bg="#E8F5E9", fg="#2E7D32", command=self.clear_cal_form, cursor="hand2", padx=4)
        btn_new_cal_evt.pack(side=tk.RIGHT)

        cal_table_frame = tk.Frame(self.left_frame)
        cal_table_frame.pack(fill=tk.BOTH, expand=False, pady=2)

        self.cal_tree = ttk.Treeview(cal_table_frame, columns=("time", "type", "note"), show="headings", selectmode="browse", height=4)
        self.cal_tree.heading("time", text="Time / Period")
        self.cal_tree.heading("type", text="Repeat")
        self.cal_tree.heading("note", text="Event Note")

        self.cal_tree.column("time", width=145, minwidth=120, stretch=False)
        self.cal_tree.column("type", width=60, minwidth=50, stretch=False)
        self.cal_tree.column("note", width=220, stretch=True)

        cal_scrl = ttk.Scrollbar(cal_table_frame, orient=tk.VERTICAL, command=self.cal_tree.yview)
        self.cal_tree.configure(yscrollcommand=cal_scrl.set)

        self.cal_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cal_scrl.pack(side=tk.RIGHT, fill=tk.Y)
        self.cal_tree.bind("<<TreeviewSelect>>", self.on_cal_tree_select)

        # Form Frame
        cal_form = tk.LabelFrame(self.left_frame, text=" Event Details ", font=("Arial", 9, "bold"), padx=6, pady=4)
        cal_form.pack(fill=tk.BOTH, expand=True, pady=(2, 2))

        # Time Row: Start Time & Optional End Time
        time_row = tk.Frame(cal_form)
        time_row.pack(fill=tk.X, pady=2)

        tk.Label(time_row, text="Start:", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(0, 2))
        self.cal_hour_var = tk.StringVar(value="09")
        self.cal_hour_sb = tk.Spinbox(time_row, from_=1, to=12, width=3, format="%02.0f", textvariable=self.cal_hour_var, font=("Arial", 9), wrap=True)
        self.cal_hour_sb.pack(side=tk.LEFT)
        tk.Label(time_row, text=":", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.cal_min_var = tk.StringVar(value="00")
        self.cal_min_sb = tk.Spinbox(time_row, from_=0, to=59, width=3, format="%02.0f", textvariable=self.cal_min_var, font=("Arial", 9), wrap=True)
        self.cal_min_sb.pack(side=tk.LEFT, padx=(0, 3))
        self.cal_ampm = AMPMToggle(time_row, initial="AM", on_change=lambda val: self.on_start_time_changed("cal"))
        self.cal_ampm.btn.pack(side=tk.LEFT, padx=(0, 10))

        # Optional End Time Checkbox & Pickers
        self.cal_has_end_var = tk.BooleanVar(value=False)
        self.cal_end_cb = tk.Checkbutton(time_row, text="End Time:", variable=self.cal_has_end_var,
                                         font=("Arial", 9, "bold"), command=self.on_cal_end_toggle)
        self.cal_end_cb.pack(side=tk.LEFT, padx=(0, 2))

        self.cal_end_hour_var = tk.StringVar(value="09")
        self.cal_end_hour_sb = tk.Spinbox(time_row, from_=1, to=12, width=3, format="%02.0f", textvariable=self.cal_end_hour_var, font=("Arial", 9), wrap=True)
        self.cal_end_hour_sb.pack(side=tk.LEFT)
        self.cal_end_colon = tk.Label(time_row, text=":", font=("Arial", 9, "bold"))
        self.cal_end_colon.pack(side=tk.LEFT)
        self.cal_end_min_var = tk.StringVar(value="00")
        self.cal_end_min_sb = tk.Spinbox(time_row, from_=0, to=59, width=3, format="%02.0f", textvariable=self.cal_end_min_var, font=("Arial", 9), wrap=True)
        self.cal_end_min_sb.pack(side=tk.LEFT, padx=(0, 3))
        self.cal_end_ampm = AMPMToggle(time_row, initial="AM")
        self.cal_end_ampm.btn.pack(side=tk.LEFT)

        self.cal_hour_var.trace_add("write", lambda *args: self.on_start_time_changed("cal"))
        self.cal_min_var.trace_add("write", lambda *args: self.on_start_time_changed("cal"))

        self.on_cal_end_toggle()

        # Options Row: Yearly Repeat
        opt_row = tk.Frame(cal_form)
        opt_row.pack(fill=tk.X, pady=2)
        self.annual_var = tk.BooleanVar(value=False)
        self.annual_cb = tk.Checkbutton(opt_row, text="Repeat Yearly (Birthdays / Anniversaries)", variable=self.annual_var, font=("Arial", 9))
        self.annual_cb.pack(side=tk.LEFT)

        # Note Text
        tk.Label(cal_form, text="Note:", font=("Arial", 9)).pack(anchor=tk.W, pady=(2, 0))
        self.cal_note_entry = tk.Text(cal_form, height=4, wrap=tk.WORD, font=("Arial", 9))
        self.cal_note_entry.pack(fill=tk.BOTH, expand=True, pady=2)

        # Action Buttons
        cal_btn_frame = tk.Frame(cal_form)
        cal_btn_frame.pack(fill=tk.X, pady=2)

        self.btn_save_cal = tk.Button(cal_btn_frame, text="Save / Add Event", bg="#4CAF50", fg="white", font=("Arial", 9, "bold"),
                                      width=15, command=self.save_cal_event, cursor="hand2")
        self.btn_save_cal.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_del_cal = tk.Button(cal_btn_frame, text="Delete Event", bg="#f44336", fg="white", font=("Arial", 9, "bold"),
                                     width=13, command=self.delete_cal_event, cursor="hand2")
        self.btn_del_cal.pack(side=tk.LEFT)

    def on_cal_end_toggle(self):
        state = "normal" if self.cal_has_end_var.get() else "disabled"
        self.cal_end_hour_sb.config(state=state)
        self.cal_end_min_sb.config(state=state)
        self.cal_end_colon.config(fg="#000000" if state == "normal" else "#9E9E9E")
        self.cal_end_ampm.set_state(state)
        if self.cal_has_end_var.get():
            self.sync_end_to_start_if_needed("cal")

    # =========================================================================
    # RIGHT PANEL: Weekly Timetable & Daily Reminders
    # =========================================================================
    def setup_right_panel(self):
        desc = tk.Label(self.right_frame, text="Click a day to view/add its recurring reminders. (Pops up 5 min ahead)",
                        font=("Arial", 8), fg="#555555", justify=tk.LEFT)
        desc.pack(anchor=tk.W, pady=(0, 3))

        tk.Label(self.right_frame, text="Weekly Time Table:", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(1, 2))

        timetable_bar = tk.Frame(self.right_frame)
        timetable_bar.pack(fill=tk.X, pady=(0, 4))

        self.day_buttons = {}
        timetable_days = ["Daily"] + WEEKDAY_SHORT

        for idx, day_name in enumerate(timetable_days):
            timetable_bar.grid_columnconfigure(idx, weight=1)
            btn = tk.Button(timetable_bar, text=day_name, font=("Arial", 9, "bold"), pady=2,
                            bg="#EEEEEE", fg="#333333", cursor="hand2", relief=tk.RAISED,
                            command=lambda d=day_name: self.on_select_timetable_day(d))
            btn.grid(row=0, column=idx, sticky="ew", padx=1)
            self.day_buttons[day_name] = btn

        rec_hdr = tk.Frame(self.right_frame)
        rec_hdr.pack(fill=tk.X, pady=(4, 2))

        self.rec_day_label = tk.Label(rec_hdr, text="Reminders for: Daily", font=("Arial", 10, "bold"), fg="#1565C0")
        self.rec_day_label.pack(side=tk.LEFT)

        self.btn_new_rec_evt = tk.Button(rec_hdr, text="＋ New Reminder for Daily", font=("Arial", 8, "bold"),
                                         bg="#E8F5E9", fg="#2E7D32", command=self.clear_rec_form, cursor="hand2", padx=4)
        self.btn_new_rec_evt.pack(side=tk.RIGHT)

        rec_table_frame = tk.Frame(self.right_frame)
        rec_table_frame.pack(fill=tk.BOTH, expand=True, pady=2)

        self.rec_tree = ttk.Treeview(rec_table_frame, columns=("time", "note"), show="headings", selectmode="browse", height=5)
        self.rec_tree.heading("time", text="Time / Period")
        self.rec_tree.heading("note", text="Reminder Note")

        self.rec_tree.column("time", width=155, minwidth=130, stretch=False)
        self.rec_tree.column("note", width=260, stretch=True)

        rec_scrl = ttk.Scrollbar(rec_table_frame, orient=tk.VERTICAL, command=self.rec_tree.yview)
        self.rec_tree.configure(yscrollcommand=rec_scrl.set)

        self.rec_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rec_scrl.pack(side=tk.RIGHT, fill=tk.Y)
        self.rec_tree.bind("<<TreeviewSelect>>", self.on_rec_tree_select)

        rec_form = tk.LabelFrame(self.right_frame, text=" Reminder Details ", font=("Arial", 9, "bold"), padx=6, pady=4)
        rec_form.pack(fill=tk.BOTH, expand=True, pady=(4, 2))

        sched_row = tk.Frame(rec_form)
        sched_row.pack(fill=tk.X, pady=2)

        tk.Label(sched_row, text="Start:", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(0, 2))
        self.rec_hour_var = tk.StringVar(value="09")
        self.rec_hour_sb = tk.Spinbox(sched_row, from_=1, to=12, width=3, format="%02.0f", textvariable=self.rec_hour_var, font=("Arial", 9), wrap=True)
        self.rec_hour_sb.pack(side=tk.LEFT)
        tk.Label(sched_row, text=":", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.rec_min_var = tk.StringVar(value="00")
        self.rec_min_sb = tk.Spinbox(sched_row, from_=0, to=59, width=3, format="%02.0f", textvariable=self.rec_min_var, font=("Arial", 9), wrap=True)
        self.rec_min_sb.pack(side=tk.LEFT, padx=(0, 3))
        self.rec_ampm = AMPMToggle(sched_row, initial="AM", on_change=lambda val: self.on_start_time_changed("rec"))
        self.rec_ampm.btn.pack(side=tk.LEFT, padx=(0, 10))

        # Optional End Time Checkbox & Pickers for Recurring
        self.rec_has_end_var = tk.BooleanVar(value=False)
        self.rec_end_cb = tk.Checkbutton(sched_row, text="End Time:", variable=self.rec_has_end_var,
                                         font=("Arial", 9, "bold"), command=self.on_rec_end_toggle)
        self.rec_end_cb.pack(side=tk.LEFT, padx=(0, 2))

        self.rec_end_hour_var = tk.StringVar(value="09")
        self.rec_end_hour_sb = tk.Spinbox(sched_row, from_=1, to=12, width=3, format="%02.0f", textvariable=self.rec_end_hour_var, font=("Arial", 9), wrap=True)
        self.rec_end_hour_sb.pack(side=tk.LEFT)
        self.rec_end_colon = tk.Label(sched_row, text=":", font=("Arial", 9, "bold"))
        self.rec_end_colon.pack(side=tk.LEFT)
        self.rec_end_min_var = tk.StringVar(value="00")
        self.rec_end_min_sb = tk.Spinbox(sched_row, from_=0, to=59, width=3, format="%02.0f", textvariable=self.rec_end_min_var, font=("Arial", 9), wrap=True)
        self.rec_end_min_sb.pack(side=tk.LEFT, padx=(0, 3))
        self.rec_end_ampm = AMPMToggle(sched_row, initial="AM")
        self.rec_end_ampm.btn.pack(side=tk.LEFT)

        self.rec_hour_var.trace_add("write", lambda *args: self.on_start_time_changed("rec"))
        self.rec_min_var.trace_add("write", lambda *args: self.on_start_time_changed("rec"))

        self.on_rec_end_toggle()

        # Day Indicator
        ind_row = tk.Frame(rec_form)
        ind_row.pack(fill=tk.X, pady=1)
        self.rec_day_indicator = tk.Label(ind_row, text="(Repeats Daily)", font=("Arial", 9, "italic"), fg="#555555")
        self.rec_day_indicator.pack(side=tk.LEFT)

        # Note Text
        tk.Label(rec_form, text="Note:", font=("Arial", 9)).pack(anchor=tk.W, pady=(2, 0))
        self.rec_note_entry = tk.Text(rec_form, height=5, wrap=tk.WORD, font=("Arial", 9))
        self.rec_note_entry.pack(fill=tk.BOTH, expand=True, pady=2)

        # Buttons
        rec_btn_frame = tk.Frame(rec_form)
        rec_btn_frame.pack(fill=tk.X, pady=2)

        self.btn_save_rec = tk.Button(rec_btn_frame, text="Save / Add Reminder", bg="#2196F3", fg="white",
                                      font=("Arial", 9, "bold"), width=18, command=self.save_rec_event, cursor="hand2")
        self.btn_save_rec.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_del_rec = tk.Button(rec_btn_frame, text="Delete Reminder", bg="#f44336", fg="white",
                                     font=("Arial", 9, "bold"), width=14, command=self.delete_rec_event, cursor="hand2")
        self.btn_del_rec.pack(side=tk.LEFT)

        self.highlight_timetable_button("Daily")

    def on_rec_end_toggle(self):
        state = "normal" if self.rec_has_end_var.get() else "disabled"
        self.rec_end_hour_sb.config(state=state)
        self.rec_end_min_sb.config(state=state)
        self.rec_end_colon.config(fg="#000000" if state == "normal" else "#9E9E9E")
        self.rec_end_ampm.set_state(state)
        if self.rec_has_end_var.get():
            self.sync_end_to_start_if_needed("rec")

    def sync_end_to_start_if_needed(self, panel="cal"):
        if self._updating_form:
            return

        if panel == "cal":
            sh = self.cal_hour_var.get()
            sm = self.cal_min_var.get()
            s_ampm = self.cal_ampm.get()
            eh = self.cal_end_hour_var.get()
            em = self.cal_end_min_var.get()
            e_ampm = self.cal_end_ampm.get()
        else:
            sh = self.rec_hour_var.get()
            sm = self.rec_min_var.get()
            s_ampm = self.rec_ampm.get()
            eh = self.rec_end_hour_var.get()
            em = self.rec_end_min_var.get()
            e_ampm = self.rec_end_ampm.get()

        needs_sync = False
        try:
            s24 = scheduler_helper.to_24h_str(int(sh), int(sm), s_ampm)
            e24 = scheduler_helper.to_24h_str(int(eh), int(em), e_ampm)
            if e24 <= s24:
                needs_sync = True
        except Exception:
            needs_sync = True

        if s_ampm == "PM" and e_ampm == "AM":
            needs_sync = True

        if needs_sync:
            if panel == "cal":
                self.cal_end_hour_var.set(sh)
                self.cal_end_min_var.set(sm)
                self.cal_end_ampm.set(s_ampm)
            else:
                self.rec_end_hour_var.set(sh)
                self.rec_end_min_var.set(sm)
                self.rec_end_ampm.set(s_ampm)

    def on_start_time_changed(self, panel="cal"):
        if self._updating_form:
            return

        if panel == "cal":
            has_end = self.cal_has_end_var.get()
            sh = self.cal_hour_var.get().strip()
            sm = self.cal_min_var.get().strip()
            s_ampm = self.cal_ampm.get()

            if not has_end:
                if sh.isdigit() and 1 <= int(sh) <= 12:
                    self.cal_end_hour_var.set(f"{int(sh):02d}")
                if sm.isdigit() and 0 <= int(sm) <= 59:
                    self.cal_end_min_var.set(f"{int(sm):02d}")
                self.cal_end_ampm.set(s_ampm)
        else:
            has_end = self.rec_has_end_var.get()
            sh = self.rec_hour_var.get().strip()
            sm = self.rec_min_var.get().strip()
            s_ampm = self.rec_ampm.get()

            if not has_end:
                if sh.isdigit() and 1 <= int(sh) <= 12:
                    self.rec_end_hour_var.set(f"{int(sh):02d}")
                if sm.isdigit() and 0 <= int(sm) <= 59:
                    self.rec_end_min_var.set(f"{int(sm):02d}")
                self.rec_end_ampm.set(s_ampm)

    def on_select_timetable_day(self, day_name):
        self.active_timetable_day = day_name
        self.highlight_timetable_button(day_name)

        if day_name == "Daily":
            self.rec_day_label.config(text="Reminders for: Daily")
            self.btn_new_rec_evt.config(text="＋ New Reminder for Daily")
            self.rec_day_indicator.config(text="(Repeats Daily)")
        else:
            self.rec_day_label.config(text=f"Reminders for: {day_name} (Weekly)")
            self.btn_new_rec_evt.config(text=f"＋ New Reminder on {day_name}")
            self.rec_day_indicator.config(text=f"(Repeats every {day_name})")

        self.load_recurring_events_for_active_day()

    def highlight_timetable_button(self, active_day):
        for name, btn in self.day_buttons.items():
            if name == active_day:
                btn.config(bg="#1976D2", fg="white", relief=tk.SUNKEN)
            else:
                btn.config(bg="#EEEEEE", fg="#333333", relief=tk.RAISED)

    # =========================================================================
    # DATA LOADING & SYNC
    # =========================================================================
    def load_all_data(self):
        self.reminders = scheduler_helper.load_reminders()

        self.cal.calevent_remove('all')

        today = datetime.now().date()
        curr_year = datetime.now().year
        dates_with_notes = set()

        for item in self.reminders:
            rtype = item.get("type", item.get("repeat", "once"))

            if rtype == "annual":
                dt_obj = scheduler_helper.parse_dt_fast(item.get("datetime"))
                if dt_obj:
                    for y in range(curr_year - 3, curr_year + 5):
                        try:
                            annual_dt = dt_obj.replace(year=y)
                            dates_with_notes.add(annual_dt.date())
                        except ValueError:
                            pass

            elif rtype == "once":
                dt_obj = scheduler_helper.parse_dt_fast(item.get("datetime"))
                if dt_obj:
                    dates_with_notes.add(dt_obj.date())

        # Batch create tags once per unique date to minimize Tkinter redraw overhead
        for d in dates_with_notes:
            if d != today:
                self.cal.calevent_create(d, 'Reminder', 'has_note')

        if today in dates_with_notes:
            self.cal.calevent_create(today, 'TodayNote', 'today_has_note')
        else:
            self.cal.calevent_create(today, 'Today', 'is_today')

        cur_date_str = self.cal.get_date()
        self.load_cal_events_for_date(cur_date_str)
        self.load_recurring_events_for_active_day()

        num_tasks = scheduler_helper.sync_all_tasks(self.reminders)
        self.status_var.set(f" Active Scheduled Reminders: {num_tasks} | 5-min alert auto-popup armed in Windows (0 background CPU)")

    # =========================================================================
    # LEFT PANEL LOGIC (Calendar & Multi-Event)
    # =========================================================================
    def go_to_today(self):
        today = datetime.now().date()
        self.cal.see(today)
        self.cal.selection_set(today)
        self.load_cal_events_for_date(today.strftime("%Y-%m-%d"))

    def on_date_click(self, event):
        self.root.after(50, self.smart_process_click)

    def smart_process_click(self):
        try:
            sel_date = self.cal.selection_get()
            if not sel_date:
                sel_date = datetime.strptime(self.cal.get_date(), "%Y-%m-%d").date()
        except Exception:
            try:
                sel_date = datetime.strptime(self.cal.get_date(), "%Y-%m-%d").date()
            except Exception:
                return

        disp_month, disp_year = self.cal.get_displayed_month()
        if sel_date.month != disp_month or sel_date.year != disp_year:
            self.cal.see(sel_date)

        date_str = sel_date.strftime("%Y-%m-%d")
        self.load_cal_events_for_date(date_str)

    def load_cal_events_for_date(self, date_str):
        self.cal_date_label.config(text=f"Events for: {date_str}")
        self.clear_cal_form()

        for row in self.cal_tree.get_children():
            self.cal_tree.delete(row)

        try:
            target_dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return

        date_events = []
        for item in self.reminders:
            irtype = item.get("type", item.get("repeat", "once"))
            if irtype == "once" and item.get("datetime", "").startswith(date_str):
                date_events.append(item)
            elif irtype == "annual":
                try:
                    val_dt = datetime.strptime(item['datetime'], "%Y-%m-%d %H:%M")
                    if val_dt.month == target_dt.month and val_dt.day == target_dt.day:
                        date_events.append(item)
                except Exception:
                    pass

        date_events.sort(key=lambda x: x.get("time", "09:00"))

        for evt in date_events:
            t_24 = evt.get("time", "09:00")
            has_end = evt.get("has_end_time", False)
            end_24 = evt.get("end_time")
            period_str = scheduler_helper.format_time_period(t_24, end_24, has_end)

            rep = "Yearly" if evt.get("type") == "annual" else "Once"
            note_snip = evt.get("note", "").replace("\n", " ")
            self.cal_tree.insert("", tk.END, iid=evt["id"], values=(period_str, rep, note_snip))

        if date_events:
            self.cal_tree.selection_set(date_events[0]["id"])
            self.populate_cal_form(date_events[0])

    def on_cal_tree_select(self, event):
        sel = self.cal_tree.selection()
        if not sel:
            return
        eid = sel[0]
        for item in self.reminders:
            if item.get("id") == eid:
                self.populate_cal_form(item)
                break

    def populate_cal_form(self, item):
        self._updating_form = True
        try:
            self.selected_cal_event_id = item.get("id")

            # Start Time
            t_24 = item.get("time", "09:00")
            h12, m12, ampm = scheduler_helper.to_12h_parts(t_24)
            self.cal_hour_var.set(h12)
            self.cal_min_var.set(m12)
            self.cal_ampm.set(ampm)

            # End Time
            has_end = item.get("has_end_time", False)
            self.cal_has_end_var.set(has_end)

            end_24 = item.get("end_time")
            if has_end and end_24:
                eh12, em12, eampm = scheduler_helper.to_12h_parts(end_24)
                self.cal_end_hour_var.set(eh12)
                self.cal_end_min_var.set(em12)
                self.cal_end_ampm.set(eampm)
            else:
                self.cal_end_hour_var.set(h12)
                self.cal_end_min_var.set(m12)
                self.cal_end_ampm.set(ampm)

            self.on_cal_end_toggle()

            self.annual_var.set(item.get("type") == "annual" or item.get("repeat") == "annual")

            self.cal_note_entry.delete("1.0", tk.END)
            self.cal_note_entry.insert(tk.END, item.get("note", ""))
            self.btn_save_cal.config(text="Update Event")
        finally:
            self._updating_form = False

    def clear_cal_form(self):
        self._updating_form = True
        try:
            self.selected_cal_event_id = None
            self.cal_hour_var.set("09")
            self.cal_min_var.set("00")
            self.cal_ampm.set("AM")

            self.cal_has_end_var.set(False)
            self.cal_end_hour_var.set("09")
            self.cal_end_min_var.set("00")
            self.cal_end_ampm.set("AM")
            self.on_cal_end_toggle()

            self.annual_var.set(False)
            self.cal_note_entry.delete("1.0", tk.END)
            self.btn_save_cal.config(text="Save / Add Event")
            self.cal_tree.selection_remove(self.cal_tree.selection())
        finally:
            self._updating_form = False

    def save_cal_event(self):
        selected_date = self.cal.get_date()
        note_text = self.cal_note_entry.get("1.0", tk.END).strip()

        if not note_text:
            messagebox.showwarning("Warning", "Note cannot be empty.")
            return

        try:
            h = int(self.cal_hour_var.get())
            m = int(self.cal_min_var.get())
            if not (1 <= h <= 12 and 0 <= m <= 59):
                raise ValueError()
        except ValueError:
            messagebox.showerror("Error", "Start hour must be 1-12, and minute must be 0-59.")
            return

        ampm = self.cal_ampm.get()
        start_time_24 = scheduler_helper.to_24h_str(h, m, ampm)

        has_end = self.cal_has_end_var.get()
        end_time_24 = None
        if has_end:
            try:
                eh = int(self.cal_end_hour_var.get())
                em = int(self.cal_end_min_var.get())
                if not (1 <= eh <= 12 and 0 <= em <= 59):
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Error", "End hour must be 1-12, and minute must be 0-59.")
                return
            eampm = self.cal_end_ampm.get()
            end_time_24 = scheduler_helper.to_24h_str(eh, em, eampm)

            if end_time_24 < start_time_24:
                ans = messagebox.askyesno(
                    "Warning: Overnight Event",
                    f"End time should be later than start time.\n\n"
                    f"Start: {scheduler_helper.to_12h_str(start_time_24)}\n"
                    f"End:   {scheduler_helper.to_12h_str(end_time_24)} (Next Day)\n\n"
                    f"Save this as an OVERNIGHT event?"
                )
                if not ans:
                    return
            elif end_time_24 == start_time_24:
                ans = messagebox.askyesno(
                    "Warning: Same Start and End Time",
                    f"End time should be later than start time.\n\n"
                    f"Start time and End time are currently identical ({scheduler_helper.to_12h_str(start_time_24)}).\n\n"
                    f"Do you still want to save this event?"
                )
                if not ans:
                    return

        full_datetime_str = f"{selected_date} {start_time_24}"
        is_annual = self.annual_var.get()
        rtype = "annual" if is_annual else "once"

        entry = {
            "id": self.selected_cal_event_id if self.selected_cal_event_id else "rem_" + os.urandom(4).hex(),
            "datetime": full_datetime_str,
            "time": start_time_24,
            "has_end_time": has_end,
            "end_time": end_time_24,
            "is_overnight": (end_time_24 < start_time_24) if has_end and end_time_24 else False,
            "note": note_text,
            "type": rtype,
            "repeat": rtype
        }

        if self.selected_cal_event_id:
            for idx, item in enumerate(self.reminders):
                if item.get("id") == self.selected_cal_event_id:
                    self.reminders[idx] = entry
                    break
        else:
            self.reminders.append(entry)

        scheduler_helper.save_reminders(self.reminders)
        self.load_all_data()

        period = scheduler_helper.format_time_period(start_time_24, end_time_24, has_end)
        messagebox.showinfo("Saved", f"Event saved for {selected_date} ({period})")

    def delete_cal_event(self):
        if not self.selected_cal_event_id:
            messagebox.showinfo("Info", "Please select an event from the list to delete.")
            return

        to_remove = None
        for item in self.reminders:
            if item.get("id") == self.selected_cal_event_id:
                to_remove = item
                break

        if to_remove:
            selected_date = self.cal.get_date()
            self.reminders.remove(to_remove)
            scheduler_helper.save_reminders(self.reminders)
            self.load_all_data()
            messagebox.showinfo("Deleted", "Event removed.")

    # =========================================================================
    # RIGHT PANEL LOGIC (Weekly Timetable & Recurring Multi-Event)
    # =========================================================================
    def load_recurring_events_for_active_day(self):
        self.clear_rec_form()

        for row in self.rec_tree.get_children():
            self.rec_tree.delete(row)

        day = self.active_timetable_day
        events = []

        for item in self.reminders:
            rtype = item.get("type", item.get("repeat", "once"))
            if day == "Daily":
                if rtype == "daily":
                    events.append(item)
            else:
                if rtype == "weekly":
                    dname = item.get("day_name", "Mon")[:3]
                    if dname == day:
                        events.append(item)

        events.sort(key=lambda x: x.get("time", "09:00"))

        for evt in events:
            t_24 = evt.get("time", "09:00")
            has_end = evt.get("has_end_time", False)
            end_24 = evt.get("end_time")
            period_str = scheduler_helper.format_time_period(t_24, end_24, has_end)
            note_snip = evt.get("note", "").replace("\n", " ")
            self.rec_tree.insert("", tk.END, iid=evt["id"], values=(period_str, note_snip))

        if events:
            self.rec_tree.selection_set(events[0]["id"])
            self.populate_rec_form(events[0])

    def on_rec_tree_select(self, event):
        sel = self.rec_tree.selection()
        if not sel:
            return
        rid = sel[0]
        for item in self.reminders:
            if item.get("id") == rid:
                self.populate_rec_form(item)
                break

    def populate_rec_form(self, item):
        self._updating_form = True
        try:
            self.selected_rec_event_id = item.get("id")

            # Start Time
            time_24 = item.get("time", "09:00")
            h12, m12, ampm = scheduler_helper.to_12h_parts(time_24)
            self.rec_hour_var.set(h12)
            self.rec_min_var.set(m12)
            self.rec_ampm.set(ampm)

            # End Time
            has_end = item.get("has_end_time", False)
            self.rec_has_end_var.set(has_end)

            end_24 = item.get("end_time")
            if has_end and end_24:
                eh12, em12, eampm = scheduler_helper.to_12h_parts(end_24)
                self.rec_end_hour_var.set(eh12)
                self.rec_end_min_var.set(em12)
                self.rec_end_ampm.set(eampm)
            else:
                self.rec_end_hour_var.set(h12)
                self.rec_end_min_var.set(m12)
                self.rec_end_ampm.set(ampm)

            self.on_rec_end_toggle()

            self.rec_note_entry.delete("1.0", tk.END)
            self.rec_note_entry.insert(tk.END, item.get("note", ""))
            self.btn_save_rec.config(text="Update Reminder")
        finally:
            self._updating_form = False

    def clear_rec_form(self):
        self._updating_form = True
        try:
            self.selected_rec_event_id = None
            self.rec_hour_var.set("09")
            self.rec_min_var.set("00")
            self.rec_ampm.set("AM")

            self.rec_has_end_var.set(False)
            self.rec_end_hour_var.set("09")
            self.rec_end_min_var.set("00")
            self.rec_end_ampm.set("AM")
            self.on_rec_end_toggle()

            self.rec_note_entry.delete("1.0", tk.END)
            self.btn_save_rec.config(text="Save / Add Reminder")
            self.rec_tree.selection_remove(self.rec_tree.selection())
        finally:
            self._updating_form = False

    def save_rec_event(self):
        note_text = self.rec_note_entry.get("1.0", tk.END).strip()
        if not note_text:
            messagebox.showwarning("Warning", "Reminder note cannot be empty.")
            return

        try:
            h = int(self.rec_hour_var.get())
            m = int(self.rec_min_var.get())
            if not (1 <= h <= 12 and 0 <= m <= 59):
                raise ValueError()
        except ValueError:
            messagebox.showerror("Error", "Start hour must be 1-12, and minute must be 0-59.")
            return

        ampm = self.rec_ampm.get()
        start_time_24 = scheduler_helper.to_24h_str(h, m, ampm)

        has_end = self.rec_has_end_var.get()
        end_time_24 = None
        if has_end:
            try:
                eh = int(self.rec_end_hour_var.get())
                em = int(self.rec_end_min_var.get())
                if not (1 <= eh <= 12 and 0 <= em <= 59):
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Error", "End hour must be 1-12, and minute must be 0-59.")
                return
            eampm = self.rec_end_ampm.get()
            end_time_24 = scheduler_helper.to_24h_str(eh, em, eampm)

            if end_time_24 < start_time_24:
                ans = messagebox.askyesno(
                    "Warning: Overnight Event",
                    f"End time should be later than start time.\n\n"
                    f"Start: {scheduler_helper.to_12h_str(start_time_24)}\n"
                    f"End:   {scheduler_helper.to_12h_str(end_time_24)} (Next Day)\n\n"
                    f"Save this as an OVERNIGHT event?"
                )
                if not ans:
                    return
            elif end_time_24 == start_time_24:
                ans = messagebox.askyesno(
                    "Warning: Same Start and End Time",
                    f"End time should be later than start time.\n\n"
                    f"Start time and End time are currently identical ({scheduler_helper.to_12h_str(start_time_24)}).\n\n"
                    f"Do you still want to save this reminder?"
                )
                if not ans:
                    return

        day = self.active_timetable_day
        rtype = "daily" if day == "Daily" else "weekly"

        entry = {
            "id": self.selected_rec_event_id if self.selected_rec_event_id else "rem_" + os.urandom(4).hex(),
            "time": start_time_24,
            "has_end_time": has_end,
            "end_time": end_time_24,
            "is_overnight": (end_time_24 < start_time_24) if has_end and end_time_24 else False,
            "note": note_text,
            "type": rtype,
            "repeat": rtype
        }

        if rtype == "weekly":
            entry["day_name"] = day
            entry["weekday"] = WEEKDAY_SHORT.index(day)

        if self.selected_rec_event_id:
            for idx, item in enumerate(self.reminders):
                if item.get("id") == self.selected_rec_event_id:
                    self.reminders[idx] = entry
                    break
        else:
            self.reminders.append(entry)

        scheduler_helper.save_reminders(self.reminders)
        self.load_all_data()

        period = scheduler_helper.format_time_period(start_time_24, end_time_24, has_end)
        messagebox.showinfo("Saved", f"Reminder saved for {day} ({period})!")

    def delete_rec_event(self):
        if not self.selected_rec_event_id:
            messagebox.showinfo("Info", "Please select a reminder from the list to delete.")
            return

        to_remove = None
        for item in self.reminders:
            if item.get("id") == self.selected_rec_event_id:
                to_remove = item
                break

        if to_remove:
            self.reminders.remove(to_remove)
            scheduler_helper.save_reminders(self.reminders)
            self.load_all_data()
            messagebox.showinfo("Deleted", "Reminder removed.")

if __name__ == "__main__":
    root = tk.Tk()
    app = ReminderEditor(root)
    root.mainloop()
