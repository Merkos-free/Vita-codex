"""Synthetic package tests. Passing them does not make a runnable Vita binary."""
from pathlib import Path
import importlib.util
import struct
import tempfile
import unittest
import warnings
import zipfile

ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
assets=load('make_vita_assets'); vpk=load('verify_vpk')

def sfo(title='CVITA0001',version='00.20',category='gd'):
    keys=bytearray(); data=bytearray(); entries=bytearray()
    for key,value in {'TITLE_ID':title,'APP_VER':version,'CATEGORY':category}.items():
        value=value.encode()+b'\0'
        entries+=struct.pack('<HHIII',len(keys),0x0204,len(value),len(value),len(data))
        keys+=key.encode()+b'\0'; data+=value
    k=20+len(entries); d=k+len(keys)
    return struct.pack('<4s4I',b'\0PSF',0x101,k,d,3)+entries+keys+data

class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); assets.generate(self.root/'assets')
        self.files={'eboot.bin':b'SCE\0'+bytes(124),'sce_sys/param.sfo':sfo()}
        for name in (*vpk.IMAGES,vpk.TEMPLATE): self.files[name]=(self.root/'assets'/Path(name).name).read_bytes()
    def write(self,extra=None):
        path=self.root/'test.vpk'
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
            for name,data in self.files.items(): z.writestr(name,data)
            if extra:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore'); z.writestr(*extra)
        return path
    def bad(self):
        with self.assertRaises((ValueError,UnicodeError)): vpk.verify(self.write())
    def test_valid_structure_not_hardware(self):
        result=vpk.verify(self.write()); self.assertFalse(result['hardware_tested']); self.assertEqual(len(result['sha256']),64)
    def test_generated_assets_deterministic(self):
        assets.generate(self.root/'again')
        for p in (self.root/'assets').iterdir(): self.assertEqual(p.read_bytes(),(self.root/'again'/p.name).read_bytes())
    def test_known_directory_entries(self):
        self.assertFalse(vpk.verify(self.write(('sce_sys/',b'')))['hardware_tested'])
    def test_wrong_title(self): self.files['sce_sys/param.sfo']=sfo(title='OTHER0001'); self.bad()
    def test_wrong_version(self): self.files['sce_sys/param.sfo']=sfo(version='01.00'); self.bad()
    def test_wrong_category(self): self.files['sce_sys/param.sfo']=sfo(category='xx'); self.bad()
    def test_sfo_bad_bounds(self):
        data=bytearray(sfo()); struct.pack_into('<I',data,16,999999); self.files['sce_sys/param.sfo']=data; self.bad()
    def test_missing_self(self): del self.files['eboot.bin']; self.bad()
    def test_invalid_self(self): self.files['eboot.bin']=b'not an executable'; self.bad()
    def test_unexpected_configuration(self): self.files['auth.json']=b'{}'; self.bad()
    def test_path_traversal(self): self.files['../test']=b'x'; self.bad()
    def test_duplicate(self):
        with self.assertRaises(ValueError): vpk.verify(self.write(('eboot.bin',b'SCE\0'+bytes(124))))
    def test_symlink(self):
        del self.files['eboot.bin']; entry=zipfile.ZipInfo('eboot.bin'); entry.create_system=3; entry.external_attr=0o120777<<16
        with self.assertRaises(ValueError): vpk.verify(self.write((entry,b'SCE\0'+bytes(124))))
    def test_wrong_icon_dimensions(self): self.files['sce_sys/icon0.png']=assets.png(64,64); self.bad()
    def test_corrupt_png_crc(self):
        data=bytearray(self.files['sce_sys/icon0.png']); data[-1]^=1; self.files['sce_sys/icon0.png']=data; self.bad()
    def test_external_livearea_link(self):
        self.files[vpk.TEMPLATE]=self.files[vpk.TEMPLATE].replace(b'</livearea>',b'<target>https://example.com</target></livearea>'); self.bad()
    def test_xml_declaration_attack(self):
        self.files[vpk.TEMPLATE]=b'<!DOCTYPE livearea>'+self.files[vpk.TEMPLATE]; self.bad()
