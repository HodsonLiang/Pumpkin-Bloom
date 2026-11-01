"""Versioned coordinate files and project-local data directories."""
import json
import math
from pathlib import Path
import uuid

BASE = Path(__file__).resolve().parent.parent
DATA = BASE/'data'
WAYPOINTS = DATA/'waypoints'
ROUTES = DATA/'routes'
CACHE = DATA/'cache'/'geoapify'


def coordinates(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('座標必須是 [緯度, 經度]。')
    try:
        lat, lon = map(float, value)
    except (TypeError, ValueError):
        raise ValueError('座標必須為有效數字。') from None
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('緯度須為 -90～90，經度須為 -180～180。')
    return lat, lon


def write_json(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_points(path):
    path = Path(path)
    text = path.read_text(encoding='utf-8-sig')
    if path.suffix.lower() in ('.pikscan', '.pikroute'):
        data = json.loads(text)
        expected = 'pikmin.scan' if path.suffix.lower() == '.pikscan' else 'pikmin.route'
        if not isinstance(data, dict) or data.get('format') != expected or data.get('version') != 1:
            raise ValueError('無法辨認座標檔格式或版本。')
        if not isinstance(data.get('points'), list):
            raise ValueError('座標檔缺少 points 清單。')
        points = [coordinates(p) for p in data['points']]
    else:
        points = []
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                points.append(coordinates(line.split(',')))
            except (TypeError, ValueError):
                raise ValueError(f'第 {number} 行座標無效，格式須為緯度,經度。') from None
    if not points:
        raise ValueError('座標檔沒有標點。')
    return points


def save_points(path, points, *, kind='scan', **metadata):
    if kind not in ('scan', 'route') or Path(path).suffix.lower() != '.pik'+kind:
        raise ValueError('搜尋座標請使用 .pikscan，移動路線請使用 .pikroute 副檔名。')
    points = [coordinates(p) for p in points]
    if not points:
        raise ValueError('沒有標點可儲存。')
    write_json(path, dict(metadata, format='pikmin.'+kind, version=1, points=points))


def import_waypoints(source):
    source = Path(source)
    points = read_points(source)
    WAYPOINTS.mkdir(parents=True, exist_ok=True)
    destination = WAYPOINTS/(source.stem+'.pikscan')
    if source.resolve() == destination.resolve():
        return destination
    suffix = 1
    while destination.exists():
        try:
            if read_points(destination) == points:
                return destination
        except (ValueError, OSError):
            pass
        destination = WAYPOINTS/f'{source.stem}_{suffix}.pikscan'
        suffix += 1
    save_points(destination, points)
    return destination


def waypoint_files():
    WAYPOINTS.mkdir(parents=True, exist_ok=True)
    return sorted(WAYPOINTS.glob('*.pikscan'), key=lambda p: p.name.casefold())


def initialize_library():
    """Install only the example when the library is empty; preserve user files."""
    ROUTES.mkdir(parents=True, exist_ok=True)
    if not waypoint_files():
        import_waypoints(BASE/'examples'/'waypoints.txt')


if __name__ == '__main__':
    initialize_library()
