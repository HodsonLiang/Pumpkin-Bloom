"""Stream Geoapify's country archives and sample selected locality types."""
import io
import json
import random
import re
from pathlib import Path, PurePosixPath
import zipfile
import requests
from .storage import CACHE, coordinates, save_points

KINDS = {'city': 'Cities（城市）', 'town': 'Towns（城鎮）',
         'village': 'Villages（村莊）', 'hamlet': 'Hamlets（聚落）'}
SOURCE = 'https://www.geoapify.com/data-share/localities/'


def country_codes(text):
    codes = list(dict.fromkeys(x.lower() for x in re.split(r'[,，\s]+', text.strip()) if x))
    if not codes or any(not re.fullmatch(r'[a-z]{2}', code) for code in codes):
        raise ValueError('請輸入兩碼國家代碼，例如 tw, jp, in。')
    return codes


def archive_kind(name):
    stem = PurePosixPath(name).stem.replace('_', '-')
    return stem[6:] if stem.startswith('place-') and stem[6:] in KINDS and name.endswith('.ndjson') else None


def validate_archive(path):
    with zipfile.ZipFile(path) as archive:
        if not any(archive_kind(n) for n in archive.namelist()):
            raise ValueError('下載檔案未包含 Geoapify 地點資料。')


def get_archive(code, cache=CACHE, progress=print):
    if country_codes(code) != [code]:
        raise ValueError('國家代碼無效。')
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache/f'{code}.zip'
    if path.exists():
        try:
            validate_archive(path)
            progress(f'使用本地資料：{code.upper()}')
            return path
        except (ValueError, zipfile.BadZipFile):
            progress(f'{code.upper()} 快取損壞，重新下載。')
    temporary = path.with_suffix('.zip.part')
    try:
        progress(f'下載 {code.upper()}，首次下載可能需要數分鐘…')
        with requests.get(SOURCE+code+'.zip', stream=True, timeout=(15, 60)) as response:
            response.raise_for_status()
            with temporary.open('wb') as output:
                for block in response.iter_content(1024*1024):
                    output.write(block)
        validate_archive(temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def iter_points(path, kinds):
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            if archive_kind(member.filename) not in kinds:
                continue
            # Never extract archive paths onto disk.
            with archive.open(member) as raw, io.TextIOWrapper(raw, encoding='utf-8-sig') as lines:
                for line in lines:
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                        lon, lat = item['location']
                        yield coordinates((lat, lon))
                    except (KeyError, TypeError, ValueError):
                        continue


def generate(countries, kinds, maximum, output, *, cache=CACHE, progress=print, rng=None):
    codes = country_codes(','.join(countries) if isinstance(countries, list) else countries)
    kinds = set(kinds)
    if not kinds or not kinds <= KINDS.keys():
        raise ValueError('請至少選擇一種有效的地點類型。')
    maximum = int(maximum)
    if maximum <= 0:
        raise ValueError('點數上限須大於 0。')
    rng = rng or random.Random()
    sample, seen = [], set()
    for code in codes:
        path = get_archive(code, cache, progress)
        for point in iter_points(path, kinds):
            key = tuple(round(x, 7) for x in point)
            if key in seen:
                continue
            seen.add(key)
            count = len(seen)
            if len(sample) < maximum:
                sample.append(point)
            else:
                index = rng.randrange(count)
                if index < maximum:
                    sample[index] = point
        progress(f'{code.upper()} 已讀取，累計 {len(seen)} 個不重複地點。')
    rng.shuffle(sample)
    save_points(output, sample, countries=codes, locality_types=sorted(kinds),
                attribution='© OpenStreetMap contributors; Geoapify extracts; ODbL', source=SOURCE)
    progress(f'完成：{len(sample)} 點 → {output}')
    return sample
