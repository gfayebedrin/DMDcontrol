# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'widget_control_valveDiLQEj.ui'
##
## Created by: Qt User Interface Compiler version 6.8.0
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (
    QCoreApplication,
    QDate,
    QDateTime,
    QLocale,
    QMetaObject,
    QObject,
    QPoint,
    QRect,
    QSize,
    QTime,
    QUrl,
    Qt,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QCursor,
    QFont,
    QFontDatabase,
    QGradient,
    QIcon,
    QImage,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPalette,
    QPixmap,
    QRadialGradient,
    QTransform,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)


class Ui_WidgetControlValve(object):
    def setupUi(self, WidgetControlValve):
        if not WidgetControlValve.objectName():
            WidgetControlValve.setObjectName("WidgetControlValve")
        WidgetControlValve.resize(400, 620)
        self.verticalLayout = QVBoxLayout(WidgetControlValve)
        self.verticalLayout.setObjectName("verticalLayout")
        self.group_box_arduino = QGroupBox(WidgetControlValve)
        self.group_box_arduino.setObjectName("group_box_arduino")
        self.gridLayout_2 = QGridLayout(self.group_box_arduino)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.label_opening_time = QLabel(self.group_box_arduino)
        self.label_opening_time.setObjectName("label_opening_time")

        self.gridLayout_2.addWidget(self.label_opening_time, 1, 0, 1, 1)

        self.spin_box_opening_time = QSpinBox(self.group_box_arduino)
        self.spin_box_opening_time.setObjectName("spin_box_opening_time")
        self.spin_box_opening_time.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTrailing
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.spin_box_opening_time.setMaximum(999999999)

        self.gridLayout_2.addWidget(self.spin_box_opening_time, 1, 1, 1, 1)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.push_button_close_valve = QPushButton(self.group_box_arduino)
        self.push_button_close_valve.setObjectName("push_button_close_valve")
        sizePolicy = QSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
        )
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.push_button_close_valve.sizePolicy().hasHeightForWidth()
        )
        self.push_button_close_valve.setSizePolicy(sizePolicy)

        self.horizontalLayout.addWidget(self.push_button_close_valve)

        self.push_button_open_valve = QPushButton(self.group_box_arduino)
        self.push_button_open_valve.setObjectName("push_button_open_valve")
        sizePolicy.setHeightForWidth(
            self.push_button_open_valve.sizePolicy().hasHeightForWidth()
        )
        self.push_button_open_valve.setSizePolicy(sizePolicy)

        self.horizontalLayout.addWidget(self.push_button_open_valve)

        self.gridLayout_2.addLayout(self.horizontalLayout, 2, 0, 1, 2)

        self.verticalLayout.addWidget(self.group_box_arduino)

        self.group_box_video_projectors = QGroupBox(WidgetControlValve)
        self.group_box_video_projectors.setObjectName("group_box_video_projectors")
        self.gridLayout = QGridLayout(self.group_box_video_projectors)
        self.gridLayout.setObjectName("gridLayout")
        self.combo_box_screen_number = QComboBox(self.group_box_video_projectors)
        self.combo_box_screen_number.setObjectName("combo_box_screen_number")
        self.combo_box_screen_number.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        self.gridLayout.addWidget(self.combo_box_screen_number, 0, 1, 1, 2)

        self.combo_box_color = QComboBox(self.group_box_video_projectors)
        self.combo_box_color.addItem("")
        self.combo_box_color.addItem("")
        self.combo_box_color.addItem("")
        self.combo_box_color.addItem("")
        self.combo_box_color.addItem("")
        self.combo_box_color.addItem("")
        self.combo_box_color.setObjectName("combo_box_color")
        self.combo_box_color.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        self.gridLayout.addWidget(self.combo_box_color, 1, 1, 1, 2)

        self.push_button_update_image = QPushButton(self.group_box_video_projectors)
        self.push_button_update_image.setObjectName("push_button_update_image")

        self.gridLayout.addWidget(self.push_button_update_image, 4, 0, 1, 3)

        self.label_video_time = QLabel(self.group_box_video_projectors)
        self.label_video_time.setObjectName("label_video_time")

        self.gridLayout.addWidget(self.label_video_time, 2, 0, 1, 1)

        self.label_color = QLabel(self.group_box_video_projectors)
        self.label_color.setObjectName("label_color")

        self.gridLayout.addWidget(self.label_color, 1, 0, 1, 1)

        self.label_screen_number = QLabel(self.group_box_video_projectors)
        self.label_screen_number.setObjectName("label_screen_number")

        self.gridLayout.addWidget(self.label_screen_number, 0, 0, 1, 1)

        self.time_edit_video_time = QTimeEdit(self.group_box_video_projectors)
        self.time_edit_video_time.setObjectName("time_edit_video_time")
        self.time_edit_video_time.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTrailing
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.time_edit_video_time.setCurrentSectionIndex(0)

        self.gridLayout.addWidget(self.time_edit_video_time, 2, 1, 1, 2)

        self.label_color_while_waiting = QLabel(self.group_box_video_projectors)
        self.label_color_while_waiting.setObjectName("label_color_while_waiting")

        self.gridLayout.addWidget(self.label_color_while_waiting, 3, 0, 1, 1)

        self.combo_box_color_while_waiting = QComboBox(self.group_box_video_projectors)
        self.combo_box_color_while_waiting.addItem("")
        self.combo_box_color_while_waiting.addItem("")
        self.combo_box_color_while_waiting.addItem("")
        self.combo_box_color_while_waiting.addItem("")
        self.combo_box_color_while_waiting.addItem("")
        self.combo_box_color_while_waiting.addItem("")
        self.combo_box_color_while_waiting.setObjectName(
            "combo_box_color_while_waiting"
        )

        self.gridLayout.addWidget(self.combo_box_color_while_waiting, 3, 1, 1, 2)

        self.verticalLayout.addWidget(self.group_box_video_projectors)

        self.group_box_sequence = QGroupBox(WidgetControlValve)
        self.group_box_sequence.setObjectName("group_box_sequence")
        self.gridLayout_3 = QGridLayout(self.group_box_sequence)
        self.gridLayout_3.setObjectName("gridLayout_3")
        self.label_number_iteration = QLabel(self.group_box_sequence)
        self.label_number_iteration.setObjectName("label_number_iteration")

        self.gridLayout_3.addWidget(self.label_number_iteration, 0, 0, 1, 1)

        self.line = QFrame(self.group_box_sequence)
        self.line.setObjectName("line")
        self.line.setFrameShape(QFrame.Shape.HLine)
        self.line.setFrameShadow(QFrame.Shadow.Sunken)

        self.gridLayout_3.addWidget(self.line, 5, 0, 1, 3)

        self.label_end_time_text = QLabel(self.group_box_sequence)
        self.label_end_time_text.setObjectName("label_end_time_text")

        self.gridLayout_3.addWidget(self.label_end_time_text, 15, 0, 1, 1)

        self.label_init_time = QLabel(self.group_box_sequence)
        self.label_init_time.setObjectName("label_init_time")

        self.gridLayout_3.addWidget(self.label_init_time, 3, 0, 1, 1)

        self.progress_bar = QProgressBar(self.group_box_sequence)
        self.progress_bar.setObjectName("progress_bar")
        self.progress_bar.setValue(0)

        self.gridLayout_3.addWidget(self.progress_bar, 14, 0, 1, 3)

        self.time_edit_init_time = QTimeEdit(self.group_box_sequence)
        self.time_edit_init_time.setObjectName("time_edit_init_time")
        self.time_edit_init_time.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTrailing
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.time_edit_init_time.setCurrentSection(QDateTimeEdit.Section.MinuteSection)
        self.time_edit_init_time.setCurrentSectionIndex(0)

        self.gridLayout_3.addWidget(self.time_edit_init_time, 3, 1, 1, 2)

        self.label_total_time_text = QLabel(self.group_box_sequence)
        self.label_total_time_text.setObjectName("label_total_time_text")

        self.gridLayout_3.addWidget(self.label_total_time_text, 6, 0, 1, 1)

        self.label_end_time_value = QLabel(self.group_box_sequence)
        self.label_end_time_value.setObjectName("label_end_time_value")
        self.label_end_time_value.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTrailing
            | Qt.AlignmentFlag.AlignVCenter
        )

        self.gridLayout_3.addWidget(self.label_end_time_value, 15, 1, 1, 2)

        self.label_total_time_value = QLabel(self.group_box_sequence)
        self.label_total_time_value.setObjectName("label_total_time_value")
        self.label_total_time_value.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTrailing
            | Qt.AlignmentFlag.AlignVCenter
        )

        self.gridLayout_3.addWidget(self.label_total_time_value, 6, 1, 1, 2)

        self.checkbox_record_sequence = QCheckBox(self.group_box_sequence)
        self.checkbox_record_sequence.setObjectName("checkbox_record_sequence")
        self.checkbox_record_sequence.setChecked(True)

        self.gridLayout_3.addWidget(self.checkbox_record_sequence, 10, 0, 1, 1)

        self.label_time_between_opening = QLabel(self.group_box_sequence)
        self.label_time_between_opening.setObjectName("label_time_between_opening")

        self.gridLayout_3.addWidget(self.label_time_between_opening, 1, 0, 1, 1)

        self.spin_box_number_iteration = QSpinBox(self.group_box_sequence)
        self.spin_box_number_iteration.setObjectName("spin_box_number_iteration")
        self.spin_box_number_iteration.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTrailing
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.spin_box_number_iteration.setMaximum(999)
        self.spin_box_number_iteration.setValue(10)

        self.gridLayout_3.addWidget(self.spin_box_number_iteration, 0, 1, 1, 2)

        self.time_edit_between_opening = QTimeEdit(self.group_box_sequence)
        self.time_edit_between_opening.setObjectName("time_edit_between_opening")
        self.time_edit_between_opening.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTrailing
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.time_edit_between_opening.setCurrentSectionIndex(0)

        self.gridLayout_3.addWidget(self.time_edit_between_opening, 1, 1, 1, 2)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.push_button_start_sequence = QPushButton(self.group_box_sequence)
        self.push_button_start_sequence.setObjectName("push_button_start_sequence")

        self.horizontalLayout_2.addWidget(self.push_button_start_sequence)

        self.push_button_stop_sequence = QPushButton(self.group_box_sequence)
        self.push_button_stop_sequence.setObjectName("push_button_stop_sequence")

        self.horizontalLayout_2.addWidget(self.push_button_stop_sequence)

        self.push_button_abort_sequence = QPushButton(self.group_box_sequence)
        self.push_button_abort_sequence.setObjectName("push_button_abort_sequence")

        self.horizontalLayout_2.addWidget(self.push_button_abort_sequence)

        self.gridLayout_3.addLayout(self.horizontalLayout_2, 11, 0, 1, 3)

        self.verticalLayout.addWidget(self.group_box_sequence)

        self.vertical_spacer = QSpacerItem(
            20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )

        self.verticalLayout.addItem(self.vertical_spacer)

        self.retranslateUi(WidgetControlValve)

        QMetaObject.connectSlotsByName(WidgetControlValve)

    # setupUi

    def retranslateUi(self, WidgetControlValve):
        WidgetControlValve.setWindowTitle(
            QCoreApplication.translate("WidgetControlValve", "Form", None)
        )
        self.group_box_arduino.setTitle(
            QCoreApplication.translate("WidgetControlValve", "Arduino", None)
        )
        self.label_opening_time.setText(
            QCoreApplication.translate("WidgetControlValve", "Opening time", None)
        )
        self.spin_box_opening_time.setSuffix(
            QCoreApplication.translate("WidgetControlValve", " ms", None)
        )
        self.push_button_close_valve.setText(
            QCoreApplication.translate("WidgetControlValve", "Close valve", None)
        )
        self.push_button_open_valve.setText(
            QCoreApplication.translate("WidgetControlValve", "Open valve", None)
        )
        self.group_box_video_projectors.setTitle(
            QCoreApplication.translate("WidgetControlValve", "Video projectors", None)
        )
        self.combo_box_color.setItemText(
            0, QCoreApplication.translate("WidgetControlValve", "None", None)
        )
        self.combo_box_color.setItemText(
            1, QCoreApplication.translate("WidgetControlValve", "White", None)
        )
        self.combo_box_color.setItemText(
            2, QCoreApplication.translate("WidgetControlValve", "Black", None)
        )
        self.combo_box_color.setItemText(
            3, QCoreApplication.translate("WidgetControlValve", "Blue", None)
        )
        self.combo_box_color.setItemText(
            4, QCoreApplication.translate("WidgetControlValve", "Red", None)
        )
        self.combo_box_color.setItemText(
            5, QCoreApplication.translate("WidgetControlValve", "Green", None)
        )

        self.push_button_update_image.setText(
            QCoreApplication.translate("WidgetControlValve", "Update image", None)
        )
        self.label_video_time.setText(
            QCoreApplication.translate("WidgetControlValve", "Video time", None)
        )
        self.label_color.setText(
            QCoreApplication.translate("WidgetControlValve", "Color", None)
        )
        self.label_screen_number.setText(
            QCoreApplication.translate("WidgetControlValve", "Screen number", None)
        )
        self.time_edit_video_time.setDisplayFormat(
            QCoreApplication.translate("WidgetControlValve", "mm:ss.zzz", None)
        )
        self.label_color_while_waiting.setText(
            QCoreApplication.translate(
                "WidgetControlValve", "Color while waiting", None
            )
        )
        self.combo_box_color_while_waiting.setItemText(
            0, QCoreApplication.translate("WidgetControlValve", "None", None)
        )
        self.combo_box_color_while_waiting.setItemText(
            1, QCoreApplication.translate("WidgetControlValve", "White", None)
        )
        self.combo_box_color_while_waiting.setItemText(
            2, QCoreApplication.translate("WidgetControlValve", "Black", None)
        )
        self.combo_box_color_while_waiting.setItemText(
            3, QCoreApplication.translate("WidgetControlValve", "Red", None)
        )
        self.combo_box_color_while_waiting.setItemText(
            4, QCoreApplication.translate("WidgetControlValve", "Blue", None)
        )
        self.combo_box_color_while_waiting.setItemText(
            5, QCoreApplication.translate("WidgetControlValve", "Green", None)
        )

        self.group_box_sequence.setTitle(
            QCoreApplication.translate("WidgetControlValve", "Sequence", None)
        )
        self.label_number_iteration.setText(
            QCoreApplication.translate(
                "WidgetControlValve", "Number of iterations", None
            )
        )
        self.label_end_time_text.setText(
            QCoreApplication.translate("WidgetControlValve", "End time", None)
        )
        self.label_init_time.setText(
            QCoreApplication.translate(
                "WidgetControlValve", "Initialization time", None
            )
        )
        self.time_edit_init_time.setDisplayFormat(
            QCoreApplication.translate("WidgetControlValve", "mm:ss.zzz", None)
        )
        self.label_total_time_text.setText(
            QCoreApplication.translate("WidgetControlValve", "Total time", None)
        )
        self.label_end_time_value.setText("")
        self.label_total_time_value.setText("")
        self.checkbox_record_sequence.setText(
            QCoreApplication.translate("WidgetControlValve", "Record Sequence", None)
        )
        self.label_time_between_opening.setText(
            QCoreApplication.translate(
                "WidgetControlValve", "Time between opening", None
            )
        )
        self.time_edit_between_opening.setDisplayFormat(
            QCoreApplication.translate("WidgetControlValve", "mm:ss.zzz", None)
        )
        self.push_button_start_sequence.setText(
            QCoreApplication.translate("WidgetControlValve", "Start", None)
        )
        self.push_button_stop_sequence.setText(
            QCoreApplication.translate("WidgetControlValve", "Stop", None)
        )
        self.push_button_abort_sequence.setText(
            QCoreApplication.translate("WidgetControlValve", "Abort", None)
        )

    # retranslateUi
