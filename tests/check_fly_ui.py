"""Offline UI smoke check: real Tk/map widgets, no device calls or tile downloads."""
import tkinter as tk
import math
import io
from PIL import Image
from unittest.mock import patch, Mock
from pikmin.world_map import WorldMap
from pikmin.fly_ui import FakeGPSApp


def main():
    original_map = WorldMap
    def offline_map(*args, **kwargs):
        return original_map(*args, use_database_only=True, **kwargs)
    root = tk.Tk()
    root.withdraw()
    with patch('pikmin.fly_ui.WorldMap', side_effect=offline_map), patch('pikmin.fly_ui.DeviceSession'), patch('pikmin.fly_ui.Controller.start'):
        app = FakeGPSApp(root)
    try:
        assert app.current_marker is None and app.snapshot['position'] is None
        saved_value = app.speed.get()
        assert not app.settings_panel.opened
        app.settings_panel.toggle()
        assert app.settings_panel.body.winfo_manager() == "pack"
        app.settings_panel.toggle()
        assert not app.settings_panel.body.winfo_manager()
        assert not app.coords_panel.opened
        app.coords_panel.toggle()
        assert app.coords_panel.body.winfo_manager() == "pack"
        app.coords_panel.toggle()
        assert not app.coords_panel.body.winfo_manager()
        assert app.speed.get() == saved_value
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
        world = app.map_widget
        world.width, world.height = 800, 400
        world.set_zoom(8)
        world.set_position(0, 179.9)
        left = world.set_marker(0, 179.9)
        right = world.set_marker(0, -179.9)
        x1, _ = left.get_canvas_pos(left.position)
        x2, _ = right.get_canvas_pos(right.position)
        assert 0 < x2-x1 < 50, (x1, x2)
        route = world.set_path([(0, 179.9), (0, -179.9)])
        coords = world.canvas.coords(route.canvas_line)
        assert 0 < coords[2]-coords[0] < 50, coords
        size = 2**round(world.zoom)
        assert math.floor(world.upper_left_tile_pos[0]/size) != math.floor(world.lower_right_tile_pos[0]/size)
        latitude, longitude = world.convert_canvas_coords_to_decimal_coords(world.width-1, world.height/2)
        assert -180 <= longitude <= 180
        before = world.center_longitude()
        world.set_position(0, -179.9)
        assert abs(world.center_longitude()-before-.2) < .001
        world.set_zoom(9)
        assert abs(world.center_longitude()-before-.2) < .001
        tile = world.canvas_tile_array[1][1]
        x, y = tile.tile_name_position
        zoom = round(world.zoom)
        stream = io.BytesIO()
        Image.new('RGB', (256, 256), 'green').save(stream, format='PNG')
        world.image_load_queue_results.append(((zoom, x, y), tile, stream.getvalue()))
        with patch.object(world, 'winfo_viewable', return_value=True):
            world.update_canvas_tile_images()
        assert tile.canvas_object is not None
        assert (zoom, x % (2**zoom), y) in world.tile_image_cache
        # A response for a recycled canvas tile must never paint the wrong place.
        world.image_load_queue_results.append(((zoom, x+1, y), tile, stream.getvalue()))
        old_image = tile.image
        with patch.object(world, 'winfo_viewable', return_value=True):
            world.update_canvas_tile_images()
        assert tile.image is old_image
        with patch.object(world.tile_client, 'fetch') as fetch:
            world.pre_cache()
            fetch.assert_not_called()
        print('Offline UI check passed: real map, route line, unique labels, clear, re-add.')
        print('Requested layout:', root.winfo_reqwidth(), root.winfo_reqheight())
    finally:
        app.map_widget.destroy()
        root.destroy()


if __name__ == '__main__':
    main()
