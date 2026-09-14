"""Offline UI smoke check: real Tk/map widgets, no device calls or tile downloads."""
import tkinter as tk
from unittest.mock import patch
import tkintermapview
from pikmin.fly_ui import FakeGPSApp


def main():
    original_map = tkintermapview.TkinterMapView
    def offline_map(*args, **kwargs):
        return original_map(*args, use_database_only=True, **kwargs)
    root = tk.Tk()
    root.withdraw()
    with patch('pikmin.fly_ui.tkintermapview.TkinterMapView', side_effect=offline_map), patch('pikmin.fly_ui.Controller.start'):
        app = FakeGPSApp(root)
    try:
        c = app.controller
        c.command('add', [(25.034, 121.565), (25.035, 121.566)])
        app.render(c.snapshot())
        root.update_idletasks()
        assert len(app.markers) == 2 and app.path is not None
        assert app.listbox.size() == 2
        c.command('clear', None)
        app.render(c.snapshot())
        assert not app.markers and app.path is None and app.listbox.size() == 0
        c.command('add', [(25.036, 121.567)])
        app.render(c.snapshot())
        assert list(app.markers) == [3]
        assert not c.route.running
        print('Offline UI check passed: real map, route line, unique labels, clear, re-add.')
        print('Requested layout:', root.winfo_reqwidth(), root.winfo_reqheight())
    finally:
        app.map_widget.destroy()
        root.destroy()


if __name__ == '__main__':
    main()
