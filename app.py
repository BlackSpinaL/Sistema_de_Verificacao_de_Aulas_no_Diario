import streamlit as st
import pandas as pd
import pdfplumber
import re

st.set_page_config(
    page_title="Verificador de Diário",
    layout="wide",
    page_icon="📚"
)

st.title("📚 Verificador de Aulas Lançadas no Diário")

# =========================================================
# 1) Uploads
# =========================================================
col1, col2 = st.columns(2)

with col1:
    excel_file = st.file_uploader(
        "📊 Planilha de Dias Letivos (.xlsx)",
        type=["xlsx"]
    )

with col2:
    pdf_file = st.file_uploader(
        "📄 Diário de Classe (.pdf)",
        type=["pdf"]
    )


# =========================================================
# 2) Etapa
# =========================================================
st.divider()

etapa_opcoes = {
    "1ª Etapa": 1,
    "2ª Etapa": 2,
    "3ª Etapa": 3
}

etapa_label = st.radio(
    "Deseja verificar os dados de qual etapa?",
    options=list(etapa_opcoes.keys()),
    horizontal=True,
)

etapa_selecionada = etapa_opcoes[etapa_label]


# =========================================================
# 3) Distribuição de aulas
# =========================================================
st.divider()

st.subheader("⚙️ Distribuição de Aulas")

st.caption(
    f"Informe quantas aulas da disciplina acontecem em cada "
    f"dia da semana na {etapa_label}."
)

default_dist = pd.DataFrame({
    "Dia da Semana": [
        "Segunda-feira",
        "Terça-feira",
        "Quarta-feira",
        "Quinta-feira",
        "Sexta-feira"
    ],
    "Nº de Aulas": [1, 0, 1, 1, 1],
})

dist_df = st.data_editor(
    default_dist,
    num_rows="fixed",
    use_container_width=True,
    key="dist_editor"
)


# =========================================================
# 4) EXTRAÇÃO DO PDF
# =========================================================
def extract_lessons_from_text(text):
    """
    Procura registros no formato:

        09/09 1 Texto da aula
        10/09 1 Texto da aula
        16/09 2 Texto da aula

    Também aceita espaços diferentes.
    """

    normalized = re.sub(
        r'[\u00A0\u2007\u202F\u2009]',
        ' ',
        text
    )

    lessons = []

    # Data + quantidade de aulas
    pattern = r'\b(\d{1,2})/(\d{1,2})\s+(\d{1,2})(?=\s|$)'

    for m in re.finditer(pattern, normalized):

        d = int(m.group(1))
        mo = int(m.group(2))
        count = int(m.group(3))

        if (
            1 <= d <= 31
            and 1 <= mo <= 12
            and 0 <= count <= 10
        ):
            lessons.append(
                (f"{d:02d}/{mo:02d}", count)
            )

    return lessons


# =========================================================
# 5) EXTRAÇÃO POR PALAVRAS
# =========================================================
def extract_lessons_from_words(pdf):

    lessons = []

    for page in pdf.pages:

        try:
            words = page.extract_words()
        except Exception:
            continue

        # Agrupa palavras aproximadamente por linha
        rows = {}

        for w in words:
            key = round(w["top"] / 5)

            rows.setdefault(key, []).append(w)

        for key in sorted(rows.keys()):

            line = sorted(
                rows[key],
                key=lambda w: w["x0"]
            )

            for j, w in enumerate(line):

                if re.match(
                    r'^\d{1,2}/\d{1,2}$',
                    w["text"]
                ):

                    # procura os próximos tokens
                    for k in range(
                        j + 1,
                        min(j + 4, len(line))
                    ):

                        token = line[k]["text"]

                        if re.match(
                            r'^\d{1,2}$',
                            token
                        ):

                            n = int(token)

                            if 0 <= n <= 10:

                                d, mo = w["text"].split("/")

                                lessons.append(
                                    (
                                        f"{int(d):02d}/{int(mo):02d}",
                                        n
                                    )
                                )

                                break

    return lessons


# =========================================================
# 6) PROCESSAMENTO
# =========================================================
st.divider()

if not excel_file or not pdf_file:

    st.info(
        "👆 Faça upload dos dois arquivos para habilitar a verificação."
    )

    st.stop()


if not st.button(
    "🔍 Verificar Aulas",
    type="primary",
    use_container_width=True
):

    st.stop()


with st.spinner(f"Processando {etapa_label}..."):

    try:

        # =====================================================
        # EXCEL
        # =====================================================

        xls = pd.ExcelFile(excel_file)

        sheet = (
            "Dias Letivos"
            if "Dias Letivos" in xls.sheet_names
            else xls.sheet_names[0]
        )

        dias_df = pd.read_excel(
            xls,
            sheet_name=sheet
        )

        dias_df["Data"] = pd.to_datetime(
            dias_df["Data"],
            errors="coerce"
        )

        dias_df = dias_df.dropna(
            subset=["Data"]
        )

        dias_etapa = dias_df[
            dias_df["Etapa"] == etapa_selecionada
        ].copy()

        if dias_etapa.empty:

            st.error(
                f"Nenhum dia letivo encontrado para a {etapa_label}."
            )

            st.stop()


        # =====================================================
        # PDF
        # =====================================================

        text_lessons = []
        word_lessons = []
        raw_pages = []

        with pdfplumber.open(pdf_file) as pdf:

            total_pages = len(pdf.pages)

            # IMPORTANTE:
            # NÃO ignorar a primeira página.
            for i, page in enumerate(pdf.pages):

                txt = page.extract_text() or ""

                raw_pages.append(
                    f"--- Página {i + 1} ---\n{txt}"
                )

                text_lessons.extend(
                    extract_lessons_from_text(txt)
                )

            # fallback
            word_lessons = extract_lessons_from_words(
                pdf
            )


        # =====================================================
        # Escolhe melhor método
        # =====================================================

        if len(text_lessons) >= len(word_lessons):

            lessons = text_lessons
            method_used = "texto"

        else:

            lessons = word_lessons
            method_used = "coordenadas"


        # =====================================================
        # Soma por data
        # =====================================================

        pdf_by_date = {}

        for date_str, count in lessons:

            pdf_by_date[date_str] = (
                pdf_by_date.get(date_str, 0)
                + count
            )


        # =====================================================
        # DIAGNÓSTICO
        # =====================================================

        with st.expander(
            "🐞 Diagnóstico da extração do PDF"
        ):

            st.write(
                f"**Total de páginas:** {total_pages}"
            )

            st.write(
                f"**Registros encontrados pelo texto:** "
                f"{len(text_lessons)}"
            )

            st.write(
                f"**Registros encontrados pelas palavras:** "
                f"{len(word_lessons)}"
            )

            st.write(
                f"**Método utilizado:** {method_used}"
            )

            st.write(
                "**Aulas detectadas:**"
            )

            st.json(pdf_by_date)

            st.text_area(
                "Texto bruto extraído",
                "\n\n".join(raw_pages)[:12000],
                height=300
            )


        # =====================================================
        # DATA DE CORTE
        # =====================================================

        if not pdf_by_date:

            st.error(
                "Nenhuma aula foi encontrada no PDF."
            )

            st.stop()


        # transforma DD/MM em datas do ano da etapa
        ano = dias_etapa["Data"].dt.year.mode()[0]

        datas_pdf = []

        for ddmm in pdf_by_date:

            try:

                data = pd.to_datetime(
                    f"{ddmm}/{ano}",
                    format="%d/%m/%Y"
                )

                datas_pdf.append(data)

            except Exception:
                pass


        if not datas_pdf:

            st.error(
                "Não foi possível determinar a data de corte."
            )

            st.stop()


        data_corte = max(datas_pdf)


        st.info(
            f"📅 Data de corte encontrada no diário: "
            f"**{data_corte.strftime('%d/%m/%Y')}**"
        )


        # =====================================================
        # COMPARAÇÃO
        # =====================================================

        rows = []

        for _, row in dias_etapa.iterrows():

            data = row["Data"]

            weekday = str(
                row["Dia da Semana"]
            ).strip()

            ddmm = data.strftime("%d/%m")


            # distribuição da disciplina
            match = dist_df[
                dist_df["Dia da Semana"] == weekday
            ]


            if len(match) > 0:

                expected = int(
                    match["Nº de Aulas"].iloc[0]
                )

            else:

                expected = 0


            launched = pdf_by_date.get(
                ddmm,
                0
            )


            # =================================================
            # STATUS
            # =================================================

            if data > data_corte:

                status = "⚪ Futuro"

                missing = 0

            elif launched >= expected:

                status = "🟢 OK"

                missing = 0

            else:

                status = "🔴 Faltante"

                missing = expected - launched


            if expected > 0:

                rows.append({

                    "Data": data.strftime(
                        "%d/%m/%Y"
                    ),

                    "Dia da Semana": weekday,

                    "Previstas": expected,

                    "Lançadas": launched,

                    "Faltantes": missing,

                    "Status": status

                })


        result_df = pd.DataFrame(rows)


        # =====================================================
        # RESUMO ATÉ DATA DE CORTE
        # =====================================================

        valid_df = result_df[
            pd.to_datetime(
                result_df["Data"],
                format="%d/%m/%Y"
            ) <= data_corte
        ].copy()


        total_prev_ate_corte = int(
            valid_df["Previstas"].sum()
        )

        total_lanc_ate_corte = int(
            valid_df["Lançadas"].sum()
        )

        total_falt_ate_corte = int(
            valid_df["Faltantes"].sum()
        )


        # =====================================================
        # RESUMO DA ETAPA INTEIRA
        # =====================================================

        total_prev_etapa = int(
            result_df["Previstas"].sum()
        )

        total_lanc = int(
            result_df["Lançadas"].sum()
        )

        total_futuras = int(
            result_df[
                result_df["Status"] == "⚪ Futuro"
            ]["Previstas"].sum()
        )


        # =====================================================
        # PAINEL
        # =====================================================

        st.subheader(
            f"📊 Resumo — {etapa_label}"
        )


        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Previstas até o corte",
            total_prev_ate_corte
        )

        c2.metric(
            "Lançadas até o corte",
            total_lanc_ate_corte
        )

        c3.metric(
            "Faltantes até o corte",
            total_falt_ate_corte
        )

        c4.metric(
            "Previstas na etapa",
            total_prev_etapa
        )


        # =====================================================
        # SITUAÇÃO
        # =====================================================

        st.subheader(
            "📌 Situação das aulas"
        )


        if total_falt_ate_corte == 0:

            st.success(
                f"Todas as aulas previstas até "
                f"{data_corte.strftime('%d/%m/%Y')} "
                f"estão lançadas no diário."
            )

        else:

            st.warning(
                f"Existem {total_falt_ate_corte} "
                f"aulas que deveriam estar lançadas "
                f"até {data_corte.strftime('%d/%m/%Y')}."
            )


        # =====================================================
        # FALTANTES
        # =====================================================

        st.subheader(
            "❌ Aulas faltantes"
        )

        missing_df = result_df[
            result_df["Faltantes"] > 0
        ].copy()


        if missing_df.empty:

            st.success(
                "🎉 Nenhuma aula faltante até a data de corte."
            )

        else:

            st.dataframe(
                missing_df,
                use_container_width=True,
                hide_index=True
            )


        # =====================================================
        # TODOS OS DIAS
        # =====================================================

        with st.expander(
            "🔎 Todos os dias da etapa"
        ):

            st.dataframe(
                result_df,
                use_container_width=True,
                hide_index=True
            )


    except Exception as e:

        st.error(
            f"Erro ao processar: {e}"
        )

        with st.expander(
            "Detalhes do erro"
        ):

            st.exception(e)
