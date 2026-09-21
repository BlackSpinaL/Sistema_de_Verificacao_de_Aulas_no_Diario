import streamlit as st
import pandas as pd
import pdfplumber
import re

st.set_page_config(page_title="Verificador de Diário", layout="wide", page_icon="📚")
st.title("📚 Verificador de Aulas Lançadas no Diário")

# =========================================================
# 1) Uploads
# =========================================================
col1, col2 = st.columns(2)
with col1:
    excel_file = st.file_uploader("📊 Planilha de Dias Letivos (.xlsx)", type=["xlsx"])
with col2:
    pdf_file = st.file_uploader("📄 Diário de Classe (.pdf)", type=["pdf"])

# =========================================================
# 2) Etapa
# =========================================================
st.divider()
etapa_opcoes = {"1ª Etapa": 1, "2ª Etapa": 2, "3ª Etapa": 3}
etapa_label = st.radio(
    "Deseja verificar os dados de qual etapa?",
    options=list(etapa_opcoes.keys()),
    horizontal=True,
)
etapa_selecionada = etapa_opcoes[etapa_label]

# =========================================================
# 3) Distribuição
# =========================================================
st.divider()
st.subheader("⚙️ Distribuição de Aulas (manual)")
st.caption(f"Quantas aulas da disciplina ocorrem em cada dia da semana **na {etapa_label}**.")

default_dist = pd.DataFrame({
    "Dia da Semana": ["Segunda-feira", "Terça-feira", "Quarta-feira",
                      "Quinta-feira", "Sexta-feira"],
    "Nº de Aulas": [2, 1, 1, 1, 1],
})
dist_df = st.data_editor(default_dist, num_rows="fixed",
                         use_container_width=True, key="dist_editor")

# =========================================================
# 4) Extração do PDF — apenas páginas 2+ (Síntese)
# =========================================================
def extract_lessons_from_text(text):
    """
    Extrai pares (DD/MM, qtd_aulas) do texto da Síntese.
    Suporta formatos:
      "18/05 1 ..." → 18/05 com 1 aula
      "05/02 0 ..." → 05/02 com 0 aulas
    """
    normalized = re.sub(r'[\u00A0\u2007\u202F\u2009]', ' ', text)

    lessons = []
    # Agora aceita espaço entre a data e o número de aulas
    pattern = r'(\d{1,2})/(\d{1,2})\s+(\d{1,2})'
    for m in re.finditer(pattern, normalized):
        d, mo, count = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12 and 0 <= count <= 10:
            lessons.append((f"{d:02d}/{mo:02d}", count))
    return lessons


def extract_lessons_from_words(pdf):
    """
    Fallback: usa coordenadas de palavras (para PDFs onde extract_text falha).
    Procura DD/MM seguido de número pequeno (aulas).
    """
    lessons = []
    for i, page in enumerate(pdf.pages):
        if i == 0:
            continue
        try:
            words = page.extract_words()
        except Exception:
            continue

        rows = {}
        for w in words:
            key = round(w['top'] / 5)
            rows.setdefault(key, []).append(w)

        for key in sorted(rows.keys()):
            line = sorted(rows[key], key=lambda w: w['x0'])
            for j, w in enumerate(line):
                if re.match(r'^\d{1,2}/\d{1,2}$', w['text']):
                    for k in range(j + 1, min(j + 3, len(line))):
                        if re.match(r'^\d{1,2}$', line[k]['text']):
                            n = int(line[k]['text'])
                            if 0 <= n <= 10:
                                d, mo = w['text'].split('/')
                                lessons.append((f"{int(d):02d}/{int(mo):02d}", n))
                                break
    return lessons

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
        # ---------- Dias letivos da planilha ----------
        xls = pd.ExcelFile(excel_file)
        sheet = "Dias Letivos" if "Dias Letivos" in xls.sheet_names else xls.sheet_names[0]
        dias_df = pd.read_excel(xls, sheet_name=sheet)
        dias_df["Data"] = pd.to_datetime(dias_df["Data"], errors="coerce")
        dias_df = dias_df.dropna(subset=["Data"])

        dias_etapa = dias_df[dias_df["Etapa"] == etapa_selecionada].copy()
        if dias_etapa.empty:
            st.error(f"Nenhum dia letivo encontrado para a {etapa_label}.")
            st.stop()

        # ---------- Extração do PDF ----------
        text_lessons, word_lessons, raw_pages = [], [], []

        with pdfplumber.open(pdf_file) as pdf:
            total_pages = len(pdf.pages)

            for i, page in enumerate(pdf.pages):
                if i == 0:
                    continue
                txt = page.extract_text() or ""
                raw_pages.append(f"--- Página {i+1} ---\n{txt}")
                text_lessons.extend(extract_lessons_from_text(txt))

            word_lessons = extract_lessons_from_words(pdf)

        lessons = text_lessons if len(text_lessons) >= len(word_lessons) else word_lessons
        method_used = "texto" if lessons is text_lessons else "coordenadas (palavras)"

        pdf_by_date = {}
        for date_str, count in lessons:
            pdf_by_date[date_str] = pdf_by_date.get(date_str, 0) + count

        # ---------- Diagnóstico ----------
        with st.expander("🐞 Diagnóstico da extração do PDF"):
            st.write(f"**Total de páginas no PDF:** {total_pages}")
            st.write(f"**Aulas detectadas via texto:** {len(text_lessons)}")
            st.write(f"**Aulas detectadas via palavras:** {len(word_lessons)}")
            st.write(f"**Método usado:** {method_used}")
            st.json(pdf_by_date)
            st.text_area("Texto bruto extraído (páginas 2+)",
                         "\n\n".join(raw_pages)[:8000], height=250)

        # ---------- Comparação dia a dia ----------
        rows = []
        for _, row in dias_etapa.iterrows():
            data = row["Data"]
            weekday = str(row["Dia da Semana"]).strip()
            ddmm = data.strftime("%d/%m")

            match = dist_df[dist_df["Dia da Semana"] == weekday]
            expected = int(match["Nº de Aulas"].iloc[0]) if len(match) > 0 else 0
            launched = pdf_by_date.get(ddmm, 0)
            missing = max(0, expected - launched)

            if expected > 0:
                rows.append({
                    "Data": data.strftime("%d/%m/%Y"),
                    "Dia da Semana": weekday,
                    "Previstas": expected,
                    "Lançadas": launched,
                    "Faltantes": missing,
                })

        result_df = pd.DataFrame(rows)

        # ---------- Resumo ----------
        st.subheader(f"📊 Resumo — {etapa_label}")
        total_prev = int(result_df["Previstas"].sum())
        total_lanc = int(result_df["Lançadas"].sum())
        total_falt = int(result_df["Faltantes"].sum())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Dias com aula na etapa", len(result_df))
        c2.metric("Aulas previstas", total_prev)
        c3.metric("Aulas lançadas (PDF)", total_lanc)
        c4.metric("Aulas faltantes", total_falt)

        # ---------- Faltantes ----------
        st.subheader("❌ Dias com aulas não lançadas")
        missing_df = result_df[result_df["Faltantes"] > 0].copy()

        if missing_df.empty:
            st.success(f"🎉 Todas as aulas da {etapa_label} foram lançadas!")
        else:
            st.dataframe(missing_df, use_container_width=True, hide_index=True)
            csv = missing_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                f"📥 Baixar CSV ({etapa_label})", csv,
                f"faltantes_{etapa_selecionada}etapa.csv", "text/csv",
            )

        # ---------- Todos os dias ----------
        with st.expander(f"🔎 Todos os dias da {etapa_label} e status"):
            st.data
