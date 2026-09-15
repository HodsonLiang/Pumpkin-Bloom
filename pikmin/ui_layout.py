"""Small reusable layout controls; hiding a panel preserves its values."""
from tkinter import ttk


class Foldout(ttk.Frame):
    def __init__(self, parent, title, *, opened=False):
        super().__init__(parent)
        self.title, self.opened = title, opened
        self.toggle_button = ttk.Button(self, command=self.toggle)
        self.toggle_button.pack(anchor='w')
        self.body = ttk.Frame(self, padding=(8, 4))
        self.refresh()

    def toggle(self):
        self.opened = not self.opened
        self.refresh()

    def refresh(self):
        self.toggle_button.configure(text=('▾ ' if self.opened else '▸ ')+self.title)
        if self.opened:
            self.body.pack(fill='x')
        else:
            self.body.pack_forget()
