#! python3
import sys
if sys.version_info < (3, 0):
    sys.stdout.write("Python 3.x is required")
    sys.exit(1)

import re, os
from argparse import ArgumentParser

def finddats():
    files = os.listdir('.')
    print(files)
    pattern = r'\[dat-(?P<platform>.*)\].*\.dat'
    for file in files:
        match = re.match(pattern, file)
        if not match:
            continue
        print(match['platform'])
        print(match)
        
def main():
    parser = ArgumentParser()
    parser.add_argument('-l', '--list', action="store_true", help='List dat content')
    finddats()
    args = parser.parse_args()
    parser.print_help()
    
if __name__ == "__main__":
    main()