import streamlit as st
import pandas as pd
import pdfplumber
import re

st.set_page_config(page_title="Verificador de Diário", layout="wide", page_icon="📚")

st.title("📚 Verificador de Aulas Lançadas no Diário")
st.markdown("""
Compara os **dias letivos previstos** (planilha de distribuição) com os dias 
**efetivamente registrados** no PDF do diário de classe, identificando aulas não lançadas.
""")

# ============================
# 1) Uploads
# ============================
col1, col2 = st.columns(2)

with col1:
    excel_file = st.file_uploader("📊 Planilha de Dias Letivos (.xlsx)", type=["xlsx"])

with col2:
    pdf_file = st.file_uploader("📄 Diário de Classe (.pdf)", type=["pdf"])

# ============================
# 2) Distribuição manual
# ============================
st.divider()
st.subheader("⚙️ Distribuição de Aulas (manual)")
st.caption("Informe quantas aulas da disciplina ocorrem em cada dia da semana, por etapa.")

default_dist = pd.DataFrame({
    "Etapa": [1,1,1,1,1, 2,2,2,2,2, 3,3,3,3,3],
    "Dia da Semana": ["Segunda-feira","Terça-feira","Quarta-feira","Quinta-feira","Sexta-feira"] * 3,
    "Nº de Aulas": [2,1,1,1,1, 2,1,1,1,1, 2,1,1,1,1],
})

dist_df = st.data_editor(
    default_dist,
    num_rows="dynamic",
    use_container_width=True,
    key="dist_editor",
)

# ============================
# 3) Verificação
# ============================
st.divider()

if not excel_file or not pdf_file:
    st.info("👆 Faça upload dos dois arquivos para habilitar a verificação.")
    st.stop()

if not st.button("🔍 Verificar Aulas Faltantes", type="primary", use_container_width=True):
    st.stop()

with st.spinner("Processando planilha e PDF..."):
    try:
        # --- Dias letivos ---
        xls = pd.ExcelFile(excel_file)
        sheet_name = "Dias Letivos" if "Dias Letivos" in xls.sheet_names else xls.sheet_names[0]
        dias_df = pd.read_excel(xls, sheet_name=sheet_name)
        dias_df["Data"] = pd.to_datetime(dias_df["Data"], errors="coerce")
        dias_df = dias_df.dropna(subset=["Data"])

        # --- Extrai datas do PDF ---
        registered_dates = set()
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for m in re.finditer(r'^\s*(\d{1,2})/(\d{1,2})\b', text, re.MULTILINE):
                    d, mo = int(m.group(1)), int(m.group(2))
                    registered_dates.add(f"{d:02d}/{mo:02d}")

        # --- Monta tabela ---
        rows = []
        for _, row in dias_df.iterrows():
            etapa = row["Etapa"]
            data = row["Data"]
            weekday = str(row["Dia da Semana"]).strip()
            ddmm = data.strftime("%d/%m")

            match = dist_df[
                (dist_df["Etapa"] == etapa) &
                (dist_df["Dia da Semana"] == weekday)
            ]
            n_aulas = int(match["Nº de Aulas"].iloc[0]) if len(match) > 0 else 0
            if n_aulas == 0:
                continue

            rows.append({
                "Etapa": etapa,
                "Data": data.strftime("%d/%m/%Y"),
                "Dia da Semana": weekday,
                "Aulas Previstas": n_aulas,
                "Lançado": "✅" if ddmm in registered_dates else "❌",
            })

        if not rows:
            st.warning("Nenhuma aula prevista encontrada. Verifique a distribuição informada.")
            st.stop()

        result_df = pd.DataFrame(rows)

        # --- Resumo por etapa ---
        st.subheader("📊 Resumo")
        summary_rows = []
        for etapa in sorted(result_df["Etapa"].unique()):
            sub = result_df[result_df["Etapa"] == etapa]
            prev = int(sub["Aulas Previstas"].sum())
            lanc = int(sub[sub["Lançado"] == "✅"]["Aulas Previstas"].sum())
            summary_rows.append({
                "Etapa": f"{etapa}ª Etapa",
                "Aulas Previstas": prev,
                "Aulas Lançadas": lanc,
                "Aulas Faltantes": prev - lanc,
            })
        summary_rows.append({
            "Etapa": "TOTAL",
            "Aulas Previstas": int(result_df["Aulas Previstas"].sum()),
            "Aulas Lançadas": int(result_df[result_df["Lançado"] == "✅"]["Aulas Previstas"].sum()),
            "Aulas Faltantes": int(result_df[result_df["Lançado"] == "❌"]["Aulas Previstas"].sum()),
        })
        summary_df = pd.DataFrame(summary_rows)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        # --- Aulas faltantes ---
        st.subheader("❌ Aulas Não Lançadas no Diário")
        missing = result_df[result_df["Lançado"] == "❌"].copy()
        if missing.empty:
            st.success("🎉 Todas as aulas previstas foram lançadas!")
        else:
            st.dataframe(missing, use_container_width=True, hide_index=True)
            st.warning(
                f"**{len(missing)} dia(s) com aula não lançada** — "
                f"Total de aulas faltantes: **{int(missing['Aulas Previstas'].sum())}**"
            )
            csv = missing.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 Baixar lista (CSV)", csv, "aulas_faltantes.csv", "text/csv")

        # --- Detalhes ---
        with st.expander("🔎 Ver todos os dias e status"):
            st.dataframe(result_df, use_container_width=True, hide_index=True)

        with st.expander("🗓️ Datas detectadas no PDF"):
            st.write(f"Total: **{len(registered_dates)}** datas")
            st.write(sorted(registered_dates))

    except Exception as e:
        st.error(f"Erro ao processar: {e}")
        with st.expander("Detalhes do erro"):
            st.exception(e)