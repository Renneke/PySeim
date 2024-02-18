import argparse
import os
import sys

import ltspice
from PyQt5.QtCore import pyqtRemoveInputHook

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from matplotlib.backends.backend_qt5agg import \
    FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import \
    NavigationToolbar2QT as NavigationToolbar
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import QSettings, Qt, QMimeData

from PyQt5.QtGui import QIcon, QDrag
from PyQt5.QtWidgets import (QAction, QApplication, QDialog, QDockWidget,QAbstractItemView,
                             QFileDialog, QHBoxLayout, QListWidgetItem, QLabel, QLineEdit,
                             QListWidget, QMainWindow, QMenu, QPushButton,
                             QVBoxLayout, QWidget)

icon_refresh = os.path.join(os.path.dirname(__file__), "refresh.png")
icon_show = os.path.join(os.path.dirname(__file__), "show.png")
icon = os.path.join(os.path.dirname(__file__), 'icon', 'icon.icns')

__version__ = "0.1.0"
settings = QSettings(os.path.expanduser("~/.pysim.ini"), QSettings.IniFormat)


def get_settings():
    default_kicad_path = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
    if not os.path.isfile(default_kicad_path):
        default_kicad_path = "kicad-cli"

    kicad_path = settings.value("kicad_path", default_kicad_path)
    ngspice_path = settings.value("ngspice_path", "ngspice")

    return kicad_path, ngspice_path


class MyEquationField(QLineEdit):
    def __init__(self, parent):
        super(MyEquationField, self).__init__(parent)

        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("text/plain"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        text = event.mimeData().text()

        # Set the drop action to MoveAction
        event.setDropAction(Qt.MoveAction)

        # Get the cursor position
        cursor_position = self.cursorPosition()

        # Insert the text at the cursor position
        current_text = self.text()
        new_text = current_text[:cursor_position] + text + current_text[cursor_position:]
        self.setText(new_text)


class DraggableListWidget(QListWidget):
    def __init__(self, parent=None):
        super(DraggableListWidget, self).__init__(parent)

        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        mime_data = QMimeData()
        mime_data.setText(item.text())

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec_(Qt.MoveAction)

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super(SettingsDialog, self).__init__(parent)
        self.setWindowTitle("Settings")

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        self.kicad_input = self.createPathInput(
            layout, "KiCad-cli Binary Path:", "Enter the path to the KiCad-cli binary"
        )
        self.ngspice_input = self.createPathInput(
            layout, "Ngspice Binary Path:", "Enter the path to the Ngspice binary"
        )

        self.loadSettings()  # Load settings when initializing the dialog

        save_button = QPushButton("Save", self)
        save_button.clicked.connect(self.savePaths)
        layout.addWidget(save_button)

    def createPathInput(self, layout, label_text, tooltip_text):
        hbox = QHBoxLayout()

        label = QLabel(label_text)
        hbox.addWidget(label)

        path_input = QLineEdit(self)
        path_input.setToolTip(tooltip_text)
        hbox.addWidget(path_input)

        file_button = QPushButton("Browse", self)
        file_button.clicked.connect(lambda: self.openFileDialog(path_input))
        hbox.addWidget(file_button)

        layout.addLayout(hbox)
        return path_input

    def openFileDialog(self, path_input):
        file_dialog = QFileDialog(self)
        file_path, _ = file_dialog.getOpenFileName(self, "Select File")
        if file_path:
            path_input.setText(file_path)

    def savePaths(self):
        kicad_path = self.kicad_input.text()
        ngspice_path = self.ngspice_input.text()

        settings.setValue("kicad_path", kicad_path)
        settings.setValue("ngspice_path", ngspice_path)

        self.accept()

    def loadSettings(self):
        kicad_path, ngspice_path = get_settings()
        self.kicad_input.setText(kicad_path)
        self.ngspice_input.setText(ngspice_path)


class CustomToolbar(NavigationToolbar):
    def __init__(self, canvas, parent):
        super().__init__(canvas, parent)

        self.setIconSize(QtCore.QSize(24, 24))
        self.layout().setSpacing(12)

        # Add your custom icon
        self.refresh_button_action = self.create_action(icon_refresh, "Resimulate")
        self.addAction(self.refresh_button_action)
        self.show_button_action = self.create_action(icon_show, "Show Netlist")
        self.addAction(self.show_button_action)

    def create_action(self, icon_path, tooltip):
        action = QAction(self)
        action.setIcon(QIcon(icon_path))
        action.setToolTip(tooltip)
        return action


class MyWindow(QMainWindow):
    def __init__(self, file_path: str):
        super().__init__()
        self.current_display = []
        self.file_path = file_path
        self.initUI()

    def show_netlist(self):
        kicad_path, _ = get_settings()

        os.system(f"{kicad_path} sch export netlist  --output tmp.cir --format spice {self.file_path} && open tmp.cir&")

    def refresh_sim(self):
        kicad_path, ngspice_path = get_settings()
        os.system(
            f"{kicad_path} sch export netlist  --output tmp.cir --format spice {self.file_path} && {ngspice_path} -b tmp.cir  "
        )

        self.l = ltspice.Ltspice("rawspice.raw")
        self.l.parse()  # Data loading sequence. It may take few minutes for huge file.

        self.time = self.l.get_time()

        self.list_widget.clear()
        for sig in self.l.variables:
            if sig == "time":
                continue
            item = QListWidgetItem(sig)
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled)
            self.list_widget.addItem(item)

        self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)

        self.updateCanvas()

    def initUI(self):

        # Create a menu bar
        menubar = self.menuBar()
        fileMenu = menubar.addMenu("File")

        # Create actions for the menu
        settingsAction = QAction("Settings", self)
        settingsAction.triggered.connect(self.showSettingsDialog)
        fileMenu.addAction(settingsAction)

        exitAction = QAction("Exit", self)
        exitAction.triggered.connect(self.close)
        fileMenu.addAction(exitAction)

        fileMenu = menubar.addMenu("File")

        openFile = QAction("Open", self)
        openFile.setShortcut("Ctrl+O")
        openFile.triggered.connect(self.showDialog)
        fileMenu.addAction(openFile)

        # Create a central widget
        central_widget = QWidget(self)

        # Create layouts
        main_layout = QVBoxLayout()
        list_layout = QHBoxLayout()
        input_layout = QHBoxLayout()

        # Create a QListWidget on the left side
        self.list_widget = DraggableListWidget(self)

        # Connect double-click event to custom slot
        self.list_widget.itemDoubleClicked.connect(self.handleItemDoubleClick)
        self.list_widget.itemClicked.connect(self.on_item_clicked)

        # Connect right-click event to custom slot
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.showContextMenu)

        list_layout.addWidget(self.list_widget)

        # Create a Matplotlib figure and canvas
        center_layout = QVBoxLayout()
        self.fig, self.ax = plt.subplots()


        # Shrink current axis by 20%
        box = self.ax.get_position()
        self.ax.set_position([box.x0, box.y0, box.width * 0.8, box.height])

        self.canvas = FigureCanvas(self.fig)
        self.toolbar = CustomToolbar(self.canvas, self)

        self.toolbar.refresh_button_action.triggered.connect(self.refresh_sim)
        self.toolbar.show_button_action.triggered.connect(self.show_netlist)

        center_layout.addWidget(self.toolbar)
        center_layout.addWidget(self.canvas)
        main_central_widget = QWidget(self)
        main_central_widget.setLayout(center_layout)
        self.setCentralWidget(main_central_widget)

        # Create a QLineEdit and QPushButton for adding new items
        self.add_item_textbox = MyEquationField(self)

        add_button = QPushButton("Add", self)
        add_button.clicked.connect(self.addItemToList)

        # Add the QLineEdit and QPushButton to the input layout
        input_layout.addWidget(self.add_item_textbox)
        input_layout.addWidget(add_button)

        # Add the layouts to the main layout
        main_layout.addLayout(list_layout)
        main_layout.addLayout(input_layout)

        # Set the central widget layout
        central_widget.setLayout(main_layout)

        # Create a QDockWidget and set the central widget
        dock_widget = QDockWidget("List and Input", self)
        dock_widget.setWidget(central_widget)

        # Add the dock widget to the main window
        self.addDockWidget(Qt.LeftDockWidgetArea, dock_widget)

        self.setGeometry(100, 100, 800, 400)

        self.update_title()

    def on_item_clicked(self, item):
        self.add_item_textbox.setText(item.text())

    def showDialog(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Open file", "", "KiCad Files (*.kicad_sch);;All Files (*)")

        if fname:
            # Process the selected file (fname) as needed
            print(f"Selected file: {fname}")
            self.file_path = fname
            self.update_title()
            self.list_widget.clear()
            self.ax.clear()

    def update_title(self):
        self.setWindowTitle(f"PySim {__version__} - {self.file_path}")

    def showSettingsDialog(self):
        settings_dialog = SettingsDialog(self)
        settings_dialog.exec_()

    def saveBinaryPath(self, path, dialog):
        # Save the binary path and update the label
        self.binary_path_label.setText(f"Binary Path: {path}")
        dialog.close()

    def handleItemDoubleClick(self, item):
        # Clear previous plot
        self.ax.clear()
        self.current_display.clear()
        self.ax.grid(True)
        selected_item_text = item.text()
        self.updatePlot(selected_item_text)

    def showContextMenu(self, pos):
        context_menu = QMenu(self)

        # Add action to the context menu
        add_to_plot_action = QAction("Add to Plot", self)
        add_to_plot_action.triggered.connect(self.addToPlot)
        context_menu.addAction(add_to_plot_action)

        # Show the context menu at the specified position
        context_menu.exec_(self.list_widget.mapToGlobal(pos))

    def addToPlot(self):
        selected_items = self.list_widget.selectedItems()
        for item in selected_items:
            item_text = item.text()
            self.updatePlot(item_text)

    def addItemToList(self):
        new_item_text = self.add_item_textbox.text()
        if new_item_text:
            self.list_widget.addItem(new_item_text)
            self.add_item_textbox.clear()

    def add_plot_for(self, time, data, label:str):
        self.ax.plot(time, data, label=label)
        self.ax.xaxis.set_major_formatter(FuncFormatter(self.format_xaxis_time))

    def format_xaxis_time(self, value, _):
        """
        Custom formatter function for x-axis labels based on time range.
        """
        if value >= 1e3:
            return f'{value / 1e3:.1f} s'
        elif value >= 1e-3:
            return f'{value / 1e-3:.1f} ms'
        elif value >= 1e-6:
            return f'{value / 1e-6:.1f} µs'
        else:
            return f'{value / 1e-9:.1f} ns'

    def encode(self, item_text):
        for i, var in enumerate(self.l.variables):
            item_text = item_text.replace(var, f"var_{i}")
        return item_text

    def apply_equation(self, equation):

        data = {}
        for i, var in enumerate(self.l.variables):
            data[f"var_{i}"] = self.l.get_data(var)

        output = []
        for i, _ in enumerate(self.time):
            data_for_t = {v: data[i] for v, data in data.items()}
            output.append(eval(equation, data_for_t))
        return output



    def get_data(self, item_text:str):
        answ = self.l.get_data(item_text)
        if answ is None:
            equation = self.encode(item_text)
            return self.apply_equation(equation)
        return answ

    def updateCanvas(self):

        self.ax.clear()

        # Update the Matplotlib diagram based on the selected item
        for item_text in self.current_display:
            self.add_plot_for(self.time, self.get_data(item_text), label=item_text)

        self.ax.grid(True)

        self.ax.legend()

        # Redraw the canvas
        self.canvas.draw()

    def updatePlot(self, item_text):

        # Update the Matplotlib diagram based on the selected item
        self.current_display.append(item_text)

        self.ax.grid(True)
        self.add_plot_for(self.time, self.get_data(item_text), label=item_text)

        # Put a legend to the right of the current axis
        self.ax.legend(loc="center left", bbox_to_anchor=(1, 0.5))

        # Redraw the canvas
        self.canvas.draw()


def main(argv=sys.argv):


    parser = argparse.ArgumentParser(description="PySim")
    parser.add_argument("file_path", nargs="?", default=None, help="Path to a *.kicad_sch file")
    args = parser.parse_args(argv[1:])

    app = QApplication(argv)
    pyqtRemoveInputHook()

    app.setWindowIcon(QIcon(icon))
    window = MyWindow(args.file_path)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
