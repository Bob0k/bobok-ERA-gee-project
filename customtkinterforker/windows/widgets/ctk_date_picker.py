from datetime import date, timedelta

from .ctk_frame import CTkFrame
from .ctk_button import CTkButton
from .ctk_entry import CTkEntry

translate = {
    "Jan": "Январь",
    "Feb": "Февраль",
    "Mar": "Март",
    "Apr": "Апрель",
    "May": "Май",
    "Jun": "Июнь",
    "Jul": "Июль",
    "Aug": "Август",
    "Sep": "Сентябрь",
    "Oct": "Октябрь",
    "Nov": "Ноябрь",
    "Dec": "Декабрь"
}

class CTkCalendar(CTkFrame):
    def __init__(self,
                 entry=None,
                 chosen_date=None,
                 **kwargs):
        super().__init__(**kwargs)

        self.entry = entry

        # Logic
        self.current_date = chosen_date
        if chosen_date is None:
            self.current_date = date.today()

        #
        self.previous_year_button = CTkButton(
            master=self, text="<",
            width=40, height=40,
            command=self.year_down_command)
        self.previous_year_button.grid(row=0, column=0, rowspan=2)

        # Spinbox
        self.month_entry = CTkEntry(
            master=self)
        self.month_entry.grid(row=0, column=1, rowspan=2, columnspan=2)

        self.month_up = CTkButton(
            master=self, text="+",
            width=40, height=20,
            command=self.month_up_command)
        self.month_up.grid(row=0, column=3)

        self.month_down = CTkButton(
            master=self, text="-",
            width=40, height=20,
            command=self.month_down_command)
        self.month_down.grid(row=1, column=3)

        #
        self.year_entry = CTkEntry(
            master=self)
        self.year_entry.grid(row=0, column=4, rowspan=2, columnspan=2)
        self.year_entry.insert(0, self.current_date.strftime("%Y"))

        self.next_year_button = CTkButton(
            master=self, text=">",
            width=40, height=40,
            command=self.year_up_command
        )
        self.next_year_button.grid(row=0, column=6, rowspan=2)

        # Calendar
        self.day_buttons = []

        self.reset_entry()

    def month_up_command(self):
        if self.current_date.month < 12:
            self.current_date = self.current_date.replace(month=self.current_date.month + 1)
        else:
            self.current_date = self.current_date.replace(month=1, year=self.current_date.year + 1)
        self.reset_entry()
    
    def month_down_command(self):
        if self.current_date.month > 1:
            self.current_date = self.current_date.replace(month=self.current_date.month - 1)
        else:
            self.current_date = self.current_date.replace(month=12, year=self.current_date.year - 1)
        self.reset_entry()

    def year_up_command(self):
        self.current_date = self.current_date.replace(year=self.current_date.year + 1)
        self.reset_entry()

    def year_down_command(self):
        self.current_date = self.current_date.replace(year=self.current_date.year - 1)
        self.reset_entry()

    def choose_date(self, day):
        self.current_date = self.current_date.replace(day=day)

        self.reset_entry()
        self.entry.command()
        self.entry._entry_focus_out()

    def reset_entry(self):
        for button in self.day_buttons:
            del button

        cday = self.current_date.replace(day=1)
        cday -= cday.weekday() * timedelta(days=1)
        for week in range(6):
            for day in range(7):
                d = cday + timedelta(days=1) * (week * 7 + day)

                if d.month == self.current_date.month:
                    if d.day == self.current_date.day:
                        button = CTkButton(master=self, text=d.strftime("%d"),
                                           width=40, height=40, fg_color="#000000")
                    else:  # This month
                        button = CTkButton(master=self, text=d.strftime("%d"),
                                           width=40, height=40,
                                           command=lambda text=d.strftime("%d"): self.choose_date(int(text)))
                else:  # Other month
                    button = CTkButton(master=self, text=d.strftime("%d"),
                                       width=40, height=40, fg_color="#888888",
                                       state="disabled")

                self.day_buttons.append(
                    button
                )
                button.grid(row=2 + week, column=day)

        self.month_entry.delete(0, 9)
        self.month_entry.insert(0, translate[self.current_date.strftime("%b")])

        self.year_entry.delete(0, 5)
        self.year_entry.insert(0, self.current_date.strftime("%Y"))

        if self.entry is not None:
            self.entry.delete(0, 10)
            self.entry.insert(0, self.current_date.strftime("%Y-%m-%d"))


class CTkDatePicker(CTkEntry):

    def __init__(self,
                 chosen_date=None,
                 command=lambda: None,
                 **kwargs):

        super().__init__(**kwargs)

        self.command = command
        self.is_calendar_shown = False
        self.calendar = CTkCalendar(master=None, chosen_date=chosen_date, entry=self)

    def _entry_focus_out(self, event=None):
        super()._entry_focus_out(event=event)

        self.calendar.place_forget()

    def _entry_focus_in(self, event=None):
        super()._entry_focus_out(event=event)

        self.calendar.place(x=self.winfo_x(), y=self.winfo_y())
        self.calendar.lift()
