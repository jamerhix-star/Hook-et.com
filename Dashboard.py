"""
PAWFFINATED – Point of Sale  (PyQt6 Edition)
============================================
Updated:
  • Cart panel shows ALL items from one person's order in one list
  • Running subtotal / discount / total always visible
  • "Charge" opens a full-screen Thank You receipt with itemised breakdown
  • Customer can mix any categories (bouquet, keychain, latte…) in one order
  • Renamed sidebar label  "Order" → kept as "Order" (matches Sidebar.py route)

Run:
    python POS.py
"""

from __future__ import annotations
import sys, csv, io
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QScrollArea, QGridLayout, QHBoxLayout, QVBoxLayout, QSizePolicy,
    QButtonGroup, QFileDialog, QDialog, QLineEdit, QTextEdit,
    QMessageBox, QToolBar, QComboBox, QGraphicsOpacityEffect,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QSize, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QLinearGradient, QPainterPath, QAction, QPixmap

from Sidebar import PawffinatedSidebar
from DbConnection import get_db, close_db, db_info

# ── Palette ───────────────────────────────────────────────────────────────────
C = dict(
    bg        = "#F7F5F0",
    sidebar   = "#FFFFFF",
    card      = "#FFFFFF",
    white     = "#FFFFFF",
    accent    = "#2D7A5F",
    accent_lt = "#E8F4F0",
    warn      = "#E07B39",
    warn_lt   = "#FFF7ED",
    danger    = "#D94F4F",
    danger_lt = "#FEE2E2",
    ok        = "#059669",
    ok_lt     = "#D1FAE5",
    text      = "#1A1A1A",
    sub       = "#6B7280",
    border    = "#E5E7EB",
    purple    = "#7C3AED",
    purple_lt = "#EDE9FE",
    gold      = "#D97706",
    gold_lt   = "#FEF3C7",
)

DISCOUNT_RATE  = 0.20
DISCOUNT_TYPES = ["None", "PWD", "Senior Citizen"]

CATEGORY_EMOJI = {
    "Coffee & Espresso": "☕",
    "Cold Beverages":    "🧊",
    "Pastries":          "🥐",
    "Sandwiches":        "🥪",
    "Merchandise":       "🛍️",
    "Dairy":             "🥛",
    "Dairy Alt":         "🌿",
    "Whole Beans":       "☕",
    "Syrups":            "🍯",
    "Food":              "🍽️",
    "Drinks":            "🥤",
    "Snacks":            "🍩",
}

GLOBAL_QSS = f"""
QWidget {{
    font-family: 'Segoe UI', Helvetica, sans-serif;
    font-size: 13px;
    color: {C['text']};
}}
QMainWindow, #centralWidget {{ background: {C['bg']}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: {C['bg']}; width: 5px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C['border']}; border-radius: 3px; min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QToolBar {{
    background: {C['sidebar']};
    border-bottom: 1px solid {C['border']};
    spacing: 6px; padding: 4px 12px;
}}
QStatusBar {{
    background: {C['sidebar']};
    border-top: 1px solid {C['border']};
    color: {C['sub']}; font-size: 11px; padding: 0 12px;
}}
"""


# ── Domain models ─────────────────────────────────────────────────────────────
@dataclass
class Product:
    id: int
    name: str
    category: str
    price: float
    stock: int
    sku: str = ""
    unit: str = "units"
    description: str = ""


@dataclass
class OrderLine:
    product: Product
    qty: int = 1

    @property
    def subtotal(self) -> float:
        return self.product.price * self.qty


# ── UI helpers ────────────────────────────────────────────────────────────────
def lbl(text="", bold=False, size=13, color=None) -> QLabel:
    w = QLabel(text)
    f = QFont("Segoe UI", size)
    f.setBold(bold)
    w.setFont(f)
    w.setStyleSheet(f"color:{color or C['text']};background:transparent;")
    return w


def hline() -> QFrame:
    ln = QFrame()
    ln.setFrameShape(QFrame.Shape.HLine)
    ln.setStyleSheet(f"background:{C['border']};max-height:1px;border:none;")
    ln.setFixedHeight(1)
    return ln


def action_btn(text: str, color=None, hover=None) -> QPushButton:
    bg = color or C["accent"]
    hv = hover or "#245f4a"
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(
        f"QPushButton{{background:{bg};color:white;border-radius:8px;"
        f"padding:8px 18px;font-weight:700;font-size:13px;border:none;}}"
        f"QPushButton:hover{{background:{hv};}}"
        f"QPushButton:pressed{{background:{hv};}}"
    )
    return b


def status_badge(stock: int) -> QLabel:
    if stock == 0:
        bg, fg, text = C["danger_lt"], C["danger"], "Out of Stock"
    elif stock <= 5:
        bg, fg, text = C["warn_lt"], C["warn"], f"{stock} left"
    else:
        bg, fg, text = C["ok_lt"], C["ok"], f"{stock} in stock"
    w = QLabel(text)
    w.setAlignment(Qt.AlignmentFlag.AlignCenter)
    w.setStyleSheet(
        f"background:{bg};color:{fg};border-radius:4px;"
        f"padding:2px 7px;font-size:10px;font-weight:700;border:none;"
    )
    return w


def pill_button(text: str, active=False) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setCheckable(True)
    btn.setChecked(active)
    btn.setFlat(True)
    _style_pill(btn)
    btn.toggled.connect(lambda: _style_pill(btn))
    return btn


def _style_pill(btn: QPushButton):
    if btn.isChecked():
        btn.setStyleSheet(
            f"QPushButton{{background:{C['accent']};color:white;"
            f"border-radius:6px;padding:5px 14px;font-weight:600;border:none;}}"
        )
    else:
        btn.setStyleSheet(
            f"QPushButton{{background:{C['border']};color:{C['text']};"
            f"border-radius:6px;padding:5px 14px;border:none;}}"
            f"QPushButton:hover{{background:#D1D5DB;}}"
        )


# ── POS State ─────────────────────────────────────────────────────────────────
class POSState(QObject):
    order_changed    = pyqtSignal()
    charge_completed = pyqtSignal(int, float, str, list)  # #, total, dtype, lines
    inventory_loaded = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.order_lines:    list[OrderLine] = []
        self.order_number:   int  = 1042
        self.order_type:     str  = "Dine In"
        self.customer_name:  str  = "Walk-in Customer"
        self.discount_type:  str  = "None"
        self.subtotal:       float = 0.0
        self.discount_amount:float = 0.0
        self.total_amount:   float = 0.0
        self.products:       list[Product] = []
        self.active_category:str  = "All Items"
        self._load_from_db()

    def _rows_to_products(self, rows: list[dict]) -> list[Product]:
        out = []
        for r in rows:
            try:
                out.append(Product(
                    id=int(r["id"]), name=str(r["name"]),
                    category=str(r.get("category","Other")),
                    price=float(r.get("price",0)),
                    stock=int(r.get("stock",0)),
                    sku=str(r.get("sku","")),
                    unit=str(r.get("unit","units")),
                    description=str(r.get("description","")),
                ))
            except (ValueError, TypeError):
                continue
        return out

    def _load_from_db(self):
        try:
            db = get_db()
            self.products = self._rows_to_products(db.fetch_all())
            self.active_category = "All Items"
        except Exception as e:
            print(f"[POS] DB load error: {e}")
            self.products = []

    def reload_from_db(self) -> int:
        self._load_from_db()
        self.inventory_loaded.emit(len(self.products))
        return len(self.products)

    # ── Cart ops ──────────────────────────────────────────────────────────────
    def add_product(self, product: Product):
        if product.stock <= 0:
            return
        product.stock -= 1
        for line in self.order_lines:
            if line.product.id == product.id:
                line.qty += 1
                self._recalc()
                return
        self.order_lines.append(OrderLine(product=product))
        self._recalc()

    def increment(self, line: OrderLine):
        if line.product.stock <= 0:
            return
        line.product.stock -= 1
        line.qty += 1
        self._recalc()

    def decrement(self, line: OrderLine):
        line.product.stock += 1
        line.qty -= 1
        if line.qty <= 0:
            self.order_lines.remove(line)
        self._recalc()

    def clear_order(self):
        for ln in self.order_lines:
            ln.product.stock += ln.qty
        self.order_lines.clear()
        self.discount_type = "None"
        self._recalc()

    def set_discount(self, dtype: str):
        self.discount_type = dtype
        self._recalc()

    def _recalc(self):
        self.subtotal = sum(l.subtotal for l in self.order_lines)
        self.discount_amount = (self.subtotal * DISCOUNT_RATE
                                if self.discount_type != "None" else 0.0)
        self.total_amount = self.subtotal - self.discount_amount
        self.order_changed.emit()

    def complete_charge(self):
        n  = self.order_number
        t  = self.total_amount
        dt = self.discount_type
        snapshot = [(ln.product.name, ln.product.category,
                     ln.product.price, ln.qty, ln.subtotal)
                    for ln in self.order_lines]
        try:
            db = get_db()
            order_id = db.insert_order({
                "order_number":    n,
                "order_type":      self.order_type,
                "customer_name":   self.customer_name,
                "subtotal":        self.subtotal,
                "discount_type":   self.discount_type,
                "discount_amount": self.discount_amount,
                "total_amount":    self.total_amount,
            })
            items = [{
                "product_id": ln.product.id,
                "name":       ln.product.name,
                "category":   ln.product.category,
                "sku":        ln.product.sku,
                "unit_price": ln.product.price,
                "quantity":   ln.qty,
                "subtotal":   ln.subtotal,
            } for ln in self.order_lines]
            db.insert_order_items(order_id, items)
            for ln in self.order_lines:
                p = ln.product
                db.update({"id":p.id,"name":p.name,"sku":p.sku,
                           "category":p.category,"stock":p.stock,
                           "unit":p.unit,"price":p.price,
                           "description":p.description})
        except Exception as e:
            print(f"[POS] DB write error: {e}")

        self.order_lines.clear()
        self.order_number += 1
        self.discount_type = "None"
        self._recalc()
        self.charge_completed.emit(n, t, dt, snapshot)

    @property
    def categories(self) -> list[str]:
        cats, seen = ["All Items"], set()
        for p in self.products:
            if p.category not in seen:
                cats.append(p.category)
                seen.add(p.category)
        return cats

    @property
    def filtered_products(self) -> list[Product]:
        if self.active_category == "All Items":
            return self.products
        return [p for p in self.products if p.category == self.active_category]

    # ── CSV loaders (unchanged) ───────────────────────────────────────────────
    _COL_ALIASES = {
        "name":["name","product_name","item_name","title"],
        "category":["category","cat","type","section"],
        "price":["price","cost","unit_price","amount"],
        "stock":["stock","qty","quantity","inventory","count","available"],
        "sku":["sku","code","barcode","product_code"],
        "unit":["unit","unit_of_measure","uom","units"],
        "description":["description","desc","details","note","size"],
    }

    def _normalize_row(self, row: dict) -> dict:
        rl = {k.lower().strip():v for k,v in row.items()}
        out = {"name":"","category":"Other","price":0.0,"stock":0,
               "sku":"","unit":"units","description":""}
        for f, aliases in self._COL_ALIASES.items():
            for a in aliases:
                if a in rl:
                    out[f] = rl[a]
                    break
        return out

    def _clean_rows(self, rows: list[dict]) -> list[dict]:
        clean = []
        for row in rows:
            r = self._normalize_row(row)
            try:
                if not r["name"]: continue
                clean.append({
                    "name":str(r["name"]),
                    "sku":str(r.get("sku","") or ""),
                    "category":str(r["category"]),
                    "stock":int(float(str(r["stock"]) or 0)),
                    "unit":str(r.get("unit","units") or "units"),
                    "price":float(str(r["price"]).replace("₱","").replace(",","") or 0),
                    "description":str(r.get("description","") or ""),
                })
            except (ValueError, TypeError):
                continue
        return clean

    def load_inventory_from_csv(self, filepath: str) -> int:
        with open(filepath, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        clean = self._clean_rows(rows)
        if not clean: return 0
        db = get_db()
        n = db.bulk_replace(clean)
        self._load_from_db()
        self.inventory_loaded.emit(len(self.products))
        return n

    def load_inventory_from_list(self, data: list[dict]) -> int:
        if not data: return 0
        clean = self._clean_rows(data)
        if not clean: return 0
        db = get_db()
        n = db.bulk_replace(clean)
        self._load_from_db()
        self.inventory_loaded.emit(len(self.products))
        return n


# ── Product Card ──────────────────────────────────────────────────────────────
class ProductCard(QFrame):
    clicked = pyqtSignal(object)

    def __init__(self, product: Product, parent=None):
        super().__init__(parent)
        self.product = product
        self.setObjectName("productCard")
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if product.stock > 0
            else Qt.CursorShape.ForbiddenCursor
        )
        self.setFixedSize(160, 196)
        self.setStyleSheet(
            f"QFrame#productCard{{background:{C['card']};border-radius:12px;"
            f"border:1px solid {C['border']};}}"
            f"QFrame#productCard:hover{{border:1.5px solid {C['accent']};}}"
        )
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(4)

        badge_row = QHBoxLayout()
        badge_row.addStretch()
        badge_row.addWidget(status_badge(self.product.stock))
        lay.addLayout(badge_row)

        emoji_lbl = QLabel(CATEGORY_EMOJI.get(self.product.category, "🍽️"))
        emoji_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        emoji_lbl.setStyleSheet(
            "font-size:34px;background:#F0EDE8;border-radius:8px;"
            "padding:8px;border:none;"
        )
        lay.addWidget(emoji_lbl)

        name_lbl = lbl(self.product.name, bold=True, size=11)
        name_lbl.setWordWrap(True)
        lay.addWidget(name_lbl)

        cat_lbl = lbl(self.product.category, size=9, color=C["sub"])
        lay.addWidget(cat_lbl)

        lay.addStretch()
        lay.addWidget(lbl(f"₱{self.product.price:.2f}", bold=True, size=13,
                          color=C["accent"]))

    def mousePressEvent(self, e):
        if self.product.stock > 0:
            self.clicked.emit(self.product)
        super().mousePressEvent(e)


# ── Cart Line Widget ──────────────────────────────────────────────────────────
class CartLineWidget(QWidget):
    inc_clicked = pyqtSignal(object)
    dec_clicked = pyqtSignal(object)

    def __init__(self, line: OrderLine, index: int, parent=None):
        super().__init__(parent)
        self.line = line
        self._build(index)

    def _build(self, index: int):
        self.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(10)

        # Index bubble
        num = QLabel(str(index))
        num.setFixedSize(22, 22)
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setStyleSheet(
            f"background:{C['accent_lt']};color:{C['accent']};"
            f"border-radius:11px;font-size:11px;font-weight:700;"
        )
        lay.addWidget(num)

        # Name + category
        info = QVBoxLayout()
        info.setSpacing(1)
        info.addWidget(lbl(self.line.product.name, bold=True, size=12))
        info.addWidget(lbl(self.line.product.category, size=10, color=C["sub"]))
        # Stock warning
        if 0 < self.line.product.stock <= 3:
            info.addWidget(lbl(f"⚠ {self.line.product.stock} left", size=9, color=C["warn"]))
        lay.addLayout(info, stretch=1)

        # Qty controls
        def qty_btn(txt) -> QPushButton:
            b = QPushButton(txt)
            b.setFixedSize(26, 26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton{{background:{C['border']};border-radius:6px;"
                f"font-weight:700;font-size:14px;border:none;}}"
                f"QPushButton:hover{{background:#D1D5DB;}}"
            )
            return b

        btn_dec = qty_btn("−")
        qty_lbl = lbl(str(self.line.qty), bold=True, size=12)
        qty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qty_lbl.setFixedWidth(24)
        btn_inc = qty_btn("+")

        btn_dec.clicked.connect(lambda: self.dec_clicked.emit(self.line))
        btn_inc.clicked.connect(lambda: self.inc_clicked.emit(self.line))

        qty_row = QHBoxLayout()
        qty_row.setSpacing(4)
        qty_row.addWidget(btn_dec)
        qty_row.addWidget(qty_lbl)
        qty_row.addWidget(btn_inc)
        lay.addLayout(qty_row)

        # Subtotal
        sub_lbl = lbl(f"₱{self.line.subtotal:.2f}", bold=True, size=12,
                      color=C["accent"])
        sub_lbl.setFixedWidth(68)
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(sub_lbl)


# ── Thank You Receipt Dialog ──────────────────────────────────────────────────
class ThankYouDialog(QDialog):
    """Full-screen styled receipt shown after a successful charge."""

    def __init__(self, order_num: int, total: float, discount_type: str,
                 discount_amount: float, subtotal: float,
                 order_type: str, customer_name: str,
                 lines: list[tuple], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Order Complete")
        self.setMinimumWidth(480)
        self.setMaximumWidth(560)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(pal.ColorRole.Window, QColor(C["white"]))
        self.setPalette(pal)

        from PyQt6.QtGui import QGuiApplication
        sh = QGuiApplication.primaryScreen().availableGeometry().height()
        self.setMaximumHeight(min(780, sh - 40))

        self._build(order_num, total, discount_type, discount_amount,
                    subtotal, order_type, customer_name, lines)

    def _build(self, order_num, total, discount_type, discount_amount,
               subtotal, order_type, customer_name, lines):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Green header ──────────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setStyleSheet(f"background:{C['accent']};")
        hl = QVBoxLayout(hdr)
        hl.setContentsMargins(32, 28, 32, 28)
        hl.setSpacing(6)
        hl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        check = QLabel("✓")
        check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        check.setStyleSheet(
            "font-size:42px;color:white;background:transparent;"
            "font-weight:700;"
        )
        hl.addWidget(check)

        ty = QLabel("Thank You!")
        ty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ty_f = QFont("Segoe UI", 24)
        ty_f.setBold(True)
        ty.setFont(ty_f)
        ty.setStyleSheet("color:white;background:transparent;")
        hl.addWidget(ty)

        sub_msg = QLabel(f"Your order has been placed successfully.")
        sub_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_msg.setStyleSheet("color:rgba(255,255,255,0.85);font-size:13px;"
                              "background:transparent;")
        hl.addWidget(sub_msg)
        outer.addWidget(hdr)

        # ── Scrollable receipt body ───────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{C['white']};border:none;}}"
            f"QScrollBar:vertical{{background:{C['bg']};width:4px;}}"
            f"QScrollBar::handle:vertical{{background:{C['border']};border-radius:2px;}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}"
        )

        body = QWidget()
        body.setStyleSheet(f"background:{C['white']};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(32, 24, 32, 24)
        bl.setSpacing(0)

        # Order meta
        meta_card = QFrame()
        meta_card.setStyleSheet(
            f"QFrame{{background:{C['bg']};border-radius:10px;"
            f"border:1px solid {C['border']};}}"
        )
        ml = QGridLayout(meta_card)
        ml.setContentsMargins(16, 12, 16, 12)
        ml.setSpacing(6)

        def meta_row(r, label, value, value_color=None):
            ll = lbl(label, size=10, color=C["sub"])
            vl = lbl(value, bold=True, size=11, color=value_color or C["text"])
            vl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            ml.addWidget(ll, r, 0)
            ml.addWidget(vl, r, 1)

        meta_row(0, "Order #",    str(order_num))
        meta_row(1, "Type",       order_type)
        meta_row(2, "Customer",   customer_name)
        if discount_type != "None":
            meta_row(3, "Discount", discount_type, C["purple"])
        bl.addWidget(meta_card)
        bl.addSpacing(20)

        # Items heading
        bl.addWidget(lbl("ORDER SUMMARY", size=9, bold=True, color=C["sub"]))
        bl.addSpacing(8)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"background:{C['border']};border:none;")
        div.setFixedHeight(1)
        bl.addWidget(div)

        # Items list
        for i, (name, cat, unit_price, qty, line_sub) in enumerate(lines):
            item_w = QWidget()
            item_w.setStyleSheet("background:transparent;")
            il = QHBoxLayout(item_w)
            il.setContentsMargins(0, 10, 0, 10)
            il.setSpacing(10)

            # Number bubble
            num_lbl = QLabel(str(i + 1))
            num_lbl.setFixedSize(20, 20)
            num_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num_lbl.setStyleSheet(
                f"background:{C['accent_lt']};color:{C['accent']};"
                f"border-radius:10px;font-size:10px;font-weight:700;"
            )
            il.addWidget(num_lbl)

            # Name + category
            nc = QVBoxLayout()
            nc.setSpacing(1)
            nc.addWidget(lbl(name, bold=True, size=12))
            nc.addWidget(lbl(cat, size=10, color=C["sub"]))
            il.addLayout(nc, stretch=1)

            # Qty × price
            qp = QVBoxLayout()
            qp.setSpacing(1)
            qp.setAlignment(Qt.AlignmentFlag.AlignRight)
            qp.addWidget(lbl(f"×{qty}  ₱{unit_price:.2f}", size=11, color=C["sub"]))
            qp.addWidget(lbl(f"₱{line_sub:.2f}", bold=True, size=12,
                             color=C["accent"]))
            il.addLayout(qp)

            bl.addWidget(item_w)

            # Separator between items
            if i < len(lines) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setStyleSheet(
                    f"background:{C['border']};border:none;max-height:1px;"
                )
                sep.setFixedHeight(1)
                bl.addWidget(sep)

        bl.addSpacing(16)

        # Totals block
        totals = QFrame()
        totals.setStyleSheet(
            f"QFrame{{background:{C['bg']};border-radius:10px;"
            f"border:1px solid {C['border']};}}"
        )
        tl = QVBoxLayout(totals)
        tl.setContentsMargins(16, 12, 16, 12)
        tl.setSpacing(6)

        def total_row(label, value, bold=False, color=None):
            rw = QHBoxLayout()
            rw.addWidget(lbl(label, bold=bold, size=12 if bold else 11,
                             color=color or (C["text"] if bold else C["sub"])))
            rw.addStretch()
            rw.addWidget(lbl(value, bold=bold, size=13 if bold else 11,
                             color=color or (C["accent"] if bold else C["text"])))
            tl.addLayout(rw)

        total_row("Subtotal", f"₱{subtotal:.2f}")
        if discount_type != "None":
            total_row(f"{discount_type} Discount (−20%)",
                      f"−₱{discount_amount:.2f}", color=C["purple"])
            # Divider before total
            sep2 = QFrame()
            sep2.setFrameShape(QFrame.Shape.HLine)
            sep2.setStyleSheet(f"background:{C['border']};border:none;")
            sep2.setFixedHeight(1)
            tl.addWidget(sep2)
        total_row("TOTAL PAID", f"₱{total:.2f}", bold=True)

        bl.addWidget(totals)
        bl.addSpacing(8)

        # Paw print footer message
        footer_msg = QLabel("🐾  Thank you for choosing Pawffinated!\n"
                            "We hope to see you again soon.")
        footer_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_msg.setWordWrap(True)
        footer_msg.setStyleSheet(
            f"color:{C['sub']};font-size:11px;background:transparent;"
            f"padding:8px 0;"
        )
        bl.addWidget(footer_msg)
        bl.addStretch()

        scroll.setWidget(body)
        outer.addWidget(scroll, stretch=1)

        # ── Footer button ─────────────────────────────────────────────────────
        btn_bar = QWidget()
        btn_bar.setStyleSheet(
            f"background:{C['white']};border-top:1px solid {C['border']};"
        )
        bbl = QHBoxLayout(btn_bar)
        bbl.setContentsMargins(32, 14, 32, 16)
        bbl.setSpacing(10)

        new_order_btn = QPushButton("＋  New Order")
        new_order_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_order_btn.setFixedHeight(44)
        new_order_btn.setStyleSheet(
            f"QPushButton{{background:{C['accent']};color:white;"
            f"border-radius:9px;font-size:14px;font-weight:700;border:none;}}"
            f"QPushButton:hover{{background:#236850;}}"
        )
        new_order_btn.clicked.connect(self.accept)
        bbl.addWidget(new_order_btn)

        outer.addWidget(btn_bar)


# ── Import Dialog ─────────────────────────────────────────────────────────────
class ImportDialog(QDialog):
    def __init__(self, pos: POSState, parent=None):
        super().__init__(parent)
        self.pos = pos
        self.setWindowTitle("Import / Reload Inventory")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumSize(520, 440)
        self.resize(520, 440)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(pal.ColorRole.Window, QColor(C["white"]))
        self.setPalette(pal)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(14)
        lay.addWidget(lbl("Import / Reload Inventory", bold=True, size=17))
        sub = lbl("Re-fetch from database or load a CSV file.\n"
                  "⚠ CSV import replaces ALL existing inventory.", size=11, color=C["sub"])
        sub.setWordWrap(True)
        lay.addWidget(sub)
        lay.addWidget(hline())

        def section(icon, title, hint):
            box = QFrame()
            box.setStyleSheet(
                f"QFrame{{background:{C['bg']};border:1.5px solid {C['border']};"
                f"border-radius:10px;}}"
            )
            bl = QVBoxLayout(box)
            bl.setContentsMargins(16, 12, 16, 12)
            bl.setSpacing(6)
            th = QHBoxLayout()
            th.addWidget(lbl(icon, size=14))
            th.addWidget(lbl(title, bold=True, size=13))
            th.addStretch()
            bl.addLayout(th)
            hl = lbl(hint, size=10, color=C["sub"])
            hl.setWordWrap(True)
            bl.addWidget(hl)
            return box, bl

        db_box, db_bl = section("🐘", "Reload from Database",
                                "Re-fetches all products from PostgreSQL.")
        db_btn = action_btn("Reload from Database")
        db_btn.clicked.connect(self._reload_db)
        db_bl.addWidget(db_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(db_box)

        csv_box, csv_bl = section("📄", "From CSV File",
                                  "Columns: name, category, price, stock, unit, description")
        csv_btn = action_btn("Browse CSV…", color=C["sub"], hover="#4B5563")
        csv_btn.clicked.connect(self._import_csv)
        csv_bl.addWidget(csv_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(csv_box)

        lay.addStretch()
        close_row = QHBoxLayout()
        close_row.addStretch()
        cb = QPushButton("Close")
        cb.setFixedSize(84, 34)
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.setStyleSheet(
            f"QPushButton{{background:{C['border']};color:{C['text']};"
            f"border-radius:8px;font-size:13px;font-weight:600;border:none;}}"
            f"QPushButton:hover{{background:#D1D5DB;}}"
        )
        cb.clicked.connect(self.accept)
        close_row.addWidget(cb)
        lay.addLayout(close_row)

    def _reload_db(self):
        try:
            n = self.pos.reload_from_db()
            QMessageBox.information(self, "Done", f"✅ {n} products loaded.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select CSV", "",
                                              "CSV (*.csv);;All (*)")
        if not path: return
        try:
            n = self.pos.load_inventory_from_csv(path)
            QMessageBox.information(self, "Done",
                                    f"✅ {n} products imported from CSV.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


# ── Main Window ───────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.pos = POSState()
        self.setWindowTitle("Pawffinated – Point of Sale")
        self.resize(1280, 820)
        self.setMinimumSize(1040, 680)
        self.setStyleSheet(GLOBAL_QSS)
        self._build_toolbar()
        self._build_ui()
        self._build_statusbar()

        self.pos.order_changed.connect(self._refresh_cart)
        self.pos.inventory_loaded.connect(self._on_inventory_loaded)
        self.pos.charge_completed.connect(self._on_charge_complete)

        self._refresh_category_tabs()
        self._refresh_product_grid()
        self._refresh_cart()

    # ── Toolbar ───────────────────────────────────────────────────────────────
    def _build_toolbar(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)

        logo = QLabel("  🐾  PAWFFINATED  ")
        logo.setStyleSheet(
            f"font-weight:800;font-size:14px;color:{C['accent']};"
        )
        tb.addWidget(logo)

        sp = QWidget()
        sp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(sp)

        self._db_lbl = QLabel()
        self._update_db_label()
        tb.addWidget(self._db_lbl)

        imp = QAction("📦  Import / Reload", self)
        imp.triggered.connect(self._open_import)
        tb.addAction(imp)

        new_a = QAction("🆕  New Order", self)
        new_a.triggered.connect(self._new_order)
        tb.addAction(new_a)

    def _update_db_label(self):
        n = len(self.pos.products)
        if n:
            self._db_lbl.setText(f"🐘  {n} products loaded")
            self._db_lbl.setStyleSheet(
                f"color:{C['accent']};font-size:11px;"
                f"border:1px solid {C['accent']};border-radius:5px;"
                f"padding:3px 10px;background:{C['accent_lt']};"
            )
        else:
            self._db_lbl.setText("⚠  No products")
            self._db_lbl.setStyleSheet(
                f"color:{C['warn']};font-size:11px;"
                f"border:1px solid {C['warn']};border-radius:5px;"
                f"padding:3px 10px;background:{C['warn_lt']};"
            )

    # ── Central UI ────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(PawffinatedSidebar(active_page="Order"))
        self._build_product_area(root)
        self._build_cart_panel(root)

    # ── Product area (left / centre) ──────────────────────────────────────────
    def _build_product_area(self, parent):
        self.main_area = QWidget()
        self.main_area.setStyleSheet(f"background:{C['bg']};")
        ml = QVBoxLayout(self.main_area)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        # Page header
        hdr = QWidget()
        hdr.setStyleSheet(
            f"background:{C['white']};border-bottom:1px solid {C['border']};"
        )
        hl = QVBoxLayout(hdr)
        hl.setContentsMargins(28, 18, 28, 0)
        hl.setSpacing(4)
        hl.addWidget(lbl("Order", bold=True, size=20))
        hl.addWidget(lbl("Tap items to add to the cart. Mix any categories freely.",
                         size=11, color=C["sub"]))

        # Category tabs
        self.tab_row = QHBoxLayout()
        self.tab_row.setSpacing(6)
        self.tab_row.setContentsMargins(0, 10, 0, 12)
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        hl.addLayout(self.tab_row)
        ml.addWidget(hdr)

        # Product grid
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"background:{C['bg']};border:none;")
        self.grid_container = QWidget()
        self.grid_container.setStyleSheet(f"background:{C['bg']};")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(20, 16, 20, 16)
        self.grid_layout.setSpacing(12)
        self.scroll.setWidget(self.grid_container)
        ml.addWidget(self.scroll)

        parent.addWidget(self.main_area, stretch=1)

    # ── Cart panel (right) ────────────────────────────────────────────────────
    def _build_cart_panel(self, parent):
        self.cart_panel = QWidget()
        self.cart_panel.setFixedWidth(340)
        self.cart_panel.setStyleSheet(
            f"background:{C['white']};border-left:1px solid {C['border']};"
        )
        cp = QVBoxLayout(self.cart_panel)
        cp.setContentsMargins(0, 0, 0, 0)
        cp.setSpacing(0)

        # ── Cart header ───────────────────────────────────────────────────────
        cart_hdr = QWidget()
        cart_hdr.setStyleSheet(
            f"background:{C['white']};border-bottom:1px solid {C['border']};"
        )
        ch_lay = QVBoxLayout(cart_hdr)
        ch_lay.setContentsMargins(18, 14, 18, 0)
        ch_lay.setSpacing(6)

        # Title row
        title_row = QHBoxLayout()
        self.cart_title = lbl("🛒  Cart", bold=True, size=16)
        self.cart_count_badge = QLabel("0")
        self.cart_count_badge.setFixedSize(22, 22)
        self.cart_count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cart_count_badge.setStyleSheet(
            f"background:{C['accent']};color:white;"
            f"border-radius:11px;font-size:11px;font-weight:700;"
        )
        menu_btn = QPushButton("⋮")
        menu_btn.setFlat(True)
        menu_btn.setFixedSize(28, 28)
        menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_btn.setStyleSheet(
            f"QPushButton{{border:none;background:transparent;"
            f"color:{C['sub']};font-size:18px;font-weight:700;}}"
            f"QPushButton:hover{{background:{C['bg']};border-radius:5px;}}"
        )
        menu_btn.clicked.connect(self._cart_menu)
        title_row.addWidget(self.cart_title)
        title_row.addWidget(self.cart_count_badge)
        title_row.addStretch()
        title_row.addWidget(menu_btn)
        ch_lay.addLayout(title_row)

        # Customer name
        self.customer_lbl = lbl(self.pos.customer_name, size=10, color=C["sub"])
        ch_lay.addWidget(self.customer_lbl)

        # Order type toggle
        type_row = QHBoxLayout()
        type_row.setSpacing(0)
        self.type_group = QButtonGroup(self)
        self.type_group.setExclusive(True)
        for ot in ["Dine In", "Takeout", "Delivery"]:
            b = QPushButton(ot)
            b.setCheckable(True)
            b.setChecked(ot == self.pos.order_type)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(30)
            b.setStyleSheet(self._type_qss(ot == self.pos.order_type))
            b.toggled.connect(lambda checked, btn=b, t=ot:
                              self._set_order_type(t, btn, checked))
            self.type_group.addButton(b)
            type_row.addWidget(b)
        ch_lay.addLayout(type_row)
        ch_lay.addSpacing(6)
        cp.addWidget(cart_hdr)

        # ── Scrollable cart lines ─────────────────────────────────────────────
        self.cart_scroll = QScrollArea()
        self.cart_scroll.setWidgetResizable(True)
        self.cart_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cart_scroll.setStyleSheet("border:none;background:white;")
        self.cart_lines_w = QWidget()
        self.cart_lines_w.setStyleSheet("background:white;")
        self.cart_lines_lay = QVBoxLayout(self.cart_lines_w)
        self.cart_lines_lay.setContentsMargins(0, 0, 0, 0)
        self.cart_lines_lay.setSpacing(0)
        self.cart_lines_lay.addStretch()
        self.cart_scroll.setWidget(self.cart_lines_w)
        cp.addWidget(self.cart_scroll, stretch=1)

        # ── Cart footer (totals + charge) ─────────────────────────────────────
        self.cart_footer = QWidget()
        self.cart_footer.setStyleSheet(
            f"background:{C['white']};border-top:1px solid {C['border']};"
        )
        self.cart_footer_lay = QVBoxLayout(self.cart_footer)
        self.cart_footer_lay.setContentsMargins(18, 12, 18, 16)
        self.cart_footer_lay.setSpacing(6)
        cp.addWidget(self.cart_footer)

        parent.addWidget(self.cart_panel)

    def _type_qss(self, active: bool) -> str:
        if active:
            return (f"QPushButton{{background:{C['white']};color:{C['text']};"
                    f"border:1px solid {C['border']};font-weight:700;"
                    f"padding:0 10px;border-radius:0;}}")
        return (f"QPushButton{{background:{C['border']};color:{C['sub']};"
                f"border:none;padding:0 10px;border-radius:0;}}"
                f"QPushButton:hover{{background:#D1D5DB;}}")

    def _set_order_type(self, ot: str, btn: QPushButton, checked: bool):
        if checked:
            self.pos.order_type = ot
            for b in self.type_group.buttons():
                b.setStyleSheet(self._type_qss(b is btn))

    # ── Category tabs ─────────────────────────────────────────────────────────
    def _refresh_category_tabs(self):
        for i in reversed(range(self.tab_row.count())):
            item = self.tab_row.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()
                self.tab_row.removeItem(item)
        for b in self.tab_group.buttons():
            self.tab_group.removeButton(b)
        for cat in self.pos.categories:
            btn = pill_button(cat, active=(cat == self.pos.active_category))
            self.tab_group.addButton(btn)
            self.tab_row.addWidget(btn)
            btn.clicked.connect(lambda _, c=cat: self._select_cat(c))
        self.tab_row.addStretch()

    def _select_cat(self, cat: str):
        self.pos.active_category = cat
        self._refresh_product_grid()

    # ── Product grid ──────────────────────────────────────────────────────────
    def _refresh_product_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        products = self.pos.filtered_products
        if not products:
            empty = lbl("No products. Click 📦 Import / Reload to load from DB.",
                        color=C["sub"])
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setContentsMargins(0, 60, 0, 0)
            self.grid_layout.addWidget(empty, 0, 0)
            return

        cols = max(1, (self.main_area.width() - 40) // 176)
        for i, prod in enumerate(products):
            pc = ProductCard(prod)
            pc.clicked.connect(self._on_product_clicked)
            self.grid_layout.addWidget(pc, i // cols, i % cols)

    def _on_product_clicked(self, product: Product):
        self.pos.add_product(product)
        self._refresh_product_grid()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._refresh_product_grid)

    # ── Cart refresh ──────────────────────────────────────────────────────────
    def _refresh_cart(self):
        # Update badge count
        total_items = sum(l.qty for l in self.pos.order_lines)
        self.cart_count_badge.setText(str(total_items))
        self.cart_count_badge.setStyleSheet(
            f"background:{'#2D7A5F' if total_items else C['border']};"
            f"color:{'white' if total_items else C['sub']};"
            f"border-radius:11px;font-size:11px;font-weight:700;"
        )
        self.cart_title.setText(
            f"🛒  Cart  ·  Order #{self.pos.order_number}"
        )
        self.customer_lbl.setText(self.pos.customer_name)

        # Clear lines
        while self.cart_lines_lay.count() > 1:
            item = self.cart_lines_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.pos.order_lines:
            empty = QWidget()
            empty.setStyleSheet("background:transparent;")
            el = QVBoxLayout(empty)
            el.setAlignment(Qt.AlignmentFlag.AlignCenter)
            el.setContentsMargins(20, 40, 20, 20)
            cart_icon = QLabel("🛒")
            cart_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cart_icon.setStyleSheet("font-size:36px;background:transparent;")
            el.addWidget(cart_icon)
            empty_lbl = lbl("Your cart is empty.\nTap any product to add it.",
                            size=12, color=C["sub"])
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            el.addWidget(empty_lbl)
            self.cart_lines_lay.insertWidget(0, empty)
        else:
            for i, line in enumerate(self.pos.order_lines):
                clw = CartLineWidget(line, i + 1)
                clw.inc_clicked.connect(self.pos.increment)
                clw.dec_clicked.connect(self.pos.decrement)
                self.cart_lines_lay.insertWidget(i * 2, clw)
                if i < len(self.pos.order_lines) - 1:
                    self.cart_lines_lay.insertWidget(i * 2 + 1, hline())

        # Rebuild footer
        for i in reversed(range(self.cart_footer_lay.count())):
            item = self.cart_footer_lay.takeAt(i)
            if item.widget():
                item.widget().deleteLater()

        def summary_row(left, right, bold=False, left_color=None, right_color=None):
            rw = QHBoxLayout()
            rw.addWidget(lbl(left, bold=bold, size=12 if bold else 11,
                             color=left_color or (C["text"] if bold else C["sub"])))
            rw.addStretch()
            rw.addWidget(lbl(right, bold=bold, size=13 if bold else 11,
                             color=right_color or (C["accent"] if bold else C["text"])))
            w = QWidget()
            w.setStyleSheet("background:transparent;")
            w.setLayout(rw)
            self.cart_footer_lay.addWidget(w)

        summary_row("Subtotal", f"₱{self.pos.subtotal:.2f}")
        summary_row(f"Items in cart",
                    str(sum(l.qty for l in self.pos.order_lines)),
                    left_color=C["sub"])

        # Discount selector
        disc_w = QWidget()
        disc_w.setStyleSheet(
            f"background:{C['purple_lt']};border-radius:8px;"
        )
        dl = QVBoxLayout(disc_w)
        dl.setContentsMargins(10, 8, 10, 8)
        dl.setSpacing(6)

        dt_row = QHBoxLayout()
        dt_row.addWidget(lbl("Discount", bold=True, size=11, color=C["purple"]))
        dt_row.addWidget(lbl("PWD / Senior (20%)", size=10, color=C["purple"]))
        dt_row.addStretch()
        dl.addLayout(dt_row)

        disc_btn_row = QHBoxLayout()
        disc_btn_row.setSpacing(6)
        disc_group = QButtonGroup(disc_w)
        disc_group.setExclusive(True)
        for dtype in DISCOUNT_TYPES:
            b = QPushButton(dtype)
            b.setCheckable(True)
            b.setChecked(dtype == self.pos.discount_type)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(26)
            active = dtype == self.pos.discount_type
            b.setStyleSheet(self._disc_qss(active))
            b.toggled.connect(
                lambda checked, btn=b, d=dtype:
                self._on_disc_toggled(d, btn, checked)
            )
            disc_group.addButton(b)
            disc_btn_row.addWidget(b)
        dl.addLayout(disc_btn_row)

        if self.pos.discount_type != "None":
            dr = QHBoxLayout()
            dr.addWidget(lbl(f"−20% applied", size=10, color=C["purple"]))
            dr.addStretch()
            dr.addWidget(lbl(f"−₱{self.pos.discount_amount:.2f}",
                             bold=True, size=11, color=C["purple"]))
            dl.addLayout(dr)

        self.cart_footer_lay.addWidget(disc_w)

        # Divider + total
        self.cart_footer_lay.addWidget(hline())
        summary_row("TOTAL", f"₱{self.pos.total_amount:.2f}", bold=True)

        # Charge button
        charge_btn = QPushButton(
            f"  Charge  ₱{self.pos.total_amount:.2f}  "
        )
        charge_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        charge_btn.setFixedHeight(50)
        charge_btn.setEnabled(bool(self.pos.order_lines))
        charge_btn.setStyleSheet(
            f"QPushButton{{background:{'#2D7A5F' if self.pos.order_lines else C['border']};"
            f"color:{'white' if self.pos.order_lines else C['sub']};"
            f"border-radius:10px;font-size:15px;font-weight:700;border:none;}}"
            f"QPushButton:hover{{background:#245f4a;}}"
            f"QPushButton:disabled{{background:{C['border']};color:{C['sub']};}}"
        )
        charge_btn.clicked.connect(self._charge)
        self.cart_footer_lay.addWidget(charge_btn)

        # Status bar
        self._status_items.setText(
            f"Items: {sum(l.qty for l in self.pos.order_lines)}  ·  "
            f"Subtotal: ₱{self.pos.subtotal:.2f}  ·  "
            f"Total: ₱{self.pos.total_amount:.2f}"
        )

    def _disc_qss(self, active: bool) -> str:
        if active:
            return (f"QPushButton{{background:{C['purple']};color:white;"
                    f"border-radius:5px;padding:0 10px;"
                    f"font-weight:700;font-size:11px;border:none;}}")
        return (f"QPushButton{{background:transparent;color:{C['purple']};"
                f"border:1px solid {C['purple']};border-radius:5px;"
                f"padding:0 10px;font-size:11px;}}"
                f"QPushButton:hover{{background:{C['purple_lt']};}}")

    def _on_disc_toggled(self, dtype: str, btn: QPushButton, checked: bool):
        if checked:
            self.pos.set_discount(dtype)

    # ── Actions ───────────────────────────────────────────────────────────────
    def _charge(self):
        if not self.pos.order_lines:
            return

        # Confirm dialog
        items_text = "\n".join(
            f"  • {ln.product.name} ×{ln.qty}  ₱{ln.subtotal:.2f}"
            for ln in self.pos.order_lines
        )
        disc_line = ""
        if self.pos.discount_type != "None":
            disc_line = f"\nDiscount: −₱{self.pos.discount_amount:.2f}"

        reply = QMessageBox.question(
            self, "Confirm Payment",
            f"{self.pos.order_type}  ·  {self.pos.customer_name}\n\n"
            f"{items_text}\n\n"
            f"Subtotal: ₱{self.pos.subtotal:.2f}"
            f"{disc_line}\n"
            f"TOTAL: ₱{self.pos.total_amount:.2f}\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.pos.complete_charge()
            self._refresh_product_grid()

    def _on_charge_complete(self, order_num: int, total: float,
                            discount_type: str, lines: list):
        # Show full thank-you receipt
        disc_amt = 0.0
        sub = sum(p * q for _, _, p, q, _ in lines)
        if discount_type != "None":
            disc_amt = sub * DISCOUNT_RATE

        dlg = ThankYouDialog(
            order_num=order_num,
            total=total,
            discount_type=discount_type,
            discount_amount=disc_amt,
            subtotal=sub,
            order_type=self.pos.order_type,
            customer_name=self.pos.customer_name,
            lines=lines,
            parent=self,
        )
        dlg.exec()
        self._refresh_product_grid()

    def _new_order(self):
        if self.pos.order_lines:
            r = QMessageBox.question(
                self, "New Order",
                "Clear the current cart and start a fresh order?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if r != QMessageBox.StandardButton.Yes:
                return
        self.pos.clear_order()
        self._refresh_product_grid()

    def _cart_menu(self):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu{{background:{C['white']};border:1px solid {C['border']};"
            f"border-radius:8px;padding:4px;}}"
            f"QMenu::item{{padding:8px 20px;border-radius:4px;}}"
            f"QMenu::item:selected{{background:{C['accent_lt']};}}"
        )
        menu.addAction("🗑️  Clear Cart",      self._new_order)
        menu.addAction("👤  Change Customer", self._change_customer)
        menu.addSeparator()
        menu.addAction("🖨️  Print Receipt",   self._print_receipt)
        menu.exec(self.cursor().pos())

    def _change_customer(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Customer Name")
        dlg.setFixedSize(300, 120)
        dlg.setAutoFillBackground(True)
        pal = dlg.palette()
        pal.setColor(pal.ColorRole.Window, QColor(C["white"]))
        dlg.setPalette(pal)
        ll = QVBoxLayout(dlg)
        ll.setContentsMargins(20, 16, 20, 16)
        ll.setSpacing(10)
        ll.addWidget(lbl("Customer Name:", bold=True))
        entry = QLineEdit(self.pos.customer_name)
        entry.setStyleSheet(
            f"border:1px solid {C['border']};border-radius:7px;"
            f"padding:7px 10px;background:{C['bg']};font-size:13px;"
        )
        ll.addWidget(entry)
        save = action_btn("Save")
        save.clicked.connect(lambda: (
            setattr(self.pos, "customer_name",
                    entry.text().strip() or "Walk-in Customer"),
            self._refresh_cart(), dlg.accept(),
        ))
        ll.addWidget(save, alignment=Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def _print_receipt(self):
        if not self.pos.order_lines:
            QMessageBox.information(self, "Receipt", "Cart is empty.")
            return
        lines = [f"PAWFFINATED  ·  Order #{self.pos.order_number}",
                 f"Type: {self.pos.order_type}",
                 f"Customer: {self.pos.customer_name}", "─" * 38]
        for ln in self.pos.order_lines:
            lines.append(
                f"{ln.product.name:24s}  ×{ln.qty}  ₱{ln.subtotal:>8.2f}"
            )
        lines += ["─" * 38,
                  f"{'Subtotal':30s}  ₱{self.pos.subtotal:>8.2f}"]
        if self.pos.discount_type != "None":
            lines.append(
                f"{self.pos.discount_type + ' (20%)':30s}"
                f"  −₱{self.pos.discount_amount:>7.2f}"
            )
        lines.append(f"{'TOTAL':30s}  ₱{self.pos.total_amount:>8.2f}")
        QMessageBox.information(self, "Receipt Preview", "\n".join(lines))

    def _open_import(self):
        dlg = ImportDialog(self.pos, self)
        dlg.exec()
        self._refresh_category_tabs()
        self._refresh_product_grid()
        self._update_db_label()

    def _on_inventory_loaded(self, count: int):
        self._update_db_label()
        self._refresh_category_tabs()
        self._refresh_product_grid()
        self._flash(f"✅ {count} products loaded.")

    # ── Status bar ────────────────────────────────────────────────────────────
    def _build_statusbar(self):
        self._status_items = QLabel()
        self._status_msg   = QLabel()
        self._status_msg.setStyleSheet(
            f"color:{C['accent']};font-weight:600;"
        )
        self.statusBar().addWidget(self._status_items)
        self.statusBar().addPermanentWidget(self._status_msg)

    def _flash(self, msg: str, ms: int = 4000):
        self._status_msg.setText(msg)
        QTimer.singleShot(ms, lambda: self._status_msg.setText(""))


# ── Entry point ───────────────────────────────────────────────────────────────
class PawffinatedApp(QApplication):
    def __init__(self, argv=None):
        super().__init__(argv or sys.argv)
        self.setApplicationName("Pawffinated POS")
        self.window = MainWindow()

    def run(self):
        self.window.show()
        return self.exec()


if __name__ == "__main__":
    app = PawffinatedApp(sys.argv)
    sys.exit(app.run())