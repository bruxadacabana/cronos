"""
Cronos - FlowLayout
Layout responsivo que recalcula colunas automaticamente.
Cards se reorganizam ao redimensionar a janela.
"""
from PyQt6.QtWidgets import QLayout, QSizePolicy
from PyQt6.QtCore import Qt, QRect, QSize, QPoint


class FlowLayout(QLayout):
    def __init__(self, parent=None, h_spacing=10, v_spacing=10):
        super().__init__(parent)
        self._items = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing

    def addItem(self, item):
        self._items.append(item)

    def horizontalSpacing(self): return self._h_spacing
    def verticalSpacing(self):   return self._v_spacing

    def count(self): return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self): return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        effective_rect = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y = effective_rect.x(), effective_rect.y()
        row_height = 0
        line_items = []

        def flush_line(items, row_y, row_h, available_w):
            """Distribui itens uniformemente na linha."""
            if not items or test_only:
                return
            total_spacing = self._h_spacing * (len(items) - 1)
            item_w = max(1, (available_w - total_spacing) // len(items))
            cx = effective_rect.x()
            for it in items:
                if not test_only:
                    it.setGeometry(QRect(QPoint(cx, row_y), QSize(item_w, row_h)))
                cx += item_w + self._h_spacing

        for item in self._items:
            w = item.sizeHint()
            item_w = w.width()
            item_h = w.height()

            # Quebra de linha
            if line_items and x + item_w > effective_rect.right() + 1:
                flush_line(line_items, y, row_height, effective_rect.width())
                y += row_height + self._v_spacing
                x = effective_rect.x()
                row_height = 0
                line_items = []

            line_items.append(item)
            x += item_w + self._h_spacing
            row_height = max(row_height, item_h)

        # Última linha
        flush_line(line_items, y, row_height, effective_rect.width())
        return y + row_height - rect.y() + margins.bottom()
