# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'DMD_stim.ui'
##
## Created by: Qt User Interface Compiler version 6.9.0
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QSizePolicy, QSplitter, QStackedWidget, QTabWidget,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget)

class Ui_widget_dmd_stim(object):
    def setupUi(self, widget_dmd_stim):
        if not widget_dmd_stim.objectName():
            widget_dmd_stim.setObjectName(u"widget_dmd_stim")
        widget_dmd_stim.resize(1280, 580)
        widget_dmd_stim.setMinimumSize(QSize(0, 0))
        self.horizontalLayout = QHBoxLayout(widget_dmd_stim)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.splitter_control_image = QSplitter(widget_dmd_stim)
        self.splitter_control_image.setObjectName(u"splitter_control_image")
        self.splitter_control_image.setOrientation(Qt.Orientation.Horizontal)
        self.splitter_control_image.setHandleWidth(10)
        self.splitter_control_output = QSplitter(self.splitter_control_image)
        self.splitter_control_output.setObjectName(u"splitter_control_output")
        self.splitter_control_output.setEnabled(True)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.splitter_control_output.sizePolicy().hasHeightForWidth())
        self.splitter_control_output.setSizePolicy(sizePolicy)
        self.splitter_control_output.setMinimumSize(QSize(0, 0))
        self.splitter_control_output.setOrientation(Qt.Orientation.Vertical)
        self.splitter_control_output.setHandleWidth(10)
        self.verticalLayoutWidget = QWidget(self.splitter_control_output)
        self.verticalLayoutWidget.setObjectName(u"verticalLayoutWidget")
        self.verticalLayout_controls = QVBoxLayout(self.verticalLayoutWidget)
        self.verticalLayout_controls.setObjectName(u"verticalLayout_controls")
        self.verticalLayout_controls.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout_6 = QHBoxLayout()
        self.horizontalLayout_6.setObjectName(u"horizontalLayout_6")
        self.pushButton_calibrate_dmd = QPushButton(self.verticalLayoutWidget)
        self.pushButton_calibrate_dmd.setObjectName(u"pushButton_calibrate_dmd")

        self.horizontalLayout_6.addWidget(self.pushButton_calibrate_dmd)

        self.pushButton_show_grid = QPushButton(self.verticalLayoutWidget)
        self.pushButton_show_grid.setObjectName(u"pushButton_show_grid")
        self.pushButton_show_grid.setCheckable(True)

        self.horizontalLayout_6.addWidget(self.pushButton_show_grid)

        self.pushButton_define_axis = QPushButton(self.verticalLayoutWidget)
        self.pushButton_define_axis.setObjectName(u"pushButton_define_axis")
        self.pushButton_define_axis.setCheckable(True)

        self.horizontalLayout_6.addWidget(self.pushButton_define_axis)

        self.label_axis_behaviour = QLabel(self.verticalLayoutWidget)
        self.label_axis_behaviour.setObjectName(u"label_axis_behaviour")

        self.horizontalLayout_6.addWidget(self.label_axis_behaviour)

        self.comboBox_axis_behaviour = QComboBox(self.verticalLayoutWidget)
        self.comboBox_axis_behaviour.addItem("")
        self.comboBox_axis_behaviour.addItem("")
        self.comboBox_axis_behaviour.setObjectName(u"comboBox_axis_behaviour")
        self.comboBox_axis_behaviour.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)

        self.horizontalLayout_6.addWidget(self.comboBox_axis_behaviour)


        self.verticalLayout_controls.addLayout(self.horizontalLayout_6)

        self.horizontalLayout_patternLoading = QHBoxLayout()
        self.horizontalLayout_patternLoading.setObjectName(u"horizontalLayout_patternLoading")
        self.label_file_path = QLabel(self.verticalLayoutWidget)
        self.label_file_path.setObjectName(u"label_file_path")

        self.horizontalLayout_patternLoading.addWidget(self.label_file_path)

        self.pushButton_new_file = QPushButton(self.verticalLayoutWidget)
        self.pushButton_new_file.setObjectName(u"pushButton_new_file")

        self.horizontalLayout_patternLoading.addWidget(self.pushButton_new_file)

        self.lineEdit_file_path = QLineEdit(self.verticalLayoutWidget)
        self.lineEdit_file_path.setObjectName(u"lineEdit_file_path")

        self.horizontalLayout_patternLoading.addWidget(self.lineEdit_file_path)

        self.pushButton_load_patterns = QPushButton(self.verticalLayoutWidget)
        self.pushButton_load_patterns.setObjectName(u"pushButton_load_patterns")
        icon = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen))
        self.pushButton_load_patterns.setIcon(icon)

        self.horizontalLayout_patternLoading.addWidget(self.pushButton_load_patterns)

        self.pushButton_save_patterns = QPushButton(self.verticalLayoutWidget)
        self.pushButton_save_patterns.setObjectName(u"pushButton_save_patterns")
        icon1 = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.DocumentSave))
        self.pushButton_save_patterns.setIcon(icon1)

        self.horizontalLayout_patternLoading.addWidget(self.pushButton_save_patterns)


        self.verticalLayout_controls.addLayout(self.horizontalLayout_patternLoading)

        self.tabWidget = QTabWidget(self.verticalLayoutWidget)
        self.tabWidget.setObjectName(u"tabWidget")
        sizePolicy.setHeightForWidth(self.tabWidget.sizePolicy().hasHeightForWidth())
        self.tabWidget.setSizePolicy(sizePolicy)
        self.tab_editor = QWidget()
        self.tab_editor.setObjectName(u"tab_editor")
        self.horizontalLayout_13 = QHBoxLayout(self.tab_editor)
        self.horizontalLayout_13.setObjectName(u"horizontalLayout_13")
        self.verticalLayout_patterns = QVBoxLayout()
        self.verticalLayout_patterns.setObjectName(u"verticalLayout_patterns")
        self.label_patterns = QLabel(self.tab_editor)
        self.label_patterns.setObjectName(u"label_patterns")

        self.verticalLayout_patterns.addWidget(self.label_patterns)

        self.treeWidget = QTreeWidget(self.tab_editor)
        __qtreewidgetitem = QTreeWidgetItem()
        __qtreewidgetitem.setText(0, u"1");
        self.treeWidget.setHeaderItem(__qtreewidgetitem)
        self.treeWidget.setObjectName(u"treeWidget")
        self.treeWidget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.treeWidget.setAlternatingRowColors(True)

        self.verticalLayout_patterns.addWidget(self.treeWidget)

        self.gridLayout_patternsButtons = QGridLayout()
        self.gridLayout_patternsButtons.setObjectName(u"gridLayout_patternsButtons")
        self.gridLayout_patternsButtons.setContentsMargins(-1, 0, -1, -1)
        self.pushButton_draw_rectangle = QPushButton(self.tab_editor)
        self.pushButton_draw_rectangle.setObjectName(u"pushButton_draw_rectangle")

        self.gridLayout_patternsButtons.addWidget(self.pushButton_draw_rectangle, 1, 0, 1, 1)

        self.pushButton_draw_polygon = QPushButton(self.tab_editor)
        self.pushButton_draw_polygon.setObjectName(u"pushButton_draw_polygon")

        self.gridLayout_patternsButtons.addWidget(self.pushButton_draw_polygon, 1, 1, 1, 1)

        self.pushButton_add_pattern = QPushButton(self.tab_editor)
        self.pushButton_add_pattern.setObjectName(u"pushButton_add_pattern")
        icon2 = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.ListAdd))
        self.pushButton_add_pattern.setIcon(icon2)

        self.gridLayout_patternsButtons.addWidget(self.pushButton_add_pattern, 0, 0, 1, 2)

        self.pushButton_remove_pattern = QPushButton(self.tab_editor)
        self.pushButton_remove_pattern.setObjectName(u"pushButton_remove_pattern")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.pushButton_remove_pattern.sizePolicy().hasHeightForWidth())
        self.pushButton_remove_pattern.setSizePolicy(sizePolicy1)
        icon3 = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.EditDelete))
        self.pushButton_remove_pattern.setIcon(icon3)

        self.gridLayout_patternsButtons.addWidget(self.pushButton_remove_pattern, 0, 2, 2, 1)


        self.verticalLayout_patterns.addLayout(self.gridLayout_patternsButtons)


        self.horizontalLayout_13.addLayout(self.verticalLayout_patterns)

        self.line = QFrame(self.tab_editor)
        self.line.setObjectName(u"line")
        self.line.setFrameShape(QFrame.Shape.VLine)
        self.line.setFrameShadow(QFrame.Shadow.Sunken)

        self.horizontalLayout_13.addWidget(self.line)

        self.verticalLayout_sequence = QVBoxLayout()
        self.verticalLayout_sequence.setObjectName(u"verticalLayout_sequence")
        self.label_sequence = QLabel(self.tab_editor)
        self.label_sequence.setObjectName(u"label_sequence")

        self.verticalLayout_sequence.addWidget(self.label_sequence)

        self.tableWidget = QTableWidget(self.tab_editor)
        if (self.tableWidget.columnCount() < 3):
            self.tableWidget.setColumnCount(3)
        __qtablewidgetitem = QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        self.tableWidget.setObjectName(u"tableWidget")
        self.tableWidget.setDragEnabled(True)
        self.tableWidget.setDragDropOverwriteMode(False)
        self.tableWidget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tableWidget.setColumnCount(3)

        self.verticalLayout_sequence.addWidget(self.tableWidget)

        self.gridLayout = QGridLayout()
        self.gridLayout.setObjectName(u"gridLayout")
        self.gridLayout.setContentsMargins(-1, 0, -1, -1)
        self.pushButton_add_row = QPushButton(self.tab_editor)
        self.pushButton_add_row.setObjectName(u"pushButton_add_row")
        self.pushButton_add_row.setIcon(icon2)

        self.gridLayout.addWidget(self.pushButton_add_row, 0, 0, 1, 1)

        self.pushButton_remove_row = QPushButton(self.tab_editor)
        self.pushButton_remove_row.setObjectName(u"pushButton_remove_row")
        icon4 = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.ListRemove))
        self.pushButton_remove_row.setIcon(icon4)

        self.gridLayout.addWidget(self.pushButton_remove_row, 0, 1, 1, 1)

        self.pushButton_3 = QPushButton(self.tab_editor)
        self.pushButton_3.setObjectName(u"pushButton_3")

        self.gridLayout.addWidget(self.pushButton_3, 1, 0, 1, 1)

        self.pushButton_4 = QPushButton(self.tab_editor)
        self.pushButton_4.setObjectName(u"pushButton_4")

        self.gridLayout.addWidget(self.pushButton_4, 1, 1, 1, 1)


        self.verticalLayout_sequence.addLayout(self.gridLayout)


        self.horizontalLayout_13.addLayout(self.verticalLayout_sequence)

        self.tabWidget.addTab(self.tab_editor, "")
        self.tab_run = QWidget()
        self.tab_run.setObjectName(u"tab_run")
        self.gridLayout_3 = QGridLayout(self.tab_run)
        self.gridLayout_3.setObjectName(u"gridLayout_3")
        self.stackedWidget_live_graph = QStackedWidget(self.tab_run)
        self.stackedWidget_live_graph.setObjectName(u"stackedWidget_live_graph")

        self.gridLayout_3.addWidget(self.stackedWidget_live_graph, 1, 0, 1, 2)

        self.pushButton_connect_dmd = QPushButton(self.tab_run)
        self.pushButton_connect_dmd.setObjectName(u"pushButton_connect_dmd")
        icon5 = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.NetworkWired))
        self.pushButton_connect_dmd.setIcon(icon5)

        self.gridLayout_3.addWidget(self.pushButton_connect_dmd, 0, 0, 1, 1)

        self.pushButton_listen_to_matlab = QPushButton(self.tab_run)
        self.pushButton_listen_to_matlab.setObjectName(u"pushButton_listen_to_matlab")
        icon6 = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.MediaPlaybackStart))
        self.pushButton_listen_to_matlab.setIcon(icon6)

        self.gridLayout_3.addWidget(self.pushButton_listen_to_matlab, 0, 1, 1, 1)

        self.tabWidget.addTab(self.tab_run, "")

        self.verticalLayout_controls.addWidget(self.tabWidget)

        self.splitter_control_output.addWidget(self.verticalLayoutWidget)
        self.groupBox_console_output = QGroupBox(self.splitter_control_output)
        self.groupBox_console_output.setObjectName(u"groupBox_console_output")
        self.verticalLayout = QVBoxLayout(self.groupBox_console_output)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.plainTextEdit_console_output = QPlainTextEdit(self.groupBox_console_output)
        self.plainTextEdit_console_output.setObjectName(u"plainTextEdit_console_output")

        self.verticalLayout.addWidget(self.plainTextEdit_console_output)

        self.splitter_control_output.addWidget(self.groupBox_console_output)
        self.splitter_control_image.addWidget(self.splitter_control_output)
        self.layoutWidget = QWidget(self.splitter_control_image)
        self.layoutWidget.setObjectName(u"layoutWidget")
        self.verticalLayout_image = QVBoxLayout(self.layoutWidget)
        self.verticalLayout_image.setObjectName(u"verticalLayout_image")
        self.verticalLayout_image.setContentsMargins(0, 0, 0, 0)
        self.stackedWidget_image = QStackedWidget(self.layoutWidget)
        self.stackedWidget_image.setObjectName(u"stackedWidget_image")

        self.verticalLayout_image.addWidget(self.stackedWidget_image)

        self.verticalLayout_load_image = QVBoxLayout()
        self.verticalLayout_load_image.setObjectName(u"verticalLayout_load_image")
        self.verticalLayout_load_image.setContentsMargins(0, 0, -1, -1)
        self.horizontalLayout_image_controls = QHBoxLayout()
        self.horizontalLayout_image_controls.setObjectName(u"horizontalLayout_image_controls")
        self.pushButton_load_image = QPushButton(self.layoutWidget)
        self.pushButton_load_image.setObjectName(u"pushButton_load_image")
        icon7 = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.InsertImage))
        self.pushButton_load_image.setIcon(icon7)

        self.horizontalLayout_image_controls.addWidget(self.pushButton_load_image)

        self.pushButton_reset_image_view = QPushButton(self.layoutWidget)
        self.pushButton_reset_image_view.setObjectName(u"pushButton_reset_image_view")
        icon8 = QIcon(QIcon.fromTheme(QIcon.ThemeIcon.ViewRefresh))
        self.pushButton_reset_image_view.setIcon(icon8)

        self.horizontalLayout_image_controls.addWidget(self.pushButton_reset_image_view)


        self.verticalLayout_load_image.addLayout(self.horizontalLayout_image_controls)

        self.horizontalLayout_image_folder = QHBoxLayout()
        self.horizontalLayout_image_folder.setSpacing(5)
        self.horizontalLayout_image_folder.setObjectName(u"horizontalLayout_image_folder")
        self.label_image_folder = QLabel(self.layoutWidget)
        self.label_image_folder.setObjectName(u"label_image_folder")

        self.horizontalLayout_image_folder.addWidget(self.label_image_folder)

        self.lineEdit_image_folder_path = QLineEdit(self.layoutWidget)
        self.lineEdit_image_folder_path.setObjectName(u"lineEdit_image_folder_path")

        self.horizontalLayout_image_folder.addWidget(self.lineEdit_image_folder_path)

        self.pushButton_change_folder = QPushButton(self.layoutWidget)
        self.pushButton_change_folder.setObjectName(u"pushButton_change_folder")
        self.pushButton_change_folder.setIcon(icon)
        self.pushButton_change_folder.setAutoDefault(False)

        self.horizontalLayout_image_folder.addWidget(self.pushButton_change_folder)

        self.pushButton_refresh_image = QPushButton(self.layoutWidget)
        self.pushButton_refresh_image.setObjectName(u"pushButton_refresh_image")
        self.pushButton_refresh_image.setIcon(icon8)

        self.horizontalLayout_image_folder.addWidget(self.pushButton_refresh_image)


        self.verticalLayout_load_image.addLayout(self.horizontalLayout_image_folder)


        self.verticalLayout_image.addLayout(self.verticalLayout_load_image)

        self.splitter_control_image.addWidget(self.layoutWidget)

        self.horizontalLayout.addWidget(self.splitter_control_image)


        self.retranslateUi(widget_dmd_stim)

        self.tabWidget.setCurrentIndex(0)
        self.pushButton_change_folder.setDefault(False)


        QMetaObject.connectSlotsByName(widget_dmd_stim)
    # setupUi

    def retranslateUi(self, widget_dmd_stim):
        widget_dmd_stim.setWindowTitle(QCoreApplication.translate("widget_dmd_stim", u"Form", None))
        self.pushButton_calibrate_dmd.setText(QCoreApplication.translate("widget_dmd_stim", u"Calibrate DMD", None))
        self.pushButton_show_grid.setText(QCoreApplication.translate("widget_dmd_stim", u"Show grid", None))
        self.pushButton_define_axis.setText(QCoreApplication.translate("widget_dmd_stim", u"Define Axis", None))
        self.label_axis_behaviour.setText(QCoreApplication.translate("widget_dmd_stim", u"Patterns:", None))
        self.comboBox_axis_behaviour.setItemText(0, QCoreApplication.translate("widget_dmd_stim", u"Move with image", None))
        self.comboBox_axis_behaviour.setItemText(1, QCoreApplication.translate("widget_dmd_stim", u"Stay fixed", None))

        self.label_file_path.setText(QCoreApplication.translate("widget_dmd_stim", u"Pattern sequence", None))
        self.pushButton_new_file.setText(QCoreApplication.translate("widget_dmd_stim", u"New", None))
        self.pushButton_load_patterns.setText(QCoreApplication.translate("widget_dmd_stim", u"Load", None))
#if QT_CONFIG(shortcut)
        self.pushButton_load_patterns.setShortcut(QCoreApplication.translate("widget_dmd_stim", u"Ctrl+O", None))
#endif // QT_CONFIG(shortcut)
        self.pushButton_save_patterns.setText(QCoreApplication.translate("widget_dmd_stim", u"Save", None))
#if QT_CONFIG(shortcut)
        self.pushButton_save_patterns.setShortcut(QCoreApplication.translate("widget_dmd_stim", u"Ctrl+S", None))
#endif // QT_CONFIG(shortcut)
        self.label_patterns.setText(QCoreApplication.translate("widget_dmd_stim", u"Patterns", None))
        self.pushButton_draw_rectangle.setText(QCoreApplication.translate("widget_dmd_stim", u"Draw rectangle", None))
        self.pushButton_draw_polygon.setText(QCoreApplication.translate("widget_dmd_stim", u"Draw polygon", None))
        self.pushButton_add_pattern.setText(QCoreApplication.translate("widget_dmd_stim", u"Add pattern", None))
        self.pushButton_remove_pattern.setText(QCoreApplication.translate("widget_dmd_stim", u"Delete", None))
        self.label_sequence.setText(QCoreApplication.translate("widget_dmd_stim", u"Sequence", None))
        ___qtablewidgetitem = self.tableWidget.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("widget_dmd_stim", u"Timing (ms)", None));
        ___qtablewidgetitem1 = self.tableWidget.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("widget_dmd_stim", u"Duration (ms)", None));
        ___qtablewidgetitem2 = self.tableWidget.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("widget_dmd_stim", u"Pattern", None));
        self.pushButton_add_row.setText(QCoreApplication.translate("widget_dmd_stim", u"Add row", None))
        self.pushButton_remove_row.setText(QCoreApplication.translate("widget_dmd_stim", u"Remove row", None))
        self.pushButton_3.setText(QCoreApplication.translate("widget_dmd_stim", u"Add series...", None))
        self.pushButton_4.setText(QCoreApplication.translate("widget_dmd_stim", u"Cycle patterns...", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_editor), QCoreApplication.translate("widget_dmd_stim", u"Edit", None))
        self.pushButton_connect_dmd.setText(QCoreApplication.translate("widget_dmd_stim", u"Connect to DMD", None))
        self.pushButton_listen_to_matlab.setText(QCoreApplication.translate("widget_dmd_stim", u"Listen to Matlab", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_run), QCoreApplication.translate("widget_dmd_stim", u"Run", None))
        self.groupBox_console_output.setTitle(QCoreApplication.translate("widget_dmd_stim", u"Console output", None))
        self.pushButton_load_image.setText(QCoreApplication.translate("widget_dmd_stim", u"Load single image", None))
        self.pushButton_reset_image_view.setText(QCoreApplication.translate("widget_dmd_stim", u"Reset image view", None))
        self.label_image_folder.setText(QCoreApplication.translate("widget_dmd_stim", u"Load last image from folder", None))
        self.pushButton_change_folder.setText("")
        self.pushButton_refresh_image.setText("")
    # retranslateUi

