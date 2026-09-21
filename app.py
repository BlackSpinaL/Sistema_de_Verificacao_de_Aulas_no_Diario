import streamlit as st
import pandas as pd
import pdfplumber
import re

st.set_page_config(page_title="Verificador de Diário", layout="wide", page_icon="📚")

st.title("📚 Verificador de Aulas Lançadas no Diário")
st.markdown("""
Compara os **dias letivos previstos** (planilha) com os dias 
**efetivamente registrados** no PDF do diário, apontando aulas não lançadas.
""")

# =========================================================
# 1) Uploads
# =========================================================
col1, col2 = st.columns(2)
with col1:
    excel_file = st.file_uploader("📊 Planilha de Dias Letivos (.xlsx)", type=["xlsx"])
with col2:
    pdf_file = st.file_uploader("📄 Diário de Classe (.pdf)", type=["pdf"])

# =========================================================
# 2) Seleção da Etapa
# =========================================================
st.divider()
st.subheader("🎯 Etapa a Verificar")

etapa_opcoes = {"1ª Etapa": 1, "2ª Etapa": 2, "3ª Etapa": 3}
etapa_label = st.radio(
    "Deseja verificar os dados de qual etapa?",
    options=list(etapa_opcoes.keys()),
    horizontal=True,
)
etapa_selecionada = etapa_opcoes[etapa_label]

# =========================================================
# 3) Distribuição manual
# =========================================================
st.divider()
st.subheader("⚙️ Distribuição de Aulas (manual)")
st.caption(f"Informe quantas aulas da disciplina ocorrem em cada dia da semana **na {etapa_label}**.")

dias_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira"]
default_dist = pd.DataFrame({
    "Dia da Semana": dias_semana,
    "Nº de Aulas": [2, 1, 1, 1, 1],
})
dist_df = st.data_editor(default_dist, num_rows="fixed",
                         use_container_width=True, key="dist_editor")

# =========================================================
# 4) Extração robusta de datas
# =========================================================
def extract_dates_from_pdf(pdf_file):
    """
    Extrai datas DD/MM do PDF usando múltiplos padrões.
    Retorna (set_de_datas, texto_bruto_concatenado).
    """
    dates = set()
    pages_text = []

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages_text.append(text)

            # Normaliza espaços especiais que o pdfplumber insere
            normalized = re.sub(r'[\u00A0\u2007\u202F\u2009]', ' ', text)

            # --- Padrão 1: DD/MM em qualquer lugar (sem ^) ---
            for m in re.finditer(r'(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)', normalized):
                d, mo = int(m.group(1)), int(m.group(2))
                if 1 <= d <= 31 and 1 <= mo <= 12:
                    dates.add(f"{d:02d}/{mo:02d}")

    return dates, "\n\n===== PAGE BREAK =====\n\n".join(pages_text)


# =========================================================
# 5) Verificação
# =========================================================
st.divider()

if not excel_file or not pdf_file:
    st.info("👆 Faça upload dos dois arquivos para habilitar a verificação.")
    st.stop()

if not st.button("🔍 Verificar Aulas Faltantes", type="primary", use_container_width=True):
    st.stop()

with st.spinner(f"Processando {etapa_label}..."):
    try:
        # ---------- Dias letivos ----------
        xls = pd.ExcelFile(excel_file)
        sheet_name = "Dias Letivos" if "Dias Letivos" in xls.sheet_names else xls.sheet_names[0]
        dias_df = pd.read_excel(xls, sheet_name=sheet_name)
        dias_df["Data"] = pd.to_datetime(dias_df["Data"], errors="coerce")
        dias_df = dias_df.dropna(subset=["Data"])

        dias_etapa = dias_df[dias_df["Etapa"] == etapa_selecionada].copy()
        if dias_etapa.empty:
            st.error(f"Nenhum dia letivo encontrado para a {etapa_label} na planilha.")
            st.stop()

        # ---------- Datas do PDF ----------
        registered_dates, raw_text = extract_dates_from_pdf(pdf_file)

        # ---------- Diagnóstico ----------
        with st.expander("🐞 Diagnóstico (abra se algo parecer errado)"):
            st.write(f"**Datas detectadas no PDF:** {len(registered_dates)}")
            if registered_dates:
                st.write(sorted(registered_dates))
            else:
                st.error("⚠️ Nenhuma data DD/MM foi encontrada no PDF. "
                         "Copie um trecho do texto bruto abaixo e me mostre.")
            st.text_area("📄 Texto bruto extraído (primeiros 5000 caracteres)",
                         raw_text[:5000], height=300)

        # ---------- Verificação ----------
        rows = []
        for _, row in dias_etapa.iterrows():
            data = row["Data"]
            weekday = str(row["Dia da Semana"]).strip()
            ddmm = data.strftime("%d/%m")

            match = dist_df[dist_df["Dia da Semana"] == weekday]
            n_aulas = int(match["Nº de Aulas"].iloc[0]) if len(match) > 0 else 0
            if n_aulas == 0:
                continue

            rows.append({
                "Data": data.strftime("%d/%m/%Y"),
                "Dia da Semana": weekday,
                "Aulas Previstas": n_aulas,
                "Lançado": "✅" if ddmm in registered_dates else "❌",
            })

        if not rows:
            st.warning("Nenhuma aula prevista encontrada.")
            st.stop()

        result_df = pd.DataFrame(rows)

        # ---------- Resumo ----------
        st.subheader(f"📊 Resumo — {etapa_label}")
        prev_total = int(result_df["Aulas Previstas"].sum())
        lanc_total = int(result_df[result_df["Lançado"] == "✅"]["Aulas Previstas"].sum())
        falt_total = prev_total - lanc_total

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Dias letivos", len(result_df))
        c2.metric("Aulas previstas", prev_total)
        c3.metric("Aulas lançadas", lanc_total)
        c4.metric("Aulas faltantes", falt_total)

        # ---------- Aulas faltantes ----------
        st.subheader("❌ Aulas Não Lançadas no Diário")
        missing = result_df[result_df["Lançado"] == "❌"].copy()

        if missing.empty:
            st.success(f"🎉 Todas as aulas da {etapa_label} foram lançadas!")
        else:
            st.dataframe(missing, use_container_width=True, hide_index=True)
            st.warning(
                f"**{len(missing)} dia(s) com aula não lançada** na {etapa_label} — "
                f"Total de aulas faltantes: **{int(missing['Aulas Previstas'].sum())}**"
            )
            csv = missing.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                f"📥 Baixar CSV ({etapa_label})",
                csv,
                f"aulas_faltantes_{etapa_selecionada}etapa.csv",
                "text/csv",
            )

        with st.expander(f"🔎 Todos os dias da {etapa_label} e status"):
            st.dataframe(result_df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Erro ao processar: {e}")
        with st.expander("Detalhes do erro"):
            st.exception(e)
