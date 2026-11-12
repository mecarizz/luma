from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTableWidget, QTableWidgetItem, QHeaderView

class StatusCard(QFrame):
    def __init__(self, title: str, initial_value: str):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        self.setStyleSheet("background-color: #f0f0f0; border-radius: 5px; padding: 10px;")
        
        layout = QVBoxLayout(self)
        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-weight: bold; color: #555;")
        
        self.lbl_value = QLabel(initial_value)
        self.lbl_value.setStyleSheet("font-size: 24px; font-weight: bold;")
        
        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)

class DashboardTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # Top Metric Cards
        card_layout = QHBoxLayout()
        self.card_active_sellers = StatusCard("Active Sellers", "0")
        self.card_orders_today = StatusCard("Orders Processed Today", "0")
        self.card_errors = StatusCard("Failed / Retrying", "0")
        
        card_layout.addWidget(self.card_active_sellers)
        card_layout.addWidget(self.card_orders_today)
        card_layout.addWidget(self.card_errors)
        layout.addLayout(card_layout)

        # Recent Orders Table
        layout.addWidget(QLabel("<b>Recent Orders Across All Sellers</b>"))
        self.order_table = QTableWidget(0, 5)
        self.order_table.setHorizontalHeaderLabels(["Timestamp", "Seller", "Order No.", "Cargo", "Status"])
        self.order_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.order_table)

    def add_order_row(self, timestamp, seller, order_no, cargo, status):
        """Slot to receive new orders from worker threads."""
        row_pos = 0  # Insert at top
        self.order_table.insertRow(row_pos)
        self.order_table.setItem(row_pos, 0, QTableWidgetItem(timestamp))
        self.order_table.setItem(row_pos, 1, QTableWidgetItem(seller))
        self.order_table.setItem(row_pos, 2, QTableWidgetItem(order_no))
        self.order_table.setItem(row_pos, 3, QTableWidgetItem(cargo))
        self.order_table.setItem(row_pos, 4, QTableWidgetItem(status))