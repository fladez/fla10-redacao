"""Interface local da Redação FLA10.

Roda o pipeline (`main.py`) a partir de uma pauta e mostra as quatro versões
em abas, com registro local da versão aprovada. Não envia nada ao site.

Uso:
    /Users/rcorreas/miniconda3/envs/fla10/bin/streamlit run app.py
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

from versoes import separar_versoes

BASE = Path(__file__).resolve().parent
PYTHON = Path(sys.executable)
PASTA_SAIDAS = BASE / "exports"

st.set_page_config(page_title="Redação FLA10", page_icon="🔴", layout="wide")

st.title("Redação FLA10 News")
st.caption("6 agentes em sequência: apuração → 4 versões → revisão. Custo zero, DeepSeek local.")

with st.form("pauta"):
    pauta = st.text_input(
        "Pauta",
        value="Último jogo do Flamengo no Brasileirão (resultado, gols, destaques e declarações)",
        help="Ex.: Flamengo x Palmeiras — destaques e declarações pós-jogo",
    )
    gerar = st.form_submit_button("Gerar matérias", type="primary")

if gerar:
    if not pauta.strip():
        st.error("Informe a pauta.")
        st.stop()

    inicio = datetime.now()
    with st.status("Rodando o pipeline...", expanded=True) as status:
        st.write(f"Pauta: {pauta}")
        processo = subprocess.run(
            [str(PYTHON), str(BASE / "main.py"), pauta.strip()],
            cwd=BASE,
            capture_output=True,
            text=True,
            check=False,
        )
        status.update(label="Pipeline concluído", state="complete")

    if processo.returncode != 0:
        st.error(f"O pipeline terminou com código {processo.returncode}.")
        st.code((processo.stderr or processo.stdout)[-4000:])
        st.stop()

    pastas = sorted(
        (p for p in PASTA_SAIDAS.glob("redacao-*") if p.stat().st_mtime >= inicio.timestamp()),
        key=lambda p: p.stat().st_mtime,
    )
    if not pastas:
        st.warning("Nenhum arquivo novo em exports/. Veja o log abaixo.")
        st.code(processo.stdout[-4000:])
        st.stop()

    pasta = pastas[-1]
    completa = (pasta / "completa.md").read_text(encoding="utf-8")
    versoes = separar_versoes(completa)

    st.success(f"{len(versoes)} versões geradas em {pasta.name}")
    if len(versoes) == 4:
        st.caption("Quantidade esperada de versões confirmada.")
    else:
        st.warning("Quantidade diferente de 4: confira o texto antes de aprovar.")

    abas = st.tabs([f"Versão {numero}" for numero, _ in versoes] or ["Sem versões"])
    for aba, (numero, corpo) in zip(abas, versoes):
        with aba:
            st.markdown(corpo)
            st.download_button(
                "Baixar Markdown",
                corpo,
                file_name=f"versao-{numero}.md",
                key=f"baixar-{pasta.name}-{numero}",
            )

    st.divider()
    st.subheader("Aprovação")
    if versoes:
        escolhida = st.selectbox(
            "Versão aprovada",
            options=[numero for numero, _ in versoes],
            format_func=lambda n: f"Versão {n}",
        )
        if st.button("Registrar aprovação local"):
            registro = {
                "pasta": pasta.name,
                "versao": escolhida,
                "aprovada_em": datetime.now().isoformat(timespec="seconds"),
                "pauta": pauta.strip(),
            }
            (pasta / "aprovada.json").write_text(
                json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            st.success(
                f"Versão {escolhida} marcada como aprovada em {pasta.name}. "
                "Nada foi publicado: o envio ao site continua manual."
            )

    with st.expander("Log do pipeline"):
        st.code(processo.stdout[-8000:])
