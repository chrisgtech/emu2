#! python3
import sys, os
if sys.version_info < (3, 5):
    sys.stdout.write("Python 3.5+ is required")
    sys.exit(1)

import re, glob, math, statistics
from xml.etree import ElementTree
from contextlib import contextmanager
from argparse import ArgumentParser
from pathlib import Path

import patoolib
from tqdm import tqdm

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

def finddats(filter=None):
    files = glob.glob('*.dat')
    pattern = r'\[dat-(?P<platform>.*)\].*\.dat'
    datfiles = {}
    for file in files:
        match = re.match(pattern, file)
        if not match:
            continue
        platform = match['platform']
        if filter and platform != filter:
            continue
        datfiles[platform] = file
    return datfiles
    
def printinfo(datinfo):
    print(f'Platform [{datinfo["platform"]}]')
    print(f'{datinfo["description"]}')
    print(f'Version {datinfo["version"]}')
    print(f'Props {datinfo["props"]}')
    print(f'Props {datinfo["types"]}')
    print(f'Found {len(datinfo["games"])} game definitions')
    #for name, game in list(datinfo['games'].items())[:5]:
    #    print(name)
    #    print(game)
    print()
    
def printroms(romfiles):
    bydir = {}
    for romfile in romfiles:
        path = Path(romfile)
        dirname = path.parts[-2]
        if not dirname in bydir:
            bydir[dirname] = []
        bydir[dirname].append(romfiles[romfile])
    for dir in bydir:
        print(f'Rom Set {dir}')
        roms = bydir[dir]
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
    
def pulldata(datfile):
    datinfo = {}
    datinfo['file'] = datfile
    xml = ElementTree.parse(datfile)
    header = xml.find('header')
    for property in header:
        datinfo[property.tag] = property.text
    entries = xml.findall('game')
    if len(entries) < 1:
        entries = xml.findall('machine')
    atts = []
    childs = []
    games = {}
    nonmeta = ['rom', 'release', 'device_ref', 'sample', 'biosset', 'disk']
    for entry in tqdm(entries, desc='dat read'):
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
    return datinfo
    
def scanroms(locations, types=['.7z', '.zip']):
    romfiles = {}
    allfiles = []
    for location in locations:
        for type in types:
            allfiles.extend(glob.glob(f'{location}\\**\\*{type}'))
    for allfile in tqdm(allfiles, desc='rom files', unit='file'):
        if not 'the' in allfile:
            continue
        #print(allfile)
        listed = patoolib.list_archive(allfile, verbosity=-1)
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
            #print(line)
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
                #print(line)
                for i in range(len(offsets)):
                    begin = offsets[i]
                    end = len(line)
                    if i+1 < len(offsets):
                        end = offsets[i+1]
                    subline = line[begin:end]
                    if i < len(offsets) - 1:
                        subline = subline.strip()
                    info[headers[i]] = subline
                    #print(f'"{subline}"')
                subname = info['Name']
                fileinfo['files'][subname] = info
                #print(f'"{info["Date"]}" "{info["Time"]}" "{info["Attr"]}" "{info["Size"]}" "{info["Compressed"]}" "{info["Name"]}"') 
                #if len(parts) > len(headers):
                #    laststart = 0
                #    for part in parts[:len(headers)-1]:
                #        laststart = line.index(part, laststart)
                #        laststart += len(part)
                #    last = line[laststart:].strip()
                #    newparts = parts[:len(headers)-1]
                #    newparts.append(last)
                #    #print(newparts)
            else:
                last = parts
        #print(fileinfo)
        romfiles[allfile] = fileinfo
    return romfiles
    
def main():
    parser = ArgumentParser()
    parser.add_argument('-l', '--list', action="store_true", help='List dat content')
    parser.add_argument('-s', '--scan', action="store_true", help='Scan roms')
    parser.add_argument('-p', '--platform', default=None, help='Use specified platform only')
    args = parser.parse_args()
    if args.list:
        datfiles = finddats(args.platform)
        for platform, datfile in datfiles.items():
            datinfo = pulldata(datfile)
            datinfo['platform'] = platform
            printinfo(datinfo)
    elif args.scan:
        locations = ['F:\\emu2-roms\\']
        romfiles = scanroms(locations)
        printroms(romfiles)
    else:
        parser.print_help()
    
if __name__ == "__main__":
    main()