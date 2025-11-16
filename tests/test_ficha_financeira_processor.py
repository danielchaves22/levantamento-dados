from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from processors.ficha_financeira_processor import FichaFinanceiraProcessor


class ApplyVacationAdjustmentsTest(unittest.TestCase):
    def test_applies_adjustment_when_single_vacation_code_has_value(self) -> None:
        processor = FichaFinanceiraProcessor()
        aggregated = {
            "173-Ferias": {},
            "174-Ferias": { (2024, 1): Decimal("2000") },
            "527-INSS-Comp": { (2024, 1): Decimal("3000") },
            "527-INSS-Valor": { (2024, 1): Decimal("300") },
        }

        processor._apply_vacation_adjustments(aggregated)

        base_values = aggregated.get("3123-Base", {})
        self.assertIn((2024, 1), base_values)
        self.assertEqual(Decimal("10"), base_values[(2024, 1)])

    def test_applies_adjustment_using_inss_months_when_vacation_values_zero(self) -> None:
        processor = FichaFinanceiraProcessor()
        aggregated = {
            "167-Ferias": { (2024, 2): Decimal("0") },
            "168-Ferias": { (2024, 2): Decimal("0") },
            "173-Ferias": { (2024, 2): Decimal("0") },
            "174-Ferias": { (2024, 2): Decimal("0") },
            "527-INSS-Comp": { (2024, 2): Decimal("3000") },
            "527-INSS-Valor": { (2024, 2): Decimal("300") },
        }

        processor._apply_vacation_adjustments(aggregated)

        base_values = aggregated.get("3123-Base", {})
        self.assertIn((2024, 2), base_values)
        self.assertEqual(Decimal("10"), base_values[(2024, 2)])


class InsalubridadeExtractionTest(unittest.TestCase):
    def test_extracts_insalubridade_values_from_pdf(self) -> None:
        processor = FichaFinanceiraProcessor()
        pdf_path = Path(
            "Testes/ExtracaoAparecidaSLima_FichaFinanceira/896_APARECIDA DOS SANTOS "
            "LIMA DA SILVAProcesso_0000132-43.2023.5.09.0562.pdf"
        )

        parse_result = processor._parse_pdf(pdf_path)
        insalubridade = parse_result["values"].get("8-Insalubridade", {})

        self.assertEqual(Decimal("484.80"), insalubridade.get((2022, 3)))
        self.assertEqual(Decimal("607.20"), insalubridade.get((2025, 4)))


class HorasTrabalhadasCsvTest(unittest.TestCase):
    def test_includes_day_columns_with_formula(self) -> None:
        processor = FichaFinanceiraProcessor()
        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "horas.csv"
            processor._write_horas_trabalhadas_csv(
                output_path,
                months=[(2024, 1)],
                horas=[(2024, 1, Decimal("180"))],
                faltas=[],
            )

            content = output_path.read_text(encoding="utf-8").strip().splitlines()

        self.assertEqual(
            "PERIODO;HORAS TRAB.;FALTAS;DIAS TRABALHADOS;DIAS FERIAS",
            content[0],
        )
        self.assertEqual("01/2024;180;0;27;-3", content[1])

    def test_leaves_day_columns_blank_when_hours_equal_reference(self) -> None:
        processor = FichaFinanceiraProcessor()
        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "horas.csv"
            processor._write_horas_trabalhadas_csv(
                output_path,
                months=[(2024, 2)],
                horas=[(2024, 2, Decimal("200"))],
                faltas=[(2024, 2, Decimal("5"))],
            )

            content = output_path.read_text(encoding="utf-8").strip().splitlines()

        self.assertEqual("02/2024;200;5;;", content[1])


if __name__ == "__main__":
    unittest.main()
