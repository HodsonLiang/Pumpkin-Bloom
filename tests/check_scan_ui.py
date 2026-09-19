"""Offline integration check with actual Tk/map/image widgets."""
import io
from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch, Mock
from PIL import Image
import tkintermapview
from pikmin.scan_ui import ScanApp


def main():
    original = tkintermapview.TkinterMapView
    def offline_map(*args, **kwargs):
        return original(*args, use_database_only=True, **kwargs)
    root = tk.Tk()
    root.withdraw()
    with patch('pikmin.scan_ui.tkintermapview.TkinterMapView', side_effect=offline_map):
        app = ScanApp(root)
    try:
        saved_value = app.fields['interval'].get()
        assert not app.settings_panel.opened
        app.settings_panel.toggle()
        assert app.settings_panel.body.winfo_manager() == "pack"
        app.settings_panel.toggle()
        assert not app.settings_panel.body.winfo_manager()
        assert not app.manual_panel.opened
        app.manual_panel.toggle()
        assert app.manual_panel.body.winfo_manager() == "pack"
        app.manual_panel.toggle()
        assert not app.manual_panel.body.winfo_manager()
        assert app.fields['interval'].get() == saved_value
        app.handle(dict(kind='search', point=(25, 121), index=1))
        app.handle(dict(kind='position', point=(25, 121)))
        assert app.current_marker and not app.sent_marker
        app.handle(dict(kind='position', point=(26, 122)))
        assert app.sent_marker
        image = Image.new('RGB', (100, 200), 'green')
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'hit.png'
            image.save(path)
            app.handle(dict(kind='screenshot', content=stream.getvalue(), point=(25, 121), index=1,
                            timestamp='2026-09-14T12:00:00', path=str(path)))
            target_name = next((Path(__file__).resolve().parent.parent/'mushroom_pics').glob('*.png')).name
            app.bookmark_file = Path(folder)/'bookmarks.json'
            app.bookmarks = set()
            record = dict(index=1, target=target_name, lat=25, lon=121, timestamp='2026-09-14T12:00:00',
                          path=str(path), found=True, timing='pipeline', session='test')
            app.handle(dict(kind='result', record=record, hits=1, errors=0, processed=1))
            root.update_idletasks()
            assert len(app.markers)==1 and len(app.table.get_children())==1
            assert app.current_preview.original.size == (100, 200)
            assert app.hit_preview.original.size == (100, 200)
            assert app.current_marker.icon is None
            assert app.sent_marker.icon is None
            assert app.markers[0].icon is app.icon_for(target_name)
            app.table.selection_set('0')
            app.set_bookmarks(True)
            assert app.table.set('0', 'bookmark') == '★'
            assert app.bookmark_key(record) in app.bookmarks
            assert app.bookmark_file.is_file()
            app.add_record(record)
            assert len(app.records) == 1, 'History/live duplicate was not deduplicated'
            app.result_folder = Path(folder)
            second_path = Path(folder)/'second.png'
            image.save(second_path)
            app.add_record({**record, 'path': str(second_path), 'index': 2})
            app.select_all()
            assert len(app.table.selection()) == 2
            with patch.object(app.table, 'identify_row', return_value='1'), patch('pikmin.scan_actions.tk.Menu'):
                app.target_context(Mock(y=20, x_root=30, y_root=40))
                assert len(app.table.selection()) == 2
            app.set_bookmarks(True)
            assert app.table.set('1', 'bookmark') == '★'
            app.set_bookmarks(False)
            assert not app.bookmarks
            app.delete_selected()
            assert not path.exists() and not second_path.exists()
            assert len(list((Path(folder)/'.trash').rglob('*.png'))) == 2
            assert not app.records and not app.markers and not app.table.get_children()
            app.current_preview.draw()
            assert app.current_preview.photo is not None
        app.active = True
        app.scanner = Mock()
        app.end_index = 3
        with patch.object(app, 'run_manual') as dispatch:
            app.request_teleport((25.1, 121.1))
            app.scanner.stop_event.set.assert_called_once()
            dispatch.assert_not_called()
            app.handle(dict(kind='done', text='已停止', next_index=2, hits=0, errors=0))
            dispatch.assert_called_once_with('set', (25.1, 121.1))
        app.manual_device = Mock(process=None)
        app.run_manual('set', (25.2, 121.2))
        event = app.events.get(timeout=3)
        assert event['kind'] == 'manual_done' and event['error'] is None
        app.handle(event)
        app.manual_device.send.assert_called_once_with((25.2, 121.2))
        assert app.manual_active and not app.manual_busy
        with patch.object(app, 'run_manual') as dispatch:
            app.start()
            dispatch.assert_called_once_with('reset')
        with patch.object(app, 'start') as restart:
            app.handle(dict(kind='manual_done', operation='reset', point=None, error=None))
            restart.assert_called_once()
        assert not app.manual_active
        print('Offline scan UI passed: search/sent/hit markers, selection, both previews, image retained after deletion.')
        print('Requested layout:', root.winfo_reqwidth(), root.winfo_reqheight())
    finally:
        app.manual_executor.shutdown(wait=True)
        app.map_widget.destroy()
        root.destroy()


if __name__ == '__main__':
    main()
