from pathlib import Path

from processors.planilha_dados_processor import PlanilhaDadosProcessor


def test_planilha_dados_processor_matches_samples(tmp_path: Path) -> None:
    processor = PlanilhaDadosProcessor()
    workbook = Path("NOVO_MODULO_PLANILHA_DADOS/AISLAN DE MIRA CIDRAL.xlsm")

    processor.process(workbook, tmp_path, start_period=(2013, 9), end_period=(2015, 10))

    expected_dir = Path("NOVO_MODULO_PLANILHA_DADOS")
    for filename in [
        PlanilhaDadosProcessor.REMUNERACAO_FILENAME,
        PlanilhaDadosProcessor.PRODUCAO_FILENAME,
        PlanilhaDadosProcessor.CARTOES_FILENAME,
    ]:
        generated = (tmp_path / filename).read_text(encoding="latin-1")
        expected = (expected_dir / filename).read_text(encoding="latin-1")
        assert generated == expected
