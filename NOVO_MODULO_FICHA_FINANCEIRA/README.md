# 📄 Módulo "Ficha Financeira"

Este módulo processa as fichas financeiras quadrimestrais e gera arquivos CSV padronizados. A implementação atual cria quatro arquivos (`PROVENTOS.csv`, `ADIC. INSALUBRIDADE PAGO.csv`, `CARTÕES.csv` e `HORAS TRABALHADAS.csv`), seguindo os exemplos disponíveis na pasta `NOVO_MODULO_FICHA_FINANCEIRA`.

## 🧭 Fluxo de uso na interface desktop

1. Abra a aplicação normalmente. Após o splash screen, selecione **Ficha Financeira**.
2. Informe o período desejado (mês/ano inicial e final).
3. Adicione um ou mais PDFs da ficha financeira. Todos os valores encontrados são consolidados, mês a mês.
4. Clique em **PROCESSAR Ficha Financeira** para criar os arquivos no diretório do primeiro PDF selecionado.

A janela mantém um painel de logs para acompanhar o andamento da extração.

> ℹ️ Na aba **⚙️ Configurações** é possível definir, de forma independente, como interpretar a parte decimal das horas extras dos cartões e das horas trabalhadas/faltas. Escolha entre considerar os valores como decimais ou como minutos (`00-59`).

## 🧮 Regras de extração

- Cada página é dividida em blocos de quatro meses. O último bloco do ano possui uma coluna adicional de totais que é ignorada.
- Os valores são extraídos pela posição das colunas `Comp.` e `Valor` identificadas no PDF. A rotina reconhece automaticamente as colunas, mesmo quando determinados campos estão vazios.
- Para o `PROVENTOS.csv`, são coletados os valores da verba **`3123 - Base INSS (Folha)`** na coluna `Valor`. Se o mês estiver ausente no PDF, o resultado é preenchido com `0`.
- Para o `ADIC. INSALUBRIDADE PAGO.csv`, são utilizados os valores da verba **`8 - Insalubridade`** na coluna `Valor`, seguindo a mesma regra de preenchimento com `0` para meses não encontrados.
- Para o `CARTÕES.csv`, são utilizados os valores da verba **`6 - Horas Extras 50%`** na coluna `Comp.`. Meses que não apresentarem essa verba são preenchidos com `0`.
- Para o `HORAS TRABALHADAS.csv`, a coluna `HORAS TRAB.` usa os valores da verba **`1 - Salário`** (coluna `Comp.`) e a coluna `FALTAS` usa os valores da verba **`952 - Falta Injustifica`** (coluna `Comp.`). A planilha também inclui `DIAS TRABALHADOS` e `DIAS FERIAS`, calculados pela fórmula `(HORAS TRAB. * 30 / 200)` e `DIAS TRABALHADOS - 30`, respectivamente, exceto quando `HORAS TRAB.` é igual a `200`, caso em que os campos permanecem em branco. Todos os campos aplicam a conversão de minutos para centesimal quando configurado especificamente para "horas trabalhadas/faltas" nas opções do projeto.
- Meses fora do intervalo solicitado são descartados, mesmo que existam no documento.
- As colunas `FGTS`, `FGTS_REC.`, `CONTRIBUICAO_SOCIAL` e `CONTRIBUICAO_SOCIAL_REC.` são preenchidas com `N`, conforme especificação.

## 🗂️ Estrutura dos arquivos gerados

Os arquivos `PROVENTOS.csv` e `ADIC. INSALUBRIDADE PAGO.csv` seguem o padrão de separador `;` e contêm dez colunas:

```
MES_ANO;VALOR;FGTS;FGTS_REC.;CONTRIBUICAO_SOCIAL;CONTRIBUICAO_SOCIAL_REC.;;;;
```

Cada linha representa um mês no formato `MM/AAAA`, com os valores convertidos para vírgula como separador decimal.

O arquivo `CARTÕES.csv` possui duas ou três colunas (`PERIODO`, `HORA EXTRA 50%` e opcionalmente `HORA EXTRA 100%`), usando o mesmo separador `;`.

O arquivo `HORAS TRABALHADAS.csv` possui cinco colunas (`PERIODO`, `HORAS TRAB.`, `FALTAS`, `DIAS TRABALHADOS` e `DIAS FERIAS`), seguindo o padrão de separador `;` e os mesmos ajustes de conversão de minutos para centesimal quando habilitados. Os dias são calculados usando a equivalência de 200 horas = 30 dias.

## 🔁 Reutilização futura

O processador `FichaFinanceiraProcessor` centraliza a lógica de leitura das fichas e facilita a inclusão de novas verbas ou CSVs. Os métodos responsáveis por mapear colunas e agrupar meses foram pensados para servir outros arquivos de saída que venham a ser necessários.

