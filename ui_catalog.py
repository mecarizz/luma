from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                               QTableWidgetItem, QHeaderView, QComboBox, QLabel, QPushButton)

class CatalogTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # Context Selector
        context_layout = QHBoxLayout()
        context_layout.addWidget(QLabel("<b>Viewing Context:</b>"))
        self.combo_context = QComboBox()
        self.combo_context.addItem("Master Catalog (Global)")
        self.combo_context.addItem("Seller 1 Overrides")
        self.combo_context.addItem("Seller 2 Overrides")
        context_layout.addWidget(self.combo_context)
        context_layout.addStretch()
        
        self.btn_save_changes = QPushButton("Save Changes")
        context_layout.addWidget(self.btn_save_changes)
        layout.addLayout(context_layout)

        # Catalog Table
        self.catalog_table = QTableWidget(0, 5)
        self.catalog_table.setHorizontalHeaderLabels([
            "Barcode (PK)", "Display Name", "Stock Code", "Product Type", "Outsourced"
        ])
        self.catalog_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.catalog_table)

    def load_master_catalog(self, db_rows):
        """Populates the table with Master data."""
        self.catalog_table.setRowCount(0)
        for row_idx, row_data in enumerate(db_rows):
            self.catalog_table.insertRow(row_idx)
            for col_idx, item in enumerate(row_data):
                self.catalog_table.setItem(row_idx, col_idx, QTableWidgetItem(str(item)))
                
    def apply_seller_overrides(self, overrides_dict):
        """Highlights cells green if they are overridden by the selected seller."""
        # Logic to iterate table and apply PyQt QBrush highlighting to modified cells
        pass