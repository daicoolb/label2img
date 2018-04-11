from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement
from lxml import etree
import sys, os

AttrNameList = ['sex' , 'age', 'clothing', 'heading', 'haveBag', 'clothingColor', 'hairStyle', 'glasses', 'mask']
AttrNum = len(AttrNameList)

dirpath = sys.argv[1]
outputfilepath = sys.argv[2]
outputfile = open(outputfilepath, 'w')
filelist = os.listdir(dirpath)
for list in filelist:
	if list.endswith('.xml'):
		filepath = os.path.join(dirpath, list)
		parser = etree.XMLParser(encoding='utf-8')
		xmltree = ElementTree.parse(filepath, parser=parser).getroot()
		filename = xmltree.find('filename').text
		outputfile.write("%s\n"%filename)
		boxlist = []
		for object_iter in xmltree.findall('object'):
			attrDict = {}
			bndbox = object_iter.find("bndbox")
			x1 = int(bndbox.find("xmin").text)
			y1 = int(bndbox.find("ymin").text)
			x2 = int(bndbox.find("xmax").text)
			y2 = int(bndbox.find("ymax").text)
			attrDict["bndbox"] = (x1, y1, x2, y2)
			attributes = object_iter.find('attributes')
			for attrName in AttrNameList:
				attrNum = int(attributes.find(attrName).text)
				attrDict[attrName] = attrNum
			boxlist.append(attrDict)
		outputfile.write("%d %d\n"%(len(boxlist), AttrNum))
		for box in boxlist:
			outputfile.write("%d %d %d %d\n"%(box["bndbox"][0], box["bndbox"][1],box["bndbox"][2],box["bndbox"][3]))
			for attrName in AttrNameList:
				outputfile.write("%s: %d\n"%(attrName, box[attrName]))
outputfile.close()