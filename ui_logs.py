from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit
class LogsTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        
        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas;")
        
        layout.addWidget(self.log_viewer)

    def append_log(self, html_message):
        """Append a plain-text message emitted by the watcher worker."""
        self.log_viewer.append(str(html_message))