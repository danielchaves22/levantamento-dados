#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF para Excel Desktop App - Interface PyQt6
============================================

Interface gráfica moderna usando PyQt6 que utiliza o módulo
pdf_processor_core.py para toda a lógica de processamento.

Versão 4.0.1 - PROCESSAMENTO UNIFICADO:
- Performance 10-20x superior
- Threading nativo com signals/slots thread-safe
- Virtualização automática de listas grandes
- Drag & Drop nativo do PyQt6
- Interface responsiva e moderna
- Eliminação de polling manual
- Splash Screen profissional
- Sistema de atenção para códigos duplicados (01003601 + 01003602)
- NOVO: Processamento sempre via ThreadPoolExecutor (simplificação)

Funcionalidades v4.0.1:
- Seleção múltipla de PDFs com interface otimizada
- Processamento paralelo unificado com comunicação thread-safe
- Updates em tempo real sem latência
- Histórico virtualizado para performance máxima
- Styling moderno com QSS
- Splash screen com progresso de carregamento
- Sistema automático para duplicidades de PREMIO PROD. MENSAL
- Arquitetura simplificada (sempre threads, zero inconsistência)

Dependências:
pip install PyQt6

Como usar:
python desktop_app.py

Autor: Sistema de Extração Automatizada
Data: 2025
"""

import sys
import os
import json
import uuid
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Callable, Tuple
from dataclasses import dataclass

# PyQt6 imports
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QLineEdit, QTextEdit, QProgressBar,
    QListWidget, QListWidgetItem, QFrame, QDialog, QScrollArea,
    QCheckBox, QSpinBox, QFileDialog, QMessageBox, QSizePolicy,
    QSplitter, QGroupBox, QFormLayout, QComboBox, QSplashScreen,
    QDialogButtonBox, QToolButton
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QSize, pyqtSlot, QMimeData, QObject
)
from PyQt6.QtGui import (
    QFont, QTextCursor, QPalette, QColor, QDragEnterEvent, QDropEvent, QAction,
    QPixmap, QPainter, QLinearGradient
)

# Importa o processador core
try:
    from pdf_processor_core import PDFProcessorCore
    from processors.ficha_financeira_processor import FichaFinanceiraProcessor
    from processors.planilha_dados_processor import PlanilhaDadosProcessor
    from project_manager import ProjectManager, ProjectMetadata, MONTH_NAMES
except ImportError:
    print("ERRO: Módulo pdf_processor_core.py não encontrado!")
    print("Certifique-se de que o arquivo pdf_processor_core.py está na mesma pasta.")
    sys.exit(1)


def get_ficha_results_from_payload(result_data: Optional[Dict[str, object]]) -> List[Dict[str, object]]:
    """Extrai a lista de resultados por PDF do payload da ficha financeira."""

    if not result_data:
        return []

    results = result_data.get('results')
    if isinstance(results, list):
        return results
    return []


def flatten_ficha_outputs(result_data: Optional[Dict[str, object]]) -> List[Dict[str, object]]:
    """Agrupa os CSVs gerados, preservando a origem de cada PDF."""

    results = get_ficha_results_from_payload(result_data)
    if results:
        flattened: List[Dict[str, object]] = []
        for result in results:
            pdf_file = result.get('pdf_file')
            output_folder = result.get('output_folder')
            person_name = result.get('person_name')
            for item in result.get('outputs', []):
                flattened.append(
                    {
                        'label': item.get('label'),
                        'path': item.get('path'),
                        'pdf_file': pdf_file,
                        'output_folder': output_folder,
                        'person_name': person_name,
                    }
                )
        return flattened

    legacy_outputs = (result_data or {}).get('outputs', [])
    return [dict(item) for item in legacy_outputs]


def collect_ficha_person_names(result_data: Optional[Dict[str, object]]) -> List[str]:
    """Retorna a lista de nomes identificados no processamento da ficha."""

    names: List[str] = []
    for result in get_ficha_results_from_payload(result_data):
        name = result.get('person_name')
        if name and name not in names:
            names.append(name)

    if not names and result_data:
        legacy = result_data.get('person_name')
        if legacy:
            names.append(legacy)

    return names


def collect_ficha_output_folders(result_data: Optional[Dict[str, object]]) -> List[str]:
    """Lista as pastas geradas para cada PDF processado."""

    folders: List[str] = []
    for result in get_ficha_results_from_payload(result_data):
        folder = result.get('output_folder')
        if folder and folder not in folders:
            folders.append(folder)

    if not folders and result_data:
        legacy_folder = result_data.get('output_folder')
        if legacy_folder:
            folders.append(legacy_folder)

    return folders


class SplashScreen(QSplashScreen):
    """Splash screen moderna com progresso de carregamento"""
    
    def __init__(self):
        # Cria pixmap simples para splash screen
        splash_pixmap = self.create_splash_pixmap()
        super().__init__(splash_pixmap)
        
        self.setWindowFlags(Qt.WindowType.SplashScreen | Qt.WindowType.WindowStaysOnTopHint)
        
        # Define fonte maior e em negrito para as mensagens de progresso
        progress_font = QFont("Arial", 13, QFont.Weight.Bold)
        self.setFont(progress_font)
        
        # Timer para simular progresso
        self.progress_value = 0
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self.update_progress)
        
        # Centraliza na tela
        self.center_on_screen()
        
    def create_splash_pixmap(self):
        """Cria pixmap customizado para a splash screen"""
        width, height = 480, 220  # Altura reduzida
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor("#1e1e1e"))
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Fundo com gradiente
        gradient = QLinearGradient(0, 0, 0, height)
        gradient.setColorAt(0, QColor("#1e1e1e"))
        gradient.setColorAt(1, QColor("#2b2b2b"))
        painter.fillRect(pixmap.rect(), gradient)
        
        # Borda
        painter.setPen(QColor("#1f538d"))
        painter.drawRoundedRect(5, 5, width-10, height-10, 10, 10)
        
        # Título principal
        painter.setPen(QColor("#ffffff"))
        title_font = QFont("Arial", 22, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.drawText(
            20,
            50,
            width - 40,
            40,
            Qt.AlignmentFlag.AlignCenter,
            "Levantamento de Dados",
        )

        # Subtítulo (com espaçamento aumentado)
        subtitle_font = QFont("Arial", 14)
        painter.setFont(subtitle_font)
        painter.setPen(QColor("#aaaaaa"))
        painter.drawText(
            20,
            100,
            width - 40,
            25,
            Qt.AlignmentFlag.AlignCenter,
            "Processamento automatizado de PDFs",
        )
        
        painter.end()
        return pixmap
    
    def center_on_screen(self):
        """Centraliza splash screen na tela"""
        try:
            screen = QApplication.primaryScreen().geometry()
            splash_size = self.size()
            x = (screen.width() - splash_size.width()) // 2
            y = (screen.height() - splash_size.height()) // 2
            self.move(x, y)
        except Exception:
            # Fallback se não conseguir centralizar
            self.move(400, 300)
    
    def start_loading(self):
        """Inicia processo de carregamento simulado"""
        self.progress_value = 0
        self.progress_timer.start(30)  # Atualiza a cada 30ms para animação mais suave
        self.show()
        self.showMessage("Inicializando aplicação...", Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom, QColor("#ffffff"))
        QApplication.processEvents()  # Força renderização
    
    def update_progress(self):
        """Atualiza progresso da splash screen"""
        if self.progress_value < 100:
            # Incremento variável para parecer mais natural
            if self.progress_value < 30:
                self.progress_value += 1.5  # Início mais rápido
            elif self.progress_value < 70:
                self.progress_value += 1    # Meio mais lento
            else:
                self.progress_value += 0.8  # Final mais lento
                
            current_progress = int(self.progress_value)
            
            # Atualiza mensagem baseado no progresso
            if self.progress_value < 15:
                message = f"{current_progress}% - Inicializando PyQt6..."
            elif self.progress_value < 30:
                message = f"{current_progress}% - Carregando dependências..."
            elif self.progress_value < 50:
                message = f"{current_progress}% - Configurando interface..."
            elif self.progress_value < 70:
                message = f"{current_progress}% - Preparando sistema..."
            elif self.progress_value < 85:
                message = f"{current_progress}% - Finalizando..."
            elif self.progress_value < 95:
                message = f"{current_progress}% - Quase pronto..."
            else:
                message = f"{current_progress}% - Carregando..."
                
            self.showMessage(message, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom, QColor("#ffffff"))
        else:
            self.progress_timer.stop()
            self.showMessage("100% - Aplicação pronta!", Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom, QColor("#2cc985"))
    
    def set_status(self, message):
        """Define status personalizado"""
        current_val = int(self.progress_value)
        if "✅" in message:
            display_message = f"{current_val}% - {message}"
            color = QColor("#2cc985")
        elif "❌" in message:
            display_message = f"{current_val}% - {message}"
            color = QColor("#f44336")
        else:
            display_message = f"{current_val}% - {message}"
            color = QColor("#ffffff")
            
        self.showMessage(display_message, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom, color)
        QApplication.processEvents()  # Força atualização imediata
    
    def finish_loading(self, main_window=None):
        """Finaliza carregamento e, se informado, abre a janela principal."""
        self.showMessage("100% - Aplicação pronta! Abrindo...", Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom, QColor("#2cc985"))
        QApplication.processEvents()

        def _finalize():
            if main_window is not None:
                self.finish(main_window)
            else:
                self.close()

        # Pequena pausa para mostrar "100%" e mensagem final
        QTimer.singleShot(500, _finalize)




class ProjectCreationDialog(QDialog):
    """Diálogo para criação de um novo projeto."""

    def __init__(self, project_manager: ProjectManager, parent=None):
        super().__init__(parent)
        self.project_manager = project_manager
        self.created_project: Optional[ProjectMetadata] = None

        self.setWindowTitle("Novo projeto")
        self.setModal(True)
        self.setFixedWidth(520)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        description = QLabel(
            "Informe os dados do projeto. O modelo define qual rotina será utilizada "
            "ao abrir o projeto. O período inicial precisa ser menor ou igual ao final."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ex.: Folha Janeiro/2025")
        form_layout.addRow("Nome do projeto:", self.name_edit)

        self.model_combo = QComboBox()
        self.model_combo.addItem("Recibo Modelo 1", ProjectManager.MODEL_RECIBO)
        self.model_combo.addItem("Ficha Financeira", ProjectManager.MODEL_FICHA)
        self.model_combo.addItem("Planilha de Dados", ProjectManager.MODEL_PLANILHA)
        form_layout.addRow("Modelo:", self.model_combo)

        self.start_month_combo = QComboBox()
        self.start_month_combo.addItems(MONTH_NAMES)
        self.start_year_spin = QSpinBox()
        self.start_year_spin.setRange(1990, 2100)

        self.end_month_combo = QComboBox()
        self.end_month_combo.addItems(MONTH_NAMES)
        self.end_year_spin = QSpinBox()
        self.end_year_spin.setRange(1990, 2100)

        current_year = datetime.now().year
        self.start_year_spin.setValue(current_year)
        self.end_year_spin.setValue(current_year)

        period_start_layout = QHBoxLayout()
        period_start_layout.addWidget(self.start_month_combo)
        period_start_layout.addWidget(self.start_year_spin)
        form_layout.addRow("Período inicial:", period_start_layout)

        period_end_layout = QHBoxLayout()
        period_end_layout.addWidget(self.end_month_combo)
        period_end_layout.addWidget(self.end_year_spin)
        form_layout.addRow("Período final:", period_end_layout)

        layout.addLayout(form_layout)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #f44336; font-size: 11px;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        try:
            name = self.name_edit.text().strip()
            model = self.model_combo.currentData()
            start_month = self.start_month_combo.currentIndex() + 1
            start_year = self.start_year_spin.value()
            end_month = self.end_month_combo.currentIndex() + 1
            end_year = self.end_year_spin.value()

            project = self.project_manager.create_project(
                name,
                model,
                start_month,
                start_year,
                end_month,
                end_year,
            )
            self.created_project = project
            self.accept()
        except ValueError as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()


class ProjectListItemWidget(QWidget):
    """Widget com o resumo de um projeto."""

    MODEL_LABELS = {
        ProjectManager.MODEL_RECIBO: "Recibo Modelo 1",
        ProjectManager.MODEL_FICHA: "Ficha Financeira",
        ProjectManager.MODEL_PLANILHA: "Planilha de Dados",
    }

    def __init__(self, project: ProjectMetadata, open_callback: Optional[Callable[[str], None]] = None):
        super().__init__()
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 6, 10, 6)
        main_layout.setSpacing(12)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        name_label = QLabel(f"📁 {project.name}")
        name_label.setStyleSheet("font-weight: bold; font-size: 14px;")

        model_label = QLabel(f"Modelo: {self.MODEL_LABELS.get(project.model, project.model)}")
        model_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")

        period_label = QLabel(f"Período: {ProjectManager.format_period(project)}")
        period_label.setStyleSheet("color: #888; font-size: 11px;")

        info_layout.addWidget(name_label)
        info_layout.addWidget(model_label)
        info_layout.addWidget(period_label)

        main_layout.addLayout(info_layout, 1)

        open_button = QPushButton("🚀 Abrir")
        open_button.setToolTip("Abrir este projeto")
        open_button.setProperty("class", "primary")

        if open_callback is not None:
            open_button.clicked.connect(lambda: open_callback(project.project_id))

        main_layout.addWidget(open_button)


class ProjectSelectionWindow(QMainWindow):
    """Tela inicial de seleção e criação de projetos."""

    project_open_requested = pyqtSignal(str)

    def __init__(self, project_manager: ProjectManager):
        super().__init__()
        self.project_manager = project_manager

        self.setWindowTitle("Levantamento de Dados")
        self.setFixedSize(950, 600)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)

        title_label = QLabel("Levantamento de Dados")
        title_label.setStyleSheet("font-size: 22px; font-weight: 700; padding-top: 12px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        subtitle = QLabel("Selecione um projeto para iniciar ou crie um novo.")
        subtitle.setStyleSheet("font-size: 16px; padding-bottom: 6px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        self.projects_list = QListWidget()
        self.projects_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.projects_list.itemDoubleClicked.connect(self._on_open_selected)

        layout.addWidget(self.projects_list, 1)

        self.empty_label = QLabel("Nenhum projeto cadastrado. Clique em 'Criar projeto' para começar.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self.empty_label)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)

        self.create_button = QPushButton("➕ Criar projeto")
        self.create_button.clicked.connect(self._on_create_project)

        self.refresh_button = QPushButton("🔄 Atualizar lista")
        self.refresh_button.clicked.connect(self.refresh_projects)

        self.close_button = QPushButton("❌ Fechar")
        self.close_button.clicked.connect(self.close)

        buttons_layout.addWidget(self.create_button)
        buttons_layout.addWidget(self.refresh_button)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.close_button)

        layout.addLayout(buttons_layout)

        self.refresh_projects()

    def refresh_projects(self):
        self.projects_list.clear()
        projects = self.project_manager.list_projects()
        last_selected = self.project_manager.get_last_selected()

        has_projects = bool(projects)
        self.projects_list.setVisible(has_projects)
        self.empty_label.setVisible(not has_projects)

        for project in projects:
            item = QListWidgetItem()
            widget = ProjectListItemWidget(project, self._open_project_by_id)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, project.project_id)
            self.projects_list.addItem(item)
            self.projects_list.setItemWidget(item, widget)

        if projects:
            index_to_select = 0
            if last_selected:
                for index in range(self.projects_list.count()):
                    item = self.projects_list.item(index)
                    if item.data(Qt.ItemDataRole.UserRole) == last_selected:
                        index_to_select = index
                        break
            self.projects_list.setCurrentRow(index_to_select)

    def _current_project_id(self) -> Optional[str]:
        item = self.projects_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _on_open_selected(self):
        project_id = self._current_project_id()
        if project_id:
            self._open_project_by_id(project_id)

    def _open_project_by_id(self, project_id: str):
        for index in range(self.projects_list.count()):
            item = self.projects_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == project_id:
                self.projects_list.setCurrentRow(index)
                break
        self.project_manager.set_last_selected(project_id)
        self.project_open_requested.emit(project_id)

    def _on_create_project(self):
        dialog = ProjectCreationDialog(self.project_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.created_project:
            self.refresh_projects()
            self.project_manager.set_last_selected(dialog.created_project.project_id)
            self.project_open_requested.emit(dialog.created_project.project_id)
# Estilo escuro moderno
DARK_STYLE = """
QMainWindow {
    background-color: #1e1e1e;
    color: white;
}

QWidget {
    background-color: #1e1e1e;
    color: white;
}

QPushButton {
    background-color: #1f538d;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    color: white;
    font-weight: bold;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #2a5f9e;
}

QPushButton:pressed {
    background-color: #1a4a7a;
}

QPushButton:disabled {
    background-color: #666;
    color: #aaa;
}

QPushButton.success {
    background-color: #2cc985;
}

QPushButton.success:hover {
    background-color: #259b6e;
}

QPushButton.secondary {
    background-color: #14375e;
}

QPushButton.secondary:hover {
    background-color: #1a4a7a;
}

QPushButton.danger {
    background-color: #dc3545;
}

QPushButton.danger:hover {
    background-color: #c82333;
}

QPushButton.attention {
    background-color: #ff9800;
}

QPushButton.attention:hover {
    background-color: #f57c00;
}

QTabWidget::pane {
    border: 1px solid #444;
    background-color: #2b2b2b;
    border-radius: 4px;
}

QTabBar::tab {
    background-color: #3b3b3b;
    color: white;
    padding: 8px 16px;
    margin: 2px;
    border-radius: 4px;
}

QTabBar::tab:selected {
    background-color: #1f538d;
}

QTabBar::tab:hover {
    background-color: #4a4a4a;
}

QProgressBar {
    border: 1px solid #444;
    border-radius: 4px;
    text-align: center;
    background-color: #2b2b2b;
    color: white;
}

QProgressBar::chunk {
    background-color: #2cc985;
    border-radius: 3px;
}

QLineEdit {
    background-color: #2b2b2b;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 8px;
    color: white;
}

QLineEdit:focus {
    border-color: #1f538d;
}

QTextEdit {
    background-color: #2b2b2b;
    border: 1px solid #444;
    border-radius: 4px;
    color: white;
    selection-background-color: #1f538d;
}

QListWidget {
    background-color: #2b2b2b;
    border: 1px solid #444;
    border-radius: 4px;
    outline: none;
}

QListWidget::item {
    padding: 0px;
    border-bottom: 1px solid #444;
    background-color: transparent;
}

QListWidget::item:selected {
    background-color: transparent;
}

QListWidget::item:hover {
    background-color: #333;
}

QFrame {
    background-color: #2b2b2b;
    border: 1px solid #444;
    border-radius: 6px;
}

QFrame:hover {
    border-color: #1f538d;
}

QFrame.attention {
    border-color: #ff9800;
}

QFrame.attention:hover {
    border-color: #f57c00;
}

QGroupBox {
    background-color: #2b2b2b;
    border: 1px solid #444;
    border-radius: 6px;
    font-weight: bold;
    padding-top: 10px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px 0 5px;
}

QGroupBox.attention {
    border: 2px solid #ff9800;
    background-color: #2d2416;
}

QGroupBox.attention::title {
    color: #ff9800;
}

QLabel {
    color: white;
}

QCheckBox {
    color: white;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
}

QCheckBox::indicator:unchecked {
    background-color: #2b2b2b;
    border: 1px solid #666;
    border-radius: 3px;
}

QCheckBox::indicator:checked {
    background-color: #1f538d;
    border: 1px solid #1f538d;
    border-radius: 3px;
}

QComboBox {
    background-color: #2b2b2b;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 4px;
    color: white;
}

QComboBox:hover {
    border-color: #1f538d;
}

QComboBox::drop-down {
    border: none;
}

QComboBox::down-arrow {
    width: 12px;
    height: 12px;
}

QScrollBar:vertical {
    background-color: #2b2b2b;
    width: 12px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background-color: #666;
    border-radius: 6px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #777;
}
"""

@dataclass
class HistoryEntry:
    """Representa uma entrada no histórico de processamentos"""
    timestamp: datetime
    pdf_file: str
    success: bool
    result_data: dict
    logs: List[str]
    is_batch: bool = False
    batch_info: Dict = None
    has_attention: bool = False  # NOVO
    attention_details: List = None  # NOVO
    
    def __post_init__(self):
        if self.batch_info is None:
            self.batch_info = {}
        if self.attention_details is None:
            self.attention_details = []

class PersistenceManager:
    """Gerencia persistência de configurações e histórico"""

    def __init__(self, app_dir=None, project_id: Optional[str] = None):
        if app_dir is None:
            if getattr(sys, 'frozen', False):
                self.app_dir = Path(sys.executable).parent
            else:
                self.app_dir = Path(__file__).parent
        else:
            self.app_dir = Path(app_dir)

        self.base_data_dir = self.app_dir / ".data"
        self.base_data_dir.mkdir(exist_ok=True)

        if project_id:
            self.data_dir = self.base_data_dir / "projetos" / project_id
            self.data_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.data_dir = self.base_data_dir

        self.config_file = self.data_dir / "config.json"
        self.history_file = self.data_dir / "history.json"
        
        self.session_id = str(uuid.uuid4())
        self.session_start = datetime.now()
    
    def load_config(self):
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"Erro ao carregar configurações: {e}")
            return {}
    
    def save_config(self, config_data):
        try:
            config_data['last_saved'] = datetime.now().isoformat()
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Erro ao salvar configurações: {e}")
    
    def load_all_history_entries(self):
        try:
            if not self.history_file.exists():
                return []
            
            with open(self.history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            all_entries = []
            for session in data.get('sessions', []):
                for entry_data in session.get('entries', []):
                    entry = HistoryEntry(
                        timestamp=datetime.fromisoformat(entry_data['timestamp']),
                        pdf_file=entry_data['pdf_file'],
                        success=entry_data['success'],
                        result_data=entry_data['result_data'],
                        logs=entry_data['logs'],
                        is_batch=entry_data.get('is_batch', False),
                        batch_info=entry_data.get('batch_info', {}),
                        has_attention=entry_data.get('has_attention', False),  # NOVO
                        attention_details=entry_data.get('attention_details', [])  # NOVO
                    )
                    all_entries.append(entry)
            
            return all_entries
        except Exception as e:
            print(f"Erro ao carregar histórico: {e}")
            return []
    
    def save_history_entry(self, entry_data):
        try:
            history_data = {'sessions': []}
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    history_data = json.load(f)
            
            current_session = None
            for session in history_data['sessions']:
                if session['session_id'] == self.session_id:
                    current_session = session
                    break
            
            if current_session is None:
                current_session = {
                    'session_id': self.session_id,
                    'start_time': self.session_start.isoformat(),
                    'entries': []
                }
                history_data['sessions'].append(current_session)
            
            current_session['entries'].append({
                'timestamp': entry_data.timestamp.isoformat(),
                'pdf_file': entry_data.pdf_file,
                'success': entry_data.success,
                'result_data': entry_data.result_data,
                'logs': entry_data.logs[:50],
                'is_batch': getattr(entry_data, 'is_batch', False),
                'batch_info': getattr(entry_data, 'batch_info', {}),
                'has_attention': getattr(entry_data, 'has_attention', False),  # NOVO
                'attention_details': getattr(entry_data, 'attention_details', [])  # NOVO
            })
            
            history_data['sessions'] = history_data['sessions'][-10:]
            
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"Erro ao salvar histórico: {e}")
    
    def clear_history(self):
        try:
            if self.history_file.exists():
                self.history_file.unlink()
        except Exception as e:
            print(f"Erro ao limpar histórico: {e}")

class PDFProcessorThread(QThread):
    """Thread para processamento de PDFs com signals thread-safe"""
    
    progress_updated = pyqtSignal(str, int, str)  # filename, progress, message
    pdf_completed = pyqtSignal(str, dict)         # filename, result_data
    batch_completed = pyqtSignal()
    log_message = pyqtSignal(str)
    
    def __init__(self, pdf_files, processor_factory, trabalho_dir, max_workers=3):
        super().__init__()
        self.pdf_files = pdf_files
        self.processor_factory = processor_factory
        self.trabalho_dir = trabalho_dir
        self.max_workers = max_workers
        self.completed_count = 0
        self.total_count = len(pdf_files)
    
    def run(self):
        """Executa processamento unificado com ThreadPoolExecutor para todos os casos"""
        # Sempre usa processamento em lote (ThreadPoolExecutor)
        # mesmo para 1 arquivo - simplicidade > micro-otimização
        self._process_batch()
        self.batch_completed.emit()
    
    def _process_single_pdf(self, pdf_file):
        """
        Processa um único PDF (usado tanto para casos individuais quanto em lote)
        
        Este método é chamado sempre através do ThreadPoolExecutor, 
        garantindo comportamento consistente independente da quantidade de arquivos.
        """
        filename = Path(pdf_file).name
        
        try:
            processor = self.processor_factory()
            processor.set_trabalho_dir(self.trabalho_dir)
            
            def progress_callback(progress, message=""):
                self.progress_updated.emit(filename, progress, message)
            
            def log_callback(log_message):
                self.log_message.emit(f"[{filename}] {log_message}")
            
            processor.progress_callback = progress_callback
            processor.log_callback = log_callback
            
            self.progress_updated.emit(filename, 0, "Iniciando...")
            
            if Path(pdf_file).parent == Path(self.trabalho_dir):
                pdf_filename = filename
            else:
                pdf_filename = pdf_file
            
            results = processor.process_pdf(pdf_filename)
            
            if results['success']:
                # Determina ícone baseado em atenção
                if results.get('has_attention', False):
                    icon = "⚠️"
                    message = f"⚠️ {results['total_extracted']} períodos processados (ATENÇÃO)"
                else:
                    icon = "✅"
                    message = f"✅ {results['total_extracted']} períodos processados"
                
                self.progress_updated.emit(filename, 100, message)
            else:
                self.progress_updated.emit(filename, 0, f"❌ {results['error']}")
            
            self.pdf_completed.emit(filename, results)
            
        except Exception as e:
            error_result = {'success': False, 'error': str(e)}
            self.progress_updated.emit(filename, 0, f"❌ Erro: {str(e)}")
            self.pdf_completed.emit(filename, error_result)
    
    def _process_batch(self):
        """
        Processa arquivos usando ThreadPoolExecutor (unificado para todos os casos)
        
        Sempre usa ThreadPoolExecutor mesmo para 1 arquivo, garantindo:
        - Comportamento consistente
        - Código mais simples
        - Menos bugs de inconsistência
        - Overhead desprezível (~0.01% do tempo total)
        """
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_pdf = {
                executor.submit(self._process_single_pdf, pdf_file): pdf_file
                for pdf_file in self.pdf_files
            }

            for future in as_completed(future_to_pdf):
                pdf_file = future_to_pdf[future]
                try:
                    future.result()
                except Exception as e:
                    filename = Path(pdf_file).name
                    self.progress_updated.emit(filename, 0, f"❌ Exceção: {str(e)}")
                    self.pdf_completed.emit(filename, {'success': False, 'error': str(e)})


class FichaFinanceiraBatchThread(QThread):
    """Thread dedicada à rotina da ficha financeira."""

    progress_updated = pyqtSignal(str, int, str)
    pdf_completed = pyqtSignal(str, dict)
    batch_completed = pyqtSignal()
    log_message = pyqtSignal(str)

    def __init__(
        self,
        pdf_files: List[str],
        start_period: date,
        end_period: date,
        output_dir: str,
        max_workers: int,
        cartoes_time_mode: str,
        horas_trabalhadas_time_mode: str,
    ):
        super().__init__()
        self.pdf_files = [str(path) for path in pdf_files]
        self.start_period = start_period
        self.end_period = end_period
        self.output_dir = Path(output_dir)
        self.max_workers = max(1, max_workers)
        self.cartoes_time_mode = cartoes_time_mode
        self.horas_trabalhadas_time_mode = (
            horas_trabalhadas_time_mode
            if horas_trabalhadas_time_mode
            else cartoes_time_mode
        )

    def run(self):
        processor = FichaFinanceiraProcessor(
            log_callback=self._emit_log,
            config={
                "cartoes_time_mode": self.cartoes_time_mode,
                "horas_trabalhadas_time_mode": self.horas_trabalhadas_time_mode,
            },
        )

        try:
            effective_workers = max(1, min(self.max_workers, len(self.pdf_files)))

            for index, pdf_file in enumerate(self.pdf_files):
                name = Path(pdf_file).name
                if index < effective_workers:
                    initial_message = "Preparando para iniciar..."
                else:
                    initial_message = "Aguardando disponibilidade na fila..."
                self.progress_updated.emit(name, 0, initial_message)

            def handle_progress(pdf_path: Path, current_page: int, total_pages: int) -> None:
                filename = Path(pdf_path).name
                if current_page < 0:
                    self.progress_updated.emit(
                        filename,
                        0,
                        "Worker liberado, preparando processamento...",
                    )
                    return
                if current_page == 0:
                    self.progress_updated.emit(
                        filename,
                        0,
                        "Preparando processamento...",
                    )
                    return
                if total_pages <= 0:
                    self.progress_updated.emit(
                        filename,
                        50,
                        "Processando páginas...",
                    )
                    return
                percent = int(current_page * 100 / max(total_pages, 1))
                percent = max(1, min(percent, 99))
                message = f"Processando página {current_page}/{total_pages}"
                self.progress_updated.emit(filename, percent, message)

            results = processor.generate_csvs(
                [Path(path) for path in self.pdf_files],
                self.start_period,
                self.end_period,
                self.output_dir,
                max_workers=self.max_workers,
                progress_callback=handle_progress,
            )

            sanitized_results: List[Dict[str, object]] = []
            flattened_outputs: List[Dict[str, object]] = []

            for original_path, result in zip(self.pdf_files, results):
                pdf_path = Path(result.get('pdf_path', original_path))
                output_folder_path = result.get('output_folder')
                output_folder = str(output_folder_path) if output_folder_path else None

                sanitized_outputs = []
                for item in result.get('outputs', []):
                    output_path = item.get('path')
                    sanitized_item = {
                        'label': item.get('label'),
                        'path': str(output_path),
                    }
                    sanitized_outputs.append(sanitized_item)
                    flattened_outputs.append(
                        {
                            'label': item.get('label'),
                            'path': str(output_path),
                            'pdf_file': str(pdf_path),
                            'output_folder': output_folder,
                            'person_name': result.get('person_name'),
                        }
                    )

                sanitized_results.append(
                    {
                        'pdf_file': str(pdf_path),
                        'person_name': result.get('person_name'),
                        'output_folder': output_folder,
                        'folder_slug': result.get('folder_slug'),
                        'outputs': sanitized_outputs,
                    }
                )

            for result in sanitized_results:
                pdf_name = Path(result['pdf_file']).name if result.get('pdf_file') else 'PDF'
                folder = result.get('output_folder')
                message = "✅ CSVs gerados"
                if folder:
                    message = f"✅ CSVs gerados em {folder}"
                self.progress_updated.emit(pdf_name, 100, message)

            payload = {
                'success': True,
                'person_name': sanitized_results[0].get('person_name') if sanitized_results else None,
                'outputs': flattened_outputs,
                'results': sanitized_results,
                'output_folder': sanitized_results[0].get('output_folder') if sanitized_results else None,
                'pdf_count': len(sanitized_results),
                'period': {
                    'start': {'year': self.start_period.year, 'month': self.start_period.month},
                    'end': {'year': self.end_period.year, 'month': self.end_period.month},
                },
            }

            self.pdf_completed.emit('Ficha Financeira', payload)
        except Exception as exc:
            error_message = f"❌ Erro: {exc}"
            for pdf_file in self.pdf_files:
                name = Path(pdf_file).name
                self.progress_updated.emit(name, 0, error_message)

            self.log_message.emit(f"Erro durante o processamento: {exc}")
            self.pdf_completed.emit('Ficha Financeira', {'success': False, 'error': str(exc)})
        finally:
            self.batch_completed.emit()

    def _emit_log(self, message: str):
        self.log_message.emit(message)


class PlanilhaDadosBatchThread(QThread):
    """Thread dedicada ao processamento das planilhas de dados."""

    progress_updated = pyqtSignal(str, int, str)
    pdf_completed = pyqtSignal(str, dict)
    batch_completed = pyqtSignal()
    log_message = pyqtSignal(str)

    def __init__(
        self,
        workbooks: List[str],
        start_period: date,
        end_period: date,
        output_dir: str,
        max_workers: int,
    ) -> None:
        super().__init__()
        self.workbooks = [str(path) for path in workbooks]
        self.start_period = start_period
        self.end_period = end_period
        self.output_dir = Path(output_dir)
        self.max_workers = max(1, max_workers)

    def run(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)

        def process_single(workbook_path: str) -> dict:
            filename = Path(workbook_path).name
            target_dir = self.output_dir / Path(workbook_path).stem
            target_dir.mkdir(parents=True, exist_ok=True)

            processor = PlanilhaDadosProcessor(log_callback=lambda msg: self._emit_log(filename, msg))
            self.progress_updated.emit(filename, 0, "Preparando arquivo...")

            try:
                processor.process(
                    workbook_path,
                    target_dir,
                    start_period=(self.start_period.year, self.start_period.month),
                    end_period=(self.end_period.year, self.end_period.month),
                )

                outputs = [
                    {
                        'label': 'REMUNERAÇÃO RECEBIDA',
                        'path': str(target_dir / PlanilhaDadosProcessor.REMUNERACAO_FILENAME),
                    },
                    {
                        'label': 'PRODUÇÃO',
                        'path': str(target_dir / PlanilhaDadosProcessor.PRODUCAO_FILENAME),
                    },
                    {
                        'label': 'CARTÕES',
                        'path': str(target_dir / PlanilhaDadosProcessor.CARTOES_FILENAME),
                    },
                ]

                self.progress_updated.emit(filename, 100, "✅ CSVs gerados")
                return {
                    'success': True,
                    'output_folder': str(target_dir),
                    'outputs': outputs,
                    'processor': 'planilha_dados',
                }
            except Exception as exc:
                self.progress_updated.emit(filename, 0, f"❌ Erro: {exc}")
                return {'success': False, 'error': str(exc), 'processor': 'planilha_dados'}

        try:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_map = {executor.submit(process_single, wb): wb for wb in self.workbooks}
                for future in as_completed(future_map):
                    workbook = future_map[future]
                    filename = Path(workbook).name
                    try:
                        result = future.result()
                    except Exception as exc:  # salvaguarda
                        result = {'success': False, 'error': str(exc), 'processor': 'planilha_dados'}
                        self.progress_updated.emit(filename, 0, f"❌ Erro inesperado: {exc}")
                    self.pdf_completed.emit(filename, result)
        finally:
            self.batch_completed.emit()

    def _emit_log(self, filename: str, message: str) -> None:
        self.log_message.emit(f"[{filename}] {message}")


class DropZoneWidget(QWidget):
    """Widget para drag & drop de arquivos configurável."""

    files_dropped = pyqtSignal(list)

    def __init__(self, *, label: str = "🎯 Arraste arquivos aqui ou clique para selecionar", extensions: Optional[List[str]] = None):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(60)
        self.allowed_extensions = [ext.lower() for ext in (extensions or ['.pdf'])]

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.label = QLabel(label)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 14px;
                padding: 20px;
                border: 2px dashed #666;
                border-radius: 8px;
                background-color: #2b2b2b;
            }
        """)

        layout.addWidget(self.label)

        # Permite clicar para selecionar
        self.label.mousePressEvent = self._on_click

    def _on_click(self, event):
        """Abre diálogo de seleção quando clicado"""
        if hasattr(self.parent(), 'select_pdfs'):
            self.parent().select_pdfs()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            dropped_files = [url.toLocalFile() for url in urls]
            filtered = [
                file
                for file in dropped_files
                if any(file.lower().endswith(ext) for ext in self.allowed_extensions)
            ]
            if filtered:
                event.acceptProposedAction()
                self.label.setStyleSheet(self.label.styleSheet() + "border-color: #2cc985;")

    def dragLeaveEvent(self, event):
        self.label.setStyleSheet(self.label.styleSheet().replace("border-color: #2cc985;", ""))
    
    def dropEvent(self, event: QDropEvent):
        files = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith('.pdf'):
                files.append(file_path)
        
        if files:
            self.files_dropped.emit(files)
        
        event.acceptProposedAction()
        self.label.setStyleSheet(self.label.styleSheet().replace("border-color: #2cc985;", ""))

class BatchProgressDialog(QDialog):
    """Dialog para mostrar progresso de processamento em lote"""
    
    def __init__(self, pdf_files, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Processando {len(pdf_files)} PDFs...")
        self.setModal(True)
        
        # Define tamanho fixo e desabilita redimensionamento/maximizar
        self.setFixedSize(850, 580)
        self.setWindowFlags(
            Qt.WindowType.Dialog | 
            Qt.WindowType.WindowCloseButtonHint
        )
        
        self.pdf_widgets = {}
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # Header
        self.header = QLabel(f"🔄 Processando {len(pdf_files)} PDFs em Paralelo")
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header.setStyleSheet("font-size: 16px; font-weight: bold; padding: 15px;")
        layout.addWidget(self.header)
        
        # Status informativo
        status_info = QLabel("Acompanhe o progresso individual de cada arquivo abaixo:")
        status_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_info.setStyleSheet("font-size: 12px; color: #888; padding-bottom: 10px;")
        layout.addWidget(status_info)
        
        # Lista de PDFs (sem progresso geral)
        pdfs_group = QGroupBox("📋 Status de Processamento dos Arquivos PDF")
        pdfs_layout = QVBoxLayout(pdfs_group)
        
        # Scroll area para PDFs
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(4)
        
        # Cria widgets para cada PDF
        for pdf_file in pdf_files:
            filename = Path(pdf_file).name
            pdf_frame = self._create_pdf_frame(filename)
            scroll_layout.addWidget(pdf_frame)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        pdfs_layout.addWidget(scroll)
        
        layout.addWidget(pdfs_group)
        
        # Botão fechar (desabilitado durante processamento)
        self.close_button = QPushButton("Fechar")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        self.close_button.setFixedHeight(35)
        layout.addWidget(self.close_button)
    
    def _create_pdf_frame(self, filename):
        """Cria frame para um PDF individual"""
        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.StyledPanel)
        frame.setFixedHeight(50)  # Altura fixa para evitar oscilações
        
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)
        
        # Ícone de status
        icon = QLabel("⏳")
        icon.setStyleSheet("font-size: 16px;")
        icon.setFixedSize(24, 24)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Nome do arquivo (truncado se muito longo)
        display_name = filename
        if len(display_name) > 45:
            display_name = display_name[:42] + "..."
        
        name_label = QLabel(f"📄 {display_name}")
        name_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        name_label.setFixedWidth(350)  # Largura fixa
        name_label.setToolTip(f"📄 {filename}")  # Tooltip com nome completo
        
        # Progress bar
        progress = QProgressBar()
        progress.setFixedSize(120, 18)
        progress.setMinimum(0)
        progress.setMaximum(100)
        progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 3px;
                text-align: center;
                font-size: 10px;
            }
            QProgressBar::chunk {
                background-color: #2cc985;
                border-radius: 2px;
            }
        """)
        
        # Status com largura fixa para evitar oscilações
        status = QLabel("Aguardando...")
        status.setStyleSheet("color: #888; font-size: 10px;")
        status.setFixedWidth(180)  # Largura fixa para evitar redimensionamento
        status.setWordWrap(False)  # Sem quebra de linha
        status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        layout.addWidget(icon)
        layout.addWidget(name_label)
        layout.addWidget(progress)
        layout.addWidget(status)
        layout.addStretch()  # Preenche espaço restante
        
        self.pdf_widgets[filename] = {
            'icon': icon,
            'progress': progress,
            'status': status
        }
        
        return frame
    
    @pyqtSlot(str, int, str)
    def update_pdf_progress(self, filename, progress, message):
        """Atualiza progresso de um PDF específico"""
        if filename in self.pdf_widgets:
            widgets = self.pdf_widgets[filename]

            # Atualiza progresso
            widgets['progress'].setValue(progress)
            widgets['progress'].setToolTip(f"{progress}% concluído")

            waiting_message = message.strip().lower().startswith("aguardando")
            widgets['progress'].setVisible(not waiting_message)

            # Trunca mensagem se muito longa para evitar oscilações
            display_message = message
            if len(display_message) > 25:
                display_message = display_message[:22] + "..."
            
            widgets['status'].setText(display_message)
            widgets['status'].setToolTip(message)  # Tooltip com mensagem completa
            
            # Atualiza ícone baseado no status (incluindo atenção)
            if "✅" in message:
                widgets['icon'].setText("✅")
                widgets['icon'].setStyleSheet("font-size: 16px; color: #2cc985;")
            elif "⚠️" in message:
                widgets['icon'].setText("⚠️")
                widgets['icon'].setStyleSheet("font-size: 16px; color: #ff9800;")
            elif "❌" in message:
                widgets['icon'].setText("❌")
                widgets['icon'].setStyleSheet("font-size: 16px; color: #f44336;")
            elif waiting_message:
                widgets['icon'].setText("⏳")
                widgets['icon'].setStyleSheet("font-size: 16px; color: #ffa726;")
            elif progress > 0:
                widgets['icon'].setText("🔄")
                widgets['icon'].setStyleSheet("font-size: 16px; color: #1f538d;")
            else:
                widgets['icon'].setText("🔄")
                widgets['icon'].setStyleSheet("font-size: 16px; color: #1f538d;")
    
    @pyqtSlot()
    def handle_batch_completed(self):
        """Habilita botão fechar quando processamento termina"""
        # Atualiza header para mostrar conclusão
        total_pdfs = len(self.pdf_widgets)
        self.header.setText(f"✅ Processamento Concluído - {total_pdfs} PDFs")
        self.header.setStyleSheet("font-size: 16px; font-weight: bold; padding: 15px; color: #2cc985;")
        
        self.close_button.setEnabled(True)
        self.close_button.setText("✅ Fechar")
        self.close_button.setStyleSheet("""
            QPushButton {
                background-color: #2cc985;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                color: white;
                font-weight: bold;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #259b6e;
            }
        """)

class HistoryItemWidget(QWidget):
    """Widget personalizado para item do histórico"""
    
    details_requested = pyqtSignal(object)  # HistoryEntry
    file_open_requested = pyqtSignal(object)  # HistoryEntry
    
    def __init__(self, entry: HistoryEntry):
        super().__init__()
        self.entry = entry
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)
        
        # Ícone de status com atenção
        if entry.success:
            if entry.has_attention:
                status_icon = "⚠️"
                status_color = "#ff9800"
            else:
                status_icon = "✅"
                status_color = "#2cc985"
        else:
            status_icon = "❌"
            status_color = "#f44336"
        
        status_label = QLabel(status_icon)
        status_label.setStyleSheet(f"font-size: 18px; color: {status_color};")
        status_label.setFixedSize(24, 24)
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Informações principais
        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)
        
        ficha_results = get_ficha_results_from_payload(entry.result_data)
        ficha_outputs = flatten_ficha_outputs(entry.result_data) if entry.result_data else []
        processor_name = entry.result_data.get('processor') if entry.result_data else None

        if entry.success and ficha_results:
            names = collect_ficha_person_names(entry.result_data)
            if names:
                person_name = ", ".join(names)
            else:
                person_name = Path(entry.pdf_file).stem
            display_name = f"Ficha Financeira • {person_name}"
        elif entry.success and processor_name == 'planilha_dados':
            display_name = f"Planilha de Dados • {Path(entry.pdf_file).stem}"
        elif entry.success and entry.result_data.get('arquivo_final'):
            display_name = Path(entry.result_data['arquivo_final']).stem
        else:
            display_name = Path(entry.pdf_file).stem
        
        # Indicador apenas de atenção, se necessário
        if entry.has_attention:
            display_name += " (ATENÇÃO)"
        
        # Truncar nome se muito longo
        if len(display_name) > 60:
            display_name = display_name[:57] + "..."
        
        name_label = QLabel(display_name)
        name_label.setStyleSheet("font-weight: bold; font-size: 13px; color: white;")
        name_label.setToolTip(display_name)
        
        # Resultado e timestamp
        if entry.success:
            if ficha_outputs and processor_name != 'planilha_dados':
                count_outputs = len(ficha_outputs)
                result_text = f"✓ {count_outputs} arquivo{'s' if count_outputs != 1 else ''} gerado{'s' if count_outputs != 1 else ''}"
                pdf_count = entry.result_data.get('pdf_count') or len(ficha_results)
                if pdf_count:
                    result_text += f" • {pdf_count} PDF{'s' if pdf_count != 1 else ''} consolidados"
            elif processor_name == 'planilha_dados':
                outputs = entry.result_data.get('outputs', [])
                count_outputs = len(outputs)
                result_text = f"✓ {count_outputs} CSV{'s' if count_outputs != 1 else ''} gerado{'s' if count_outputs != 1 else ''}"
            else:
                result_text = f"✓ {entry.result_data.get('total_extracted', 0)} períodos processados"
                if entry.result_data.get('person_name'):
                    person_name = entry.result_data['person_name']
                    if len(person_name) > 25:
                        person_name = person_name[:22] + "..."
                    result_text += f" • {person_name}"

                if entry.has_attention:
                    result_text += " • ⚠️ COM OBSERVAÇÕES"
        else:
            error_msg = entry.result_data.get('error', 'Erro desconhecido')
            if len(error_msg) > 40:
                error_msg = error_msg[:37] + "..."
            result_text = f"✗ {error_msg}"
        
        result_text += f" • {entry.timestamp.strftime('%d/%m/%Y %H:%M')}"
        
        result_label = QLabel(result_text)
        result_label.setStyleSheet("font-size: 11px; color: #aaa;")
        result_label.setToolTip(f"Processado em: {entry.timestamp.strftime('%d/%m/%Y %H:%M:%S')}")
        
        info_layout.addWidget(name_label)
        info_layout.addWidget(result_label)
        
        # Botões de ação
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(6)
        
        if entry.success:
            open_btn = QPushButton("📂")
            if ficha_outputs:
                open_btn.setToolTip("Abrir pasta com os CSVs gerados")
            else:
                open_btn.setToolTip("Abrir arquivo Excel")
            open_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #259b6e;
                }
            """)
            open_btn.clicked.connect(lambda: self.file_open_requested.emit(self.entry))
            buttons_layout.addWidget(open_btn)
        
        details_btn = QPushButton("📝")
        details_btn.setToolTip("Ver logs detalhados")
        details_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
            }
            QPushButton:hover {
                background-color: #2a5f9e;
            }
        """)
        details_btn.clicked.connect(lambda: self.details_requested.emit(self.entry))
        buttons_layout.addWidget(details_btn)
        
        layout.addWidget(status_label)
        layout.addLayout(info_layout, 1)
        layout.addLayout(buttons_layout)

class HistoryDetailsDialog(QDialog):
    """Dialog para mostrar detalhes do histórico"""
    
    def __init__(self, entry: HistoryEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle("📝 Detalhes do Histórico")
        self.setModal(True)
        
        # Define tamanho fixo e desabilita redimensionamento/maximizar  
        self.setFixedSize(750, 650)  # Aumentado para incluir seção de atenção
        self.setWindowFlags(
            Qt.WindowType.Dialog | 
            Qt.WindowType.WindowCloseButtonHint
        )
        
        layout = QVBoxLayout(self)
        
        # Header compacto
        header_frame = QFrame()
        header_layout = QVBoxLayout(header_frame)
        
        # Título (simples, sem indicação de lote)
        ficha_names = collect_ficha_person_names(entry.result_data)
        if entry.success and ficha_names:
            title_core = ", ".join(ficha_names)
        else:
            title_core = Path(entry.pdf_file).stem
        title_text = f"📄 {title_core}"
        if entry.has_attention:
            title_text += " ⚠️"
        
        title_label = QLabel(title_text)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Informações resumidas
        info_parts = []
        
        if entry.success:
            if entry.has_attention:
                info_parts.append("⚠️ Sucesso com Atenção")
            else:
                info_parts.append("✅ Sucesso")
        else:
            info_parts.append("❌ Erro")
        
        info_parts.append(f"🕒 {entry.timestamp.strftime('%d/%m/%Y %H:%M:%S')}")
        
        ficha_results = get_ficha_results_from_payload(entry.result_data)
        ficha_outputs = flatten_ficha_outputs(entry.result_data)

        if entry.success and entry.result_data:
            if ficha_outputs:
                info_parts.append(
                    f"📂 {len(ficha_outputs)} arquivo{'s' if len(ficha_outputs) != 1 else ''} gerado{'s' if len(ficha_outputs) != 1 else ''}"
                )
                pdf_count = entry.result_data.get('pdf_count') or len(ficha_results)
                if pdf_count:
                    info_parts.append(f"📄 {pdf_count} PDF{'s' if pdf_count != 1 else ''} consolidados")
            else:
                if entry.result_data.get('total_extracted') is not None:
                    info_parts.append(f"📊 {entry.result_data['total_extracted']} períodos")

                if entry.result_data.get('person_name'):
                    info_parts.append(f"👤 {entry.result_data['person_name']}")

                if entry.result_data.get('arquivo_final'):
                    arquivo_nome = Path(entry.result_data['arquivo_final']).name
                    info_parts.append(f"💾 {arquivo_nome}")
        
        info_text = " • ".join(info_parts)
        info_label = QLabel(info_text)
        info_label.setStyleSheet("font-size: 11px; color: #888;")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        
        header_layout.addWidget(title_label)
        header_layout.addWidget(info_label)
        layout.addWidget(header_frame)
        
        # Seção de atenção (NOVA) - prioritária
        if entry.has_attention and entry.attention_details:
            attention_group = QGroupBox("⚠️ PONTOS DE ATENÇÃO")
            attention_group.setProperty("class", "attention")
            attention_layout = QVBoxLayout(attention_group)
            
            # Informação destacada
            attention_info = QLabel(
                "🔍 Durante o processamento foram detectadas situações que requerem atenção:"
            )
            attention_info.setStyleSheet("color: #ff9800; font-weight: bold; font-size: 12px;")
            attention_info.setWordWrap(True)
            attention_layout.addWidget(attention_info)
            
            # Lista os pontos de atenção com informações estruturadas
            for i, detail in enumerate(entry.attention_details, 1):
                attention_item = QFrame()
                attention_item.setStyleSheet("""
                    QFrame {
                        background-color: #3d2d1a;
                        border: 1px solid #ff9800;
                        border-radius: 4px;
                        padding: 8px;
                        margin: 2px;
                    }
                """)
                
                attention_item_layout = QVBoxLayout(attention_item)
                attention_item_layout.setContentsMargins(8, 4, 8, 4)
                
                # Título do ponto de atenção
                titulo = QLabel(f"📋 Ponto {i}: {detail.get('periodo', 'N/A')} ({detail.get('folha_type', 'N/A')})")
                titulo.setStyleSheet("color: #ff9800; font-weight: bold; font-size: 11px;")
                attention_item_layout.addWidget(titulo)
                
                # Processa cada detalhe de atenção
                detalhes_list = detail.get('detalhes', [])
                
                # Se não há detalhes estruturados, mostra informação para dados antigos
                if not detalhes_list:
                    info_label = QLabel("💡 Dados processados com versão anterior - detalhes não disponíveis")
                    info_label.setStyleSheet("color: #ffcc80; font-size: 10px; margin-left: 15px; font-style: italic;")
                    attention_item_layout.addWidget(info_label)
                    
                    help_label = QLabel("ℹ️ Processe novamente o PDF para ver informações detalhadas")
                    help_label.setStyleSheet("color: #888; font-size: 9px; margin-left: 15px; font-style: italic;")
                    attention_item_layout.addWidget(help_label)
                    attention_layout.addWidget(attention_item)
                    continue
                
                for detalhe_raw in detalhes_list:
                    if isinstance(detalhe_raw, dict):
                        # Informação estruturada
                        tipo = detalhe_raw.get('tipo', 'desconhecido')
                        
                        if tipo == 'soma_automatica':
                            # Soma automática (PREMIO PROD, HE 100%, etc.)
                            descricao = detalhe_raw.get('descricao', 'CÓDIGOS ESPECÍFICOS')
                            codigos = detalhe_raw.get('codigos', [])
                            valor_somado = detalhe_raw.get('valor_somado', 0)
                            valores_individuais = detalhe_raw.get('valores_individuais', {})
                            
                            detalhe_label = QLabel(f"💡 SOMA AUTOMÁTICA - {descricao}")
                            detalhe_label.setStyleSheet("color: #ffcc80; font-weight: bold; font-size: 10px; margin-left: 15px;")
                            attention_item_layout.addWidget(detalhe_label)
                            
                            # Mostra códigos e valor final
                            codigos_str = ' + '.join(codigos)
                            codigos_label = QLabel(f"📋 {codigos_str} = {valor_somado}")
                            codigos_label.setStyleSheet("color: #ffcc80; font-size: 10px; margin-left: 25px;")
                            attention_item_layout.addWidget(codigos_label)
                            
                            # Mostra valores individuais
                            for codigo, valor in valores_individuais.items():
                                valor_label = QLabel(f"   • {codigo}: {valor}")
                                valor_label.setStyleSheet("color: #ffcc80; font-size: 9px; margin-left: 35px;")
                                attention_item_layout.addWidget(valor_label)
                        
                        elif tipo == 'duplicidade_descricao':
                            # Duplicidade por descrição (descoberta automática)
                            descricao = detalhe_raw.get('descricao', 'DESCRIÇÃO DESCONHECIDA')
                            codigos = detalhe_raw.get('codigos', [])
                            valores_individuais = detalhe_raw.get('valores_individuais', {})
                            colunas = detalhe_raw.get('colunas_afetadas', [])
                            
                            detalhe_label = QLabel(f"🔍 DUPLICIDADE DETECTADA - {descricao}")
                            detalhe_label.setStyleSheet("color: #ffcc80; font-weight: bold; font-size: 10px; margin-left: 15px;")
                            attention_item_layout.addWidget(detalhe_label)
                            
                            # Mostra códigos
                            codigos_str = ' + '.join(codigos)
                            codigos_label = QLabel(f"📋 {codigos_str} (verificação manual recomendada)")
                            codigos_label.setStyleSheet("color: #ffcc80; font-size: 10px; margin-left: 25px;")
                            attention_item_layout.addWidget(codigos_label)
                            
                            # Mostra colunas afetadas
                            if colunas:
                                colunas_label = QLabel(f"📊 Colunas: {', '.join(colunas)}")
                                colunas_label.setStyleSheet("color: #ffcc80; font-size: 9px; margin-left: 25px;")
                                attention_item_layout.addWidget(colunas_label)
                            
                            # Mostra valores preservados individualmente  
                            for codigo, valor in valores_individuais.items():
                                valor_label = QLabel(f"   • {codigo}: {valor} (preservado)")
                                valor_label.setStyleSheet("color: #ffcc80; font-size: 9px; margin-left: 35px;")
                                attention_item_layout.addWidget(valor_label)
                        
                        else:
                            # Formato não reconhecido - mostra detalhes como texto
                            detalhes_text = detalhe_raw.get('detalhes', str(detalhe_raw))
                            detalhe_label = QLabel(f"💡 {detalhes_text}")
                            detalhe_label.setStyleSheet("color: #ffcc80; font-size: 10px; margin-left: 15px;")
                            detalhe_label.setWordWrap(True)
                            attention_item_layout.addWidget(detalhe_label)
                    
                    else:
                        # String simples - compatibilidade com versões anteriores
                        detalhe_label = QLabel(f"💡 {detalhe_raw}")
                        detalhe_label.setStyleSheet("color: #ffcc80; font-size: 10px; margin-left: 15px;")
                        detalhe_label.setWordWrap(True)
                        attention_item_layout.addWidget(detalhe_label)
                
                attention_layout.addWidget(attention_item)
            
            # Explicação
            explanation = QLabel(
                "ℹ️ Estes pontos de atenção não impedem o funcionamento da planilha, "
                "mas indicam situações especiais que foram tratadas automaticamente."
            )
            explanation.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
            explanation.setWordWrap(True)
            attention_layout.addWidget(explanation)

            layout.addWidget(attention_group)

        if entry.success and ficha_results:
            outputs_group = QGroupBox("📂 Arquivos gerados")
            outputs_layout = QVBoxLayout(outputs_group)

            for result in ficha_results:
                pdf_file = result.get('pdf_file')
                pdf_name = Path(pdf_file).name if pdf_file else result.get('person_name', 'PDF')
                header = QLabel(f"📄 {pdf_name}")
                header.setStyleSheet("color: #fff; font-weight: bold; font-size: 11px;")
                header.setWordWrap(True)
                outputs_layout.addWidget(header)

                for item in result.get('outputs', []):
                    label = QLabel(f"• {item.get('label', 'Arquivo')}: {item.get('path', '')}")
                    label.setStyleSheet("color: #ccc; font-size: 11px; margin-left: 15px;")
                    label.setWordWrap(True)
                    outputs_layout.addWidget(label)

                folder = result.get('output_folder')
                if folder:
                    folder_label = QLabel(f"📁 Pasta: {folder}")
                    folder_label.setStyleSheet("color: #888; font-size: 10px; font-style: italic; margin-left: 15px;")
                    folder_label.setWordWrap(True)
                    outputs_layout.addWidget(folder_label)

            layout.addWidget(outputs_group)
        elif entry.success and entry.result_data.get('processor') == 'planilha_dados':
            outputs_group = QGroupBox("📂 Arquivos gerados")
            outputs_layout = QVBoxLayout(outputs_group)

            outputs = entry.result_data.get('outputs', [])
            for item in outputs:
                label = QLabel(f"• {item.get('label', 'Arquivo')}: {item.get('path', '')}")
                label.setStyleSheet("color: #ccc; font-size: 11px; margin-left: 15px;")
                label.setWordWrap(True)
                outputs_layout.addWidget(label)

            folder = entry.result_data.get('output_folder')
            if folder:
                folder_label = QLabel(f"📁 Pasta: {folder}")
                folder_label.setStyleSheet("color: #888; font-size: 10px; font-style: italic; margin-left: 15px;")
                folder_label.setWordWrap(True)
                outputs_layout.addWidget(folder_label)

            layout.addWidget(outputs_group)

        # Área de logs (ajustada)
        logs_group = QGroupBox("📄 Logs Detalhados")
        logs_layout = QVBoxLayout(logs_group)
        
        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        
        # Font monospace
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.logs_text.setFont(font)
        
        self._populate_logs()
        logs_layout.addWidget(self.logs_text)
        layout.addWidget(logs_group, 1)  # Máximo stretch
        
        # Botões
        buttons_layout = QHBoxLayout()
        
        if entry.success and entry.result_data.get('excel_path'):
            open_btn = QPushButton("📂 Abrir Arquivo")
            open_btn.clicked.connect(self._open_file)
            buttons_layout.addWidget(open_btn)
        
        buttons_layout.addStretch()
        
        close_btn = QPushButton("✖️ Fechar")
        close_btn.clicked.connect(self.accept)
        buttons_layout.addWidget(close_btn)
        
        layout.addLayout(buttons_layout)
    
    def _populate_logs(self):
        """Popula área de logs com informações resumidas"""
        header_info = [
            f"📄 Arquivo: {self.entry.pdf_file}",
            f"🕒 Processado em: {self.entry.timestamp.strftime('%d/%m/%Y %H:%M:%S')}",
        ]
        
        if self.entry.success and self.entry.result_data:
            if self.entry.result_data.get('person_name'):
                header_info.append(f"👤 Pessoa detectada: {self.entry.result_data['person_name']}")
            
            if self.entry.result_data.get('total_extracted') is not None:
                total = self.entry.result_data['total_extracted']
                folha_normal = self.entry.result_data.get('folha_normal_periods', 0)
                salario_13 = self.entry.result_data.get('salario_13_periods', 0)
                header_info.append(f"📊 Resultado: {total} períodos processados (FOLHA NORMAL: {folha_normal}, 13º SALÁRIO: {salario_13})")
            
            # Indica se há atenção
            if self.entry.has_attention:
                header_info.append(f"⚠️ ATENÇÃO: Processamento com observações especiais")
            
            if self.entry.result_data.get('arquivo_final'):
                header_info.append(f"💾 Arquivo final: {self.entry.result_data['arquivo_final']}")
                
            if self.entry.result_data.get('total_pages'):
                header_info.append(f"📑 Total de páginas analisadas: {self.entry.result_data['total_pages']}")
        else:
            if self.entry.result_data and self.entry.result_data.get('error'):
                header_info.append(f"❌ Erro: {self.entry.result_data['error']}")
        
        # Informações sobre processamento (sem logs extensos)
        header_info.append("")
        header_info.append("📋 RESUMO DO PROCESSAMENTO:")
        header_info.append(f"Status: {'✅ Sucesso' if self.entry.success else '❌ Falha'}")
        
        if self.entry.has_attention:
            header_info.append("⚠️ Observações: Situações especiais detectadas e tratadas automaticamente")
        
        # Apenas informações resumidas, sem logs extensos
        content = "\n".join(header_info)
        self.logs_text.setPlainText(content)
    
    def _open_file(self):
        """Abre arquivo Excel associado"""
        try:
            file_path = self.entry.result_data.get('excel_path')
            if not file_path:
                arquivo_rel = self.entry.result_data.get('arquivo_final')
                if arquivo_rel:
                    # Tenta construir caminho relativo
                    file_path = Path.cwd() / arquivo_rel
            
            if not file_path:
                QMessageBox.warning(self, "Arquivo Não Encontrado", "Caminho do arquivo não está disponível.")
                return
            
            file_path = Path(file_path)
            if not file_path.exists():
                QMessageBox.warning(self, "Arquivo Não Encontrado", f"O arquivo não foi encontrado:\n\n{file_path}")
                return
            
            if sys.platform.startswith('win'):
                os.startfile(file_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(file_path)])
            else:
                subprocess.Popen(['xdg-open', str(file_path)])
        
        except Exception as e:
            QMessageBox.critical(self, "Erro ao Abrir Arquivo", f"Não foi possível abrir o arquivo:\n\n{e}")

class MainWindow(QMainWindow):
    """Janela principal da aplicação"""

    def __init__(
        self,
        project_manager: ProjectManager,
        project: ProjectMetadata,
        on_back: Callable[[], None],
    ):
        super().__init__()

        self.project_manager = project_manager
        self.project = project
        self.on_back_callback = on_back
        self.project_model = project.model

        if self.project_model == ProjectManager.MODEL_RECIBO:
            window_title = f"Recibo Modelo 1 • {self.project.name}"
        else:
            window_title = f"Ficha Financeira • {self.project.name}"

        self.setWindowTitle(window_title)

        # Define tamanho fixo e desabilita redimensionamento/maximizar
        self.setFixedSize(950, 600)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint | 
            Qt.WindowType.WindowMinimizeButtonHint
        )
        
        # Estado da aplicação - INICIALIZAR PRIMEIRO
        self.selected_files = []
        self.trabalho_dir = None
        self.processing = False
        self.current_logs = []  # Inicializar antes de qualquer callback
        self.processing_history = []
        
        # Processamento
        self.processor_thread = None
        self.progress_dialog = None
        
        # Configurações
        self.max_threads = 3
        self.verbose_mode = False
        self.preferred_sheet = ""
        self.cartoes_time_mode = (
            FichaFinanceiraProcessor.CARTOES_TIME_MODE_DECIMAL
            if self.project_model == ProjectManager.MODEL_FICHA
            else ""
        )
        self.horas_trabalhadas_time_mode = (
            FichaFinanceiraProcessor.CARTOES_TIME_MODE_DECIMAL
            if self.project_model == ProjectManager.MODEL_FICHA
            else ""
        )

        # Gerenciador de persistência
        self.persistence = PersistenceManager(project_id=self.project.project_id)

        # Timer para salvar configurações - CRIAR ANTES DA INTERFACE
        self.save_timer = QTimer()
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save_current_config)
        
        # Cria interface (depois de inicializar todas as variáveis)
        self.create_interface()
        
        # Timer para carregar dados persistidos após interface pronta
        QTimer.singleShot(100, self.load_persisted_data)
    
    def create_interface(self):
        """Cria interface principal"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setSpacing(10)
        
        # Header
        self.create_header(layout)
        
        # Tabs
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Cria abas
        self.create_processing_tab()
        self.create_history_tab()
        self.create_settings_tab()

        # Status bar
        self.statusBar().showMessage("Sistema iniciado - v4.0.1 PyQt6")

    def _format_project_header(self) -> str:
        if self.project_model == ProjectManager.MODEL_RECIBO:
            model_name = "Recibo Modelo 1"
        elif self.project_model == ProjectManager.MODEL_FICHA:
            model_name = "Ficha Financeira"
        else:
            model_name = "Planilha de Dados"
        return f"{self.project.name} • {model_name}"

    def _toggle_project_panel(self):
        expanded = self.project_toggle_button.isChecked()
        self.project_panel.setVisible(expanded)
        self.project_toggle_button.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )

    def create_header(self, layout):
        """Cria header da aplicação com dados do projeto."""
        header_frame = QFrame()
        header_layout = QVBoxLayout(header_frame)
        header_layout.setSpacing(6)
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.project_header_label = QLabel(self._format_project_header())
        self.project_header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.project_header_label.setStyleSheet("font-size: 14px; font-weight: 600; padding: 4px;")

        header_layout.addWidget(self.project_header_label)

        toggle_layout = QHBoxLayout()
        toggle_layout.setContentsMargins(0, 0, 0, 0)

        self.project_toggle_button = QToolButton()
        self.project_toggle_button.setText("📁 Dados do projeto")
        self.project_toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.project_toggle_button.setCheckable(True)
        self.project_toggle_button.setChecked(False)
        self.project_toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.project_toggle_button.clicked.connect(self._toggle_project_panel)

        toggle_layout.addWidget(self.project_toggle_button)
        toggle_layout.addStretch()
        header_layout.addLayout(toggle_layout)

        self.project_panel = QFrame()
        self.project_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self.project_panel.setStyleSheet("QFrame { border: 1px solid #333; border-radius: 6px; }")

        project_layout = QVBoxLayout(self.project_panel)
        project_layout.setSpacing(8)
        project_layout.setContentsMargins(12, 10, 12, 12)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        name_label = QLabel("Nome do projeto:")
        top_row.addWidget(name_label)

        self.project_name_edit = QLineEdit(self.project.name)
        self.project_name_edit.textChanged.connect(self._mark_project_dirty)
        top_row.addWidget(self.project_name_edit, 1)

        model_text_label = QLabel("Modelo:")
        top_row.addWidget(model_text_label)

        self.model_value_label = QLabel(
            "Recibo Modelo 1" if self.project_model == ProjectManager.MODEL_RECIBO else "Ficha Financeira"
        )
        self.model_value_label.setStyleSheet("color: #ccc;")
        top_row.addWidget(self.model_value_label)

        top_row.addStretch()
        project_layout.addLayout(top_row)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        start_label = QLabel("Início do período:")
        bottom_row.addWidget(start_label)

        start_period_layout = QHBoxLayout()
        start_period_layout.setSpacing(6)
        self.start_month_combo = QComboBox()
        self.start_month_combo.addItems(MONTH_NAMES)
        self.start_year_spin = QSpinBox()
        self.start_year_spin.setRange(1990, 2100)
        start_period_layout.addWidget(self.start_month_combo)
        start_period_layout.addWidget(self.start_year_spin)
        bottom_row.addLayout(start_period_layout)

        end_label = QLabel("Fim do período:")
        bottom_row.addWidget(end_label)

        end_period_layout = QHBoxLayout()
        end_period_layout.setSpacing(6)
        self.end_month_combo = QComboBox()
        self.end_month_combo.addItems(MONTH_NAMES)
        self.end_year_spin = QSpinBox()
        self.end_year_spin.setRange(1990, 2100)
        end_period_layout.addWidget(self.end_month_combo)
        end_period_layout.addWidget(self.end_year_spin)
        bottom_row.addLayout(end_period_layout)

        bottom_row.addStretch()

        self.save_project_button = QPushButton("💾 Salvar projeto")
        self.save_project_button.setEnabled(False)
        self.save_project_button.clicked.connect(self.save_project_changes)
        bottom_row.addWidget(self.save_project_button)

        project_layout.addLayout(bottom_row)

        header_layout.addWidget(self.project_panel)
        self.project_panel.setVisible(False)

        layout.addWidget(header_frame)

        # Inicializa valores do período
        self._load_project_metadata()
        self._toggle_project_panel()

    def _load_project_metadata(self):
        """Carrega os dados do projeto para os campos do header."""
        self.project_name_edit.setText(self.project.name)
        self.start_month_combo.setCurrentIndex(self.project.start_month - 1)
        self.start_year_spin.setValue(self.project.start_year)
        self.end_month_combo.setCurrentIndex(self.project.end_month - 1)
        self.end_year_spin.setValue(self.project.end_year)

        for widget in [
            self.start_month_combo,
            self.start_year_spin,
            self.end_month_combo,
            self.end_year_spin,
        ]:
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._mark_project_dirty)
            else:
                widget.valueChanged.connect(self._mark_project_dirty)

        self.save_project_button.setEnabled(False)

    def _mark_project_dirty(self):
        self.save_project_button.setEnabled(True)

    def _get_project_period(self) -> Tuple[date, date]:
        start = date(
            self.start_year_spin.value(),
            self.start_month_combo.currentIndex() + 1,
            1,
        )
        end = date(
            self.end_year_spin.value(),
            self.end_month_combo.currentIndex() + 1,
            1,
        )
        return start, end

    def save_project_changes(self):
        try:
            name = self.project_name_edit.text().strip()
            start_month = self.start_month_combo.currentIndex() + 1
            start_year = self.start_year_spin.value()
            end_month = self.end_month_combo.currentIndex() + 1
            end_year = self.end_year_spin.value()

            updated = self.project_manager.update_project(
                self.project.project_id,
                name=name,
                start_month=start_month,
                start_year=start_year,
                end_month=end_month,
                end_year=end_year,
            )

            self.project = updated
            self.save_project_button.setEnabled(False)
            self.project_header_label.setText(self._format_project_header())

            if self.project_model == ProjectManager.MODEL_RECIBO:
                self.setWindowTitle(f"Recibo Modelo 1 • {self.project.name}")
            elif self.project_model == ProjectManager.MODEL_FICHA:
                self.setWindowTitle(f"Ficha Financeira • {self.project.name}")
            else:
                self.setWindowTitle(f"Planilha de Dados • {self.project.name}")

            QMessageBox.information(
                self,
                "Projeto atualizado",
                "As informações do projeto foram salvas com sucesso.",
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Não foi possível salvar", str(exc))

    def create_processing_tab(self):
        """Cria aba de processamento"""
        processing_widget = QWidget()
        layout = QVBoxLayout(processing_widget)
        
        # Configuração do diretório
        self.config_group = QGroupBox("📁 Configuração do Diretório de Trabalho")
        config_layout = QVBoxLayout(self.config_group)

        help_label = QLabel("Selecione a pasta que contém o arquivo MODELO.xlsm:")
        help_label.setStyleSheet("color: #888;")
        config_layout.addWidget(help_label)
        
        dir_layout = QHBoxLayout()
        self.dir_entry = QLineEdit()
        self.dir_entry.setPlaceholderText("Caminho para o diretório de trabalho...")
        self.dir_entry.textChanged.connect(self._on_dir_changed)
        
        self.dir_button = QPushButton("📂 Selecionar")
        self.dir_button.clicked.connect(self.select_directory)
        
        self.config_status = QLabel("⚠️ Configuração necessária")
        self.config_status.setStyleSheet("color: #ffa726; font-weight: bold;")
        
        dir_layout.addWidget(self.dir_entry, 1)
        dir_layout.addWidget(self.dir_button)
        dir_layout.addWidget(self.config_status)
        
        config_layout.addLayout(dir_layout)
        layout.addWidget(self.config_group)

        # Seleção de arquivos
        self.files_group = QGroupBox("📎 Seleção de Arquivos PDF")
        files_layout = QVBoxLayout(self.files_group)
        
        # Header com contador
        header_layout = QHBoxLayout()
        files_title = QLabel("Arquivos selecionados:")
        self.file_counter_label = QLabel("0 arquivos")
        self.file_counter_label.setStyleSheet("color: #888;")
        
        header_layout.addWidget(files_title)
        header_layout.addStretch()
        header_layout.addWidget(self.file_counter_label)
        files_layout.addLayout(header_layout)
        
        # Botões de ação
        actions_layout = QHBoxLayout()
        
        self.select_btn = QPushButton("📂 Selecionar PDFs")
        self.select_btn.clicked.connect(self.select_pdfs)

        clear_btn = QPushButton("🗑️ Limpar")
        clear_btn.setProperty("class", "secondary")
        clear_btn.clicked.connect(self.clear_selection)

        self.process_btn = QPushButton("🚀 Processar PDFs")
        self.process_btn.setProperty("class", "success")
        self.process_btn.clicked.connect(self.process_pdfs)
        self.process_btn.setEnabled(False)

        actions_layout.addWidget(self.select_btn)
        actions_layout.addWidget(clear_btn)
        actions_layout.addStretch()
        actions_layout.addWidget(self.process_btn)

        files_layout.addLayout(actions_layout)
        
        # Drop zone
        self.drop_zone = DropZoneWidget()
        self.drop_zone.files_dropped.connect(self.handle_dropped_files)
        files_layout.addWidget(self.drop_zone)
        
        # Lista de arquivos
        self.files_list = QListWidget()
        self.files_list.setMaximumHeight(200)
        self.files_list.setStyleSheet("""
            QListWidget {
                background-color: #2b2b2b;
                border: 1px solid #444;
                border-radius: 4px;
            }
            QListWidget::item {
                border-bottom: 1px solid #444;
                padding: 2px;
            }
            QListWidget::item:hover {
                background-color: #333;
            }
        """)
        files_layout.addWidget(self.files_list)

        layout.addWidget(self.files_group)
        layout.addStretch()

        self.tab_widget.addTab(processing_widget, "📄 Processamento")

        if self.project_model == ProjectManager.MODEL_FICHA:
            self.config_group.setTitle("📁 Pasta de saída dos CSVs")
            help_label.setText("Selecione a pasta onde os arquivos CSV serão salvos:")
            self.dir_entry.setPlaceholderText("Caminho para a pasta de saída...")
            self.process_btn.setText("🚀 PROCESSAR")
            self.select_btn.setText("📂 Selecionar PDFs da ficha")
            self.drop_zone.label.setText("🎯 Arraste PDFs da ficha financeira aqui ou clique para selecionar")
            self.files_group.setTitle("📎 PDFs da ficha financeira")
        elif self.project_model == ProjectManager.MODEL_PLANILHA:
            self.config_group.setTitle("📁 Pasta de saída dos CSVs")
            help_label.setText("Selecione a pasta onde os CSVs de cada planilha serão gravados:")
            self.dir_entry.setPlaceholderText("Caminho para a pasta de saída...")
            self.process_btn.setText("🚀 Processar planilhas")
            self.select_btn.setText("📂 Selecionar planilhas")
            self.drop_zone.label.setText("🎯 Arraste planilhas XLS/XLSX/XLSM aqui ou clique para selecionar")
            self.files_group.setTitle("📎 Seleção de Planilhas")
            self.drop_zone.allowed_extensions = ['.xls', '.xlsx', '.xlsm']
    
    def create_history_tab(self):
        """Cria aba de histórico"""
        history_widget = QWidget()
        layout = QVBoxLayout(history_widget)
        
        # Header com controles
        header_layout = QHBoxLayout()
        
        title = QLabel("📊 Histórico de Processamentos")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        self.history_status_label = QLabel("Nenhum PDF no histórico")
        self.history_status_label.setStyleSheet("color: #888;")
        
        clear_history_btn = QPushButton("🗑️ Limpar Histórico")
        clear_history_btn.setProperty("class", "secondary")
        clear_history_btn.clicked.connect(self.clear_history)
        
        header_layout.addWidget(title)
        header_layout.addWidget(self.history_status_label, 1)
        header_layout.addWidget(clear_history_btn)
        
        layout.addLayout(header_layout)
        
        # Lista de histórico (virtualizada automaticamente pelo QListWidget)
        self.history_list = QListWidget()
        layout.addWidget(self.history_list)
        
        self.tab_widget.addTab(history_widget, "📊 Histórico")
    
    def create_settings_tab(self):
        """Cria aba de configurações"""
        settings_widget = QWidget()
        layout = QVBoxLayout(settings_widget)
        
        # Processamento paralelo
        parallel_group = QGroupBox("🚀 Processamento (Sempre Paralelo)")
        parallel_layout = QFormLayout(parallel_group)
        
        parallel_desc = QLabel("Configure quantos PDFs podem ser processados simultaneamente. O sistema sempre usa ThreadPoolExecutor para garantir comportamento consistente.")
        parallel_desc.setStyleSheet("color: #888;")
        parallel_desc.setWordWrap(True)
        parallel_layout.addRow(parallel_desc)
        
        self.threads_combo = QComboBox()
        self.threads_combo.addItems(["1", "2", "3", "4", "5", "6"])
        self.threads_combo.setCurrentText(str(self.max_threads))
        self.threads_combo.currentTextChanged.connect(self._on_threads_changed)
        
        parallel_layout.addRow("PDFs simultâneos:", self.threads_combo)
        layout.addWidget(parallel_group)
        
        # Planilha personalizada
        sheet_group = QGroupBox("📊 Nome da Planilha")
        sheet_layout = QFormLayout(sheet_group)
        
        sheet_desc = QLabel("Especifique o nome da planilha a ser atualizada. Deixe vazio para usar 'LEVANTAMENTO DADOS' (padrão).")
        sheet_desc.setStyleSheet("color: #888;")
        sheet_desc.setWordWrap(True)
        sheet_layout.addRow(sheet_desc)
        
        self.sheet_entry = QLineEdit()
        self.sheet_entry.setPlaceholderText("LEVANTAMENTO DADOS")
        self.sheet_entry.textChanged.connect(self._on_config_changed)
        
        sheet_layout.addRow("Nome da planilha:", self.sheet_entry)
        layout.addWidget(sheet_group)
        
        # Modo verboso
        verbose_group = QGroupBox("🔍 Logs Detalhados")
        verbose_layout = QVBoxLayout(verbose_group)
        
        self.verbose_checkbox = QCheckBox("Habilitar modo verboso (logs detalhados)")
        self.verbose_checkbox.toggled.connect(self._on_config_changed)
        
        verbose_layout.addWidget(self.verbose_checkbox)
        layout.addWidget(verbose_group)
        
        # Informações sobre funcionalidades (SEÇÃO REORGANIZADA)
        features_group = QGroupBox("ℹ️ Funcionalidades Automáticas")
        features_layout = QVBoxLayout(features_group)
        
        features_desc = QLabel(
            "O sistema detecta e trata automaticamente situações especiais durante o processamento:\n\n"
            "• 📋 DUPLICIDADE DE CÓDIGOS: Quando os códigos 01003601 e 01003602 (PREMIO PROD. MENSAL) "
            "aparecem no mesmo mês, os valores são somados automaticamente.\n\n"
            "• ⚠️ MARCAÇÃO AUTOMÁTICA: Processamentos com situações especiais são marcados para referência.\n\n"
            "• 🧵 PROCESSAMENTO UNIFICADO: Sempre usa ThreadPoolExecutor para comportamento consistente.\n\n"
            "• 📝 DETALHES COMPLETOS: Informações detalhadas sobre o processamento estão sempre disponíveis."
        )
        features_desc.setStyleSheet("color: #888; font-size: 11px;")
        features_desc.setWordWrap(True)
        features_layout.addWidget(features_desc)
        
        layout.addWidget(features_group)
        
        layout.addStretch()
        
        if self.project_model == ProjectManager.MODEL_FICHA:
            sheet_group.hide()
            parallel_desc.setText(
                "Defina quantos PDFs serão analisados simultaneamente durante a consolidação. "
                "Ajuste este valor se notar consumo elevado de recursos."
            )
            features_desc.setText(
                "Nesta rotina os PDFs selecionados são consolidados para gerar CSVs "
                "de PROVENTOS, ADIC. INSALUBRIDADE e CARTÕES. Os arquivos de saída são "
                "salvos na pasta configurada no projeto."
            )

            cartoes_group = QGroupBox("🕒 Formato das horas extras dos cartões")
            cartoes_layout = QVBoxLayout(cartoes_group)

            cartoes_desc = QLabel(
                "Algumas fichas registram a parte decimal das horas como minutos (ex.: 4,12 = 4h12). "
                "Defina abaixo como interpretar os valores para as colunas de horas extras dos cartões."
            )
            cartoes_desc.setStyleSheet("color: #888;")
            cartoes_desc.setWordWrap(True)
            cartoes_layout.addWidget(cartoes_desc)

            self.cartoes_time_mode_combo = QComboBox()
            self.cartoes_time_mode_combo.addItem(
                "Decimais (padrão)",
                FichaFinanceiraProcessor.CARTOES_TIME_MODE_DECIMAL,
            )
            self.cartoes_time_mode_combo.addItem(
                "Minutos (00-59)",
                FichaFinanceiraProcessor.CARTOES_TIME_MODE_MINUTES,
            )
            default_index = self.cartoes_time_mode_combo.findData(
                self.cartoes_time_mode
                or FichaFinanceiraProcessor.CARTOES_TIME_MODE_DECIMAL
            )
            if default_index >= 0:
                self.cartoes_time_mode_combo.setCurrentIndex(default_index)
            self.cartoes_time_mode_combo.currentIndexChanged.connect(
                self._on_cartoes_time_mode_changed
            )
            cartoes_layout.addWidget(self.cartoes_time_mode_combo)

            layout.addWidget(cartoes_group)

            horas_trab_group = QGroupBox(
                "⏰ Formato das horas trabalhadas e faltas"
            )
            horas_trab_layout = QVBoxLayout(horas_trab_group)

            horas_trab_desc = QLabel(
                "Os mesmos PDFs podem registrar as horas trabalhadas e faltas "
                "com a parte decimal representando minutos. Configure abaixo "
                "como interpretar os valores para o arquivo HORAS TRABALHADAS.csv."
            )
            horas_trab_desc.setStyleSheet("color: #888;")
            horas_trab_desc.setWordWrap(True)
            horas_trab_layout.addWidget(horas_trab_desc)

            self.horas_trabalhadas_time_mode_combo = QComboBox()
            self.horas_trabalhadas_time_mode_combo.addItem(
                "Decimais (padrão)",
                FichaFinanceiraProcessor.CARTOES_TIME_MODE_DECIMAL,
            )
            self.horas_trabalhadas_time_mode_combo.addItem(
                "Minutos (00-59)",
                FichaFinanceiraProcessor.CARTOES_TIME_MODE_MINUTES,
            )
            default_horas_mode = (
                self.horas_trabalhadas_time_mode
                or self.cartoes_time_mode
                or FichaFinanceiraProcessor.CARTOES_TIME_MODE_DECIMAL
            )
            default_index = self.horas_trabalhadas_time_mode_combo.findData(
                default_horas_mode
            )
            if default_index >= 0:
                self.horas_trabalhadas_time_mode_combo.setCurrentIndex(
                    default_index
                )
            self.horas_trabalhadas_time_mode_combo.currentIndexChanged.connect(
                self._on_horas_trabalhadas_time_mode_changed
            )
            horas_trab_layout.addWidget(self.horas_trabalhadas_time_mode_combo)

            layout.addWidget(horas_trab_group)

        self.tab_widget.addTab(settings_widget, "⚙️ Configurações")
    
    def _get_processor(self):
        """Factory para criar processadores individuais"""
        def create_processor():
            processor = PDFProcessorCore()
            if self.preferred_sheet:
                processor.preferred_sheet = self.preferred_sheet
            return processor
        return create_processor
    
    def select_directory(self):
        """Seleciona diretório de trabalho"""
        if self.project_model in (ProjectManager.MODEL_FICHA, ProjectManager.MODEL_PLANILHA):
            caption = "Selecione a pasta de saída dos CSVs"
        else:
            caption = "Selecione o diretório de trabalho (que contém MODELO.xlsm)"

        directory = QFileDialog.getExistingDirectory(
            self,
            caption,
            self.trabalho_dir or ""
        )
        
        if directory:
            self.dir_entry.setText(directory)
    
    def _on_dir_changed(self):
        """Callback quando diretório muda"""
        QTimer.singleShot(500, self.validate_config)
    
    def validate_config(self):
        """Valida configuração do diretório"""
        directory = self.dir_entry.text().strip()
        
        if not directory:
            self.config_status.setText("⚠️ Selecione um diretório")
            self.config_status.setStyleSheet("color: #ffa726; font-weight: bold;")
            return
        
        if self.project_model in (ProjectManager.MODEL_FICHA, ProjectManager.MODEL_PLANILHA):
            path = Path(directory)
            if path.exists() and path.is_dir():
                self.config_status.setText("✅ Pasta válida")
                self.config_status.setStyleSheet("color: #2cc985; font-weight: bold;")
                self.trabalho_dir = directory
                self._update_process_button()
                self._on_config_changed()
            else:
                self.config_status.setText("❌ Pasta não encontrada")
                self.config_status.setStyleSheet("color: #f44336; font-weight: bold;")
            return

        try:
            processor_factory = self._get_processor()
            processor = processor_factory()
            processor.set_trabalho_dir(directory)
            valid, message = processor.validate_trabalho_dir()
            
            if valid:
                self.config_status.setText("✅ Configuração válida")
                self.config_status.setStyleSheet("color: #2cc985; font-weight: bold;")
                self.trabalho_dir = directory
                self._update_process_button()
                self._on_config_changed()
            else:
                self.config_status.setText(f"❌ {message}")
                self.config_status.setStyleSheet("color: #f44336; font-weight: bold;")
        except Exception as e:
            self.config_status.setText(f"❌ Erro: {str(e)}")
            self.config_status.setStyleSheet("color: #f44336; font-weight: bold;")
    
    def select_pdfs(self):
        """Seleciona arquivos PDF"""
        if not self.trabalho_dir:
            if self.project_model == ProjectManager.MODEL_FICHA:
                QMessageBox.warning(self, "Configuração necessária", "Informe a pasta de saída antes de selecionar os PDFs.")
            elif self.project_model == ProjectManager.MODEL_PLANILHA:
                QMessageBox.warning(self, "Configuração necessária", "Informe a pasta de saída antes de selecionar as planilhas.")
            else:
                QMessageBox.warning(self, "Configuração Necessária", "Configure o diretório de trabalho primeiro.")
            return

        if self.project_model == ProjectManager.MODEL_FICHA:
            dialog_title = "Selecione os PDFs da ficha financeira"
            file_filter = "Arquivos PDF (*.pdf)"
        elif self.project_model == ProjectManager.MODEL_PLANILHA:
            dialog_title = "Selecione as planilhas de dados"
            file_filter = "Planilhas Excel (*.xls *.xlsx *.xlsm)"
        else:
            dialog_title = "Selecione arquivos PDF (um ou múltiplos)"
            file_filter = "Arquivos PDF (*.pdf)"

        files, _ = QFileDialog.getOpenFileNames(
            self,
            dialog_title,
            self.trabalho_dir,
            file_filter
        )

        if files:
            self.selected_files = files
            self.update_selected_files_display()
    
    def clear_selection(self):
        """Limpa seleção de arquivos"""
        self.selected_files = []
        self.update_selected_files_display()
    
    def handle_dropped_files(self, files):
        """Manipula arquivos arrastados"""
        if self.project_model == ProjectManager.MODEL_PLANILHA:
            allowed_ext = ('.xls', '.xlsx', '.xlsm')
            self.selected_files = [f for f in files if f.lower().endswith(allowed_ext)]
        elif self.project_model == ProjectManager.MODEL_FICHA:
            self.selected_files = [f for f in files if f.lower().endswith('.pdf')]
        else:
            self.selected_files = files
        self.update_selected_files_display()
    
    def update_selected_files_display(self):
        """Atualiza display dos arquivos selecionados"""
        count = len(self.selected_files)
        self.file_counter_label.setText(f"{count} arquivo{'s' if count != 1 else ''}")
        
        if count > 0:
            self.file_counter_label.setStyleSheet("color: #2cc985; font-weight: bold;")
        else:
            self.file_counter_label.setStyleSheet("color: #888;")
        
        # Atualiza lista com botões de remoção
        self.files_list.clear()
        for i, file_path in enumerate(self.selected_files):
            filename = Path(file_path).name
            
            # Cria widget personalizado para cada item
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(5, 2, 5, 2)
            
            # Label com o arquivo
            file_label = QLabel(f"{i+1}. {filename}")
            file_label.setStyleSheet("color: white; font-size: 11px;")
            file_label.setToolTip(file_path)
            
            # Botão de remoção
            remove_btn = QPushButton("🗑️")
            item_layout.setContentsMargins(0, 0, 0,0)
            remove_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #c82333;
                }
            """)
            remove_btn.setToolTip("Remover arquivo")
            remove_btn.clicked.connect(lambda checked, idx=i: self.remove_file_at_index(idx))
            
            item_layout.addWidget(file_label, 1)
            item_layout.addWidget(remove_btn)
            
            # Adiciona item à lista
            list_item = QListWidgetItem()
            list_item.setSizeHint(QSize(0, 25))
            self.files_list.addItem(list_item)
            self.files_list.setItemWidget(list_item, item_widget)
        
        self._update_process_button()
        
        # Log da seleção
        if self.selected_files:
            filenames = [Path(f).name for f in self.selected_files]
            self.add_log_message(f"Arquivos selecionados: {', '.join(filenames)}")
    
    def remove_file_at_index(self, index):
        """Remove arquivo no índice especificado"""
        if 0 <= index < len(self.selected_files):
            removed_file = self.selected_files.pop(index)
            filename = Path(removed_file).name
            self.add_log_message(f"Arquivo removido: {filename}")
            self.update_selected_files_display()
    
    def _update_process_button(self):
        """Atualiza estado do botão processar"""
        can_process = (self.trabalho_dir is not None and 
                      len(self.selected_files) > 0 and 
                      not self.processing)
        self.process_btn.setEnabled(can_process)
    
    def process_pdfs(self):
        """Inicia processamento dos PDFs"""
        if self.processing:
            return

        if not self.trabalho_dir:
            if self.project_model == ProjectManager.MODEL_FICHA:
                QMessageBox.critical(self, "Configuração incompleta", "Selecione a pasta de saída antes de iniciar.")
            else:
                QMessageBox.critical(self, "Configuração Incompleta", "Configure o diretório de trabalho primeiro.")
            return

        if not self.selected_files:
            QMessageBox.critical(
                self,
                "Nenhum Arquivo Selecionado",
                "Selecione pelo menos um arquivo para processar."
                if self.project_model == ProjectManager.MODEL_PLANILHA
                else "Selecione pelo menos um arquivo PDF para processar."
            )
            return

        if self.project_model == ProjectManager.MODEL_FICHA:
            self._process_ficha_financeira()
        elif self.project_model == ProjectManager.MODEL_PLANILHA:
            self._process_planilha_dados()
        else:
            self._process_recibo()

    def _process_recibo(self):
        self.processing = True
        self.process_btn.setText("🔄 Processando...")
        self.process_btn.setEnabled(False)

        self.processor_thread = PDFProcessorThread(
            self.selected_files,
            self._get_processor(),
            self.trabalho_dir,
            self.max_threads
        )

        self.processor_thread.progress_updated.connect(self.handle_progress_update)
        self.processor_thread.pdf_completed.connect(self.handle_pdf_completed)
        self.processor_thread.batch_completed.connect(self.handle_batch_completed)
        self.processor_thread.log_message.connect(self.add_log_message)

        self.progress_dialog = BatchProgressDialog(self.selected_files, self)
        self.processor_thread.progress_updated.connect(self.progress_dialog.update_pdf_progress)
        self.processor_thread.batch_completed.connect(self.progress_dialog.handle_batch_completed)
        self.progress_dialog.show()

        self.processor_thread.start()

    def _process_ficha_financeira(self):
        self.processing = True
        self.process_btn.setText("🔄 Processando...")
        self.process_btn.setEnabled(False)

        start_period, end_period = self._get_project_period()

        self.processor_thread = FichaFinanceiraBatchThread(
            self.selected_files,
            start_period,
            end_period,
            self.trabalho_dir,
            self.max_threads,
            self.cartoes_time_mode,
            self.horas_trabalhadas_time_mode,
        )

        self.processor_thread.progress_updated.connect(self.handle_progress_update)
        self.processor_thread.pdf_completed.connect(self.handle_pdf_completed)
        self.processor_thread.batch_completed.connect(self.handle_batch_completed)
        self.processor_thread.log_message.connect(self.add_log_message)

        self.progress_dialog = BatchProgressDialog(self.selected_files, self)
        self.processor_thread.progress_updated.connect(self.progress_dialog.update_pdf_progress)
        self.processor_thread.batch_completed.connect(self.progress_dialog.handle_batch_completed)
        self.progress_dialog.show()

        self.processor_thread.start()

    def _process_planilha_dados(self):
        self.processing = True
        self.process_btn.setText("🔄 Processando...")
        self.process_btn.setEnabled(False)

        start_period, end_period = self._get_project_period()

        self.processor_thread = PlanilhaDadosBatchThread(
            self.selected_files,
            start_period,
            end_period,
            self.trabalho_dir,
            self.max_threads,
        )

        self.processor_thread.progress_updated.connect(self.handle_progress_update)
        self.processor_thread.pdf_completed.connect(self.handle_pdf_completed)
        self.processor_thread.batch_completed.connect(self.handle_batch_completed)
        self.processor_thread.log_message.connect(self.add_log_message)

        self.progress_dialog = BatchProgressDialog(self.selected_files, self)
        self.processor_thread.progress_updated.connect(self.progress_dialog.update_pdf_progress)
        self.processor_thread.batch_completed.connect(self.progress_dialog.handle_batch_completed)
        self.progress_dialog.show()

        self.processor_thread.start()
    
    @pyqtSlot(str, int, str)
    def handle_progress_update(self, filename, progress, message):
        """Manipula atualizações de progresso"""
        self.statusBar().showMessage(f"{filename}: {message}")
    
    @pyqtSlot(str, dict)
    def handle_pdf_completed(self, filename, result_data):
        """Manipula conclusão de PDF individual"""
        if self.project_model == ProjectManager.MODEL_FICHA:
            entry = HistoryEntry(
                timestamp=datetime.now(),
                pdf_file=filename,
                success=result_data.get('success', False),
                result_data=result_data,
                logs=self.current_logs.copy(),
                is_batch=True,
                batch_info={'pdf_count': result_data.get('pdf_count', len(self.selected_files))},
                has_attention=False,
                attention_details=[],
            )

            self.processing_history.append(entry)
            self.persistence.save_history_entry(entry)
            return
        if self.project_model == ProjectManager.MODEL_PLANILHA:
            entry = HistoryEntry(
                timestamp=datetime.now(),
                pdf_file=filename,
                success=result_data.get('success', False),
                result_data=result_data,
                logs=self.current_logs.copy(),
                is_batch=len(self.selected_files) > 1,
                batch_info={'batch_size': len(self.selected_files), 'processed_in_batch': True}
                if len(self.selected_files) > 1
                else {},
            )
            self.processing_history.append(entry)
            self.persistence.save_history_entry(entry)
            return

        # Determina se há atenção
        has_attention = result_data.get('has_attention', False)
        attention_details = []
        
        # Converte attention_periods para o formato correto
        if result_data.get('attention_periods'):
            for attention_period in result_data['attention_periods']:
                attention_details.append({
                    'periodo': attention_period.get('periodo', 'N/A'),
                    'folha_type': attention_period.get('folha_type', 'N/A'),
                    'detalhes': attention_period.get('detalhes', [])
                })
        
        # Adiciona ao histórico
        entry = HistoryEntry(
            timestamp=datetime.now(),
            pdf_file=filename,
            success=result_data['success'],
            result_data=result_data,
            logs=self.current_logs.copy(),
            is_batch=len(self.selected_files) > 1,
            batch_info={'batch_size': len(self.selected_files), 'processed_in_batch': True} if len(self.selected_files) > 1 else {},
            has_attention=has_attention,  
            attention_details=attention_details  # Estrutura corrigida
        )
        
        self.processing_history.append(entry)
        self.persistence.save_history_entry(entry)
    
    @pyqtSlot()
    def handle_batch_completed(self):
        """Manipula conclusão do processamento"""
        self.processing = False
        if self.project_model == ProjectManager.MODEL_PLANILHA:
            self.process_btn.setText("🚀 Processar planilhas")
        else:
            self.process_btn.setText("🚀 Processar PDFs")
        self.process_btn.setEnabled(True)

        # Fecha dialog de progresso se existir
        if self.progress_dialog:
            # Dialog será fechado automaticamente quando usuário clicar no botão
            pass

        # Atualiza histórico
        self.update_history_display()

        if self.project_model == ProjectManager.MODEL_FICHA:
            recent_entry = self.processing_history[-1] if self.processing_history else None
            if recent_entry and recent_entry.success:
                ficha_results = get_ficha_results_from_payload(recent_entry.result_data)
                flattened_outputs = flatten_ficha_outputs(recent_entry.result_data)
                pdf_count = recent_entry.result_data.get('pdf_count') or len(ficha_results) or len(self.selected_files)

                if ficha_results:
                    lines: List[str] = [
                        f"{pdf_count} PDF{'s' if pdf_count != 1 else ''} processado{'s' if pdf_count != 1 else ''} com sucesso.",
                        "",
                        "Detalhes por PDF:",
                    ]
                    for result in ficha_results:
                        pdf_file = result.get('pdf_file')
                        pdf_name = Path(pdf_file).name if pdf_file else result.get('person_name', 'PDF')
                        lines.append(f"• {pdf_name}")
                        folder = result.get('output_folder')
                        if result.get('outputs'):
                            for item in result.get('outputs', []):
                                lines.append(f"   - {item.get('label', 'Arquivo')}: {item.get('path', '')}")
                        else:
                            lines.append("   - Nenhum arquivo gerado para o período informado.")
                        if folder:
                            lines.append(f"   - Pasta: {folder}")
                    message = "\n".join(lines)
                else:
                    output_lines = "\n".join(
                        f"• {item['label']}: {item['path']}" for item in flattened_outputs
                    )
                    message = (
                        f"{pdf_count} PDF{'s' if pdf_count != 1 else ''} processado{'s' if pdf_count != 1 else ''} com sucesso.\n\n"
                        f"Arquivos gerados:\n{output_lines}" if flattened_outputs else "Nenhum arquivo foi gerado para o período informado."
                    )

                QMessageBox.information(
                    self,
                    "✅ Processamento concluído",
                    message,
                )
            else:
                QMessageBox.critical(
                    self,
                    "❌ Processamento falhou",
                    "Não foi possível gerar os arquivos CSV. Verifique os logs para mais detalhes.",
                )
        else:
            recent_entries = self.processing_history[-len(self.selected_files):]
            successful = sum(1 for entry in recent_entries if entry.success)
            with_attention = sum(1 for entry in recent_entries if entry.has_attention)
            total = len(self.selected_files)

            if successful == total:
                if with_attention > 0:
                    QMessageBox.information(
                        self,
                        "✅ Processamento Concluído com Atenção",
                        f"{'Todos os' if total > 1 else 'O'} {total} PDF{'s foram' if total > 1 else ' foi'} processado{'s' if total > 1 else ''} com sucesso!\n\n"
                        f"⚠️ {with_attention} arquivo{'s' if with_attention != 1 else ''} possui{'em' if with_attention != 1 else ''} observações especiais.\n\n"
                        f"📊 Verifique o histórico para mais detalhes.\n"
                        f"📂 {'Os arquivos foram salvos' if total > 1 else 'O arquivo foi salvo'} na pasta DADOS/"
                    )
                else:
                    QMessageBox.information(
                        self,
                        "✅ Processamento Concluído",
                        f"{'Todos os' if total > 1 else 'O'} {total} PDF{'s foram' if total > 1 else ' foi'} processado{'s' if total > 1 else ''} com sucesso!\n\n"
                        f"📊 Verifique o histórico para mais detalhes.\n"
                        f"📂 {'Os arquivos foram salvos' if total > 1 else 'O arquivo foi salvo'} na pasta DADOS/"
                    )
            elif successful > 0:
                attention_text = f"\n⚠️ {with_attention} com observações especiais." if with_attention > 0 else ""
                QMessageBox.warning(
                    self,
                    "⚠️ Processamento Parcial",
                    f"{successful} de {total} PDFs foram processados com sucesso.{attention_text}\n\n"
                    f"📊 Verifique o histórico para detalhes dos arquivos que falharam.\n"
                    f"📂 Os arquivos processados foram salvos na pasta DADOS/"
                )
            else:
                QMessageBox.critical(
                    self,
                    "❌ Processamento Falhou",
                    f"Nenhum PDF foi processado com sucesso.\n\n"
                    f"📊 Verifique o histórico para detalhes dos erros.\n"
                    f"🔧 Certifique-se de que os PDFs estão no formato correto."
                )

        # Limpa seleção e vai para histórico
        self.clear_selection()
        self.tab_widget.setCurrentIndex(1)  # Aba histórico

        self.statusBar().showMessage("Processamento concluído")
    
    def update_history_display(self):
        """Atualiza exibição do histórico"""
        self.history_list.clear()
        
        # Adiciona entradas (mais recentes primeiro)
        for entry in reversed(self.processing_history):
            item = QListWidgetItem()
            item_widget = HistoryItemWidget(entry)
            
            # Conecta signals
            item_widget.details_requested.connect(self.show_history_details)
            item_widget.file_open_requested.connect(self.open_data_file)
            
            item.setSizeHint(QSize(0, 55))  # Altura compacta
            self.history_list.addItem(item)
            self.history_list.setItemWidget(item, item_widget)
        
        # Atualiza status (simplificado, sem distinção de lote)
        total = len(self.processing_history)
        item_label = "planilhas" if self.project_model == ProjectManager.MODEL_PLANILHA else "PDFs"
        if total > 0:
            success_count = sum(1 for h in self.processing_history if h.success)
            attention_count = sum(1 for h in self.processing_history if h.has_attention)

            status_text = f"{total} {item_label} no histórico ({success_count} sucessos, {total - success_count} falhas)"
            if attention_count > 0:
                status_text += f" • ⚠️ {attention_count} com atenção"
            
            self.history_status_label.setText(status_text)
            
            # Cor baseada na presença de atenções
            if attention_count > 0:
                self.history_status_label.setStyleSheet("color: #ff9800; font-weight: bold;")
            else:
                self.history_status_label.setStyleSheet("color: #2cc985; font-weight: bold;")
        else:
            self.history_status_label.setText("Nenhum PDF no histórico")
            self.history_status_label.setStyleSheet("color: #888;")
    
    def show_history_details(self, entry: HistoryEntry):
        """Mostra detalhes de entrada do histórico"""
        dialog = HistoryDetailsDialog(entry, self)
        dialog.exec()
    
    def open_data_file(self, entry: HistoryEntry):
        """Abre arquivo Excel de entrada do histórico"""
        try:
            ficha_results = get_ficha_results_from_payload(entry.result_data)
            if ficha_results:
                folders = collect_ficha_output_folders(entry.result_data)
                if folders:
                    path_to_open = Path(folders[0])
                else:
                    flattened = flatten_ficha_outputs(entry.result_data)
                    if not flattened:
                        QMessageBox.warning(self, "Pasta não encontrada", "Não foi possível localizar a pasta dos arquivos gerados.")
                        return
                    first_output = Path(flattened[0].get('path', ''))
                    path_to_open = first_output.parent if first_output.is_file() else first_output

                if not path_to_open or not path_to_open.exists():
                    QMessageBox.warning(self, "Pasta não encontrada", "Não foi possível localizar a pasta dos arquivos gerados.")
                    return

                if sys.platform.startswith('win'):
                    os.startfile(path_to_open)
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', str(path_to_open)])
                else:
                    subprocess.Popen(['xdg-open', str(path_to_open)])
                return

            if entry.result_data.get('processor') == 'planilha_dados':
                outputs = entry.result_data.get('outputs', [])
                target_folder = entry.result_data.get('output_folder')
                if not target_folder and outputs:
                    first_output = Path(outputs[0].get('path', ''))
                    target_folder = str(first_output.parent) if first_output else None

                if not target_folder:
                    QMessageBox.warning(self, "Pasta não encontrada", "Não foi possível localizar os arquivos gerados.")
                    return

                path_to_open = Path(target_folder)
                if not path_to_open.exists():
                    QMessageBox.warning(self, "Pasta não encontrada", "Não foi possível localizar os arquivos gerados.")
                    return

                if sys.platform.startswith('win'):
                    os.startfile(path_to_open)
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', str(path_to_open)])
                else:
                    subprocess.Popen(['xdg-open', str(path_to_open)])
                return

            file_path = entry.result_data.get('excel_path')
            if not file_path and self.trabalho_dir:
                arquivo_rel = entry.result_data.get('arquivo_final')
                if arquivo_rel:
                    file_path = Path(self.trabalho_dir) / arquivo_rel
            
            if not file_path:
                QMessageBox.warning(self, "Arquivo Não Encontrado", "Caminho do arquivo não está disponível.")
                return
            
            file_path = Path(file_path)
            if not file_path.exists():
                QMessageBox.warning(self, "Arquivo Não Encontrado", f"O arquivo não foi encontrado:\n\n{file_path}")
                return
            
            if sys.platform.startswith('win'):
                os.startfile(file_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(file_path)])
            else:
                subprocess.Popen(['xdg-open', str(file_path)])
        
        except Exception as e:
            QMessageBox.critical(self, "Erro ao Abrir Arquivo", f"Não foi possível abrir o arquivo:\n\n{e}")
    
    def clear_history(self):
        """Limpa histórico"""
        if not self.processing_history:
            return
        
        reply = QMessageBox.question(
            self, 
            "Confirmar Limpeza", 
            "Deseja limpar todo o histórico de processamentos?\n\nEsta ação não pode ser desfeita.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No  # Botão padrão
        )
        
        # Personaliza texto dos botões
        button_yes = reply == QMessageBox.StandardButton.Yes
        
        if button_yes:
            self.processing_history.clear()
            self.persistence.clear_history()
            self.update_history_display()
            
            # Mostra confirmação de sucesso
            QMessageBox.information(
                self,
                "Histórico Limpo",
                "✅ O histórico foi limpo com sucesso!"
            )
    
    def _on_threads_changed(self, value):
        """Callback quando número de threads muda"""
        self.max_threads = int(value)
        self._on_config_changed()
        self.add_log_message(f"Threads configuradas: {value} workers (sempre ThreadPoolExecutor)")

    def _on_cartoes_time_mode_changed(self):
        """Atualiza modo de interpretação das horas extras."""
        if not hasattr(self, 'cartoes_time_mode_combo'):
            return

        mode = self.cartoes_time_mode_combo.currentData()
        if mode:
            self.cartoes_time_mode = str(mode)
        else:
            self.cartoes_time_mode = (
                FichaFinanceiraProcessor.CARTOES_TIME_MODE_DECIMAL
            )

        if self.cartoes_time_mode == FichaFinanceiraProcessor.CARTOES_TIME_MODE_MINUTES:
            self.add_log_message(
                "Configuração aplicada: horas extras dos cartões tratadas como minutos (00-59)."
            )
        else:
            self.add_log_message(
                "Configuração aplicada: horas extras dos cartões tratadas como decimais."
            )

        self._on_config_changed()

    def _on_horas_trabalhadas_time_mode_changed(self):
        """Atualiza modo de interpretação das horas trabalhadas e faltas."""
        if not hasattr(self, 'horas_trabalhadas_time_mode_combo'):
            return

        mode = self.horas_trabalhadas_time_mode_combo.currentData()
        if mode:
            self.horas_trabalhadas_time_mode = str(mode)
        else:
            self.horas_trabalhadas_time_mode = (
                FichaFinanceiraProcessor.CARTOES_TIME_MODE_DECIMAL
            )

        if (
            self.horas_trabalhadas_time_mode
            == FichaFinanceiraProcessor.CARTOES_TIME_MODE_MINUTES
        ):
            self.add_log_message(
                "Configuração aplicada: horas trabalhadas e faltas tratadas como minutos (00-59)."
            )
        else:
            self.add_log_message(
                "Configuração aplicada: horas trabalhadas e faltas tratadas como decimais."
            )

        self._on_config_changed()

    def _on_config_changed(self):
        """Callback genérico para mudanças de configuração"""
        # Verifica se save_timer existe antes de usar
        if hasattr(self, 'save_timer'):
            self.save_timer.start(1000)  # Salva após 1 segundo de inatividade
    
    def save_current_config(self):
        """Salva configuração atual"""
        config = {
            'trabalho_dir': self.trabalho_dir,
            'max_threads': self.max_threads,
            'verbose_mode': self.verbose_checkbox.isChecked(),
            'preferred_sheet': self.sheet_entry.text().strip()
        }

        if self.project_model == ProjectManager.MODEL_FICHA:
            config['cartoes_time_mode'] = self.cartoes_time_mode
            config['horas_trabalhadas_time_mode'] = (
                self.horas_trabalhadas_time_mode
            )

        self.persistence.save_config(config)
    
    def load_persisted_data(self):
        """Carrega dados persistidos"""
        try:
            self.add_log_message("Carregando configurações e histórico...")
            
            config = self.persistence.load_config()
            
            if config.get('trabalho_dir'):
                self.trabalho_dir = config['trabalho_dir']
                self.dir_entry.setText(self.trabalho_dir)
                self.validate_config()
            
            if config.get('max_threads'):
                self.max_threads = config['max_threads']
                self.threads_combo.setCurrentText(str(self.max_threads))
            
            if config.get('verbose_mode'):
                self.verbose_checkbox.setChecked(config['verbose_mode'])
            
            if config.get('preferred_sheet'):
                self.preferred_sheet = config['preferred_sheet']
                self.sheet_entry.setText(self.preferred_sheet)

            if (
                self.project_model == ProjectManager.MODEL_FICHA
                and config.get('cartoes_time_mode')
            ):
                self.cartoes_time_mode = config['cartoes_time_mode']
                if hasattr(self, 'cartoes_time_mode_combo'):
                    index = self.cartoes_time_mode_combo.findData(
                        self.cartoes_time_mode
                    )
                    if index >= 0:
                        self.cartoes_time_mode_combo.blockSignals(True)
                        self.cartoes_time_mode_combo.setCurrentIndex(index)
                        self.cartoes_time_mode_combo.blockSignals(False)

            if (
                self.project_model == ProjectManager.MODEL_FICHA
                and config.get('horas_trabalhadas_time_mode')
            ):
                self.horas_trabalhadas_time_mode = config[
                    'horas_trabalhadas_time_mode'
                ]
                if hasattr(self, 'horas_trabalhadas_time_mode_combo'):
                    index = self.horas_trabalhadas_time_mode_combo.findData(
                        self.horas_trabalhadas_time_mode
                    )
                    if index >= 0:
                        self.horas_trabalhadas_time_mode_combo.blockSignals(True)
                        self.horas_trabalhadas_time_mode_combo.setCurrentIndex(
                            index
                        )
                        self.horas_trabalhadas_time_mode_combo.blockSignals(
                            False
                        )
            
            # Carrega histórico
            self.processing_history = self.persistence.load_all_history_entries()
            self.update_history_display()
            
            attention_count = sum(1 for h in self.processing_history if h.has_attention)
            if attention_count > 0:
                self.add_log_message(f"✅ Dados carregados: {len(self.processing_history)} entradas no histórico ({attention_count} com atenção)")
            else:
                self.add_log_message(f"✅ Dados carregados: {len(self.processing_history)} entradas no histórico")
            
        except Exception as e:
            self.add_log_message(f"⚠️ Erro ao carregar dados persistidos: {e}")
    
    def add_log_message(self, message):
        """Adiciona mensagem ao log"""
        # Verifica se current_logs existe antes de usar
        if not hasattr(self, 'current_logs'):
            self.current_logs = []
            
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.current_logs.append(log_entry)
        
        # Mantém apenas últimos 100 logs
        if len(self.current_logs) > 100:
            self.current_logs = self.current_logs[-100:]
    
    def closeEvent(self, event):
        """Manipula fechamento da aplicação"""
        if self.processing:
            reply = QMessageBox.question(
                self,
                "Processamento em Andamento",
                "Há processamentos em andamento. Deseja realmente fechar a aplicação?\n\nO processamento será interrompido.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No  # Botão padrão
            )
            
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

        self.save_current_config()
        event.accept()

        if self.on_back_callback:
            QTimer.singleShot(0, self.on_back_callback)


class AppController(QObject):
    """Gerencia a alternância entre a lista de projetos e as janelas ativas."""

    def __init__(self, app: QApplication, project_manager: ProjectManager):
        super().__init__()
        self.app = app
        self.project_manager = project_manager
        self.selection_window: Optional[ProjectSelectionWindow] = None
        self.project_window: Optional[MainWindow] = None

    def show_project_selection(self):
        if self.project_window:
            self.project_window.deleteLater()
            self.project_window = None

        if self.selection_window:
            self.selection_window.deleteLater()

        self.selection_window = ProjectSelectionWindow(self.project_manager)
        self.selection_window.project_open_requested.connect(self.open_project)
        self.selection_window.show()

    def open_project(self, project_id: str):
        metadata = self.project_manager.get_project(project_id)
        if not metadata:
            QMessageBox.warning(None, "Projeto indisponível", "Não foi possível localizar o projeto selecionado.")
            if self.selection_window:
                self.selection_window.refresh_projects()
            return

        self.project_manager.set_last_selected(project_id)

        if self.selection_window:
            self.selection_window.close()
            self.selection_window = None

        self.project_window = MainWindow(self.project_manager, metadata, on_back=self.show_project_selection)
        self.project_window.show()
        self._emit_startup_logs()

    def _emit_startup_logs(self):
        if not self.project_window:
            return

        if self.project_window.project_model == ProjectManager.MODEL_FICHA:
            self.project_window.add_log_message("🚀 Módulo Ficha Financeira pronto para gerar CSVs.")
            self.project_window.add_log_message("📄 Informe o período do projeto e escolha os PDFs para consolidar os dados.")
        elif self.project_window.project_model == ProjectManager.MODEL_PLANILHA:
            self.project_window.add_log_message("🚀 Módulo Planilha de Dados pronto para gerar CSVs.")
            self.project_window.add_log_message("📊 Defina o período e selecione as planilhas XLS/XLSX/XLSM para processamento paralelo.")
        else:
            self.project_window.add_log_message("🚀 Aplicação PyQt6 v4.0.1 iniciada com sucesso!")
            self.project_window.add_log_message("💡 Interface moderna com performance nativa carregada")
            self.project_window.add_log_message("🔧 Processamento unificado (ThreadPoolExecutor) ativo")

        if getattr(sys, 'frozen', False):
            self.project_window.add_log_message("📦 Executando em modo executável (.exe)")
        else:
            self.project_window.add_log_message("🛠️ Executando em modo desenvolvimento")

def main():
    """Função principal com splash screen"""
    try:
        app = QApplication(sys.argv)
        
        # Aplica estilo escuro
        app.setStyleSheet(DARK_STYLE)
        
        # Cria e mostra splash screen
        splash = SplashScreen()
        splash.start_loading()
        
        # Permite que splash screen seja mostrada
        app.processEvents()
        
        # Detecção do ambiente (executável vs desenvolvimento)
        is_frozen = getattr(sys, 'frozen', False)
        
        if is_frozen:
            # Em executável, carregamento pode ser mais lento
            splash.set_status("Inicializando executável...")
            time.sleep(0.4)
        else:
            # Em desenvolvimento
            splash.set_status("Modo desenvolvimento...")
            time.sleep(0.2)
        
        # Simula carregamento das dependências principais
        splash.set_status("Carregando processador...")
        app.processEvents()
        time.sleep(0.3 if is_frozen else 0.2)
        
        # Verifica importações críticas
        splash.set_status("Verificando dependências...")
        app.processEvents()
        time.sleep(0.2)
        
        try:
            # Testa se consegue importar o processador
            from pdf_processor_core import PDFProcessorCore
            splash.set_status("✅ Dependências OK")
            app.processEvents()
            time.sleep(0.2)
        except ImportError as e:
            splash.set_status("❌ Erro crítico")
            app.processEvents()
            time.sleep(1)
            splash.close()
            QMessageBox.critical(None, "Erro Crítico de Dependência", 
                               f"❌ Não foi possível carregar o módulo principal:\n\n"
                               f"📄 Arquivo: pdf_processor_core.py\n"
                               f"❓ Status: Não encontrado\n\n"
                               f"🔧 Solução:\n"
                               f"Certifique-se de que todos os arquivos estão na mesma pasta do executável.\n\n"
                               f"📋 Erro técnico: {e}")
            sys.exit(1)
        
        # Carregamento da interface principal
        splash.set_status("Criando interface...")
        app.processEvents()
        time.sleep(0.3 if is_frozen else 0.2)

        splash.set_status("Inicializando PyQt6...")
        app.processEvents()

        # Aguarda até splash screen chegar a pelo menos 80%
        while splash.progress_value < 80:
            app.processEvents()
            time.sleep(0.02)

        splash.set_status("Carregando dados...")
        app.processEvents()
        time.sleep(0.2 if is_frozen else 0.1)

        # Aguarda carregamento completo
        while splash.progress_value < 100:
            app.processEvents()
            time.sleep(0.02)

        splash.set_status("✅ Carregamento concluído")
        app.processEvents()
        time.sleep(0.3)

        splash.finish_loading()

        base_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
        project_manager = ProjectManager(base_dir)
        controller = AppController(app, project_manager)
        controller.show_project_selection()

        sys.exit(app.exec())

       
    except Exception as e:
        # Tratamento de erro crítico
        try:
            if 'splash' in locals():
                splash.close()
            QMessageBox.critical(None, "Erro Crítico na Inicialização", 
                               f"❌ Erro inesperado ao iniciar a aplicação:\n\n"
                               f"📋 Detalhes do erro:\n{e}\n\n"
                               f"🔧 A aplicação será fechada.\n\n"
                               f"💡 Tente executar novamente ou verifique se todos os arquivos estão presentes.")
        except:
            pass  # Se nem QMessageBox funcionar, apenas termina
        
        sys.exit(1)

if __name__ == "__main__":
    main()