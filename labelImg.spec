# -*- mode: python -*-

block_cipher = None


a = Analysis(['labelImg.py'],
             pathex=['C:\\Users\\beililiu\\AppData\\Local\\Programs\\Python\\Python36\\Lib\\site-packages\\PyQt5\\Qt\\plugins\\imageformats', 'C:\\Users\\beililiu\\Desktop\\Test'],
             binaries=[],
             datas=[],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='labelImg',
          debug=False,
          strip=False,
          upx=True,
          runtime_tmpdir=None,
          console=False )
