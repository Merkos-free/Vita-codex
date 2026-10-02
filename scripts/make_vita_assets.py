"""Generate original geometric LiveArea artwork; no font or external image files."""
from pathlib import Path
import argparse
import struct
import zlib

PALETTE = bytes([8,12,18, 17,25,35, 22,186,245, 237,243,249, 38,56,73])

def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind+data)&0xffffffff)

def png(width: int, height: int) -> bytes:
    pixels = bytearray(width*height)
    def rect(x,y,w,h,c):
        for yy in range(max(0,y),min(height,y+h)):
            a,b=max(0,x),min(width,x+w)
            if a<b: pixels[yy*width+a:yy*width+b]=bytes([c])*(b-a)
    def line(x1,y1,x2,y2,thickness,c):
        steps=max(abs(x2-x1),abs(y2-y1),1)
        for i in range(steps+1):
            x=round(x1+(x2-x1)*i/steps); y=round(y1+(y2-y1)*i/steps)
            rect(x-thickness//2,y-thickness//2,thickness,thickness,c)
    margin=max(4,min(width,height)//16)
    rect(margin,margin,width-2*margin,height-2*margin,1)
    rect(margin,margin,width-2*margin,max(2,margin//3),2)
    size=min(width,height)*3//5; cx=width//2; cy=height//2
    t=max(3,size//13)
    for sign in (-1,1):
        line(cx+sign*size//5,cy-size//3,cx+sign*size//2,cy,t,2)
        line(cx+sign*size//2,cy,cx+sign*size//5,cy+size//3,t,2)
    line(cx+size//10,cy-size//3,cx-size//10,cy+size//3,t,3)
    rows=b''.join(b'\0'+pixels[y*width:(y+1)*width] for y in range(height))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,3,0,0,0))+chunk(b'PLTE',PALETTE)+chunk(b'IDAT',zlib.compress(rows,9))+chunk(b'IEND',b'')

def generate(destination: Path) -> None:
    destination.mkdir(parents=True,exist_ok=True)
    for name,size in {'icon0.png':(128,128),'bg.png':(840,500),'startup.png':(280,158)}.items():
        (destination/name).write_bytes(png(*size))
    xml = '''<?xml version="1.0" encoding="utf-8"?>
<livearea style="a1" format-ver="01.00" content-rev="1">
  <livearea-background><image>bg.png</image></livearea-background>
  <gate><startup-image>startup.png</startup-image></gate>
</livearea>
'''
    (destination/'template.xml').write_bytes(xml.replace('\n','\r\n').encode())

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    generate(parser.parse_args().destination)
