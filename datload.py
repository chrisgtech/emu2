#! python3
import sys, os
if sys.version_info < (3, 5):
    sys.stdout.write("Python 3.5+ is required")
    sys.exit(1)

import re, glob, math, statistics, json, tempfile, uuid, shutil
from xml.etree import ElementTree
from contextlib import contextmanager
from argparse import ArgumentParser
from pathlib import Path

import patoolib
from tqdm import tqdm
import hashfile

@contextmanager
def tempdir():
    unique = uuid.uuid4().hex
    temp = tempfile.gettempdir()
    temp = os.path.join(temp, unique)
    os.makedirs(temp)
    try:
        yield temp
    finally:
        shutil.rmtree(temp, ignore_errors=True)

@contextmanager
def tempzip(zipfile):
    with tempdir() as zipdir:
        patoolib.extract_archive(zipfile, outdir=zipdir, verbosity=-1)
        yield zipdir

def prettysize(inbytes):
    if inbytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(inbytes, 1024)))
    p = math.pow(1024, i)
    s = round(inbytes / p, 2)
    if int(s) == s:
        s = int(s)
    return "%s %s" % (s, size_name[i])

def finddats():
    files = glob.glob('*.dat')
    pattern = r'\[dat-(?P<platform>.*)\].*\.dat'
    datfiles = {}
    for file in files:
        match = re.match(pattern, file)
        if not match:
            continue
        platform = match['platform']
        datfiles[platform] = file
    return datfiles

def printinfo(datinfo):
    for _, dat in datinfo.items():
        print(f'Platform [{dat["platform"]}]')
        print(f'{dat["description"]}')
        print(f'Version {dat["version"]}')
        print(f'Props {dat["props"]}')
        print(f'Props {dat["types"]}')
        print(f'Found {len(dat["games"])} game definitions')
        print()

def printroms(romfiles):
    bydir = {}
    for romfile in romfiles:
        path = Path(romfile)
        dirname = path.parts[-2]
        if not dirname in bydir:
            bydir[dirname] = []
        bydir[dirname].append(romfiles[romfile])
    for romdir in bydir:
        print(f'Rom Set {romdir}')
        roms = bydir[romdir]
        print(f'{len(roms)} total files')
        sizes = []
        for rom in roms:
            files = rom['files']
            romsize = 0
            for file in files.values():
                size = file['Size']
                if not size:
                    continue
                size = int(size)
                romsize += size
            sizes.append(romsize)
        totalsize = sum(sizes)
        average = statistics.median(sizes)
        average = int(average)
        print(f'All files are {prettysize(totalsize)}')
        print(f'Average file is {prettysize(average)}')
        print()
    
def pulldata(datfiles):
    dats = {}
    for platform, datfile in datfiles.items():
        datinfo = {}
        dats[platform] = datinfo
        datinfo['file'] = datfile
        datinfo['platform'] = platform
        xml = ElementTree.parse(datfile)
        header = xml.find('header')
        for prop in header:
            datinfo[prop.tag] = prop.text
        entries = xml.findall('game')
        if len(entries) < 1:
            entries = xml.findall('machine')
        atts = []
        childs = []
        games = {}
        nonmeta = ['rom', 'release', 'device_ref', 'sample', 'biosset', 'disk']
        for entry in tqdm(entries, desc=f'{platform} dat read', unit='game'):
            game = {}
            attrib = entry.attrib
            name = attrib.get('name')
            if not name:
                print('Error! No name for current game')
                continue
            if name in games:
                print(f'Duplicate game "{name}" found')
            games[name] = game
            for key in attrib:
                if not key in atts:
                    atts.append(key)
                game[key] = attrib[key]
            for child in entry:
                tag = child.tag
                if not tag in childs:
                    childs.append(tag)
                if tag in nonmeta:
                    item = {}
                    subatt = child.attrib
                    subname = subatt.get('name')
                    if not subname:
                        print(f'No name found for {tag}')
                        exit()
                    item['type'] = tag
                    taglist = tag + 's'
                    if not taglist in game:
                        game[taglist] = {}
                    game[taglist][subname] = item
                    for key in subatt:
                        item[key] = subatt[key]
                else:
                    text = child.text
                    if not text:
                        text = child.get('status')
                        if text:
                            tag = tag + 'status'
                    game[tag] = text
        datinfo['games'] = games
        datinfo['props'] = atts
        datinfo['types'] = childs
    return dats
    
def scanroms(locations, types=None):
    if not types:
        types = ['.7z', '.zip']
    romfiles = {}
    allfiles = []
    for location in locations:
        for typ in types:
            allfiles.extend(glob.glob(f'{location}\\**\\*{typ}'))
    for allfile in tqdm(allfiles, desc='rom files', unit='file'):
        listed = None
        try:
            listed = patoolib.list_archive(allfile, verbosity=-1)
        except Exception as e:
            print(e)
            print(f'Bad rom file {allfile}')
            continue
        lines = listed.splitlines()
        started = False
        last = []
        headers = []
        offsets = [0]
        fileinfo = {}
        fileinfo['path'] = allfile
        fileinfo['files'] = {}
        for line in lines:
            line = str(line, 'utf-8')
            parts = line.split()
            dividers = True
            for part in parts:
                if not part.startswith('-'):
                    dividers = False
                    break
            if not started and len(parts) > 4:
                if dividers:
                    headers = last
                    validheaders = ['Date', 'Time', 'Attr', 'Size', 'Compressed', 'Name']
                    if not len(headers) == len(validheaders):
                        print(f'Headers {headers} do not match valid headers {validheaders}')
                        exit()
                    for validheader in validheaders:
                        if not validheader in headers:
                            print(f'Header {validheader} is not in headers: {headers}')
                            exit()
                    offsets.append(11)
                    offsets.append(20)
                    for part in parts[1:len(headers)-2]:
                        lastoffset = offsets[-1]
                        lastoffset += len(part) + 1
                        offsets.append(lastoffset)
                    offsets[-1] = offsets[-1] + 1
                    started = True
                    continue
            if started:
                if dividers:
                    break
                info = {}
                for index, offset in enumerate(offsets):
                    begin = offset
                    end = len(line)
                    if index+1 < len(offsets):
                        end = offsets[index+1]
                    subline = line[begin:end]
                    if index < len(offsets) - 1:
                        subline = subline.strip()
                    if subline.strip() == '':
                        continue
                    info[headers[index]] = subline
                subname = info['Name']
                fileinfo['files'][subname] = info

            else:
                last = parts
        romfiles[allfile] = fileinfo
    return romfiles
    
def matchroms(dats, roms):
    pass
            
def checkroms(roms):
    checks = {}
    for romname in tqdm(roms, desc='roms', unit='rom'):
        try:
            romcheck = {}
            romcheck['path'] = romname
            romcheck['files'] = {}
            with tempzip(romname) as temp:
                wildcard = os.path.join(temp, '**\\*')
                files = glob.glob(wildcard, recursive=True)
                for file in files:
                    path = Path(file)
                    if not path.is_file():
                        continue
                    filename = file.replace(temp, '')[1:]
                    info = {}
                    size = os.path.getsize(file)
                    info['size'] = size
                    info['name'] = filename
                    crc = hashfile.checksum_file(file, 'crc32')
                    info['crc'] = crc
                    sha1 = hashfile.hash_file(file, 'sha1')
                    info['sha1'] = sha1
                    romcheck['files'][filename] = info
            checks[romname] = romcheck
        except Exception as e:
            print(e)
            print(f'Bad rom zip {romname}')
            continue
        
    return checks
    
def main():
    parser = ArgumentParser()
    parser.add_argument('-l', '--list', action="store_true", help='List dat content')
    parser.add_argument('-s', '--scan', action="store_true", help='Scan roms')
    parser.add_argument('-m', '--match', action="store_true", help='Match roms from dats')
    parser.add_argument('-c', '--check', action="store_true", help='Check rom hashes')
    args = parser.parse_args()
    if args.list:
        datfiles = finddats()
        datinfo = pulldata(datfiles)
        print('Saving datfiles JSON')
        with open('datfiles.json', 'w') as datjson:
            json.dump(datinfo, datjson, indent=4, sort_keys=True)
        printinfo(datinfo)
    elif args.scan:
        locations = ['F:\\emu2-roms\\']
        romfiles = scanroms(locations)
        print('Saving romfiles JSON')
        with open('romfiles.json', 'w') as romjson:
            json.dump(romfiles, romjson, indent=4, sort_keys=True)
        printroms(romfiles)
    elif args.match:
        dats = None
        print('Loading datfiles JSON')
        with open('datfiles.json', 'r') as datjson:
            dats = json.load(datjson)
        roms = None
        print('Loading romfiles JSON')
        with open('romfiles.json', 'r') as romjson:
            roms = json.load(romjson)
        matchroms(dats, roms)
    elif args.check:
        roms = None
        print('Loading romfiles JSON')
        with open('romfiles.json', 'r') as romjson:
            roms = json.load(romjson)
        checks = checkroms(roms)
        print('Saving checkroms JSON')
        with open('checkroms.json', 'w') as checkjson:
            json.dump(checks, checkjson, indent=4, sort_keys=True)
    else:
        parser.print_help()
    
if __name__ == "__main__":
    main()