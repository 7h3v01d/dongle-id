#!/usr/bin/env python3
"""
DONGLE-ID :: USB Dongle Registration & Identification Console
================================================================
Reads real USB HID descriptors (Vendor ID, Product ID, Serial Number,
Manufacturer/Product strings) to fingerprint physical dongles, lets you
register what each one is for, and then tells you instantly what an
unknown dongle does the moment you plug it in.

Requires:
    pip install PyQt6 hidapi

Notes on permissions:
    - Linux: you may need a udev rule granting your user access to hidraw
      devices (run `sudo usermod -aG plugdev $USER` on many distros, or add
      a udev rule for the specific device class), otherwise devices may show
      up with blank serial/manufacturer strings or fail to enumerate.
    - Windows/macOS: should work out of the box via hidapi.

Data is stored at ~/.dongle_id/catalogue.json
"""

import sys
import os
import json
import time
from datetime import datetime

try:
    import hid
except ImportError:
    print("Missing dependency: pip install hidapi")
    sys.exit(1)

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
    QLineEdit, QTextEdit, QComboBox, QDialog, QFormLayout, QMessageBox,
    QHeaderView, QFrame, QAbstractItemView, QFileDialog, QMenuBar,
)

# ----------------------------------------------------------------------
# Storage
# ----------------------------------------------------------------------

DATA_DIR = os.path.join(os.path.expanduser("~"), ".dongle_id")
DATA_FILE = os.path.join(DATA_DIR, "catalogue.json")
EXPORT_FORMAT_VERSION = 1

CATEGORIES = [
    "Mouse Receiver", "Keyboard Receiver", "Combo Receiver",
    "Headset / Audio Dongle", "Bluetooth Adapter", "Wi-Fi Adapter",
    "Game Controller Receiver", "Security Key / 2FA", "Storage",
    "Other",
]


def fingerprint(vid, pid, serial):
    """Build a stable identity key for a physical device."""
    serial = (serial or "").strip()
    if serial:
        return f"{vid:04x}:{pid:04x}:{serial}"
    return f"{vid:04x}:{pid:04x}:NOSERIAL"


class Catalogue:
    def __init__(self):
        self.records = {}
        self._load()

    def _load(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r") as f:
                    self.records = json.load(f)
            except Exception:
                self.records = {}

    def save(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(DATA_FILE, "w") as f:
            json.dump(self.records, f, indent=2)

    def get(self, fp):
        return self.records.get(fp)

    def register(self, fp, name, category, notes, raw_info):
        now = datetime.now().isoformat(timespec="seconds")
        existing = self.records.get(fp, {})
        self.records[fp] = {
            "name": name,
            "category": category,
            "notes": notes,
            "vendor_id": raw_info["vendor_id"],
            "product_id": raw_info["product_id"],
            "serial_number": raw_info.get("serial_number", ""),
            "manufacturer": raw_info.get("manufacturer_string", ""),
            "product": raw_info.get("product_string", ""),
            "date_added": existing.get("date_added", now),
            "date_updated": now,
            "times_seen": existing.get("times_seen", 0),
            "last_seen": existing.get("last_seen", ""),
        }
        self.save()

    def delete(self, fp):
        if fp in self.records:
            del self.records[fp]
            self.save()

    def mark_seen(self, fp):
        if fp in self.records:
            self.records[fp]["times_seen"] = self.records[fp].get("times_seen", 0) + 1
            self.records[fp]["last_seen"] = datetime.now().isoformat(timespec="seconds")
            self.save()

    # -- Portability ---------------------------------------------------

    def export_dict(self):
        """Wrapped, self-describing export format — portable between machines."""
        return {
            "app": "DONGLE-ID",
            "format_version": EXPORT_FORMAT_VERSION,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "entry_count": len(self.records),
            "entries": self.records,
        }

    @staticmethod
    def parse_import_file(path):
        """
        Accepts either the wrapped export format or a bare {fp: record}
        dict (e.g. an older export, or someone's hand-built file).
        Returns the raw records dict. Raises ValueError on bad input.
        """
        with open(path, "r") as f:
            data = json.load(f)

        if isinstance(data, dict) and "entries" in data and isinstance(data["entries"], dict):
            records = data["entries"]
        elif isinstance(data, dict):
            records = data
        else:
            raise ValueError("File does not look like a DONGLE-ID catalogue export.")

        # sanity-check shape of a few entries
        for fp, rec in list(records.items())[:5]:
            if not isinstance(rec, dict) or "vendor_id" not in rec or "name" not in rec:
                raise ValueError(f"Entry '{fp}' is missing expected fields (name, vendor_id, …).")

        return records

    def merge(self, incoming_records, overwrite_conflicts):
        """
        Merge incoming records into this catalogue.
        Returns (added_count, updated_count, skipped_count).
        """
        added = updated = skipped = 0
        for fp, rec in incoming_records.items():
            if fp in self.records:
                if overwrite_conflicts:
                    self.records[fp] = rec
                    updated += 1
                else:
                    skipped += 1
            else:
                self.records[fp] = rec
                added += 1
        self.save()
        return added, updated, skipped


# ----------------------------------------------------------------------
# USB / HID scanning
# ----------------------------------------------------------------------

def scan_devices():
    """
    Returns dict: fingerprint -> aggregated device info
    Multiple HID interfaces belonging to the same physical dongle
    (same vid/pid/serial) are merged into one entry.
    """
    devices = {}
    try:
        raw = hid.enumerate()
    except Exception:
        raw = []

    for d in raw:
        vid = d.get("vendor_id", 0)
        pid = d.get("product_id", 0)
        serial = d.get("serial_number", "") or ""
        fp = fingerprint(vid, pid, serial)

        if fp not in devices:
            devices[fp] = {
                "vendor_id": vid,
                "product_id": pid,
                "serial_number": serial,
                "manufacturer_string": d.get("manufacturer_string", "") or "",
                "product_string": d.get("product_string", "") or "",
                "interfaces": 0,
            }
        entry = devices[fp]
        # Fill in strings if missing on the merged entry but present here
        if not entry["manufacturer_string"] and d.get("manufacturer_string"):
            entry["manufacturer_string"] = d.get("manufacturer_string")
        if not entry["product_string"] and d.get("product_string"):
            entry["product_string"] = d.get("product_string")
        entry["interfaces"] += 1

    return devices


# ----------------------------------------------------------------------
# Styling — dark industrial
# ----------------------------------------------------------------------

QSS = """
QWidget {
    background-color: #1a1a1a;
    color: #d4d0c8;
    font-family: Consolas, 'DejaVu Sans Mono', monospace;
    font-size: 13px;
}
QMainWindow {
    background-color: #161616;
}
QLabel#Header {
    color: #ff9500;
    font-size: 20px;
    font-weight: bold;
    letter-spacing: 3px;
    padding: 10px 4px;
}
QLabel#SubHeader {
    color: #7d7a72;
    font-size: 11px;
    letter-spacing: 2px;
    padding-bottom: 6px;
}
QFrame#Panel {
    background-color: #212121;
    border: 1px solid #3a3a3a;
    border-radius: 2px;
}
QFrame#StatusPanel {
    background-color: #202020;
    border: 2px solid #3a3a3a;
    border-radius: 3px;
}
QLabel#StatusTitle {
    font-size: 13px;
    color: #8a8578;
    letter-spacing: 2px;
}
QLabel#StatusBig {
    font-size: 22px;
    font-weight: bold;
    padding: 6px 0px;
}
QTabWidget::pane {
    border: 1px solid #3a3a3a;
    background-color: #1a1a1a;
    top: -1px;
}
QTabBar::tab {
    background-color: #232323;
    color: #8a8578;
    padding: 8px 18px;
    border: 1px solid #3a3a3a;
    border-bottom: none;
    letter-spacing: 2px;
    font-weight: bold;
}
QTabBar::tab:selected {
    background-color: #1a1a1a;
    color: #ff9500;
    border-bottom: 2px solid #ff9500;
}
QTabBar::tab:hover {
    color: #ffb64d;
}
QTableWidget {
    background-color: #1e1e1e;
    alternate-background-color: #232323;
    gridline-color: #333333;
    border: 1px solid #3a3a3a;
    selection-background-color: #3a2a10;
    selection-color: #ff9500;
}
QHeaderView::section {
    background-color: #2a2a2a;
    color: #ff9500;
    padding: 6px;
    border: none;
    border-right: 1px solid #3a3a3a;
    font-weight: bold;
    letter-spacing: 1px;
}
QPushButton {
    background-color: #2a2a2a;
    color: #d4d0c8;
    border: 1px solid #4a4a4a;
    border-radius: 2px;
    padding: 8px 16px;
    font-weight: bold;
    letter-spacing: 1px;
}
QPushButton:hover {
    background-color: #333333;
    border: 1px solid #ff9500;
    color: #ff9500;
}
QPushButton:pressed {
    background-color: #1a1a1a;
}
QPushButton#Primary {
    background-color: #3a2a10;
    border: 1px solid #ff9500;
    color: #ff9500;
}
QPushButton#Primary:hover {
    background-color: #4a3410;
}
QPushButton#Danger {
    border: 1px solid #a83232;
    color: #d97070;
}
QPushButton#Danger:hover {
    background-color: #2a1414;
}
QLineEdit, QTextEdit, QComboBox {
    background-color: #161616;
    border: 1px solid #3a3a3a;
    border-radius: 2px;
    padding: 6px;
    color: #d4d0c8;
    selection-background-color: #ff9500;
    selection-color: #1a1a1a;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 1px solid #ff9500;
}
QComboBox QAbstractItemView {
    background-color: #1e1e1e;
    color: #d4d0c8;
    selection-background-color: #3a2a10;
    selection-color: #ff9500;
}
QScrollBar:vertical {
    background: #1a1a1a;
    width: 12px;
}
QScrollBar::handle:vertical {
    background: #3a3a3a;
    min-height: 20px;
    border-radius: 2px;
}
QScrollBar::handle:vertical:hover {
    background: #ff9500;
}
QMenuBar {
    background-color: #1a1a1a;
    color: #d4d0c8;
}
QMenuBar::item:selected {
    background-color: #2a2a2a;
    color: #ff9500;
}
QMenu {
    background-color: #1e1e1e;
    color: #d4d0c8;
    border: 1px solid #3a3a3a;
}
QMenu::item:selected {
    background-color: #3a2a10;
    color: #ff9500;
}
"""


def led(color):
    lab = QLabel()
    lab.setFixedSize(12, 12)
    lab.setStyleSheet(
        f"background-color: {color}; border-radius: 6px; border: 1px solid #000;"
    )
    return lab


# ----------------------------------------------------------------------
# Register / Edit dialog
# ----------------------------------------------------------------------

class RegisterDialog(QDialog):
    def __init__(self, parent, fp, info, existing=None):
        super().__init__(parent)
        self.fp = fp
        self.info = info
        self.setWindowTitle("REGISTER DONGLE")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)

        id_text = (
            f"VID:PID   {info['vendor_id']:04x}:{info['product_id']:04x}\n"
            f"SERIAL    {info.get('serial_number') or '(none reported)'}\n"
            f"MFR       {info.get('manufacturer_string') or '(unknown)'}\n"
            f"PRODUCT   {info.get('product_string') or '(unknown)'}"
        )
        id_label = QLabel(id_text)
        id_label.setStyleSheet(
            "color:#8a8578; background-color:#161616; border:1px solid #3a3a3a;"
            "padding:8px; font-family: Consolas, monospace;"
        )
        layout.addWidget(id_label)

        form = QFormLayout()
        self.name_edit = QLineEdit(existing.get("name", "") if existing else "")
        self.name_edit.setPlaceholderText("e.g. Logitech MX Master 3S Receiver")
        form.addRow("NAME", self.name_edit)

        self.cat_combo = QComboBox()
        self.cat_combo.addItems(CATEGORIES)
        if existing and existing.get("category") in CATEGORIES:
            self.cat_combo.setCurrentText(existing["category"])
        form.addRow("CATEGORY", self.cat_combo)

        self.notes_edit = QTextEdit(existing.get("notes", "") if existing else "")
        self.notes_edit.setPlaceholderText("optional notes, e.g. 'desk PC, black mouse'")
        self.notes_edit.setFixedHeight(70)
        form.addRow("NOTES", self.notes_edit)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("SAVE")
        save_btn.setObjectName("Primary")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("CANCEL")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def result_data(self):
        return (
            self.name_edit.text().strip() or "Unnamed dongle",
            self.cat_combo.currentText(),
            self.notes_edit.toPlainText().strip(),
        )


class AddEntryDialog(QDialog):
    """
    Lets you start a new catalogue entry either by picking one of the
    currently-connected unregistered devices, or by typing in a VID/PID
    (and optional serial) manually — useful for pre-cataloguing a dongle
    that isn't plugged in right now.
    """
    MANUAL_LABEL = "— Manual entry (type VID/PID) —"

    def __init__(self, parent, unknown_devices):
        super().__init__(parent)
        self.setWindowTitle("ADD CATALOGUE ENTRY")
        self.setMinimumWidth(440)
        self.unknown_devices = unknown_devices  # dict fp -> info

        layout = QVBoxLayout(self)

        hint = QLabel(
            "Pick a currently plugged-in unregistered dongle, or enter its "
            "VID/PID manually if it isn't connected right now."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a8578;")
        layout.addWidget(hint)

        form = QFormLayout()

        self.device_combo = QComboBox()
        self.device_combo.addItem(self.MANUAL_LABEL, userData=None)
        for fp, info in unknown_devices.items():
            label = (
                f"{info.get('product_string') or 'Unknown product'}  "
                f"[{info['vendor_id']:04x}:{info['product_id']:04x}]"
            )
            self.device_combo.addItem(label, userData=fp)
        form.addRow("CONNECTED DEVICE", self.device_combo)

        self.vid_edit = QLineEdit()
        self.vid_edit.setPlaceholderText("e.g. 046d")
        self.pid_edit = QLineEdit()
        self.pid_edit.setPlaceholderText("e.g. c52b")
        self.serial_edit = QLineEdit()
        self.serial_edit.setPlaceholderText("optional")
        form.addRow("VENDOR ID (hex)", self.vid_edit)
        form.addRow("PRODUCT ID (hex)", self.pid_edit)
        form.addRow("SERIAL (optional)", self.serial_edit)

        layout.addLayout(form)

        self.device_combo.currentIndexChanged.connect(self._on_combo_change)
        self._on_combo_change()

        btn_row = QHBoxLayout()
        next_btn = QPushButton("NEXT →")
        next_btn.setObjectName("Primary")
        next_btn.clicked.connect(self._on_next)
        cancel_btn = QPushButton("CANCEL")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(next_btn)
        layout.addLayout(btn_row)

        self._result_fp = None
        self._result_info = None

    def _on_combo_change(self):
        fp = self.device_combo.currentData()
        manual = fp is None
        self.vid_edit.setEnabled(manual)
        self.pid_edit.setEnabled(manual)
        self.serial_edit.setEnabled(manual)
        if not manual:
            info = self.unknown_devices[fp]
            self.vid_edit.setText(f"{info['vendor_id']:04x}")
            self.pid_edit.setText(f"{info['product_id']:04x}")
            self.serial_edit.setText(info.get("serial_number", ""))

    def _on_next(self):
        fp = self.device_combo.currentData()
        if fp is not None:
            self._result_fp = fp
            self._result_info = self.unknown_devices[fp]
            self.accept()
            return

        vid_text = self.vid_edit.text().strip()
        pid_text = self.pid_edit.text().strip()
        try:
            vid = int(vid_text, 16)
            pid = int(pid_text, 16)
        except ValueError:
            QMessageBox.warning(
                self, "Invalid input",
                "Vendor ID and Product ID must be hex values, e.g. 046d and c52b."
            )
            return

        serial = self.serial_edit.text().strip()
        info = {
            "vendor_id": vid,
            "product_id": pid,
            "serial_number": serial,
            "manufacturer_string": "",
            "product_string": "",
        }
        self._result_fp = fingerprint(vid, pid, serial)
        self._result_info = info
        self.accept()

    def result_data(self):
        return self._result_fp, self._result_info


# ----------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DONGLE-ID // USB Identification Console")
        self.resize(980, 640)

        self.catalogue = Catalogue()
        self.previous_snapshot = set()
        self.current_devices = {}

        self._build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(1200)
        self.poll(initial=True)

    # -- UI construction --------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 16)

        header = QLabel("DONGLE-ID")
        header.setObjectName("Header")
        sub = QLabel("USB DEVICE REGISTRATION & IDENTIFICATION CONSOLE")
        sub.setObjectName("SubHeader")
        root.addWidget(header)
        root.addWidget(sub)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        self.tabs.addTab(self._build_monitor_tab(), "MONITOR")
        self.tabs.addTab(self._build_catalogue_tab(), "CATALOGUE")

        # Menu
        menubar = self.menuBar()
        file_menu = menubar.addMenu("FILE")
        export_action = file_menu.addAction("Export catalogue…")
        export_action.triggered.connect(self.export_catalogue)
        import_action = file_menu.addAction("Import catalogue…")
        import_action.triggered.connect(self.import_catalogue)
        file_menu.addSeparator()
        quit_action = file_menu.addAction("Quit")
        quit_action.triggered.connect(self.close)

    def _build_monitor_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        # Status panel
        self.status_panel = QFrame()
        self.status_panel.setObjectName("StatusPanel")
        sp_layout = QVBoxLayout(self.status_panel)

        top_row = QHBoxLayout()
        self.status_led = led("#3a3a3a")
        self.status_title = QLabel("STANDBY — WAITING FOR DEVICE EVENT")
        self.status_title.setObjectName("StatusTitle")
        top_row.addWidget(self.status_led)
        top_row.addWidget(self.status_title)
        top_row.addStretch()
        sp_layout.addLayout(top_row)

        self.status_big = QLabel("Plug in a dongle to identify it.")
        self.status_big.setObjectName("StatusBig")
        self.status_big.setStyleSheet("color:#8a8578;")
        sp_layout.addWidget(self.status_big)

        self.status_detail = QLabel("")
        self.status_detail.setStyleSheet("color:#6f6b60;")
        sp_layout.addWidget(self.status_detail)

        action_row = QHBoxLayout()
        self.register_btn = QPushButton("REGISTER THIS DEVICE")
        self.register_btn.setObjectName("Primary")
        self.register_btn.setVisible(False)
        self.register_btn.clicked.connect(self.register_pending)
        action_row.addWidget(self.register_btn)
        action_row.addStretch()
        sp_layout.addLayout(action_row)

        layout.addWidget(self.status_panel)

        # Live device table
        live_label = QLabel("CURRENTLY CONNECTED")
        live_label.setStyleSheet("color:#8a8578; letter-spacing:2px; padding-top:8px;")
        layout.addWidget(live_label)

        self.live_table = QTableWidget(0, 7)
        self.live_table.setHorizontalHeaderLabels(
            ["STATUS", "NAME", "CATEGORY", "VID:PID", "SERIAL",
             "DESCRIPTOR STRINGS", "ACTION"]
        )
        self._style_table(self.live_table)
        self.live_table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeMode.ResizeToContents
        )
        layout.addWidget(self.live_table)

        self._pending_fp = None
        self._pending_info = None

        return w

    def _build_catalogue_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter by name, category, or notes…")
        self.search_edit.textChanged.connect(self.refresh_catalogue_table)
        search_row.addWidget(self.search_edit)
        layout.addLayout(search_row)

        self.cat_table = QTableWidget(0, 8)
        self.cat_table.setHorizontalHeaderLabels(
            ["NAME", "CATEGORY", "VID:PID", "SERIAL", "TIMES SEEN",
             "LAST SEEN", "ADDED", "NOTES"]
        )
        self._style_table(self.cat_table)
        self.cat_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.cat_table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ ADD NEW ENTRY")
        add_btn.setObjectName("Primary")
        add_btn.clicked.connect(self.add_new_entry)
        edit_btn = QPushButton("EDIT SELECTED")
        edit_btn.clicked.connect(self.edit_selected)
        del_btn = QPushButton("DELETE SELECTED")
        del_btn.setObjectName("Danger")
        del_btn.clicked.connect(self.delete_selected)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()

        export_btn = QPushButton("⇩ EXPORT CATALOGUE")
        export_btn.clicked.connect(self.export_catalogue)
        import_btn = QPushButton("⇧ IMPORT CATALOGUE")
        import_btn.clicked.connect(self.import_catalogue)
        btn_row.addWidget(export_btn)
        btn_row.addWidget(import_btn)
        layout.addLayout(btn_row)

        self.refresh_catalogue_table()
        return w

    def _style_table(self, table):
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

    # -- Polling / detection ------------------------------------------

    def poll(self, initial=False):
        try:
            devices = scan_devices()
        except Exception as e:
            self.status_detail.setText(f"Scan error: {e}")
            return

        current_fps = set(devices.keys())
        new_fps = current_fps - self.previous_snapshot

        self.current_devices = devices
        self.refresh_live_table()

        if initial and len(current_fps) == 1:
            fp = next(iter(current_fps))
            self.handle_new_device(fp, devices[fp])
        elif not initial and len(new_fps) == 1:
            fp = next(iter(new_fps))
            self.handle_new_device(fp, devices[fp])
        elif not initial and len(new_fps) > 1:
            self.status_led.setStyleSheet(
                "background-color:#ff9500; border-radius:6px; border:1px solid #000;"
            )
            self.status_title.setText("MULTIPLE NEW DEVICES DETECTED")
            self.status_big.setText("Plug dongles in one at a time for reliable ID.")
            self.status_big.setStyleSheet("color:#ff9500;")
            self.status_detail.setText("")
            self.register_btn.setVisible(False)

        self.previous_snapshot = current_fps

    def handle_new_device(self, fp, info):
        record = self.catalogue.get(fp)
        if record:
            self.catalogue.mark_seen(fp)
            self.status_led.setStyleSheet(
                "background-color:#4caf50; border-radius:6px; border:1px solid #000;"
            )
            self.status_title.setText("DEVICE IDENTIFIED")
            self.status_big.setText(f"➜  {record['name']}")
            self.status_big.setStyleSheet("color:#4caf50;")
            self.status_detail.setText(
                f"Category: {record['category']}   |   "
                f"Notes: {record.get('notes') or '—'}   |   "
                f"Seen {record.get('times_seen', 0)} times"
            )
            self.register_btn.setVisible(False)
            self.refresh_catalogue_table()
        else:
            self.status_led.setStyleSheet(
                "background-color:#d97070; border-radius:6px; border:1px solid #000;"
            )
            self.status_title.setText("UNKNOWN DEVICE — NOT IN CATALOGUE")
            self.status_big.setText(
                f"Unregistered dongle: {info.get('product_string') or info['vendor_id']}"
            )
            self.status_big.setStyleSheet("color:#d97070;")
            self.status_detail.setText(
                f"VID:PID {info['vendor_id']:04x}:{info['product_id']:04x}   "
                f"Serial: {info.get('serial_number') or '(none)'}"
            )
            self._pending_fp = fp
            self._pending_info = info
            self.register_btn.setVisible(True)
        self.refresh_live_table()

    def register_pending(self):
        if not self._pending_fp:
            return
        dlg = RegisterDialog(self, self._pending_fp, self._pending_info)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, category, notes = dlg.result_data()
            self.catalogue.register(self._pending_fp, name, category, notes, self._pending_info)
            self.catalogue.mark_seen(self._pending_fp)
            self.handle_new_device(self._pending_fp, self._pending_info)
            self.refresh_catalogue_table()

    # -- Table rendering ------------------------------------------------

    def refresh_live_table(self):
        self.live_table.setRowCount(0)
        for fp, info in sorted(self.current_devices.items(), key=lambda kv: kv[1]["vendor_id"]):
            record = self.catalogue.get(fp)
            row = self.live_table.rowCount()
            self.live_table.insertRow(row)

            status_item = QTableWidgetItem("KNOWN" if record else "UNKNOWN")
            status_item.setForeground(QColor("#4caf50" if record else "#d97070"))
            self.live_table.setItem(row, 0, status_item)

            name = record["name"] if record else "—"
            category = record["category"] if record else "—"
            vidpid = f"{info['vendor_id']:04x}:{info['product_id']:04x}"
            serial = info.get("serial_number") or "—"
            desc = f"{info.get('manufacturer_string','')} {info.get('product_string','')}".strip() or "—"

            self.live_table.setItem(row, 1, QTableWidgetItem(name))
            self.live_table.setItem(row, 2, QTableWidgetItem(category))
            self.live_table.setItem(row, 3, QTableWidgetItem(vidpid))
            self.live_table.setItem(row, 4, QTableWidgetItem(serial))
            self.live_table.setItem(row, 5, QTableWidgetItem(desc))

            action_btn = QPushButton("EDIT" if record else "REGISTER")
            if not record:
                action_btn.setObjectName("Primary")
            action_btn.clicked.connect(
                lambda _checked, fp=fp, info=info, record=record: self._row_action(fp, info, record)
            )
            self.live_table.setCellWidget(row, 6, action_btn)

    def _row_action(self, fp, info, record):
        if record:
            fake_info = {
                "vendor_id": record["vendor_id"], "product_id": record["product_id"],
                "serial_number": record.get("serial_number", ""),
                "manufacturer_string": record.get("manufacturer", ""),
                "product_string": record.get("product", ""),
            }
            dlg = RegisterDialog(self, fp, fake_info, existing=record)
        else:
            dlg = RegisterDialog(self, fp, info)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, category, notes = dlg.result_data()
            self.catalogue.register(fp, name, category, notes, info)
            self.catalogue.mark_seen(fp)
            self.refresh_catalogue_table()
            self.refresh_live_table()
            if fp == self._pending_fp:
                self.register_btn.setVisible(False)

    def refresh_catalogue_table(self):
        filt = self.search_edit.text().lower().strip() if hasattr(self, "search_edit") else ""
        self.cat_table.setRowCount(0)
        for fp, rec in sorted(self.catalogue.records.items(), key=lambda kv: kv[1]["name"].lower()):
            blob = f"{rec['name']} {rec['category']} {rec.get('notes','')}".lower()
            if filt and filt not in blob:
                continue
            row = self.cat_table.rowCount()
            self.cat_table.insertRow(row)
            vidpid = f"{rec['vendor_id']:04x}:{rec['product_id']:04x}"
            vals = [
                rec["name"], rec["category"], vidpid,
                rec.get("serial_number") or "—",
                str(rec.get("times_seen", 0)),
                rec.get("last_seen", "") or "—",
                rec.get("date_added", "") or "—",
                rec.get("notes", "") or "",
            ]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setData(Qt.ItemDataRole.UserRole, fp)
                self.cat_table.setItem(row, col, item)

    # -- Catalogue actions ------------------------------------------------

    def _selected_fp(self):
        row = self.cat_table.currentRow()
        if row < 0:
            return None
        item = self.cat_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def add_new_entry(self):
        unknown = {
            fp: info for fp, info in self.current_devices.items()
            if not self.catalogue.get(fp)
        }
        picker = AddEntryDialog(self, unknown)
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        fp, info = picker.result_data()
        if fp is None:
            return

        existing = self.catalogue.get(fp)
        if existing:
            confirm = QMessageBox.question(
                self, "Already registered",
                f"'{existing['name']}' is already registered with this VID/PID"
                f"{'/serial' if info.get('serial_number') else ''}. Edit it instead?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        dlg = RegisterDialog(self, fp, info, existing=existing)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, category, notes = dlg.result_data()
            self.catalogue.register(fp, name, category, notes, info)
            self.refresh_catalogue_table()
            self.refresh_live_table()

    def edit_selected(self):
        fp = self._selected_fp()
        if not fp:
            QMessageBox.information(self, "Edit", "Select a row first.")
            return
        rec = self.catalogue.records[fp]
        fake_info = {
            "vendor_id": rec["vendor_id"], "product_id": rec["product_id"],
            "serial_number": rec.get("serial_number", ""),
            "manufacturer_string": rec.get("manufacturer", ""),
            "product_string": rec.get("product", ""),
        }
        dlg = RegisterDialog(self, fp, fake_info, existing=rec)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, category, notes = dlg.result_data()
            self.catalogue.register(fp, name, category, notes, fake_info)
            self.refresh_catalogue_table()
            self.refresh_live_table()

    def delete_selected(self):
        fp = self._selected_fp()
        if not fp:
            QMessageBox.information(self, "Delete", "Select a row first.")
            return
        rec = self.catalogue.records[fp]
        confirm = QMessageBox.question(
            self, "Confirm delete",
            f"Remove '{rec['name']}' from the catalogue?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.catalogue.delete(fp)
            self.refresh_catalogue_table()
            self.refresh_live_table()

    def export_catalogue(self):
        if not self.catalogue.records:
            QMessageBox.information(self, "Nothing to export", "Catalogue is empty.")
            return
        default_name = f"dongle_catalogue_{datetime.now().strftime('%Y%m%d')}.json"
        path, _ = QFileDialog.getSaveFileName(self, "Export catalogue", default_name, "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w") as f:
                json.dump(self.catalogue.export_dict(), f, indent=2)
            QMessageBox.information(
                self, "Exported",
                f"Exported {len(self.catalogue.records)} entries to:\n{path}\n\n"
                "Share this file — it's self-contained and can be imported on any "
                "machine running DONGLE-ID."
            )
        except Exception as e:
            QMessageBox.warning(self, "Export failed", str(e))

    def import_catalogue(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import catalogue", "", "JSON (*.json)")
        if not path:
            return
        try:
            incoming = Catalogue.parse_import_file(path)
        except Exception as e:
            QMessageBox.warning(self, "Import failed", f"Could not read file:\n{e}")
            return

        if not incoming:
            QMessageBox.information(self, "Nothing to import", "That file has no entries.")
            return

        conflicts = [fp for fp in incoming if fp in self.catalogue.records]
        new_count = len(incoming) - len(conflicts)

        overwrite = False
        if conflicts:
            box = QMessageBox(self)
            box.setWindowTitle("Import — conflicts found")
            box.setText(
                f"{len(incoming)} entries in file.\n"
                f"{new_count} are new.\n"
                f"{len(conflicts)} already exist in your catalogue (same VID/PID/serial).\n\n"
                "What should happen to the conflicting entries?"
            )
            keep_mine = box.addButton("Keep Mine", QMessageBox.ButtonRole.RejectRole)
            use_incoming = box.addButton("Overwrite With Imported", QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = box.addButton("Cancel Import", QMessageBox.ButtonRole.ActionRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is cancel_btn:
                return
            overwrite = clicked is use_incoming

        added, updated, skipped = self.catalogue.merge(incoming, overwrite_conflicts=overwrite)
        self.refresh_catalogue_table()
        self.refresh_live_table()
        QMessageBox.information(
            self, "Import complete",
            f"Added: {added}\nUpdated: {updated}\nSkipped (kept yours): {skipped}"
        )



def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    app.setFont(QFont("Consolas", 10))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
