"""Offline UI smoke check: real Tk/map widgets, no device calls or tile downloads."""
import tkinter as tk
from unittest.mock import patch, Mock
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
        app.markers[3].canvas_icon = 4321
        event = Mock(x=20, y=20, x_root=40, y_root=40)
        with patch.object(app.map_widget.canvas, 'find_overlapping', return_value=(4321,)), patch('pikmin.fly_ui.tk.Menu') as menu:
            app.map_context(event)
            command = menu.return_value.add_command.call_args.kwargs['command']
            command()
        while not app.commands.empty():
            kind, value = app.commands.get_nowait()
            c.command(kind, value)
        app.render(c.snapshot())
        assert not app.markers and app.path is None
        with patch.object(app.map_widget.canvas, 'find_overlapping', return_value=()), patch.object(app.map_widget, 'mouse_right_click') as original_menu:
            app.map_context(event)
            original_menu.assert_called_once_with(event)
        print('Offline UI check passed: real map, route line, unique labels, clear, re-add.')
        print('Requested layout:', root.winfo_reqwidth(), root.winfo_reqheight())
    finally:
        app.map_widget.destroy()
        root.destroy()


if __name__ == '__main__':
    main()
