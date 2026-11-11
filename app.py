"""Interface local da Redação FLA10.

Roda o pipeline (`main.py`) a partir de uma pauta e mostra as quatro versões
em abas, inclusive de execuções antigas (por exemplo, as geradas pela rotina
pós-jogo). A aprovação é registrada na pasta e gera o pacote de CMS. Não envia
nada ao site.

Uso:
    /Users/rcorreas/miniconda3/envs/fla10/bin/streamlit run app.py
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

import painel_editorial
from qualidade import avaliar, pode_aprovar
from versoes import separar_versoes

BASE = Path(__file__).resolve().parent
PYTHON = Path(sys.executable)
PYTHON_CLI = BASE / ".venv" / "bin" / "python"
PASTA_SAIDAS = Path(os.getenv("FLA10_EXPORTS") or (BASE / "exports")).expanduser()
PASTA_PACOTES = PASTA_SAIDAS / "pacotes"
BANCO_EDITORIAL = Path(
    os.getenv("FLA10_EDITORIAL_DATABASE") or (BASE / "data" / "editorial.db")
).expanduser()
BANCO_CALENDARIO = Path(
    os.getenv("FLA10_CALENDAR_DATABASE") or (BASE / "data" / "calendar.db")
).expanduser()


def hash_versao(texto: str) -> str:
    """Mesma regra de `publication_import.hash_versao`."""
    return hashlib.sha256(texto.strip().encode("utf-8")).hexdigest()


def montar_pacote(pasta: Path, versao: int) -> subprocess.CompletedProcess[str]:
    """Chama a CLI que monta o pacote de CMS; não publica nada."""
    python = PYTHON_CLI if PYTHON_CLI.is_file() else PYTHON
    return subprocess.run(
        [
            str(python),
            "-m",
            "fla10_agents",
            "publicacao",
            "importar",
            str(pasta),
            "--versao",
            str(versao),
            "--output",
            str(PASTA_PACOTES),
            "--database",
            str(BANCO_EDITORIAL),
        ],
        cwd=BASE,
        capture_output=True,
        text=True,
        check=False,
    )


def listar_execucoes() -> list[Path]:
    """Execuções com texto completo, da mais nova para a mais antiga."""
    pastas = [
        pasta
        for pasta in PASTA_SAIDAS.glob("redacao-*")
        if pasta.is_dir() and (pasta / "completa.md").is_file()
    ]
    return sorted(pastas, key=lambda pasta: pasta.stat().st_mtime, reverse=True)


def ler_registro(pasta: Path) -> dict:
    try:
        return json.loads((pasta / "aprovada.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ler_pauta(pasta: Path, registro: dict) -> str:
    """Pauta registrada na aprovação ou gravada pela execução do pipeline."""
    if registro.get("pauta"):
        return str(registro["pauta"])
    try:
        return (pasta / "pauta.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def mostrar_pacote(destino: Path) -> None:
    """Downloads do pacote já gerado, sem repetir o processamento."""
    artigo = destino / "article.md"
    site = destino / "site-news.json"
    if artigo.is_file():
        st.download_button(
            "Baixar article.md",
            artigo.read_text(encoding="utf-8"),
            file_name=f"{destino.name}.md",
            key=f"baixar-artigo-{destino.name}",
        )
    if site.is_file():
        st.download_button(
            "Baixar site-news.json",
            site.read_text(encoding="utf-8"),
            file_name=f"{destino.name}-site-news.json",
            key=f"baixar-site-{destino.name}",
        )


def aprovar(pasta: Path, versao: int, corpo: str, pauta: str) -> None:
    """Grava a aprovação com o hash do texto e monta o pacote de CMS."""
    registro = {
        "pasta": pasta.name,
        "versao": versao,
        "aprovada_em": datetime.now().isoformat(timespec="seconds"),
        "pauta": pauta.strip(),
        "conteudo_sha256": hash_versao(corpo),
    }
    (pasta / "aprovada.json").write_text(
        json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    st.success(
        f"Versão {versao} marcada como aprovada em {pasta.name}. "
        "Nada foi publicado: o envio ao site continua manual."
    )

    pacote = montar_pacote(pasta, versao)
    if pacote.returncode != 0:
        st.error("A aprovação foi salva, mas o pacote de CMS não foi gerado.")
        st.code((pacote.stderr or pacote.stdout)[-3000:])
        return

    dados = json.loads(pacote.stdout)
    st.info(f"Pacote de CMS pronto em `{dados['output']}`.")
    st.caption(
        f"Título: {dados['title']} · slug: {dados['slug']} · status: {dados['status']}"
    )
    mostrar_pacote(Path(dados["output"]))
    with st.expander("Detalhes do pacote"):
        st.code(pacote.stdout)


def mostrar_execucao(pasta: Path, log: str | None = None) -> None:
    completa = (pasta / "completa.md").read_text(encoding="utf-8")
    versoes = separar_versoes(completa)

    if len(versoes) == 4:
        st.caption("Quantidade esperada de versões confirmada.")
    else:
        st.warning("Quantidade diferente de 4: confira o texto antes de aprovar.")

    avisos = avaliar(versoes)
    if avisos:
        with st.expander(f"Verificação automática: {len(avisos)} aviso(s)", expanded=True):
            for aviso in avisos:
                marca = "❌" if aviso.critico else "⚠️"
                st.write(f"{marca} {aviso}")

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
    if not versoes:
        return

    registro = ler_registro(pasta)
    if registro.get("versao"):
        st.info(
            f"Versão {registro['versao']} aprovada em "
            f"{registro.get('aprovada_em', 'data não registrada')}."
        )
        gerado = PASTA_PACOTES / f"{pasta.name}-v{registro['versao']}"
        if (gerado / "article.md").is_file():
            st.caption(f"Pacote já gerado em `{gerado}`.")
            mostrar_pacote(gerado)

    pauta_salva = ler_pauta(pasta, registro)
    pauta_aprovacao = st.text_input(
        "Pauta desta execução",
        value=pauta_salva,
        placeholder="Ex.: Flamengo 3 x 1 Grêmio — resultado e declarações",
        key=f"pauta-{pasta.name}",
    )
    liberado = pode_aprovar(avisos)
    escolhida = st.selectbox(
        "Versão aprovada",
        options=[numero for numero, _ in versoes],
        format_func=lambda numero: f"Versão {numero}",
        key=f"versao-{pasta.name}",
    )
    if not liberado:
        st.caption("Corrija os erros estruturais acima antes de aprovar.")
    if st.button("Registrar aprovação local", key=f"aprovar-{pasta.name}", disabled=not liberado):
        aprovar(pasta, escolhida, dict(versoes).get(escolhida, ""), pauta_aprovacao)

    if log:
        with st.expander("Log do pipeline"):
            st.code(log[-8000:])


st.set_page_config(page_title="Redação FLA10", page_icon="🔴", layout="wide")

area = st.sidebar.radio(
    "Área",
    ["Pautas e minutas", "Redação (6 agentes)"],
    key="area",
    help=(
        "Pautas e minutas: pesquisa, dossiê e minuta com decisão humana. "
        "Redação: pipeline de 6 agentes a partir de uma pauta livre."
    ),
)

if area == "Pautas e minutas":
    st.title("Redação FLA10 News")
    painel_editorial.render(
        PYTHON_CLI if PYTHON_CLI.is_file() else PYTHON,
        BASE,
        BANCO_EDITORIAL,
        BANCO_CALENDARIO,
    )
    st.stop()

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

    novas = [p for p in listar_execucoes() if p.stat().st_mtime >= inicio.timestamp()]
    if not novas:
        st.warning("Nenhum arquivo novo em exports/. Veja o log abaixo.")
        st.code(processo.stdout[-4000:])
        st.stop()

    nova = max(novas, key=lambda pasta: pasta.stat().st_mtime)
    total = len(separar_versoes((nova / "completa.md").read_text(encoding="utf-8")))
    st.success(f"{total} versões geradas em {nova.name}")
    st.session_state.setdefault("logs", {})[nova.name] = processo.stdout
    st.session_state["execucao"] = nova.name

execucoes = listar_execucoes()
if not execucoes:
    st.info("Nenhuma execução em exports/. Gere a primeira pauta acima.")
    st.stop()

nomes = [pasta.name for pasta in execucoes]
if st.session_state.get("execucao") not in nomes:
    st.session_state["execucao"] = nomes[0]

escolhida = st.selectbox("Execução em exibição", nomes, key="execucao")
pasta = dict(zip(nomes, execucoes))[escolhida]
mostrar_execucao(pasta, log=st.session_state.get("logs", {}).get(escolhida))
