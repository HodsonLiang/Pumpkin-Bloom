"""Adapter for the existing coordinate generators; no device access."""
import json
import os
from pathlib import Path


def main():
    config = json.loads(os.environ['PIKMIN_GENERATE_CONFIG'])
    if config['source'] == '世界城市':
        if not Path('worldcities.csv').is_file():
            raise FileNotFoundError('找不到 worldcities.csv')
        from . import generate_coords as generator
        generator.TARGET_COUNTRIES = [item.strip() for item in config['countries'].split(',') if item.strip()]
        if not generator.TARGET_COUNTRIES:
            raise ValueError('請輸入至少一個國家名稱。')
    else:
        if not Path('india_villages/place-village.ndjson').is_file():
            raise FileNotFoundError('找不到印度村莊資料檔')
        from . import india_coords as generator
    generator.MAX_POINTS = int(config['max_points'])
    generator.OUTPUT_FILENAME = config['output']
    generator.main()
    from launcher import read_waypoints
    read_waypoints(Path(config['output']))


if __name__ == '__main__':
    main()
