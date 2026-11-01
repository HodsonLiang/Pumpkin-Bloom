"""Generate project coordinate files from cached Geoapify localities."""
import json
import os
from .geoapify import generate

def main():
    config = json.loads(os.environ['PIKMIN_GENERATE_CONFIG'])
    generate(config['countries'], config['kinds'], int(config['max_points']), config['output'])

if __name__ == '__main__':
    main()
