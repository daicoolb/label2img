#coding=utf-8
import codecs
import os.path
import re
import sys
import subprocess

from functools import partial
from collections import defaultdict

try:
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtWidgets import *
except ImportError:
    # needed for py3+qt4
    # Ref:
    # http://pyqt.sourceforge.net/Docs/PyQt4/incompatible_apis.html
    # http://stackoverflow.com/questions/21217399/pyqt4-qtcore-qvariant-object-instead-of-a-string
    if sys.version_info.major >= 3:
        import sip
        sip.setapi('QVariant', 2)
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *

import resources
# Add internal libs
from libs.lib import struct, newAction, newIcon, addActions, fmtShortcut
from libs.shape import Shape, DEFAULT_LINE_COLOR, DEFAULT_FILL_COLOR
from libs.canvas import Canvas
from libs.zoomWidget import ZoomWidget
from libs.labelDialog import LabelDialog
from libs.colorDialog import ColorDialog
from libs.labelFile import LabelFile, LabelFileError
from libs.toolBar import ToolBar
from libs.pascal_voc_io import PascalVocReader
from libs.pascal_voc_io import XML_EXT
from libs.ustr import ustr

__appname__ = u'标注工具V1.4(商用请联系作者)'

attrList = []
AttrNameDict = {}
attr_conf = open("attribute_config.txt",encoding="utf-8")
sku_conf = open("sku_config.txt",encoding="utf-8")
sku_num = 10000
for lint in sku_conf:
    if len(lint) > 0:
        sku_num = int(lint)
        #print(sku_num)
for line in attr_conf:
    line_sp = line.strip().split(" ")
    if len(line_sp) < 2:
        continue
    AttrNameDict[line_sp[0]] = line_sp[1]
    del line_sp[1]
    attrList.append(line_sp)
attr_conf.close()

attr_num_list = []
for i in range(len(attrList)):
    attr_num_list.append(len(attrList[i])-1)

# Utility functions and classes.

def have_qstring():
    '''p3/qt5 get rid of QString wrapper as py3 has native unicode str type'''
    return not (sys.version_info.major >= 3 or QT_VERSION_STR.startswith('5.'))


def util_qt_strlistclass():
    return QStringList if have_qstring() else list


class WindowMixin(object):

    def menu(self, title, actions=None):
        menu = self.menuBar().addMenu(title)
        if actions:
            addActions(menu, actions)
        return menu

    def toolbar(self, title, actions=None):
        toolbar = ToolBar(title)
        toolbar.setObjectName(u'%sToolBar' % title)
        # toolbar.setOrientation(Qt.Vertical)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if actions:
            addActions(toolbar, actions)
        self.addToolBar(Qt.LeftToolBarArea, toolbar)
        return toolbar


# PyQt5: TypeError: unhashable type: 'QListWidgetItem'
class HashableQListWidgetItem(QListWidgetItem):

    def __init__(self, *args):
        super(HashableQListWidgetItem, self).__init__(*args)

    def __hash__(self):
        return hash(id(self))


class MainWindow(QMainWindow, WindowMixin):
    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = list(range(3))

    def __init__(self, defaultFilename=None, defaultPrefdefClassFile=None):
        super(MainWindow, self).__init__()
        self.setWindowTitle(__appname__)
        # Save as Pascal voc xml
        self.defaultSaveDir = None
        self.usingPascalVocFormat = True
        # For loading all image under a directory
        self.mImgList = []
        self.dirname = None
        self.labelHist = []
        self.lastOpenDir = None

        # Whether we need to save or not.
        self.dirty = False
        self.haveOpenDir = False

        self._noSelectionSlot = False
        self._beginner = True
        self.screencastViewer = "firefox"
        self.screencast = "https://youtu.be/p0nR2YsCY_U"

        # Main widgets and related state.
        self.labelDialog = LabelDialog(parent=self, listItem=self.labelHist)

        self.shapesToAttrDicts = {}
        self.itemsToShapes = {}
        self.shapesToItems = {}
        self.prevLabelText = ''

        ## add by jieliu
        self.sku=0

        listLayout = QVBoxLayout()
        listLayout.setContentsMargins(0, 0, 0, 0)

        # Create a widget for using default label
        self.useDefaultLabelCheckbox = QCheckBox(u'使用默认SKU标签')
        self.useDefaultLabelCheckbox.setChecked(False)
        self.defaultLabelTextLine = QLineEdit()
        self.defaultLabelTextLine.setValidator(QIntValidator(0,sku_num))
        useDefaultLabelQHBoxLayout = QHBoxLayout()
        useDefaultLabelQHBoxLayout.addWidget(self.useDefaultLabelCheckbox)
        useDefaultLabelQHBoxLayout.addWidget(self.defaultLabelTextLine)
        useDefaultLabelContainer = QWidget()
        useDefaultLabelContainer.setLayout(useDefaultLabelQHBoxLayout)

        # Create a widget for sku setting
        self.useDefaultSKUCheckbox = QCheckBox(u'使用默认SKU数量')
        self.useDefaultSKUCheckbox.setChecked(False)
        self.defaultSKUTextLine = QLineEdit()
        self.defaultSKUTextLine.setValidator(QIntValidator(0,200))
        self.defaultSKUTextLine.textChanged.connect(self.skuChanged)
        useDefaultSKUQHBoxLayout = QHBoxLayout()
        useDefaultSKUQHBoxLayout.addWidget(self.useDefaultSKUCheckbox)
        useDefaultSKUQHBoxLayout.addWidget(self.defaultSKUTextLine)
        useDefaultSKUContainer = QWidget()
        useDefaultSKUContainer.setLayout(useDefaultSKUQHBoxLayout)
        #self.diffcButton = QCheckBox(u'difficult')
        #self.diffcButton.setChecked(False)
        #self.diffcButton.stateChanged.connect(self.btnstate)
        self.editButton = QToolButton()
        self.editButton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        ## add by jieliu
        self.useSKUCheckButton = QToolButton()
        self.useSKUCheckButton.clicked.connect(self.skuCheck)
        self.useSKUCheckButton.setEnabled(False)
        self.useSKUCheckButton.setText(u'校验SKU数量')
        self.useSKUCheckButton.setToolButtonStyle(Qt.ToolButtonTextOnly)
        useDefaultSKUQHBoxLayout.addWidget(self.useSKUCheckButton)
        #listLayout.addWidget(self.useSKUCheckButton)
        # Add some of widgets to listLayout
        listLayout.addWidget(self.editButton)
        #listLayout.addWidget(self.diffcButton)
        listLayout.addWidget(useDefaultLabelContainer)
        listLayout.addWidget(useDefaultSKUContainer)

        # Create and add a widget for showing current label items
        self.labelList = QListWidget()
        labelListContainer = QWidget()
        labelListContainer.setLayout(listLayout)
        self.labelList.itemActivated.connect(self.labelSelectionChanged)
        self.labelList.itemSelectionChanged.connect(self.labelSelectionChanged)
        self.labelList.itemDoubleClicked.connect(self.editLabel)
        # Connect to itemChanged to detect checkbox changes.
        self.labelList.itemChanged.connect(self.labelItemChanged)
        listLayout.addWidget(self.labelList)

        self.dock = QDockWidget(u'Bounding Box的标签和数量', self)
        self.dock.setObjectName(u'Labels')
        self.dock.setWidget(labelListContainer)

        # Tzutalin 20160906 : Add file list and dock to move faster
        self.fileListWidget = QListWidget()
        self.fileListWidget.itemClicked.connect(self.fileitemClicked)
        filelistLayout = QVBoxLayout()
        filelistLayout.setContentsMargins(0, 0, 0, 0)
        filelistLayout.addWidget(self.fileListWidget)
        fileListContainer = QWidget()
        fileListContainer.setLayout(filelistLayout)
        self.filedock = QDockWidget(u'文件列表', self)
        self.filedock.setObjectName(u'Files')
        self.filedock.setWidget(fileListContainer)

        self.zoomWidget = ZoomWidget()
        self.colorDialog = ColorDialog(parent=self)

        self.canvas = Canvas()
        self.canvas.zoomRequest.connect(self.zoomRequest)

        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(True)
        self.scrollBars = {
            Qt.Vertical: scroll.verticalScrollBar(),
            Qt.Horizontal: scroll.horizontalScrollBar()
        }
        self.scrollArea = scroll
        self.canvas.scrollRequest.connect(self.scrollRequest)

        self.canvas.newShape.connect(self.newShape)
        self.canvas.shapeMoved.connect(self.setDirty)
        self.canvas.selectionChanged.connect(self.shapeSelectionChanged)
        self.canvas.drawingPolygon.connect(self.toggleDrawingSensitive)

        self.setCentralWidget(scroll)

        #wuhaozhang 20170802 : Attribute dock
        attrLayout = QGridLayout()
        attrLayout.setSpacing(4)
        #attrLayout.setMargin(10)
        self.titleList = []
        self.choiceList = []
        if attrList is not None and len(attrList) > 0:
            idx = 1
            for attr in attrList:
                title = QLabel(attr[0])
                self.titleList.append(title)
                choice = QComboBox()
                choice.currentIndexChanged.connect(self.attrChanged)
                self.choiceList.append(choice)
                for i in range(1, len(attr)):
                    choice.insertItem(i-1, attr[i])
                attrLayout.addWidget(title, idx, 0)
                attrLayout.addWidget(choice, idx, 1)
                idx += 1
        attrContainer = QWidget()
        attrContainer.setLayout(attrLayout)
        self.attrdock = QDockWidget(u'属性', self)
        self.attrdock.setObjectName(u'Attr')
        self.attrdock.setWidget(attrContainer)

        self.addDockWidget(Qt.RightDockWidgetArea, self.attrdock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        # Tzutalin 20160906 : Add file list and dock to move faster
        self.addDockWidget(Qt.RightDockWidgetArea, self.filedock)
        #wuhaozhang 20170802


        self.dockFeatures = QDockWidget.DockWidgetClosable\
            | QDockWidget.DockWidgetFloatable
        self.dock.setFeatures(self.dock.features() ^ self.dockFeatures)

        # Actions
        action = partial(newAction, self)
        quit = action(u'&退出', self.close,
                      'Ctrl+Q', 'quit', u'退出应用')

        open = action(u'&打开文件', self.openFile,
                      'Ctrl+O', 'open', u'打开文件或者标签')

        opendir = action(u'&打开目录', self.openDir,
                         'Ctrl+u', 'open', u'打开目录')

        changeSavedir = action(u'&设置存储目录', self.changeSavedir,
                               'Ctrl+r', 'open', u'设置存储目录')

        openAnnotation = action(u'&打开Annotation', self.openAnnotation,
                                'Ctrl+Shift+O', 'open', u'打开 Annotation')

        openNextImg = action(u'&下一张图片', self.openNextImg,
                             'd', 'next', u'切换到下一张图片')

        openPrevImg = action(u'&上一张图片', self.openPrevImg,
                             'a', 'prev', u'切换到上一张图片')

        verify = action(u'&验证图片', self.verifyImg,
                        'space', 'verify', u'验证图片')

        save = action(u'&保存', self.saveFile,
                      'Ctrl+S', 'save', u'保存标签到文件', enabled=False)
        saveAs = action(u'&另存为', self.saveFileAs,
                        'Ctrl+Shift+S', 'save-as', u'保存标签到不同的文件',
                        enabled=False)
        close = action(u'&关闭', self.closeFile,
                       'Ctrl+W', 'close', u'关闭现在的文件')
        color1 = action(u'&Box的线框颜色', self.chooseColor1,
                        'Ctrl+L', 'color_line', u'选择Box的线框颜色')
        color2 = action(u'&Box的填充颜色', self.chooseColor2,
                        'Ctrl+Shift+L', 'color', u'选择Box的填充颜色')

        createMode = action(u'创建矩形框', self.setCreateMode,
                            'Ctrl+N', 'new', u'创建矩形框', enabled=False)
        editMode = action(u'编辑矩形框', self.setEditMode,
                          'Ctrl+J', 'edit', u'编辑矩形框', enabled=False)

        create = action(u'创造矩形框', self.createShape,
                        'w', 'new', u'创造矩形框', enabled=False)
        delete = action(u'删除矩形框', self.deleteSelectedShape,
                        'Delete', 'delete', u'删除矩形框', enabled=False)
        copy = action(u'复制矩形框', self.copySelectedShape,
                      'Ctrl+D', 'copy', u'复制矩形框',
                      enabled=False)
        deleteImg = action(u'&删除图片', self.deleteSelectedImg,
                           'x', None, u'删除选中的图片', enabled=False)
        loadPrev = action(u'&加载上一个标签', self.loadPreLabel,
                          'l', None, u'加载上一幅图片的标签', enabled=False)
        loadBboxFile = action(u'&加载Box文件', self.loadBboxFile,
                          None, None, u'加载Bounding Box到默认目录')

        advancedMode = action(u'&专家模式', self.toggleAdvancedMode,
                              'Ctrl+Shift+A', 'expert', u'转换到专家模式',
                              checkable=True)

        hideAll = action(u'&隐藏Boungding Box', partial(self.togglePolygons, False),
                         'Ctrl+H', 'hide', u'隐藏所有的BoundingBox',
                         enabled=False)
        showAll = action(u'&显示Bounding Box', partial(self.togglePolygons, True),
                         'Ctrl+A', 'hide', u'显示所有的BoundingBox',
                         enabled=False)

        #help = action('&Tutorial', self.tutorial, 'Ctrl+T', 'help',
        #              u'Show demos')

        zoom = QWidgetAction(self)
        zoom.setDefaultWidget(self.zoomWidget)
        self.zoomWidget.setWhatsThis(
            u"Zoom in or out of the image. Also accessible with"
            " %s and %s from the canvas." % (fmtShortcut("Ctrl+[-+]"),
                                             fmtShortcut("Ctrl+Wheel")))
        self.zoomWidget.setEnabled(False)

        zoomIn = action(u'&放大', partial(self.addZoom, 10),
                        'Ctrl++', 'zoom-in', u'放大', enabled=False)
        zoomOut = action(u'&缩小', partial(self.addZoom, -10),
                         'Ctrl+-', 'zoom-out', u'缩小', enabled=False)
        zoomOrg = action(u'&原始尺寸', partial(self.setZoom, 100),
                         'Ctrl+=', 'zoom', u'原始尺寸', enabled=False)
        fitWindow = action(u'&适应窗口大小', self.setFitWindow,
                           'Ctrl+F', 'fit-window', u'自适应窗口大小',
                           checkable=True, enabled=False)
        fitWidth = action(u'&适应宽度', self.setFitWidth,
                          'Ctrl+Shift+F', 'fit-width', u'适应窗口宽度',
                          checkable=True, enabled=False)
        # Group zoom controls into a list for easier toggling.
        zoomActions = (self.zoomWidget, zoomIn, zoomOut,
                       zoomOrg, fitWindow, fitWidth)
        self.zoomMode = self.MANUAL_ZOOM
        self.scalers = {
            self.FIT_WINDOW: self.scaleFitWindow,
            self.FIT_WIDTH: self.scaleFitWidth,
            # Set to one to scale to 100% when loading files.
            self.MANUAL_ZOOM: lambda: 1,
        }

        edit = action(u'&编辑标签', self.editLabel,
                      'Ctrl+E', 'edit', u'修改选中Box的标签',
                      enabled=False)
        self.editButton.setDefaultAction(edit)

        shapeLineColor = action('Shape &Line Color', self.chshapeLineColor,
                                icon='color_line', tip=u'Change the line color for this specific shape',
                                enabled=False)
        shapeFillColor = action('Shape &Fill Color', self.chshapeFillColor,
                                icon='color', tip=u'Change the fill color for this specific shape',
                                enabled=False)

        labels = self.dock.toggleViewAction()
        labels.setText(u'显示/隐藏标签窗口')
        labels.setShortcut('Ctrl+Shift+L')
        files = self.filedock.toggleViewAction()
        files.setText(u'显示/隐藏文件窗口')
        attrs = self.attrdock.toggleViewAction()
        attrs.setText(u'显示/隐藏属性窗口')

        # Lavel list context menu.
        labelMenu = QMenu()
        addActions(labelMenu, (edit, delete))
        self.labelList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.labelList.customContextMenuRequested.connect(
            self.popLabelListMenu)

        # Store actions for further handling.
        self.actions = struct(save=save, saveAs=saveAs, open=open, close=close,
                              lineColor=color1, fillColor=color2,
                              create=create, delete=delete, edit=edit, copy=copy, deleteImg=deleteImg, loadPrev = loadPrev, loadBboxFile = loadBboxFile,
                              createMode=createMode, editMode=editMode, advancedMode=advancedMode,
                              shapeLineColor=shapeLineColor, shapeFillColor=shapeFillColor,
                              zoom=zoom, zoomIn=zoomIn, zoomOut=zoomOut, zoomOrg=zoomOrg,
                              fitWindow=fitWindow, fitWidth=fitWidth,
                              zoomActions=zoomActions,
                              fileMenuActions=(
                                  open, opendir, save, saveAs, close, quit),
                              beginner=(), advanced=(),
                              editMenu=(edit, copy, delete,
                                        None, color1, color2),
                              beginnerContext=(create, edit, copy, delete),
                              advancedContext=(createMode, editMode, edit, copy,
                                               delete, shapeLineColor, shapeFillColor),
                              onLoadActive=(
                                  close, create, createMode, editMode),
                              onShapesPresent=(saveAs, hideAll, showAll))

        self.menus = struct(
            file=self.menu(u'&文件'),
            edit=self.menu(u'&编辑'),
            view=self.menu(u'&视图'),
            #help=self.menu('&Help'),
            recentFiles=QMenu(u'&打开最近的'),
            labelList=labelMenu)

        # Auto saving : Enble auto saving if pressing next
        self.autoSaving = QAction(u"自动保存", self)
        self.autoSaving.setCheckable(True)
        self.autoSaving.setChecked(True)

        # Sync single class mode from PR#106
        self.singleClassMode = QAction(u"单类模式", self)
        self.singleClassMode.setShortcut("Ctrl+Shift+S")
        self.singleClassMode.setCheckable(True)
        self.lastLabel = None

        addActions(self.menus.file,
                   (open, opendir, changeSavedir, openAnnotation, self.menus.recentFiles, save, saveAs, close, deleteImg, loadPrev, loadBboxFile, None, quit))
       # addActions(self.menus.help, (help,))
        addActions(self.menus.view, (
            self.autoSaving,
            self.singleClassMode,
            labels, files, attrs, advancedMode, None,
            hideAll, showAll, None,
            zoomIn, zoomOut, zoomOrg, None,
            fitWindow, fitWidth))

        self.menus.file.aboutToShow.connect(self.updateFileMenu)

        # Custom context menu for the canvas widget:
        addActions(self.canvas.menus[0], self.actions.beginnerContext)
        addActions(self.canvas.menus[1], (
            action('&Copy here', self.copyShape),
            action('&Move here', self.moveShape)))

        self.tools = self.toolbar('Tools')
        self.actions.beginner = (
            open, opendir, changeSavedir, openNextImg, openPrevImg, verify, save, deleteImg, loadPrev, loadBboxFile, None, create, copy, delete, None,
            zoomIn, zoom, zoomOut, fitWindow, fitWidth)

        self.actions.advanced = (
            open, opendir, changeSavedir, openNextImg, openPrevImg, save, deleteImg, loadPrev, loadBboxFile, None,
            createMode, editMode, None,
            hideAll, showAll)

        self.statusBar().showMessage('%s ' % __appname__)
        self.statusBar().show()

        # Application state.
        self.image = QImage()
        self.filePath = ustr(defaultFilename)
        self.recentFiles = []
        self.maxRecent = 7
        self.lineColor = None
        self.fillColor = None
        self.zoom_level = 100
        self.fit_window = False
        # Add Chris
        #self.difficult = False

        # Load predefined classes to the list
        self.loadPredefinedClasses(defaultPrefdefClassFile)
        # XXX: Could be completely declarative.
        # Restore application settings.
        if have_qstring():
            types = {
                'filename': QString,
                'recentFiles': QStringList,
                'window/size': QSize,
                'window/position': QPoint,
                'window/geometry': QByteArray,
                'line/color': QColor,
                'fill/color': QColor,
                'advanced': bool,
                # Docks and toolbars:
                'window/state': QByteArray,
                'savedir': QString,
                'lastOpenDir': QString,
            }
        else:
            types = {
                'filename': str,
                'recentFiles': list,
                'window/size': QSize,
                'window/position': QPoint,
                'window/geometry': QByteArray,
                'line/color': QColor,
                'fill/color': QColor,
                'advanced': bool,
                # Docks and toolbars:
                'window/state': QByteArray,
                'savedir': str,
                'lastOpenDir': str,
            }

        self.settings = settings = Settings(types)
        self.recentFiles = settings.get('recentFiles') if settings.get('recentFiles') is not None else []
        size = settings.get('window/size', QSize(600, 500))
        position = settings.get('window/position', QPoint(0, 0))
        self.resize(size)
        self.move(position)
        saveDir = ustr(settings.get('savedir', None))
        self.lastOpenDir = ustr(settings.get('lastOpenDir', None))
        if saveDir is not None and os.path.exists(saveDir):
            self.defaultSaveDir = saveDir
            self.statusBar().showMessage('%s started. Annotation will be saved to %s' %
                                         (__appname__, self.defaultSaveDir))
            self.statusBar().show()

        # or simply:
        # self.restoreGeometry(settings['window/geometry']
        self.restoreState(settings.get('window/state', QByteArray()))
        self.lineColor = QColor(settings.get('line/color', Shape.line_color))
        self.fillColor = QColor(settings.get('fill/color', Shape.fill_color))
        Shape.line_color = self.lineColor
        Shape.fill_color = self.fillColor
        # Add chris
        #Shape = self.difficult

        def xbool(x):
            if isinstance(x, QVariant):
                return x.toBool()
            return bool(x)

        if xbool(settings.get('advanced', False)):
            self.actions.advancedMode.setChecked(True)
            self.toggleAdvancedMode()

        # Populate the File menu dynamically.
        self.updateFileMenu()
        # Since loading the file may take some time, make sure it runs in the
        # background.
        self.queueEvent(partial(self.loadFile, self.filePath or ""))

        # Callbacks:
        self.zoomWidget.valueChanged.connect(self.paintCanvas)

        self.populateModeActions()

    ## Support Functions ##

    def noShapes(self):
        return not self.itemsToShapes

    def toggleAdvancedMode(self, value=True):
        self._beginner = not value
        self.canvas.setEditing(True)
        self.populateModeActions()
        self.editButton.setVisible(not value)
        if value:
            self.actions.createMode.setEnabled(True)
            self.actions.editMode.setEnabled(False)
            self.dock.setFeatures(self.dock.features() | self.dockFeatures)
        else:
            self.dock.setFeatures(self.dock.features() ^ self.dockFeatures)

    def populateModeActions(self):
        if self.beginner():
            tool, menu = self.actions.beginner, self.actions.beginnerContext
        else:
            tool, menu = self.actions.advanced, self.actions.advancedContext
        self.tools.clear()
        addActions(self.tools, tool)
        self.canvas.menus[0].clear()
        addActions(self.canvas.menus[0], menu)
        self.menus.edit.clear()
        actions = (self.actions.create,) if self.beginner()\
            else (self.actions.createMode, self.actions.editMode)
        addActions(self.menus.edit, actions + self.actions.editMenu)

    def setBeginner(self):
        self.tools.clear()
        addActions(self.tools, self.actions.beginner)

    def setAdvanced(self):
        self.tools.clear()
        addActions(self.tools, self.actions.advanced)

    def setDirty(self):
        self.dirty = True
        self.actions.save.setEnabled(True)

    def setUndirty(self):
        self.dirty = False
        self.actions.save.setEnabled(False)

    def setClean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.create.setEnabled(True)

    def toggleActions(self, value=True):
        """Enable/Disable widgets which depend on an opened image."""
        for z in self.actions.zoomActions:
            z.setEnabled(value)
        for action in self.actions.onLoadActive:
            action.setEnabled(value)

    def queueEvent(self, function):
        QTimer.singleShot(0, function)

    def status(self, message, delay=5000):
        self.statusBar().showMessage(message, delay)

    def resetState(self):
        self.itemsToShapes.clear()
        self.shapesToItems.clear()
        self.shapesToAttrDicts.clear()
        self.labelList.clear()
        self.filePath = None
        self.imageData = None
        self.labelFile = None
        self.canvas.resetState()

    def currentItem(self):
        items = self.labelList.selectedItems()
        if items:
            return items[0]
        return None

    def addRecentFile(self, filePath):
        if filePath in self.recentFiles:
            #self.recentFiles.removeAll(filePath)
            self.recentFiles.remove(filePath)
        elif len(self.recentFiles) >= self.maxRecent:
            self.recentFiles.pop(self.maxRecent-1)
        self.recentFiles.insert(0, filePath)

    def beginner(self):
        return self._beginner

    def advanced(self):
        return not self.beginner()

    ## Callbacks ##
    def tutorial(self):
        subprocess.Popen([self.screencastViewer, self.screencast])

    def createShape(self):
        assert self.beginner()
        self.canvas.setEditing(False)
        self.actions.create.setEnabled(False)

    def toggleDrawingSensitive(self, drawing=True):
        """In the middle of drawing, toggling between modes should be disabled."""
        self.actions.editMode.setEnabled(not drawing)
        if not drawing and self.beginner():
            # Cancel creation.
            print('Cancel creation.')
            self.canvas.setEditing(True)
            self.canvas.restoreCursor()
            self.actions.create.setEnabled(True)

    def toggleDrawMode(self, edit=True):
        self.canvas.setEditing(edit)
        self.actions.createMode.setEnabled(edit)
        self.actions.editMode.setEnabled(not edit)

    def setCreateMode(self):
        assert self.advanced()
        self.toggleDrawMode(False)

    def setEditMode(self):
        assert self.advanced()
        self.toggleDrawMode(True)

    def updateFileMenu(self):
        currFilePath = self.filePath

        def exists(filename):
            return os.path.exists(filename)
        menu = self.menus.recentFiles
        menu.clear()
        files = [f for f in self.recentFiles if f !=
                 currFilePath and exists(f)]
        for i, f in enumerate(files):
            icon = newIcon('labels')
            action = QAction(
                icon, '&%d %s' % (i + 1, QFileInfo(f).fileName()), self)
            action.triggered.connect(partial(self.loadRecent, f))
            menu.addAction(action)

    def popLabelListMenu(self, point):
        self.menus.labelList.exec_(self.labelList.mapToGlobal(point))

    def editLabel(self, item=None):
        if not self.canvas.editing():
            return
        item = item if item else self.currentItem()
        text = self.labelDialog.popUp(item.text())
        if text is not None:
            item.setText(text)
            self.setDirty()

    # Tzutalin 20160906 : Add file list and dock to move faster
    def fileitemClicked(self, item=None):
        currIndex = self.mImgList.index(ustr(item.text()))
        if currIndex < len(self.mImgList):
            filename = self.mImgList[currIndex]
            if filename:
                if self.dirty is True:
                    self.saveFile()
                self.loadFile(filename)

    # Add chris
    def btnstate(self, item= None):
        """ Function to handle difficult examples
        Update on each object
        if not self.canvas.editing():
            return

        item = self.currentItem()
        if not item: # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count()-1)

        difficult = self.diffcButton.isChecked()

        try:
            shape = self.itemsToShapes[item]
        except:
            pass
        # Checked and Update
        try:
            if difficult != shape.difficult:
                shape.difficult = difficult
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass
        """

    # React to canvas signals.
    def shapeSelectionChanged(self, selected=False):
        if self._noSelectionSlot:
            self._noSelectionSlot = False
        else:
            shape = self.canvas.selectedShape
            if shape:
                self.shapesToItems[shape].setSelected(True)
                self.setAttrDict(shape)
            else:
                self.labelList.clearSelection()
        self.actions.delete.setEnabled(selected)
        self.actions.copy.setEnabled(selected)
        self.actions.edit.setEnabled(selected)
        self.actions.shapeLineColor.setEnabled(selected)
        self.actions.shapeFillColor.setEnabled(selected)

    def addLabel(self, shape):
        item = HashableQListWidgetItem(shape.label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        self.itemsToShapes[item] = shape
        self.shapesToItems[shape] = item
        if shape not in self.shapesToAttrDicts:
            self.shapesToAttrDicts[shape] = self.getAttrDict()
        self.labelList.addItem(item)
        for action in self.actions.onShapesPresent:
            action.setEnabled(True)

    def remLabel(self, shape):
        if shape is None:
            # print('rm empty label')
            return
        item = self.shapesToItems[shape]
        self.labelList.takeItem(self.labelList.row(item))
        del self.shapesToItems[shape]
        del self.itemsToShapes[item]
        del self.shapesToAttrDicts[shape]

    def loadLabels(self, shapes):
        s = []
        for label, points, line_color, fill_color, attrDict in shapes:
            shape = Shape(label=label)
            for x, y in points:
                shape.addPoint(QPointF(x, y))
            shape.close()
            s.append(shape)
            self.addLabel(shape)
            if attrDict is not None:
                self.shapesToAttrDicts[shape] = attrDict
            else:
                self.setDefaultAttrDict(shape)
            if line_color:
                shape.line_color = QColor(*line_color)
            if fill_color:
                shape.fill_color = QColor(*fill_color)

        self.canvas.loadShapes(s)


    #wuhaozhang 20170802
    def setDefaultAttrChoice(self):
        for choice, num in zip(self.choiceList, attr_num_list):
            choice.setCurrentIndex(num-1)
            self.setUndirty()

    def getAttrDict(self):
        attrDict = {}
        for title, choice in zip(self.titleList, self.choiceList):
            attrDict[AttrNameDict[ustr(title.text())]] = choice.currentIndex()
        return attrDict

    def setAttrDict(self, shape):
        if shape in self.shapesToAttrDicts:
            attrDict = self.shapesToAttrDicts[shape]
        else:
            for title, num in zip(self.titleList, attr_list_num):
                attrDict[AttrNameDict[ustr(title.text())]] = num-1
        for title, choice in zip(self.titleList, self.choiceList):
            choice.setCurrentIndex(attrDict[AttrNameDict[ustr(title.text())]])

    def setDefaultAttrDict(self, shape):
        attrDict = {}
        for title, num in zip(self.titleList, attr_list_num):
            attrDict[AttrNameDict[ustr(title.text())]] = num-1
        self.shapesToAttrDicts[shape] = attrDict
        for title, choice in zip(self.titleList, self.choiceList):
            choice.setCurrentIndex(attrDict[AttrNameDict[ustr(title.text())]])

    def makeDefaultAttrDict(self):
        attrDict = {}
        for title, num in zip(self.titleList, attr_list_num):
            attrDict[AttrNameDict[ustr(title.text())]] = num-1
        return attrDict

    def skuChanged(self):
        if self.defaultSKUTextLine.text() is not None:
            self.setDirty()

    def skuCheck(self):
        if self.sku is not None:
            msg = '已经标注%d个物体，应该标注%d个物体' % (self.labelList.count(),self.sku)
            QMessageBox.warning(self, u'校验结果', msg, QMessageBox.Ok)
            #print(self.sku)
            #print(self.labelList.count())

    def attrChanged(self):
        attrDict = {}
        for title, choice in zip(self.titleList, self.choiceList):
            attrDict[AttrNameDict[ustr(title.text())]] = choice.currentIndex()
        shape = self.canvas.selectedShape
        if shape is not None:
            self.shapesToAttrDicts[shape] = attrDict
            self.setDirty()

    def saveLabels(self, annotationFilePath):
        annotationFilePath = ustr(annotationFilePath)
        if self.labelFile is None:
            self.labelFile = LabelFile()
            self.labelFile.verified = self.canvas.verified
            #if self.defaultSKUTextLine.text() is not None:
            #    self.labelFile.sku=self.defaultSKUTextLine.text()
            #else:
            #    self.labelFile.sku=0

        def format_shape(s, attrDict):
            return dict(label=s.label,
                        line_color=s.line_color.getRgb()
                        if s.line_color != self.lineColor else None,
                        fill_color=s.fill_color.getRgb()
                        if s.fill_color != self.fillColor else None,
                        points=[(p.x(), p.y()) for p in s.points],
                       # add chris
                        attrDict = attrDict)

        shapes = [format_shape(shape, self.shapesToAttrDicts[shape]) for shape in self.canvas.shapes]
        # Can add differrent annotation formats here
        try:
            if self.usingPascalVocFormat is True:
                print ('Img: ' + self.filePath + ' -> Its xml: ' + annotationFilePath)
                if self.defaultSKUTextLine.text() == "":
                    #print("0")
                    sku_text=self.sku
                else:
                    sku_text=self.defaultSKUTextLine.text()
                    print(self.defaultSKUTextLine.text())
                self.labelFile.savePascalVocFormat(annotationFilePath, shapes, self.filePath, self.imageData,
                                                   self.lineColor.getRgb(), self.fillColor.getRgb(),sku=sku_text)
            else:
                self.labelFile.save(annotationFilePath, shapes, self.filePath, self.imageData,
                                    self.lineColor.getRgb(), self.fillColor.getRgb())
            return True
        except LabelFileError as e:
            self.errorMessage(u'Error saving label data',
                              u'<b>%s</b>' % e)
            return False

    def copySelectedShape(self):
        self.addLabel(self.canvas.copySelectedShape())
        # fix copy and delete
        self.shapeSelectionChanged(True)

    def labelSelectionChanged(self):
        item = self.currentItem()
        if item and self.canvas.editing():
            self._noSelectionSlot = True
            self.canvas.selectShape(self.itemsToShapes[item])
            shape = self.itemsToShapes[item]
            # Add wuhaozhang
            self.setAttrDict(shape)

    def labelItemChanged(self, item):
        shape = self.itemsToShapes[item]
        label = item.text()
        if label != shape.label:
            shape.label = item.text()
            self.setDirty()
        else:  # User probably changed item visibility
            self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)

    # Callback functions:
    def newShape(self):
        """Pop-up and give focus to the label editor.

        position MUST be in global coordinates.
        """
        if not self.useDefaultLabelCheckbox.isChecked() or not self.defaultLabelTextLine.text():
            if len(self.labelHist) > 0:
                self.labelDialog = LabelDialog(
                    parent=self, listItem=self.labelHist)

            # Sync single class mode from PR#106
            if self.singleClassMode.isChecked() and self.lastLabel:
                text = self.lastLabel
            else:
                text = self.labelDialog.popUp(text=self.prevLabelText)
                self.lastLabel = text
        else:
            text = self.defaultLabelTextLine.text()

        # Add Chris
        #self.diffcButton.setChecked(False)
        if text is not None:
            self.prevLabelText = text
            self.addLabel(self.canvas.setLastLabel(text))
            self.shapeSelectionChanged(True)
            if self.beginner():  # Switch to edit mode.
                self.canvas.setEditing(True)
                self.actions.create.setEnabled(True)
            else:
                self.actions.editMode.setEnabled(True)
            self.setDirty()

            if text not in self.labelHist:
                self.labelHist.append(text)
        else:
            # self.canvas.undoLastLine()
            self.canvas.resetAllLines()

    def scrollRequest(self, delta, orientation):
        units = - delta / (8 * 15)
        bar = self.scrollBars[orientation]
        bar.setValue(bar.value() + bar.singleStep() * units)

    def setZoom(self, value):
        self.actions.fitWidth.setChecked(False)
        self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.MANUAL_ZOOM
        self.zoomWidget.setValue(value)

    def addZoom(self, increment=10):
        self.setZoom(self.zoomWidget.value() + increment)

    def zoomRequest(self, delta):
        # get the current scrollbar positions
        # calculate the percentages ~ coordinates
        h_bar = self.scrollBars[Qt.Horizontal]
        v_bar = self.scrollBars[Qt.Vertical]

        # get the current maximum, to know the difference after zooming
        h_bar_max = h_bar.maximum()
        v_bar_max = v_bar.maximum()

        # get the cursor position and canvas size
        # calculate the desired movement from 0 to 1
        # where 0 = move left
        #       1 = move right
        # up and down analogous
        cursor = QCursor()
        pos = cursor.pos()

        cursor_x = pos.x()
        cursor_y = pos.y()

        w = self.scrollArea.width()
        h = self.scrollArea.height()

        # the scaling from 0 to 1 has some padding
        # you don't have to hit the very leftmost pixel for a maximum-left movement
        margin = 0.1
        move_x = (cursor_x - margin * w) / (w - 2 * margin * w)
        move_y = (cursor_y - margin * h) / (h - 2 * margin * h)

        # clamp the values form 0 to 1
        move_x = min(max(move_x, 0), 1)
        move_y = min(max(move_y, 0), 1)

        # zoom in
        units = delta / (8 * 15)
        scale = 10
        self.addZoom(scale * units)

        # get the difference in scrollbar values
        # this is how far we can move
        d_h_bar_max = h_bar.maximum() - h_bar_max
        d_v_bar_max = v_bar.maximum() - v_bar_max

        # get the new scrollbar values
        new_h_bar_value = h_bar.value() + move_x * d_h_bar_max
        new_v_bar_value = v_bar.value() + move_y * d_v_bar_max

        h_bar.setValue(new_h_bar_value)
        v_bar.setValue(new_v_bar_value)

    def setFitWindow(self, value=True):
        if value:
            self.actions.fitWidth.setChecked(False)
        self.zoomMode = self.FIT_WINDOW if value else self.MANUAL_ZOOM
        self.adjustScale()

    def setFitWidth(self, value=True):
        if value:
            self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.FIT_WIDTH if value else self.MANUAL_ZOOM
        self.adjustScale()

    def togglePolygons(self, value):
        for item, shape in self.itemsToShapes.items():
            item.setCheckState(Qt.Checked if value else Qt.Unchecked)

    def loadFile(self, filePath=None):
        """Load the specified file, or the last opened file if None."""
        self.resetState()
        self.canvas.setEnabled(False)
        if filePath is None:
            filePath = self.settings.get('filename')

        unicodeFilePath = ustr(filePath)
        self.filePath = unicodeFilePath
        # Tzutalin 20160906 : Add file list and dock to move faster
        # Highlight the file item
        if unicodeFilePath and self.fileListWidget.count() > 0:
            index = self.mImgList.index(unicodeFilePath)
            fileWidgetItem = self.fileListWidget.item(index)
            fileWidgetItem.setSelected(True)
            self.fileListWidget.setCurrentItem(fileWidgetItem)

        if unicodeFilePath and os.path.exists(unicodeFilePath):
            if LabelFile.isLabelFile(unicodeFilePath):
                try:
                    self.labelFile = LabelFile(unicodeFilePath)
                except LabelFileError as e:
                    self.errorMessage(u'Error opening file',
                                      (u"<p><b>%s</b></p>"
                                       u"<p>Make sure <i>%s</i> is a valid label file.")
                                      % (e, unicodeFilePath))
                    self.status("Error reading %s" % unicodeFilePath)
                    return False
                self.imageData = self.labelFile.imageData
                self.lineColor = QColor(*self.labelFile.lineColor)
                self.fillColor = QColor(*self.labelFile.fillColor)
            else:
                # Load image:
                # read data first and store for saving into label file.
                self.imageData = read(unicodeFilePath, None)
                self.labelFile = None
            image = QImage.fromData(self.imageData)
            #print image
            if image.isNull():
                self.errorMessage(u'Error opening file',
                                  u"<p>Make sure <i>%s</i> is a valid image file." % unicodeFilePath)
                self.status("Error reading %s" % unicodeFilePath)
                return False

            self.status("Loaded %s" % os.path.basename(unicodeFilePath))
            self.image = image

            self.canvas.loadPixmap(QPixmap.fromImage(image))
            #if self.labelFile:
                #self.loadLabels(self.labelFile.shapes)
            self.setClean()
            self.canvas.setEnabled(True)
            self.adjustScale(initial=True)
            self.paintCanvas()
            self.addRecentFile(self.filePath)
            self.toggleActions(True)
            self.actions.deleteImg.setEnabled(True)
            self.actions.loadPrev.setEnabled(True)

            # Label xml file and show bound box according to its filename
            if self.usingPascalVocFormat is True:
                if self.defaultSaveDir is not None:
                    basename = os.path.basename(
                        os.path.splitext(self.filePath)[0]) + XML_EXT
                    xmlPath = os.path.join(self.defaultSaveDir, basename)
                    if os.path.isfile(xmlPath):
                        self.loadPascalXMLByFilename(xmlPath)
                    else:
                        self.setDefaultAttrChoice()
                else:
                    xmlPath = os.path.splitext(filePath)[0] + XML_EXT
                    if os.path.isfile(xmlPath):
                        self.loadPascalXMLByFilename(xmlPath)
                    else:
                        self.setDefaultAttrChoice()

            self.setWindowTitle(__appname__ + ' ' + filePath)

            # Default : select last item if there is at least one item
            if self.labelList.count():
                self.labelList.setCurrentItem(self.labelList.item(self.labelList.count()-1))
                self.labelList.item(self.labelList.count()-1).setSelected(True)

            self.canvas.setFocus(True)
            return True
        return False

    def loadFileWithPreLabel(self, filePath, PrefilePath):
        """Load the specified file, or the last opened file if None."""
        self.resetState()
        self.canvas.setEnabled(False)
        if filePath is None:
            filePath = self.settings.get('filename')

        unicodeFilePath = ustr(filePath)
        unicodePreFilePath = ustr(PrefilePath)
        # Tzutalin 20160906 : Add file list and dock to move faster
        # Highlight the file item
        if unicodeFilePath and self.fileListWidget.count() > 0:
            index = self.mImgList.index(unicodeFilePath)
            fileWidgetItem = self.fileListWidget.item(index)
            fileWidgetItem.setSelected(True)
            self.fileListWidget.setCurrentItem(fileWidgetItem)

        if unicodeFilePath and os.path.exists(unicodeFilePath):
            if LabelFile.isLabelFile(unicodeFilePath):
                try:
                    self.labelFile = LabelFile(unicodeFilePath)
                except LabelFileError as e:
                    self.errorMessage(u'Error opening file',
                                      (u"<p><b>%s</b></p>"
                                       u"<p>Make sure <i>%s</i> is a valid label file.")
                                      % (e, unicodeFilePath))
                    self.status("Error reading %s" % unicodeFilePath)
                    return False
                self.imageData = self.labelFile.imageData
                self.lineColor = QColor(*self.labelFile.lineColor)
                self.fillColor = QColor(*self.labelFile.fillColor)
            else:
                # Load image:
                # read data first and store for saving into label file.
                self.imageData = read(unicodeFilePath, None)
                self.labelFile = None
            image = QImage.fromData(self.imageData)
            if image.isNull():
                self.errorMessage(u'Error opening file',
                                  u"<p>Make sure <i>%s</i> is a valid image file." % unicodeFilePath)
                self.status("Error reading %s" % unicodeFilePath)
                return False
            self.status("Loaded %s" % os.path.basename(unicodeFilePath))
            self.image = image
            self.filePath = unicodeFilePath
            self.canvas.loadPixmap(QPixmap.fromImage(image))
            #if self.labelFile:
                #self.loadLabels(self.labelFile.shapes)
            self.setClean()
            self.canvas.setEnabled(True)
            self.adjustScale(initial=True)
            self.paintCanvas()
            self.addRecentFile(self.filePath)
            self.toggleActions(True)
            self.actions.deleteImg.setEnabled(True)
            self.actions.loadPrev.setEnabled(False)
            # Label xml file and show bound box according to its filename
            if self.usingPascalVocFormat is True:
                if self.defaultSaveDir is not None:
                    basename = os.path.basename(
                        os.path.splitext(unicodePreFilePath)[0]) + XML_EXT
                    xmlPath = os.path.join(self.defaultSaveDir, basename)
                    self.loadPascalXMLByFilename(xmlPath)
                else:
                    xmlPath = os.path.splitext(unicodePreFilePath)[0] + XML_EXT
                    if os.path.isfile(xmlPath):
                        self.loadPascalXMLByFilename(xmlPath)

            self.setWindowTitle(__appname__ + ' ' + filePath)

            # Default : select last item if there is at least one item
            if self.labelList.count():
                self.labelList.setCurrentItem(self.labelList.item(self.labelList.count()-1))
                self.labelList.item(self.labelList.count()-1).setSelected(True)

            self.canvas.setFocus(True)
            return True
        return False

    def loadPreLabel(self):
        filePath = self.filePath
        index = self.mImgList.index(filePath)
        if index == 0:
            self.status("this is the first image.")
            return
        PrefilePath = self.mImgList[index - 1]
        if self.loadFileWithPreLabel(filePath, PrefilePath):
            self.setDirty()

    def resizeEvent(self, event):
        if self.canvas and not self.image.isNull()\
           and self.zoomMode != self.MANUAL_ZOOM:
            self.adjustScale()
        super(MainWindow, self).resizeEvent(event)

    def paintCanvas(self):
        assert not self.image.isNull(), "cannot paint null image"
        self.canvas.scale = 0.01 * self.zoomWidget.value()
        self.canvas.adjustSize()
        self.canvas.update()

    def adjustScale(self, initial=False):
        value = self.scalers[self.FIT_WINDOW if initial else self.zoomMode]()
        self.zoomWidget.setValue(int(100 * value))

    def scaleFitWindow(self):
        """Figure out the size of the pixmap in order to fit the main widget."""
        e = 2.0  # So that no scrollbars are generated.
        w1 = self.centralWidget().width() - e
        h1 = self.centralWidget().height() - e
        a1 = w1 / h1
        # Calculate a new scale value based on the pixmap's aspect ratio.
        w2 = self.canvas.pixmap.width() - 0.0
        h2 = self.canvas.pixmap.height() - 0.0
        a2 = w2 / h2
        return w1 / w2 if a2 >= a1 else h1 / h2

    def scaleFitWidth(self):
        # The epsilon does not seem to work too well here.
        w = self.centralWidget().width() - 2.0
        return w / self.canvas.pixmap.width()

    def closeEvent(self, event):
        if not self.mayContinue():
            event.ignore()
        s = self.settings
        # If it loads images from dir, don't load it at the begining
        if self.dirname is None:
            s['filename'] = self.filePath if self.filePath else ''
        else:
            s['filename'] = ''

        s['window/size'] = self.size()
        s['window/position'] = self.pos()
        s['window/state'] = self.saveState()
        s['line/color'] = self.lineColor
        s['fill/color'] = self.fillColor
        s['recentFiles'] = self.recentFiles
        s['advanced'] = not self._beginner
        if self.defaultSaveDir is not None and len(self.defaultSaveDir) > 1:
            s['savedir'] = ustr(self.defaultSaveDir)
        else:
            s['savedir'] = ""

        if self.lastOpenDir is not None and len(self.lastOpenDir) > 1:
            s['lastOpenDir'] = self.lastOpenDir
        else:
            s['lastOpenDir'] = ""

    ## User Dialogs ##

    def loadRecent(self, filename):
        if self.mayContinue():
            self.loadFile(filename)

    def scanAllImages(self, folderPath):
        extensions = ['.jpeg', '.jpg', '.png', '.bmp']
        images = []

        for root, dirs, files in os.walk(folderPath):
            for file in files:
                if file.lower().endswith(tuple(extensions)):
                    relativePath = os.path.join(root, file)
                    path = ustr(os.path.abspath(relativePath))
                    images.append(path)
        images.sort(key=lambda x: x.lower())
        return images

    def changeSavedir(self, _value=False):
        if self.defaultSaveDir is not None:
            path = ustr(self.defaultSaveDir)
        else:
            path = '.'

        dirpath = ustr(QFileDialog.getExistingDirectory(self,
                                                       '%s - Save to the directory' % __appname__, path,  QFileDialog.ShowDirsOnly
                                                       | QFileDialog.DontResolveSymlinks))

        if dirpath is not None and len(dirpath) > 1:
            self.defaultSaveDir = dirpath

        self.statusBar().showMessage('%s . Annotation will be saved to %s' %
                                     ('Change saved folder', self.defaultSaveDir))
        self.statusBar().show()

    def openAnnotation(self, _value=False):
        if self.filePath is None:
            self.statusBar().showMessage('Please select image first')
            self.statusBar().show()
            return

        path = os.path.dirname(ustr(self.filePath))\
            if self.filePath else '.'
        if self.usingPascalVocFormat:
            filters = "Open Annotation XML file (%s)" % ' '.join(['*.xml'])
            filename = ustr(QFileDialog.getOpenFileName(self,'%s - Choose a xml file' % __appname__, path, filters))
            if filename:
                if isinstance(filename, (tuple, list)):
                    filename = filename[0]
            self.loadPascalXMLByFilename(filename)

    def openDir(self, _value=False):
        if not self.mayContinue():
            return

        path = os.path.dirname(self.filePath)\
            if self.filePath else '.'

        if self.lastOpenDir is not None and len(self.lastOpenDir) > 1:
            path = self.lastOpenDir

        dirpath = ustr(QFileDialog.getExistingDirectory(self,
                                                     '%s - Open Directory' % __appname__, path,  QFileDialog.ShowDirsOnly
                                                     | QFileDialog.DontResolveSymlinks))

        if dirpath is not None and len(dirpath) > 1:
            self.lastOpenDir = dirpath

        self.dirname = dirpath
        self.filePath = None
        self.fileListWidget.clear()
        self.mImgList = self.scanAllImages(dirpath)

        for imgPath in self.mImgList:
            item = QListWidgetItem(imgPath)
            self.fileListWidget.addItem(item)
        self.haveOpenDir = True
        self.openNextImg()

    def verifyImg(self, _value=False):
        # Proceding next image without dialog if having any label
         if self.filePath is not None:
            try:
                self.labelFile.toggleVerify()
            except AttributeError:
                # If the labelling file does not exist yet, create if and
                # re-save it with the verified attribute.
                self.saveFile()
                self.labelFile.toggleVerify()

            self.canvas.verified = self.labelFile.verified
            self.paintCanvas()
            self.saveFile()

    def openPrevImg(self, _value=False):
        # Proceding prev image without dialog if having any label
        if self.autoSaving.isChecked() and (self.defaultSaveDir is not None):
            if self.dirty is True:
                self.saveFile()

        ## add by jie liu
        if self.defaultSaveDir is not None and self.dirty is True:
            self.saveFile()

        if not self.mayContinue():
            return

        if len(self.mImgList) <= 0:
            return

        if self.filePath is None:
            return

        currIndex = self.mImgList.index(self.filePath)
        if currIndex - 1 >= 0:
            filename = self.mImgList[currIndex - 1]
            if filename:
                self.loadFile(filename)

    def reload(self):
        if len(self.mImgList) <= 0:
            return

        if self.filePath is None:
            return
        currIndex = self.mImgList.index(self.filePath)
        filename = self.mImgList[currIndex]
        if filename:
            self.loadFile(filename)

    def openNextImg(self, _value=False):
        # Proceding next image without dialog if having any label
        if self.autoSaving.isChecked() and (self.defaultSaveDir is not None):
            if self.dirty is True:
                self.saveFile()
        ## add by jieliu
        if self.defaultSaveDir is not None and self.dirty is True:
            self.saveFile()

        if not self.mayContinue():
            return

        if len(self.mImgList) <= 0:
            return

        filename = None
        if self.filePath is None:
            filename = self.mImgList[0]
        else:
            currIndex = self.mImgList.index(self.filePath)
            if currIndex + 1 < len(self.mImgList):
                filename = self.mImgList[currIndex + 1]

        if filename:
            self.loadFile(filename)


    def openFile(self, _value=False):
        if not self.mayContinue():
            return
        path = os.path.dirname(ustr(self.filePath)) if self.filePath else '.'
        formats = ['*.%s' % fmt.data().decode("ascii").lower() for fmt in QImageReader.supportedImageFormats()]
        formats.append('*.jpg')
        formats.append('*.jpeg')
        filters = "Image & Label files (%s)" % ' '.join(formats + ['*%s' % LabelFile.suffix])
        filename = QFileDialog.getOpenFileName(self, '%s - Choose Image or Label file' % __appname__, path, filters)
        if filename:
            if isinstance(filename, (tuple, list)):
                filename = filename[0]
            if filename not in self.mImgList:
                self.mImgList.append(ustr(filename))
                item = QListWidgetItem(ustr(filename))
                self.fileListWidget.addItem(item)
            self.loadFile(ustr(filename))

    def loadBboxFile(self, _value=False):
        if not self.haveOpenDir:
            msg = 'Please first open the images directory.'
            QMessageBox.warning(self, u'Attention', msg, QMessageBox.Ok)
            return
        if self.defaultSaveDir is None or len(ustr(self.defaultSaveDir)) == 0:
            msg = 'Please first set the default save directory.'
            QMessageBox.warning(self, u'Attention', msg, QMessageBox.Ok)
            return
        path = os.path.dirname(ustr(self.filePath)) if self.filePath else '.'
        filters = 'All Files (*)'
        filename = QFileDialog.getOpenFileName(self, '%s - Choose File' % __appname__, path, filters)
        if filename:
            self.parseBboxToXml(ustr(filename))

    def parseBboxToXml(self, filePath):
        #fileDir = os.path.dirname(os.path.normpath(filePath))
        bboxFile = open(filePath)
        image_path_pattern = re.compile(r'.+\..+')
        while True:
            image_path = bboxFile.readline().strip()
            if image_path == '':
                break
            if image_path_pattern.search(image_path) is None:
                continue
            image_name = os.path.basename(image_path)
            #if not os.path.isabs(image_path):
            #    if self.haveOpenDir:
            image_path = os.path.join(self.lastOpenDir, image_name)
            #    else:
            #        image_path = os.path.join(fileDir, image_path)

            annotationFilePath = os.path.join(self.defaultSaveDir, image_name[0:image_name.rfind('.')]+ '.xml')
            bbox_num = int(bboxFile.readline().strip())
            self.labelFile = LabelFile()
            self.labelFile.verified = self.canvas.verified
            shapes = []
            for i in range(1, bbox_num+1):
                line = bboxFile.readline().strip()
                line_split = line.split(" ")
                shape = dict(label="bbox%d"%i,
                             line_color=None,
                             fill_color=None,
                             points=[(int(line_split[0]), int(line_split[1])), (int(line_split[2]), int(line_split[3]))],
                             attrDict = self.makeDefaultAttrDict())
                shapes.append(shape)
            if not os.path.exists(image_path):
                continue
            try:
                print ('Img: ' + image_path + ' -> Its xml: ' + annotationFilePath)
                self.labelFile.savePascalVocFormat(annotationFilePath, shapes, image_path, None,sku=self.defaultSKUTextLine.text())
            except LabelFileError as e:
                self.errorMessage(u'Error saving label data',
                                  u'<b>%s</b>' % e)
        self.reload()


    def saveFile(self, _value=False):
        if self.defaultSaveDir is not None and len(ustr(self.defaultSaveDir)):
            if self.filePath:
                imgFileName = os.path.basename(self.filePath)
                savedFileName = os.path.splitext(imgFileName)[0] + XML_EXT
                savedPath = os.path.join(ustr(self.defaultSaveDir), savedFileName)
                self._saveFile(savedPath)
        else:
            imgFileDir = os.path.dirname(self.filePath)
            imgFileName = os.path.basename(self.filePath)
            savedFileName = os.path.splitext(imgFileName)[0] + XML_EXT
            savedPath = os.path.join(imgFileDir, savedFileName)
            self._saveFile(savedPath if self.labelFile
                           else self.saveFileDialog())

    def saveFileAs(self, _value=False):
        assert not self.image.isNull(), "cannot save empty image"
        self._saveFile(self.saveFileDialog())

    def saveFileDialog(self):
        caption = '%s - Choose File' % __appname__
        filters = 'File (*%s)' % LabelFile.suffix
        openDialogPath = self.currentPath()
        dlg = QFileDialog(self, caption, openDialogPath, filters)
        dlg.setDefaultSuffix(LabelFile.suffix[1:])
        dlg.setAcceptMode(QFileDialog.AcceptSave)
        filenameWithoutExtension = os.path.splitext(self.filePath)[0]
        dlg.selectFile(filenameWithoutExtension)
        dlg.setOption(QFileDialog.DontUseNativeDialog, False)
        if dlg.exec_():
            return dlg.selectedFiles()[0]
        return ''

    def _saveFile(self, annotationFilePath):
        if annotationFilePath and self.saveLabels(annotationFilePath):
            self.setClean()
            self.statusBar().showMessage('Saved to  %s' % annotationFilePath)
            self.statusBar().show()

    def closeFile(self, _value=False):
        if not self.mayContinue():
            return
        self.resetState()
        self.setClean()
        self.toggleActions(False)
        self.canvas.setEnabled(False)
        self.actions.saveAs.setEnabled(False)
        self.actions.deleteImg.setEnabled(False)
        self.actions.loadPrev.setEnabled(False)

    def mayContinue(self):
        return not (self.dirty and not self.discardChangesDialog())

    def discardChangesDialog(self):
        yes, no = QMessageBox.Yes, QMessageBox.No
        msg = u'你还没有保存，需要继续么? <b>若使用自动保存，请先设置保存目录.<\b>'
        return yes == QMessageBox.warning(self, u'注意', msg, yes | no)

    def deleteConfirm(self):
        yes, no = QMessageBox.Yes, QMessageBox.No
        msg = u'删除这幅图片? <b>这会删除你电脑中的图片.<\b>'
        return yes == QMessageBox.warning(self, u'注意', msg, yes | no)

    def errorMessage(self, title, message):
        return QMessageBox.critical(self, title,
                                    '<p><b>%s</b></p>%s' % (title, message))

    def currentPath(self):
        return os.path.dirname(self.filePath) if self.filePath else '.'

    def chooseColor1(self):
        color = self.colorDialog.getColor(self.lineColor, u'Choose line color',
                                          default=DEFAULT_LINE_COLOR)
        if color:
            self.lineColor = color
            # Change the color for all shape lines:
            Shape.line_color = self.lineColor
            self.canvas.update()
            self.setDirty()
            self.actions.loadPrev.setEnabled(True)

    def chooseColor2(self):
        color = self.colorDialog.getColor(self.fillColor, u'Choose fill color',
                                          default=DEFAULT_FILL_COLOR)
        if color:
            self.fillColor = color
            Shape.fill_color = self.fillColor
            self.canvas.update()
            self.setDirty()

    def deleteSelectedShape(self):
        self.remLabel(self.canvas.deleteSelected())
        self.setDirty()
        if self.noShapes():
            for action in self.actions.onShapesPresent:
                action.setEnabled(False)

    def chshapeLineColor(self):
        color = self.colorDialog.getColor(self.lineColor, u'Choose line color',
                                          default=DEFAULT_LINE_COLOR)
        if color:
            self.canvas.selectedShape.line_color = color
            self.canvas.update()
            self.setDirty()

    def chshapeFillColor(self):
        color = self.colorDialog.getColor(self.fillColor, u'Choose fill color',
                                          default=DEFAULT_FILL_COLOR)
        if color:
            self.canvas.selectedShape.fill_color = color
            self.canvas.update()
            self.setDirty()

    def copyShape(self):
        self.canvas.endMove(copy=True)
        self.addLabel(self.canvas.selectedShape)
        self.setDirty()

    def moveShape(self):
        self.canvas.endMove(copy=False)
        self.setDirty()

    def loadPredefinedClasses(self, predefClassesFile):
        if os.path.exists(predefClassesFile) is True:
            with codecs.open(predefClassesFile, 'r', 'utf8') as f:
                for line in f:
                    line = line.strip()
                    if self.labelHist is None:
                        self.lablHist = [line]
                    else:
                        self.labelHist.append(line)

    def loadPascalXMLByFilename(self, xmlPath):
        if self.filePath is None:
            return
        if os.path.isfile(xmlPath) is False:
            return

        tVocParseReader = PascalVocReader(xmlPath)
        shapes = tVocParseReader.getShapes()
        self.sku =tVocParseReader.sku
        if self.sku != 0:
            self.useSKUCheckButton.setEnabled(True)
        if len(shapes) == 0:
            self.setDefaultAttrChoice()
        self.loadLabels(shapes)
        self.canvas.verified = tVocParseReader.verified

    def deleteSelectedImg(self, _value=False):
        if not self.mayContinue():
            return
        if not self.deleteConfirm():
            return
        currentIndex = self.fileListWidget.row(self.fileListWidget.currentItem())
        item = self.fileListWidget.takeItem(currentIndex)
        if item is not None:
            self.closeFile()
            imgPath = self.mImgList[currentIndex]
            del self.mImgList[currentIndex]
            os.remove(imgPath)
            if(currentIndex < len(self.mImgList)):
                filename = self.mImgList[currentIndex]
                self.loadFile(filename)



class Settings(object):
    """Convenience dict-like wrapper around QSettings."""

    def __init__(self, types=None):
        self.data = QSettings()
        self.types = defaultdict(lambda: QVariant, types if types else {})

    def __setitem__(self, key, value):
        t = self.types[key]
        self.data.setValue(key,
                           t(value) if not isinstance(value, t) else value)

    def __getitem__(self, key):
        return self._cast(key, self.data.value(key))

    def get(self, key, default=None):
        return self._cast(key, self.data.value(key, default))

    def _cast(self, key, value):
        # XXX: Very nasty way of converting types to QVariant methods :P
        t = self.types.get(key)
        if t is not None and t != QVariant:
            if t is str:
                return ustr(value)
            else:
                try:
                    method = getattr(QVariant, re.sub(
                        '^Q', 'to', t.__name__, count=1))
                    return method(value)
                except AttributeError as e:
                    # print(e)
                    return value
        return value


def inverted(color):
    return QColor(*[255 - v for v in color.getRgb()])


def read(filename, default=None):
    try:
        with open(filename, 'rb') as f:
            return f.read()
    except:
        return default


def get_main_app(argv=[]):
    """
    Standard boilerplate Qt application code.
    Do everything but app.exec_() -- so that we can test the application in one thread
    """
    app = QApplication(argv)
    app.setApplicationName(__appname__)
    app.setWindowIcon(newIcon("app"))
    # Tzutalin 201705+: Accept extra agruments to change predefined class file
    # Usage : labelImg.py image predefClassFile
    win = MainWindow(argv[1] if len(argv) >= 2 else None,
                     argv[2] if len(argv) >= 3 else os.path.join('data', 'predefined_classes.txt'))
    win.show()
    return app, win


def main(argv=[]):
    '''construct main app and run it'''
    app, _win = get_main_app(argv)
    return app.exec_()

if __name__ == '__main__':
    sys.exit(main(sys.argv))
