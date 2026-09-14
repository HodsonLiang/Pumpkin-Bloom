"""Read legacy/current result filenames and reversibly delete local results."""
from datetime import datetime
import math
from pathlib import Path
import re
import uuid

NUMBER = r'-?\d+(?:\.\d+)?'
PATTERN = re.compile(rf'^(?P<target>.+)_(?P<lat>{NUMBER})_(?P<lon>{NUMBER})_(?P<stamp>\d{{8}}_\d{{6}}_[a-fA-F0-9]{{8}}_\d+|\d{{9,}})\.png$', re.IGNORECASE)


def validate_coords(lat, lon):
    lat, lon = float(lat), float(lon)
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('緯度須介於 -90～90，經度須介於 -180～180。')
    return lat, lon


def path_key(path):
    return str(Path(path).resolve()).casefold()


def read_history(folder):
    folder = Path(folder).resolve()
    records, skipped = [], 0
    for path in sorted(folder.rglob('*')):
        if path.suffix.lower() != '.png' or '.trash' in path.relative_to(folder).parts:
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(folder) or not path.is_file():
            continue
        match = PATTERN.match(path.name)
        if not match:
            skipped += 1
            continue
        try:
            lat, lon = validate_coords(match['lat'], match['lon'])
            stamp = match['stamp']
            if '_' in stamp:
                date, clock, session_id, index = stamp.split('_')
                when = datetime.strptime(date+clock, '%Y%m%d%H%M%S')
                session = f'{date}_{clock}_{session_id}'
                index = int(index)
            else:
                when = datetime.fromtimestamp(int(stamp))
                session, index = 'legacy', '—'
            target = match['target']
            if not target.lower().endswith('.png'):
                target += '.png'
            records.append(dict(index=index, target=target, lat=lat, lon=lon, timestamp=when.isoformat(timespec='seconds'),
                                path=str(path.resolve()), found=True, timing='history', session=session))
        except (ValueError, OSError, OverflowError):
            skipped += 1
    return records, skipped


def trash_target(path, folder):
    """Restrict moves to actual results; never delete templates/arbitrary paths."""
    root = Path(folder).resolve()
    source = Path(path)
    resolved = source.resolve()
    if source.is_symlink() or not resolved.is_relative_to(root) or '.trash' in resolved.relative_to(root).parts or resolved.suffix.lower() != '.png':
        raise ValueError('只能刪除 found_targets 內的結果 PNG。')
    if not resolved.exists():
        return None
    if not resolved.is_file():
        raise ValueError('結果路徑不是圖片檔案。')
    destination = root/'.trash'/uuid.uuid4().hex/resolved.name
    if not destination.resolve().is_relative_to(root):
        raise ValueError('回收區路徑不在 found_targets 內。')
    destination.parent.mkdir(parents=True)
    resolved.replace(destination)
    return destination
