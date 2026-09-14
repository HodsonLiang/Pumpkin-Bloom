"""Offline integration check with actual Tk/map/image widgets."""
import io
from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch
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
            record = dict(index=1, target='target.png', lat=25, lon=121, timestamp='2026-09-14T12:00:00',
                          path=str(path), found=True, timing='pipeline', session='test')
            app.handle(dict(kind='result', record=record, hits=1, errors=0, processed=1))
            root.update_idletasks()
            assert len(app.markers)==1 and len(app.table.get_children())==1
            assert app.current_preview.original.size == (100, 200)
            assert app.hit_preview.original.size == (100, 200)
            path.unlink()
            app.current_preview.draw()
            assert app.current_preview.photo is not None
        print('Offline scan UI passed: search/sent/hit markers, selection, both previews, image retained after deletion.')
        print('Requested layout:', root.winfo_reqwidth(), root.winfo_reqheight())
    finally:
        app.map_widget.destroy()
        root.destroy()


if __name__ == '__main__':
    main()
