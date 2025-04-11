import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
from rapidfuzz import process
from cid_classificacao_embutida import cid_embutido

# ========== CONFIG ==========
st.set_page_config(page_title="DS - Detector de CID", layout="wide")
st.markdown("""
    <style>
    .main { background-color: #f5f7fa; }
    .stButton>button {
        background-color: #0072C6;
        color: white;
        border-radius: 8px;
        padding: 0.5em 1em;
    }
    .stDownloadButton>button {
        background-color: #28a745;
        color: white;
        border-radius: 8px;
        padding: 0.5em 1em;
    }
    .centered-title {
        text-align: center;
    }
    </style>
""", unsafe_allow_html=True)

cid_df = pd.DataFrame(cid_embutido)[["codigo", "descricao"]]
cid_df.columns = ["CID", "Descrição CID"]

def identificar_cid(descricao):
    descricao = descricao.lower()
    melhores = process.extractOne(descricao, cid_df["Descrição CID"], score_cutoff=60)
    if melhores:
        match = cid_df[cid_df["Descrição CID"] == melhores[0]]
        return match.iloc[0]["CID"]
    return "N/A"

def extrair_quadroIII(pdf_file):
    try:
        with pdfplumber.open(io.BytesIO(pdf_file.read())) as pdf:
            texto_completo = ""
            for page in pdf.pages:
                texto = page.extract_text()
                if texto:
                    texto_completo += texto + "\n"

        if not texto_completo:
            return pd.DataFrame()

        padrao_quadro = r"(?i)(?:\d+\s+)?(TITULAR|CÔNJUGE|DEP\d+)\s+(\d{2}/\d{2}/\d{4}|-)\s+(.+?)(?=\n(?:\d+\s+)?(?:TITULAR|CÔNJUGE|DEP\d+)|\Z)"
        matches = re.findall(padrao_quadro, texto_completo, re.DOTALL)

        dados = []
        for segurado, data, descricao in matches:
            descricao_limpa = ' '.join(descricao.replace('\n', ' ').split())
            cid = identificar_cid(descricao_limpa)
            dados.append({
                "Segurado": segurado,
                "Data": data,
                "Descrição": descricao_limpa,
                "CID": cid
            })

        tabela = pd.DataFrame(dados)

        try:
            cid_risco_df = pd.DataFrame(cid_embutido)[["codigo", "classificacao", "justificativa"]]
            cid_risco_df.columns = ["CID", "Classificação", "Justificativa"]
            tabela["CID"] = tabela["CID"].astype(str).str.strip().str.upper()
            cid_risco_df["CID"] = cid_risco_df["CID"].astype(str).str.strip().str.upper()
            tabela = tabela.merge(cid_risco_df, on="CID", how="left")
        except Exception as e:
            st.warning(f"Erro ao aplicar classificação: {e}")

        return tabela

    except Exception as e:
        st.error(f"Erro ao processar PDF: {str(e)}")
        return pd.DataFrame()

# INTERFACE

st.markdown("<h1 class='centered-title'>🩺 SmartCID</h1>", unsafe_allow_html=True)
st.markdown("Anexe sua documentação no campo abaixo para que o sistema identifique automaticamente o CID-10")

arquivo = st.file_uploader("📤 Upload do PDF da Declaração de Saúde", type=["pdf"])

if arquivo:
    with st.spinner("🔍 Processando PDF e extraindo dados..."):
        tabela = extrair_quadroIII(arquivo)

        if tabela.empty:
            st.warning("⚠️ Nenhum dado encontrado no PDF. Verifique se o Quadro III está legível.")
        else:
            st.success("✅ Quadro resumo processado com sucesso!")
            st.subheader("📋 Quadro resumo: CID-10")

            if "Arquivo" not in tabela.columns:
                tabela.insert(0, "Arquivo", arquivo.name)
            tabela = tabela.sort_values(by=["Segurado", "Data"])

            def aplicar_cor_por_classificacao(valor):
                if valor == "Aprovado":
                    return "background-color: #28a745; color: white"
                elif valor == "Carência":
                    return "background-color: #fd7e14; color: white"
                elif valor == "Entrevista com um médico":
                    return "background-color: #dc3545; color: white"
                return ""

            styled_tabela = tabela[["Segurado", "Data", "Descrição", "CID", "Classificação", "Justificativa"]].style.applymap(aplicar_cor_por_classificacao, subset=["Classificação"])
            st.dataframe(styled_tabela, use_container_width=True, height=500)

            cids_invalidos = tabela[tabela["Classificação"].isna()]["CID"].unique().tolist()
            if cids_invalidos:
                st.info(f"CIDs não classificados na base: {', '.join(cids_invalidos)}")

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                tabela[["Arquivo", "Segurado", "Data", "Descrição", "CID", "Classificação", "Justificativa"]].to_excel(writer, index=False, sheet_name="Resumo")
            buffer.seek(0)

            st.download_button(
                label="📥 Baixar Resumo em Excel",
                data=buffer,
                file_name=f"Resumo_QuadroIII_{arquivo.name.split('.')[0]}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
