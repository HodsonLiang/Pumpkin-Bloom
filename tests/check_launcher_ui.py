"""Offline launcher form and mode validation; no child/device processes."""
from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch
import launcher


def main():
    root = tk.Tk()
    root.withdraw()
    with tempfile.TemporaryDirectory() as folder, patch('launcher.SETTINGS', Path(folder)/'settings.json'), patch('launcher.threading.Thread') as thread:
        app = launcher.Launcher(root)
        try:
            assert not app.device_connected
            for mode in (0, 1, 2):
                app.tabs.select(mode)
                app.update_start_state()
                assert str(app.start_button['state']) == 'normal'
            app.tabs.select(0)
            app.fields['speed'].set('irrelevant')
            app.start()
            assert app.busy
            assert thread.call_args.kwargs['args'][0] == 0
            app.busy = False
            app.tabs.select(1)
            app.fields['speed'].set('18')
            app.fields['max_points'].set('irrelevant')
            app.fields['start_position'].set('-16.5,179.9')
            app.start()
            assert thread.call_args.kwargs['args'][1]['start_position'] == (-16.5, 179.9)
            app.busy = False
            app.tabs.select(2)
            app.fields['max_points'].set('10')
            app.fields['countries'].set('ad')
            app.locality_types['village'].set(False)
            with patch('launcher.WAYPOINTS', Path(folder)), patch('launcher.filedialog.asksaveasfilename', return_value=str(Path(folder)/'test.pikscan')):
                app.start()
            config = thread.call_args.kwargs['args'][2]
            assert config['countries'] == ['ad']
            assert set(config['kinds']) == {'city', 'town', 'hamlet'}
            from tkinter import ttk
            app.country_picker.open()
            window = next(w for w in app.country_picker.winfo_children() if isinstance(w, tk.Toplevel))
            def descendants(widget):
                return [child for w in widget.winfo_children() for child in [w, *descendants(w)]]
            widgets = descendants(window)
            entry = next(w for w in widgets if isinstance(w, ttk.Entry))
            entry.insert(0, 'Japan')
            japan = next(w for w in widgets if isinstance(w, ttk.Checkbutton) and '(JP)' in str(w['text']))
            japan.invoke()
            entry.delete(0, 'end')
            entry.insert(0, 'Canada')
            next(w for w in widgets if isinstance(w, ttk.Button) and w['text']=='套用').invoke()
            assert app.country_picker.selected() == {'ad', 'jp'}
            assert '日本' in app.country_picker.summary.get()
            print('Offline launcher passed: all modes open without device; optional origin; Geoapify selection.')
        finally:
            app.monitor_stop.set()
            root.destroy()


if __name__ == '__main__':
    main()
