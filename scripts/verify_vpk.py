"""Structural checks for our connected test VPK, not a hardware/security certification."""
from pathlib import Path
import argparse
import hashlib
import json
import stat
import struct
import zipfile
import xml.etree.ElementTree as ET
import zlib

TITLE_ID = 'CVITA0001'
VERSION = '00.21'
IMAGES = {'sce_sys/icon0.png': (128,128),
          'sce_sys/livearea/contents/bg.png': (840,500),
          'sce_sys/livearea/contents/startup.png': (280,158)}
TEMPLATE = 'sce_sys/livearea/contents/template.xml'
REQUIRED = {'eboot.bin', 'sce_sys/param.sfo', TEMPLATE, *IMAGES}

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)

def parse_sfo(data: bytes) -> dict:
    require(20<=len(data)<=65536, 'Invalid SFO size')
    magic,version,keys,values,count=struct.unpack_from('<4s4I',data)
    require(magic==b'\0PSF' and version==0x101, 'Invalid SFO header')
    require(count<=128 and 20+16*count<=keys<=values<=len(data), 'Invalid SFO tables')
    result={}
    for n in range(count):
        key,fmt,length,maximum,offset=struct.unpack_from('<HHIII',data,20+16*n)
        start=keys+key
        require(keys<=start<values, 'Invalid SFO key offset')
        end=data.find(b'\0',start,values)
        require(end>=start, 'Unterminated SFO key')
        name=data[start:end].decode('ascii')
        require(name not in result, 'Duplicate SFO key')
        require(0<length<=maximum and values+offset+maximum<=len(data), 'Invalid SFO value bounds')
        raw=data[values+offset:values+offset+length]
        if fmt==0x0204:
            require(raw[-1:]==b'\0', 'Unterminated SFO string')
            result[name]=raw[:-1].decode('utf-8')
        elif fmt==0x0404:
            require(length==4, 'Invalid SFO integer')
            result[name]=struct.unpack('<I',raw)[0]
        else:
            result[name]=raw
    return result

def check_png(data: bytes, size: tuple) -> None:
    require(len(data)<=420*1024 and data[:8]==b'\x89PNG\r\n\x1a\n', 'Invalid PNG')
    i=8; chunks=[]; compressed=bytearray()
    while i<len(data):
        require(i+12<=len(data), 'Truncated PNG chunk')
        length=struct.unpack_from('>I',data,i)[0]
        kind=data[i+4:i+8]; end=i+12+length
        require(end<=len(data), 'PNG chunk out of bounds')
        body=data[i+8:i+8+length]
        crc=struct.unpack_from('>I',data,end-4)[0]
        require(zlib.crc32(kind+body)&0xffffffff==crc, 'PNG CRC mismatch')
        chunks.append(kind)
        if kind==b'IHDR':
            require(len(body)==13 and struct.unpack('>IIBBBBB',body)==(*size,8,3,0,0,0), 'Wrong PNG size/format')
        if kind==b'IDAT': compressed.extend(body)
        i=end
    require(chunks[0:1]==[b'IHDR'] and chunks[-1:]==[b'IEND'] and b'PLTE' in chunks, 'Incomplete PNG')
    expected=(size[0]+1)*size[1]
    decoder=zlib.decompressobj()
    raw=decoder.decompress(bytes(compressed),expected+1)
    require(len(raw)==expected and decoder.eof and not decoder.unused_data, 'Invalid PNG pixels')

def verify(path: Path) -> dict:
    require(0<path.stat().st_size<=20*1024*1024, 'Invalid archive size')
    with zipfile.ZipFile(path) as z:
        entries=z.infolist(); names=[i.filename for i in entries]
        require(len(names)==len(set(names)), 'Duplicate ZIP entries')
        require({i.filename for i in entries if not i.is_dir()}==REQUIRED, 'Unexpected or missing VPK files')
        require(all(not i.is_dir() or i.filename in {'sce_sys/','sce_sys/livearea/','sce_sys/livearea/contents/'} for i in entries), 'Unexpected VPK directory')
        require(sum(i.file_size for i in entries)<=24*1024*1024, 'Unpacked size limit')
        for entry in entries:
            require(not stat.S_ISLNK(entry.external_attr>>16), 'Symlinks forbidden')
            require(not entry.flag_bits&1, 'Encrypted entries forbidden')
        require(z.testzip() is None, 'ZIP CRC mismatch')
        executable=z.read('eboot.bin')
        require(len(executable)>=128 and executable[:4]==b'SCE\0', 'Missing SELF executable')
        sfo=parse_sfo(z.read('sce_sys/param.sfo'))
        require(sfo.get('TITLE_ID')==TITLE_ID, 'Wrong application ID')
        require(sfo.get('APP_VER')==VERSION, 'Wrong application version')
        require(sfo.get('CATEGORY')=='gd', 'Not a user application')
        for name,size in IMAGES.items(): check_png(z.read(name),size)
        xml=z.read(TEMPLATE)
        require(len(xml)<=32768 and b'<!' not in xml, 'Invalid LiveArea XML')
        root=ET.fromstring(xml)
        require(root.tag=='livearea' and root.attrib.get('style')=='a1', 'Wrong LiveArea style')
        require(root.findtext('livearea-background/image')=='bg.png', 'Wrong background')
        require(root.findtext('gate/startup-image')=='startup.png', 'Wrong startup image')
        require(not root.findall('.//target'), 'External LiveArea links forbidden')
    return {'filename':path.name, 'title_id':TITLE_ID, 'version':VERSION,
            'size_bytes':path.stat().st_size, 'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'files':sorted(REQUIRED), 'hardware_tested':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('vpk',type=Path)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    result=verify(args.vpk)
    text=json.dumps(result,indent=2)+'\n'
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(text,encoding='utf-8')
        (args.report.parent/'SHA256SUMS').write_text(result['sha256']+'  '+args.vpk.name+'\n',encoding='ascii')
    print(text,end='')
