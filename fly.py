"""Entry point for the route movement desktop UI."""
import tkinter as tk
from pikmin.fly_ui import FakeGPSApp

if __name__ == '__main__':
    root = tk.Tk()
    app = FakeGPSApp(root)
    root.mainloop()
