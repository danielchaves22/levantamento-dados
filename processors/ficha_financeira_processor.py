"""Processador dedicado ao modelo de Ficha Financeira."""

from __future__ import annotations

import csv
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pdfplumber


NumberByMonth = Dict[Tuple[int, int], Decimal]
LogCallback = Callable[[str], None]


@dataclass
class MonthColumn:
    """Representa as colunas Comp./Valor de um mês."""

    name: str
    month: int
    comp_center: Optional[float]
    valor_center: Optional[float]


@dataclass
class MonthBlock:
    """Informações de um bloco quadrimestral da ficha."""

    year: int
    months: List[MonthColumn]
    y_start: float
    y_end: float


@dataclass
class ActiveBlock:
    """Representa um bloco que pode se estender para a próxima página."""

    block: MonthBlock
    carry_count: int = 0


class FichaFinanceiraProcessor:
    """Responsável por extrair dados da ficha financeira e gerar CSVs."""

    AFASTAMENTO_CODES: Tuple[Dict[str, str], ...] = (
        {
            "code": "902-AfastDoenca",
            "label": "902-AFAST. DOENCA",
            "log": "HORAS TRABALHADAS - AFAST. DOENCA",
        },
        {
            "code": "910-AfastMaternidade",
            "label": "910-AFAST. MATERNIDADE",
            "log": "HORAS TRABALHADAS - AFAST. MATERNIDADE",
        },
    )

    TARGET_CODES: Dict[str, Dict[str, object]] = {
        "1-Salario": {"column": 1},
        "6-Horas": {"column": 1, "search_prefix": "6 -"},
        "14-Horas100": {"column": 1, "search_prefix": "14 -"},
        "8-Insalubridade": {"column": 2},
        "205-Insalubridade-ACS": {
            "column": 2,
            "search_prefix": "205",
            "alias_for": "8-Insalubridade",
        },
        "3123-Base": {"column": 2},
        "167-Ferias": {"column": 2, "search_prefix": "167"},
        "168-Ferias": {"column": 2, "search_prefix": "168"},
        "173-Ferias": {"column": 2, "search_prefix": "173"},
        "174-Ferias": {"column": 2, "search_prefix": "174"},
        "527-INSS-Comp": {"column": 1, "search_prefix": "527"},
        "527-INSS-Valor": {"column": 2, "search_prefix": "527"},
        "952-FaltaInjustifica": {"column": 1, "search_prefix": "952"},
        "902-AfastDoenca": {"column": 1, "search_prefix": "902"},
        "910-AfastMaternidade": {"column": 1, "search_prefix": "910"},
    }

    OUTPUT_SPECS: Tuple[Dict[str, object], ...] = (
        {"code": "3123-Base", "label": "PROVENTOS", "log": "PROVENTOS"},
        {
            "code": "8-Insalubridade",
            "label": "ADIC. INSALUBRIDADE PAGO",
            "log": "INSALUBRIDADE",
        },
        {
            "code": "6-Horas",
            "label": "CARTÕES",
            "log": "CARTÕES",
            "writer": "cartoes",
            "extra_hours_code": "14-Horas100",
            "extra_hours_log": "CARTÕES - HORA EXTRA 100",
        },
        {
            "code": "1-Salario",
            "label": "HORAS TRABALHADAS",
            "log": "HORAS TRABALHADAS - HORAS",
            "writer": "horas_trabalhadas",
            "faltas_code": "952-FaltaInjustifica",
            "faltas_log": "HORAS TRABALHADAS - FALTAS",
            "afastamentos": AFASTAMENTO_CODES,
        },
    )

    MAX_BLOCK_CARRY = 3

    MONTH_MAP = {
        "janeiro": 1,
        "fevereiro": 2,
        "marco": 3,
        "março": 3,
        "abril": 4,
        "maio": 5,
        "junho": 6,
        "julho": 7,
        "agosto": 8,
        "setembro": 9,
        "outubro": 10,
        "novembro": 11,
        "dezembro": 12,
    }

    NUMBER_PATTERN = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d+$|^\d+(?:,\d+)?$")

    CARTOES_TIME_MODE_DECIMAL = "decimal"
    CARTOES_TIME_MODE_MINUTES = "minutes"

    def __init__(
        self,
        log_callback: Optional[LogCallback] = None,
        *,
        config: Optional[Dict[str, object]] = None,
    ) -> None:
        self._log_callback = log_callback
        self._config: Dict[str, object] = dict(config or {})

    @classmethod
    def _storage_codes(cls) -> Set[str]:
        codes: Set[str] = set()
        for code, cfg in cls.TARGET_CODES.items():
            alias_for = cfg.get("alias_for")
            if isinstance(alias_for, str) and alias_for:
                codes.add(alias_for)
            else:
                codes.add(code)
        return codes

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def generate_proventos(
        self,
        pdf_paths: Sequence[Path],
        start_period: date,
        end_period: date,
        output_dir: Path,
        *,
        max_workers: int = 1,
    ) -> Dict[str, object]:
        """Processa PDFs e gera o arquivo PROVENTOS.csv."""

        results = self.generate_csvs(
            pdf_paths=pdf_paths,
            start_period=start_period,
            end_period=end_period,
            output_dir=output_dir,
            max_workers=max_workers,
        )

        for result in results:
            for output in result.get("outputs", []):
                if output["label"] == "PROVENTOS":
                    return {
                        "person_name": result.get("person_name"),
                        "output_path": output["path"],
                        "months": output["months"],
                    }

        raise RuntimeError("Arquivo PROVENTOS não foi gerado.")

    def generate_csvs(
        self,
        pdf_paths: Sequence[Path],
        start_period: date,
        end_period: date,
        output_dir: Path,
        *,
        max_workers: int = 1,
        progress_callback: Optional[Callable[[Path, int, int], None]] = None,
    ) -> List[Dict[str, object]]:
        """Gera todos os CSVs configurados para a ficha financeira, por PDF."""

        if start_period > end_period:
            raise ValueError("Período inicial não pode ser maior que o final.")

        resolved_paths: List[Path] = []
        for pdf_path in pdf_paths:
            path = Path(pdf_path)
            if not path.exists():
                raise FileNotFoundError(f"Arquivo não encontrado: {path}")
            resolved_paths.append(path)

        if not resolved_paths:
            raise ValueError("Informe ao menos um PDF para processamento.")

        months_range = list(self._iterate_months(start_period, end_period))
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        effective_workers = max(1, min(max_workers, len(resolved_paths)))

        start_progress_error_logged = False

        def notify_start(path: Path) -> None:
            nonlocal start_progress_error_logged
            if not progress_callback:
                return
            try:
                progress_callback(path, -1, 0)
            except Exception:
                if not start_progress_error_logged:
                    start_progress_error_logged = True
                    self._log(
                        "⚠️ Falha ao notificar início do progresso do PDF; ignorando callback."
                    )

        def process_path(path: Path) -> Dict[str, object]:
            self._log(f"📄 Lendo {path.name}")
            parse_result = self._parse_pdf(
                path, progress_callback=progress_callback
            )
            aggregated: Dict[str, NumberByMonth] = parse_result["values"]

            person_name = parse_result.get("person_name")
            if not person_name:
                person_name = path.stem
                self._log(
                    f"⚠️ Nome não encontrado no PDF {path.name}. Utilizando o nome do arquivo como identificação."
                )

            self._apply_vacation_adjustments(aggregated)

            folder_slug, file_slug = self._build_folder_and_file_slugs(
                path, person_name
            )
            target_dir = output_dir_path / folder_slug
            target_dir.mkdir(parents=True, exist_ok=True)

            self._log(
                f"📁 Gerando CSVs do arquivo {path.name} na pasta {target_dir}"
            )

            outputs = self._generate_outputs_for_pdf(
                aggregated,
                months_range,
                target_dir,
                file_slug,
            )

            self._log(
                f"🏁 Conjunto de CSVs do arquivo {path.name} disponível em {target_dir}"
            )

            return {
                "pdf_path": path,
                "person_name": person_name,
                "output_folder": target_dir,
                "folder_slug": folder_slug,
                "outputs": outputs,
            }

        results_by_path: Dict[Path, Dict[str, object]] = {}

        def run_with_start(path: Path) -> Dict[str, object]:
            notify_start(path)
            return process_path(path)

        if effective_workers == 1:
            for path in resolved_paths:
                results_by_path[path] = run_with_start(path)
        else:
            with ThreadPoolExecutor(max_workers=effective_workers) as executor:
                futures = {
                    executor.submit(run_with_start, path): path
                    for path in resolved_paths
                }

                for future in as_completed(futures):
                    path = futures[future]
                    results_by_path[path] = future.result()

        return [results_by_path[path] for path in resolved_paths]

    def _generate_outputs_for_pdf(
        self,
        aggregated: Dict[str, NumberByMonth],
        months_range: Sequence[Tuple[int, int]],
        target_dir: Path,
        file_slug: str,
    ) -> List[Dict[str, object]]:
        outputs: List[Dict[str, object]] = []

        for spec in self.OUTPUT_SPECS:
            output_path = target_dir / f"{spec['label']}_{file_slug}.csv"
            writer = spec.get("writer", "default")
            if writer == "cartoes":
                values = self._collect_values_for_code(
                    aggregated,
                    spec["code"],
                    months_range,
                    spec["log"],
                )
                extra_code = spec.get("extra_hours_code")
                extra_log = spec.get("extra_hours_log", spec["log"])
                extra_values = (
                    self._collect_values_for_code(
                        aggregated,
                        extra_code,
                        months_range,
                        extra_log,
                    )
                    if extra_code
                    else []
                )
                values = self._normalize_minutes_series(
                    values,
                    "HORA EXTRA 50",
                    config_key="cartoes_time_mode",
                )
                extra_values = self._normalize_minutes_series(
                    extra_values,
                    "HORA EXTRA 100",
                    config_key="cartoes_time_mode",
                )
                self._write_cartoes_csv(output_path, months_range, values, extra_values)
            elif writer == "horas_trabalhadas":
                horas_values = self._collect_values_for_code(
                    aggregated,
                    spec["code"],
                    months_range,
                    spec["log"],
                )
                horas_registradas = set(
                    aggregated.get(spec["code"], {}).keys()
                )
                faltas_code = spec.get("faltas_code")
                faltas_log = spec.get("faltas_log", spec["log"])
                faltas_values = (
                    self._collect_values_for_code(
                        aggregated,
                        faltas_code,
                        months_range,
                        faltas_log,
                    )
                    if faltas_code
                    else []
                )
                horas_values = self._normalize_minutes_series(
                    horas_values,
                    "HORAS TRABALHADAS",
                    config_key="horas_trabalhadas_time_mode",
                    fallback_key="cartoes_time_mode",
                )
                faltas_values = self._normalize_minutes_series(
                    faltas_values,
                    "FALTAS",
                    config_key="horas_trabalhadas_time_mode",
                    fallback_key="cartoes_time_mode",
                )
                afastamentos_config = spec.get("afastamentos", [])
                afastamentos_series: List[Dict[str, object]] = []
                for afast_config in afastamentos_config:
                    afast_values = self._collect_values_for_code(
                        aggregated,
                        afast_config["code"],
                        months_range,
                        afast_config.get("log", afast_config["label"]),
                    )
                    afast_values = self._normalize_minutes_series(
                        afast_values,
                        afast_config["label"],
                        config_key="horas_trabalhadas_time_mode",
                        fallback_key="cartoes_time_mode",
                    )
                    afastamentos_series.append(
                        {
                            "label": afast_config["label"],
                            "values": afast_values,
                            "include": self._has_non_zero_value(
                                aggregated, afast_config["code"]
                            ),
                        }
                    )
                values = horas_values
                self._write_horas_trabalhadas_csv(
                    output_path,
                    months_range,
                    horas_values,
                    faltas_values,
                    afastamentos=afastamentos_series,
                )
            else:
                values = self._collect_values_for_code(
                    aggregated,
                    spec["code"],
                    months_range,
                    spec["log"],
                )
                self._write_output_csv(output_path, values)
            self._log(f"✅ Arquivo gerado em {output_path}")
            outputs.append(
                {
                    "label": spec["label"],
                    "path": output_path,
                    "months": values,
                }
            )

        return outputs

    # ------------------------------------------------------------------
    # Extração de dados
    # ------------------------------------------------------------------

    def _parse_pdf(
        self,
        pdf_path: Path,
        *,
        progress_callback: Optional[Callable[[Path, int, int], None]] = None,
    ) -> Dict[str, object]:
        values: Dict[str, NumberByMonth] = {
            key: {} for key in self._storage_codes()
        }
        person_name: Optional[str] = None

        with pdfplumber.open(str(pdf_path)) as pdf:
            total_pages = len(pdf.pages)
            progress_error_logged = False
            if pdf.pages:
                person_name = self._extract_person_name(pdf.pages[0])

            def emit_page_progress(current_page: int) -> None:
                if not progress_callback:
                    return
                try:
                    progress_callback(pdf_path, current_page, total_pages)
                except Exception:
                    nonlocal progress_error_logged
                    if not progress_error_logged:
                        progress_error_logged = True
                        self._log(
                            "⚠️ Falha ao notificar progresso do PDF; ignorando callback."
                        )

            emit_page_progress(0)

            pending_blocks: List[ActiveBlock] = []
            last_comp_centers: List[float] = []
            last_valor_centers: List[float] = []

            for page_index, page in enumerate(pdf.pages):
                words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
                if not words:
                    emit_page_progress(page_index + 1)
                    continue

                comp_centers, valor_centers = self._extract_column_centers(words)
                if comp_centers:
                    last_comp_centers = list(comp_centers)
                else:
                    comp_centers = list(last_comp_centers)

                if valor_centers:
                    last_valor_centers = list(valor_centers)
                else:
                    valor_centers = list(last_valor_centers)
                extracted_blocks = self._extract_month_blocks(
                    words, page.height, comp_centers, valor_centers
                )

                active_blocks: List[Tuple[MonthBlock, ActiveBlock]] = []

                next_block_start = (
                    min(block.y_start for block in extracted_blocks)
                    if extracted_blocks
                    else page.height
                )

                for active in pending_blocks:
                    carry_block = MonthBlock(
                        year=active.block.year,
                        months=list(active.block.months),
                        y_start=0,
                        y_end=max(0, min(next_block_start - 0.5, page.height)),
                    )
                    active_blocks.append((carry_block, active))

                for block in extracted_blocks:
                    active_blocks.append(
                        (
                            block,
                            ActiveBlock(
                                block=MonthBlock(
                                    year=block.year,
                                    months=list(block.months),
                                    y_start=block.y_start,
                                    y_end=block.y_end,
                                )
                            ),
                        )
                    )

                next_pending: List[ActiveBlock] = []

                for block, state in active_blocks:
                    block_has_values = False

                    for code, cfg in self.TARGET_CODES.items():
                        column_index = int(cfg["column"])
                        search_prefix = str(cfg.get("search_prefix", code))
                        occurrences = self._find_row_occurrences(
                            words, search_prefix, block
                        )
                        if not occurrences:
                            continue

                        for row_words in occurrences:
                            extracted = self._extract_values_from_row(
                                row_words, block, column_index
                            )
                            if not extracted:
                                continue

                            block_has_values = True

                            storage_code = str(cfg.get("alias_for", code))
                            target = values.setdefault(storage_code, {})
                            for month_key, amount in extracted.items():
                                existing = target.get(month_key)
                                if existing is not None and existing != amount:
                                    self._log(
                                        f"⚠️ Valores conflitantes para {code} em {month_key[1]:02d}/{month_key[0]} (substituindo {existing} por {amount})."
                                    )
                                target[month_key] = amount

                    if not block_has_values:
                        next_count = state.carry_count + 1
                        if next_count <= self.MAX_BLOCK_CARRY:
                            next_pending.append(
                                ActiveBlock(block=state.block, carry_count=next_count)
                            )
                        else:
                            months_label = ", ".join(
                                f"{month.month:02d}" for month in state.block.months
                            )
                            self._log(
                                f"⚠️ Cabeçalho {state.block.year} ({months_label}) não apresentou valores após {self.MAX_BLOCK_CARRY} páginas."
                            )

                pending_blocks = next_pending

                emit_page_progress(page_index + 1)

        return {"values": values, "person_name": person_name}

    def _find_row_occurrences(
        self, words: List[Dict[str, object]], prefix: str, block: MonthBlock
    ) -> List[List[Dict[str, object]]]:
        rows: List[List[Dict[str, object]]] = []
        y_margin = 0.5
        x_margin = 1.0

        normalized_prefix = self._normalize_code_text(prefix)
        numeric_prefix = normalized_prefix.isdigit()
        seen_origins: Set[Tuple[int, int, int, int]] = set()

        code_column_margin = 12.0
        column_boundaries = [
            center
            for month in block.months
            for center in (month.comp_center, month.valor_center)
            if center is not None
        ]
        code_max_x: Optional[float] = None
        if column_boundaries:
            code_max_x = max(0.0, min(column_boundaries) - code_column_margin)
        else:
            self._log(
                "⚠️ Limite da coluna de códigos não estimado; usando heurística textual."
            )

        for word in words:
            text = word.get("text", "")
            normalized_text = self._normalize_code_text(text)

            if code_max_x is not None and float(word.get("x1", 0.0)) > code_max_x:
                continue

            if not normalized_text.startswith(normalized_prefix):
                continue

            if numeric_prefix and len(normalized_text) > len(normalized_prefix):
                next_char = normalized_text[len(normalized_prefix)]
                if next_char.isdigit() or next_char in {",", "."}:
                    continue

            origin = (
                int(round(word.get("top", 0) * 100)),
                int(round(word.get("bottom", 0) * 100)),
                int(round(word.get("x0", 0) * 100)),
                int(round(word.get("x1", 0) * 100)),
            )
            if origin in seen_origins:
                continue
            seen_origins.add(origin)

            row_top = max(block.y_start, word["top"] - y_margin)
            row_bottom = min(block.y_end, word["bottom"] + y_margin)
            min_x = word["x0"] - x_margin
            line_key = self._word_line_key(word)
            code_center = (float(word.get("top", 0)) + float(word.get("bottom", 0))) / 2
            center_tolerance = 0.3

            row_words: List[Dict[str, object]] = []
            for candidate in words:
                if self._word_line_key(candidate) != line_key:
                    continue

                if candidate["bottom"] < row_top or candidate["top"] > row_bottom:
                    continue

                if candidate["x1"] < min_x:
                    continue

                candidate_center = (
                    float(candidate.get("top", 0)) + float(candidate.get("bottom", 0))
                ) / 2
                if abs(candidate_center - code_center) > center_tolerance:
                    continue

                row_words.append(candidate)

            row_words.sort(key=lambda item: (item["x0"], item["x1"]))

            if row_words:
                rows.append(row_words)

        return rows

    def _word_line_key(self, word: Dict[str, object]) -> Tuple[str, int, Optional[int]]:
        line_number = word.get("line_number")
        if isinstance(line_number, int):
            return ("line", line_number, None)

        doctop = word.get("doctop")
        if doctop is not None:
            scaled = int(round(float(doctop) * 100))
            return ("doctop", scaled, None)

        top = word.get("top")
        bottom = word.get("bottom")
        return (
            "bounds",
            int(round(float(top or 0) * 100)),
            int(round(float(bottom or 0) * 100)),
        )

    def _normalize_code_text(self, text: str) -> str:
        cleaned = unicodedata.normalize("NFKD", text or "").replace("\xa0", " ")
        cleaned = cleaned.replace("‑", "-").replace("–", "-")
        return re.sub(r"\s+", "", cleaned)

    def _extract_values_from_row(
        self, row_words: List[Dict[str, object]], block: MonthBlock, column: int
    ) -> NumberByMonth:
        results: NumberByMonth = {}

        for word in row_words:
            text = word.get("text", "")
            if not self._is_number(text):
                continue

            value = self._to_decimal(text)
            center = (word["x0"] + word["x1"]) / 2

            best_month: Optional[MonthColumn] = None
            best_distance: Optional[float] = None

            for month in block.months:
                target_center = (
                    month.comp_center if column == 1 else month.valor_center
                )

                if target_center is not None:
                    distance = abs(center - target_center)
                else:
                    alternate_center = (
                        month.valor_center if column == 1 else month.comp_center
                    )
                    if alternate_center is None:
                        continue
                    distance = abs(center - alternate_center)

                if distance <= 25:
                    if best_distance is None or distance < best_distance:
                        best_month = month
                        best_distance = distance

            if best_month is not None:
                results[(block.year, best_month.month)] = value

        return results

    def _normalize_minutes_series(
        self,
        series: Iterable[Tuple[int, int, Decimal]],
        label: str,
        *,
        config_key: str,
        fallback_key: Optional[str] = None,
    ) -> List[Tuple[int, int, Decimal]]:
        normalized: List[Tuple[int, int, Decimal]] = []

        convert_minutes = self._should_convert_minutes(
            config_key=config_key,
            fallback_key=fallback_key,
        )

        for year, month, value in series:
            converted = (
                self._convert_minutes_value(value)
                if convert_minutes
                else value
            )
            normalized.append((year, month, converted))

            if convert_minutes and converted != value:
                self._log(
                    "⏱️ Ajuste de tempo em "
                    f"{month:02d}/{year} para {label}: "
                    f"{self._format_decimal(value)} → {self._format_decimal(converted)}."
                )

        return normalized

    def _should_convert_minutes(
        self,
        *,
        config_key: str,
        fallback_key: Optional[str] = None,
    ) -> bool:
        mode = self._config.get(config_key)
        if mode is None and fallback_key:
            mode = self._config.get(fallback_key)

        if mode is None:
            mode = self.CARTOES_TIME_MODE_DECIMAL

        return str(mode).lower() == self.CARTOES_TIME_MODE_MINUTES

    def _convert_minutes_value(self, value: Decimal) -> Decimal:
        if value == Decimal("0"):
            return value

        abs_value = value.copy_abs()
        text = format(abs_value, "f")

        if "." not in text:
            return value

        integer_text, fractional_text = text.split(".", 1)
        if not fractional_text:
            return value

        if len(fractional_text) > 2:
            return value

        try:
            minutes_total = int(fractional_text)
        except ValueError:
            return value

        hours_from_minutes = minutes_total // 60
        minutes_remainder = minutes_total % 60

        base_hours = int(integer_text) if integer_text else 0

        converted = (
            Decimal(base_hours + hours_from_minutes)
            + (Decimal(minutes_remainder) / Decimal("60"))
        )

        return converted if value >= 0 else -converted

    def _extract_column_centers(
        self, words: List[Dict[str, object]]
    ) -> Tuple[List[float], List[float]]:
        comp_centers: List[float] = []
        valor_centers: List[float] = []

        for word in words:
            text = word.get("text", "")
            if text == "Comp.":
                comp_centers.append((word["x0"] + word["x1"]) / 2)
            elif text == "Valor":
                valor_centers.append((word["x0"] + word["x1"]) / 2)

        return comp_centers, valor_centers

    def _extract_month_blocks(
        self,
        words: List[Dict[str, object]],
        page_height: float,
        comp_centers: Sequence[float],
        valor_centers: Sequence[float],
    ) -> List[MonthBlock]:
        month_blocks: List[MonthBlock] = []

        words_sorted = sorted(
            words,
            key=lambda item: ((item["top"] + item["bottom"]) / 2, item["x0"]),
        )

        for word in words_sorted:
            text = word.get("text", "")
            if not (text.isdigit() and len(text) == 4):
                continue

            year = int(text)
            row_center = round((word["top"] + word["bottom"]) / 2, 1)
            same_row = [
                candidate
                for candidate in words_sorted
                if abs(round((candidate["top"] + candidate["bottom"]) / 2, 1) - row_center)
                < 0.2
            ]
            month_names = [item["text"] for item in same_row if item["text"] != text]
            if not month_names:
                continue

            months: List[MonthColumn] = []
            comp_idx = 0
            valor_idx = 0
            for name in month_names:
                normalized = name.strip().lower()
                if normalized == "*totais*":
                    valor_idx += 1
                    continue

                month_number = self.MONTH_MAP.get(normalized)
                if not month_number:
                    continue

                comp_center = (
                    comp_centers[comp_idx] if comp_idx < len(comp_centers) else None
                )
                valor_center = (
                    valor_centers[valor_idx] if valor_idx < len(valor_centers) else None
                )
                months.append(
                    MonthColumn(
                        name=name,
                        month=month_number,
                        comp_center=comp_center,
                        valor_center=valor_center,
                    )
                )
                comp_idx += 1
                valor_idx += 1

            if not months:
                continue

            month_blocks.append(
                MonthBlock(
                    year=year,
                    months=months,
                    y_start=row_center,
                    y_end=page_height,
                )
            )

        month_blocks.sort(key=lambda block: block.y_start)
        for index, block in enumerate(month_blocks):
            next_start = (
                month_blocks[index + 1].y_start if index + 1 < len(month_blocks) else page_height
            )
            block.y_end = next_start - 0.5

        return month_blocks

    def _extract_person_name(self, page: pdfplumber.page.Page) -> Optional[str]:
        text = page.extract_text() or ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        for idx, line in enumerate(lines):
            if "Nome" in line and "Matr/Contr" in line:
                if idx + 1 < len(lines):
                    candidate = lines[idx + 1]
                    cleaned = self._clean_person_name(candidate)
                    if cleaned:
                        return cleaned
                    match = re.match(r"([A-Za-zÀ-ÿ'`\s]+?)\s+\d", candidate)
                    if match:
                        return match.group(1).strip()
                    return candidate.split("  ")[0].strip()

        name_patterns = [
            r"Nome\s*[:\-]?\s*([A-Za-zÀ-ÿ'`\s]+)",
            r"NOME\s*[:\-]?\s*([A-Za-zÀ-ÿ'`\s]+)",
        ]

        for line in lines:
            for pattern in name_patterns:
                match = re.search(pattern, line)
                if match:
                    cleaned = self._clean_person_name(match.group(1))
                    if cleaned:
                        return cleaned

        fallback_patterns = [
            r"Nome\s*:\s*([A-ZÁÇÃÂÊÔÉÍÓÚÀÈÌÒÙ\s]+)",
            r"NOME\s*:\s*([A-ZÁÇÃÂÊÔÉÍÓÚÀÈÌÒÙ\s]+)",
        ]

        for pattern in fallback_patterns:
            match = re.search(pattern, text)
            if match:
                cleaned = self._clean_person_name(match.group(1))
                if cleaned:
                    return cleaned

        return None

    def _clean_person_name(self, raw_name: str) -> Optional[str]:
        if not raw_name:
            return None

        trimmed = raw_name.strip()
        trimmed = re.sub(r"\s+\d.*$", "", trimmed)
        trimmed = re.sub(r"[^A-Za-zÀ-ÿ'`\s-]", " ", trimmed)
        cleaned = re.sub(r"\s+", " ", trimmed).strip()

        if len(cleaned) < 3:
            return None

        if not re.search(r"[A-Za-zÀ-ÿ]", cleaned):
            return None

        return cleaned

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _collect_values_for_code(
        self,
        aggregated: Dict[str, NumberByMonth],
        code: str,
        months: Iterable[Tuple[int, int]],
        log_label: str,
    ) -> List[Tuple[int, int, Decimal]]:
        results: List[Tuple[int, int, Decimal]] = []

        for year, month in months:
            value = aggregated.get(code, {}).get((year, month), Decimal("0"))
            results.append((year, month, value))
            self._log(
                f"🧮 Mês {month:02d}/{year}: {self._format_decimal(value)} extraído para {log_label}."
            )

        return results

    def _has_non_zero_value(
        self, aggregated: Dict[str, NumberByMonth], code: str
    ) -> bool:
        values = aggregated.get(code, {})
        return any(value not in (None, Decimal("0")) for value in values.values())

    def _apply_vacation_adjustments(
        self, aggregated: Dict[str, NumberByMonth]
    ) -> None:
        base_values = aggregated.setdefault("3123-Base", {})

        vacation_pairs = (
            ("173-Ferias", "174-Ferias"),
            ("167-Ferias", "168-Ferias"),
        )

        vacation_months: Set[Tuple[int, int]] = set()

        for code_a, code_b in vacation_pairs:
            values_a = aggregated.get(code_a, {})
            values_b = aggregated.get(code_b, {})

            qualifying = {
                key
                for key in values_a.keys() | values_b.keys()
                if (
                    values_a.get(key) not in (None, Decimal("0"))
                    or values_b.get(key) not in (None, Decimal("0"))
                )
            }

            vacation_months.update(qualifying)

        inss_comp = aggregated.get("527-INSS-Comp", {})
        inss_valor = aggregated.get("527-INSS-Valor", {})

        vacation_months.update(inss_comp.keys())
        vacation_months.update(inss_valor.keys())

        if not vacation_months:
            return

        for year, month in vacation_months:
            key = (year, month)
            comp_value = inss_comp.get(key)
            valor_value = inss_valor.get(key)

            if (
                comp_value is None
                or valor_value is None
                or comp_value == Decimal("0")
            ):
                continue

            divisor = comp_value / Decimal("100")
            if divisor == Decimal("0"):
                continue

            additional = valor_value / divisor
            base_current = base_values.get(key)
            if base_current is None:
                base_current = Decimal("0")
            base_values[key] = base_current + additional

            self._log(
                "➕ Ajuste de férias aplicado em "
                f"{month:02d}/{year}: {self._format_decimal(additional)} somado ao 3123."
            )

    def _write_output_csv(
        self, output_path: Path, months: Iterable[Tuple[int, int, Decimal]]
    ) -> None:
        header = [
            "MES_ANO",
            "VALOR",
            "FGTS",
            "FGTS_REC.",
            "CONTRIBUICAO_SOCIAL",
            "CONTRIBUICAO_SOCIAL_REC.",
            "",
            "",
            "",
            "",
        ]

        with output_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file, delimiter=";", lineterminator="\n")
            writer.writerow(header)
            for year, month, value in months:
                mes_ano = f"{month:02d}/{year}"
                formatted = self._format_decimal(value)
                writer.writerow(
                    [
                        mes_ano,
                        formatted,
                        "N",
                        "N",
                        "N",
                        "N",
                        "",
                        "",
                        "",
                        "",
                    ]
                )

    def _write_cartoes_csv(
        self,
        output_path: Path,
        months: Iterable[Tuple[int, int]],
        horas_50: Iterable[Tuple[int, int, Decimal]],
        horas_100: Iterable[Tuple[int, int, Decimal]],
    ) -> None:
        horas_50_map = {
            (year, month): value for year, month, value in horas_50
        }
        horas_100_map = {
            (year, month): value for year, month, value in horas_100
        }

        include_extra_100 = any(
            value != Decimal("0") for value in horas_100_map.values()
        )

        header = ["PERIODO", "HORA EXTRA 50%"]
        if include_extra_100:
            header.append("HORA EXTRA 100%")

        ordered_months: List[Tuple[int, int]] = list(months)

        missing_months = [
            key
            for key in horas_100_map.keys()
            if key not in horas_50_map and key not in ordered_months
        ]
        if missing_months:
            ordered_months.extend(sorted(missing_months))

        with output_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file, delimiter=";", lineterminator="\n")
            writer.writerow(header)

            for year, month in ordered_months:
                mes_ano = f"{month:02d}/{year}"
                valor_50 = horas_50_map.get((year, month), Decimal("0"))
                row = [mes_ano, self._format_decimal(valor_50)]

                if include_extra_100:
                    valor_100 = horas_100_map.get((year, month), Decimal("0"))
                    row.append(self._format_decimal(valor_100))

                writer.writerow(row)

    def _write_horas_trabalhadas_csv(
        self,
        output_path: Path,
        months: Iterable[Tuple[int, int]],
        horas: Iterable[Tuple[int, int, Decimal]],
        faltas: Iterable[Tuple[int, int, Decimal]],
        *,
        afastamentos: Optional[List[Dict[str, object]]] = None,
    ) -> None:
        horas_map = {(year, month): value for year, month, value in horas}
        faltas_map = {(year, month): value for year, month, value in faltas}

        ordered_months: List[Tuple[int, int]] = list(months)

        afastamentos = afastamentos or []
        afastamento_months: Set[Tuple[int, int]] = set()
        afastamento_series: List[Dict[str, object]] = []
        afastamento_headers: List[str] = []

        for afastamento in afastamentos:
            values_iter = afastamento.get("values", [])
            values_map = {
                (year, month): value
                for year, month, value in values_iter
            }
            afastamento_months.update(values_map.keys())
            include_column = bool(afastamento.get("include"))
            afastamento_series.append(
                {
                    "label": afastamento.get("label", ""),
                    "map": values_map,
                    "include": include_column,
                }
            )
            if include_column:
                afastamento_headers.append(afastamento.get("label", ""))

        additional_months = [
            key
            for key in set(horas_map.keys()) | set(faltas_map.keys())
            | afastamento_months
            if key not in ordered_months
        ]
        if additional_months:
            ordered_months.extend(sorted(additional_months))

        header = [
            "PERIODO",
            "HORAS TRAB.",
            "FALTAS",
            "SALDO HORAS",
            *afastamento_headers,
            "DIAS TRABALHADOS",
            "DIAS FERIAS",
        ]

        horas_referencia = Decimal("200")
        dias_referencia = Decimal("30")

        with output_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file, delimiter=";", lineterminator="\n")
            writer.writerow(header)

            for year, month in ordered_months:
                mes_ano = f"{month:02d}/{year}"
                horas_valor = horas_map.get(
                    (year, month), Decimal("0")
                )
                faltas_valor = faltas_map.get((year, month), Decimal("0"))
                total_afastamentos = Decimal("0")
                afastamento_row_values: List[str] = []
                for afastamento in afastamento_series:
                    valor_afast = afastamento["map"].get(
                        (year, month), Decimal("0")
                    )
                    total_afastamentos += valor_afast
                    if afastamento["include"]:
                        afastamento_row_values.append(
                            self._format_decimal(valor_afast)
                        )

                horas_planilha = horas_referencia - total_afastamentos
                if horas_planilha < Decimal("0"):
                    horas_planilha = Decimal("0")

                saldo_horas = horas_planilha - faltas_valor

                dias_trabalhados_valor = None
                dias_ferias_valor = None

                horas_para_ferias = horas_valor + total_afastamentos
                if horas_para_ferias < horas_referencia:
                    dias_trabalhados_valor = (
                        (horas_valor * dias_referencia) / horas_referencia
                    )
                    dias_ferias_valor = dias_referencia - dias_trabalhados_valor

                writer.writerow(
                    [
                        mes_ano,
                        self._format_decimal(horas_planilha),
                        self._format_decimal(faltas_valor),
                        self._format_decimal(saldo_horas),
                        *afastamento_row_values,
                        self._format_decimal(dias_trabalhados_valor, places=0)
                        if dias_trabalhados_valor is not None
                        else "",
                        self._format_decimal(dias_ferias_valor, places=0)
                        if dias_ferias_valor is not None
                        else "",
                    ]
                )

    def _iterate_months(self, start: date, end: date) -> Iterable[Tuple[int, int]]:
        current_year = start.year
        current_month = start.month

        while (current_year, current_month) <= (end.year, end.month):
            yield current_year, current_month
            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1

    def _build_folder_and_file_slugs(
        self, path: Path, person_name: str
    ) -> Tuple[str, str]:
        base_slug = self._slugify_name(person_name)
        if not base_slug:
            base_slug = self._slugify_name(path.stem)

        timestamp = datetime.now().strftime("%d%m%Y_%H%M")

        folder_slug = f"{base_slug}_{timestamp}" if base_slug else timestamp
        file_slug = base_slug or timestamp

        return folder_slug, file_slug

    def _slugify_name(self, name: str) -> str:
        normalized = unicodedata.normalize("NFKD", name)
        ascii_text = "".join(
            ch for ch in normalized if not unicodedata.combining(ch)
        )
        ascii_text = ascii_text.replace(" ", "_")
        ascii_text = re.sub(r"[^A-Za-z0-9_\-]", "", ascii_text)
        return ascii_text or "resultado"

    def _format_decimal(self, value: Decimal, *, places: int = 2) -> str:
        quant = Decimal("1").scaleb(-places) if places > 0 else Decimal("1")
        quantized = value.quantize(quant, rounding=ROUND_HALF_UP)
        text = format(quantized, "f")
        if places > 0:
            text = text.rstrip("0").rstrip(".")
        text = text.replace(".", ",")
        return text or "0"

    def _is_number(self, text: str) -> bool:
        return bool(self.NUMBER_PATTERN.match(text))

    def _to_decimal(self, text: str) -> Decimal:
        cleaned = text.replace(".", "").replace(",", ".")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return Decimal("0")

    def _log(self, message: str) -> None:
        if self._log_callback:
            self._log_callback(message)

