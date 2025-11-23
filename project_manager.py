import json
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple


MONTH_NAMES = [
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]


@dataclass
class ProjectMetadata:
    """Metadados de um projeto persistido."""

    project_id: str
    name: str
    model: str
    start_month: int
    start_year: int
    end_month: int
    end_year: int

    def period_tuple(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        return (self.start_year, self.start_month), (self.end_year, self.end_month)


class ProjectManager:
    """Gerencia a persistência e as operações dos projetos."""

    MODEL_RECIBO = "recibo_modelo_1"
    MODEL_FICHA = "ficha_financeira"
    MODEL_PLANILHA = "planilha_dados"

    def __init__(self, app_dir: Optional[Path] = None) -> None:
        if app_dir is None:
            self.app_dir = Path(__file__).parent
        else:
            self.app_dir = Path(app_dir)

        self.data_dir = self.app_dir / ".data"
        self.data_dir.mkdir(exist_ok=True)

        self.projects_dir = self.data_dir / "projetos"
        self.projects_dir.mkdir(exist_ok=True)

        self.projects_file = self.data_dir / "projects.json"

        self._ensure_projects_file()
        self._migrate_legacy_data()

    # ------------------------------------------------------------------
    # Operações básicas
    # ------------------------------------------------------------------
    def list_projects(self) -> List[ProjectMetadata]:
        data = self._read_projects_file()
        projects = []
        for raw in data.get("projects", []):
            projects.append(
                ProjectMetadata(
                    project_id=raw["id"],
                    name=raw["name"],
                    model=raw["model"],
                    start_month=raw["start_month"],
                    start_year=raw["start_year"],
                    end_month=raw["end_month"],
                    end_year=raw["end_year"],
                )
            )
        return projects

    def get_project(self, project_id: str) -> Optional[ProjectMetadata]:
        for project in self.list_projects():
            if project.project_id == project_id:
                return project
        return None

    def create_project(
        self,
        name: str,
        model: str,
        start_month: int,
        start_year: int,
        end_month: int,
        end_year: int,
    ) -> ProjectMetadata:
        self._validate_model(model)
        self._validate_name(name)
        self._validate_period(start_month, start_year, end_month, end_year)

        projects_data = self._read_projects_file()
        if any(p["name"].strip().lower() == name.strip().lower() for p in projects_data.get("projects", [])):
            raise ValueError("Já existe um projeto com este nome.")

        project_id = uuid.uuid4().hex[:8]
        metadata = {
            "id": project_id,
            "name": name.strip(),
            "model": model,
            "start_month": start_month,
            "start_year": start_year,
            "end_month": end_month,
            "end_year": end_year,
        }

        projects_data.setdefault("projects", []).append(metadata)
        projects_data["last_selected"] = project_id
        self._write_projects_file(projects_data)

        project_dir = self.get_project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)

        return ProjectMetadata(
            project_id=project_id,
            name=metadata["name"],
            model=metadata["model"],
            start_month=start_month,
            start_year=start_year,
            end_month=end_month,
            end_year=end_year,
        )

    def update_project(
        self,
        project_id: str,
        *,
        name: Optional[str] = None,
        start_month: Optional[int] = None,
        start_year: Optional[int] = None,
        end_month: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> ProjectMetadata:
        projects_data = self._read_projects_file()
        projects = projects_data.get("projects", [])

        for project in projects:
            if project["id"] == project_id:
                new_name = name.strip() if name is not None else project["name"]

                if new_name != project["name"]:
                    self._validate_name(new_name)
                    if any(
                        p["id"] != project_id and p["name"].strip().lower() == new_name.strip().lower()
                        for p in projects
                    ):
                        raise ValueError("Já existe outro projeto com este nome.")

                sm = start_month if start_month is not None else project["start_month"]
                sy = start_year if start_year is not None else project["start_year"]
                em = end_month if end_month is not None else project["end_month"]
                ey = end_year if end_year is not None else project["end_year"]

                self._validate_period(sm, sy, em, ey)

                project["name"] = new_name
                project["start_month"] = sm
                project["start_year"] = sy
                project["end_month"] = em
                project["end_year"] = ey

                self._write_projects_file(projects_data)

                return ProjectMetadata(
                    project_id=project_id,
                    name=new_name,
                    model=project["model"],
                    start_month=sm,
                    start_year=sy,
                    end_month=em,
                    end_year=ey,
                )

        raise ValueError("Projeto não encontrado.")

    def set_last_selected(self, project_id: str) -> None:
        projects_data = self._read_projects_file()
        if any(p["id"] == project_id for p in projects_data.get("projects", [])):
            projects_data["last_selected"] = project_id
            self._write_projects_file(projects_data)

    def get_last_selected(self) -> Optional[str]:
        projects_data = self._read_projects_file()
        return projects_data.get("last_selected")

    def get_project_dir(self, project_id: str) -> Path:
        return self.projects_dir / project_id

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _read_projects_file(self) -> Dict:
        with open(self.projects_file, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_projects_file(self, data: Dict) -> None:
        with open(self.projects_file, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)

    def _ensure_projects_file(self) -> None:
        if not self.projects_file.exists():
            self._write_projects_file({"projects": [], "last_selected": None})

    def _validate_model(self, model: str) -> None:
        if model not in {self.MODEL_RECIBO, self.MODEL_FICHA, self.MODEL_PLANILHA}:
            raise ValueError("Modelo de projeto inválido.")

    def _validate_name(self, name: str) -> None:
        if not name or not name.strip():
            raise ValueError("Informe um nome para o projeto.")

    def _validate_period(
        self,
        start_month: int,
        start_year: int,
        end_month: int,
        end_year: int,
    ) -> None:
        if not (1 <= start_month <= 12 and 1 <= end_month <= 12):
            raise ValueError("Os meses devem estar entre 1 e 12.")
        if (start_year, start_month) > (end_year, end_month):
            raise ValueError("O período inicial deve ser anterior ao final.")

    def _migrate_legacy_data(self) -> None:
        """Move arquivos antigos (sem projetos) para um projeto padrão."""

        legacy_config = self.data_dir / "config.json"
        legacy_history = self.data_dir / "history.json"

        if not legacy_config.exists() and not legacy_history.exists():
            return

        data = self._read_projects_file()
        if data.get("projects"):
            # Já migrado
            return

        today = date.today()
        default_project = {
            "id": uuid.uuid4().hex[:8],
            "name": "Projeto Migrado",
            "model": self.MODEL_RECIBO,
            "start_month": today.month,
            "start_year": today.year,
            "end_month": today.month,
            "end_year": today.year,
        }

        data["projects"] = [default_project]
        data["last_selected"] = default_project["id"]
        self._write_projects_file(data)

        project_dir = self.get_project_dir(default_project["id"])
        project_dir.mkdir(parents=True, exist_ok=True)

        if legacy_config.exists():
            legacy_config.rename(project_dir / "config.json")
        if legacy_history.exists():
            legacy_history.rename(project_dir / "history.json")

    @staticmethod
    def format_period(project: ProjectMetadata) -> str:
        start = f"{MONTH_NAMES[project.start_month - 1]}/{project.start_year}"
        end = f"{MONTH_NAMES[project.end_month - 1]}/{project.end_year}"
        return f"{start} → {end}"

