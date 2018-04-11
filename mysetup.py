import py2exe
from distutils.core import setup

setup(
	console=['labelImg.py'],
	data_files=[('imageformats', ['C:\ProgramData\Anaconda2\Lib\site-packages\PyQt4\plugins\imageformats\qjpeg4.dll', 'C:\ProgramData\Anaconda2\Lib\site-packages\PyQt4\plugins\imageformats\qgif4.dll'])],
	options={
		'py2exe':
		{
			'includes': ['lxml.etree', 'lxml._elementpath', 'gzip','lxml']
		}
	}
	
)