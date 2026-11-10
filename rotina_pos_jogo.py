"""Rotina pós-jogo: roda o pipeline só quando há jogo recente do Flamengo.

Pensado para agendamento no OpenBot, não em cron externo. Devolve um JSON de
uma linha com o resultado e nunca publica nada.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from resultados import coletar_jogo
from versoes import separar_versoes

BASE = Path(__file__).resolve().parent
FUSO = ZoneInfo("America/Sao_Paulo")
JANELA_HORAS = 14
MARCADOR = BASE / "exports" / ".ultima-rotina.json"
PASTA_LOGS = BASE / "logs"
FORMATO_QUANDO = "%d/%m/%Y %H:%M"


def resumo_do_jogo(jogo: dict[str, Any]) -> dict[str, Any]:
    return {
        "rodada": jogo["rodada"],
        "quando": jogo["quando"],
        "placar": (
            f"{jogo['mandante']} {jogo['gols_mandante']} x "
            f"{jogo['gols_visitante']} {jogo['visitante']}"
        ),
        "estadio": jogo["estadio"],
    }


def pauta_do_jogo(jogo: dict[str, Any]) -> str:
    """Pauta que casa com a ficha oficial (o adversário aparece no texto)."""
    return (
        f"{jogo['mandante']} {jogo['gols_mandante']} x "
        f"{jogo['gols_visitante']} {jogo['visitante']}: "
        "resultado, gols, destaques e declarações pós-jogo"
    )


def decidir(
    jogo: dict[str, Any],
    agora: datetime,
    anterior: dict[str, Any] | None = None,
    *,
    janela_horas: int = JANELA_HORAS,
) -> dict[str, Any]:
    """Diz se o pipeline deve rodar: jogo recente e ainda não redigido."""
    resumo = resumo_do_jogo(jogo)
    quando = datetime.strptime(jogo["quando"], FORMATO_QUANDO).replace(tzinfo=FUSO)
    idade = agora - quando

    if idade > timedelta(hours=janela_horas):
        return {"status": "sem_jogo_recente", **resumo, "idade_horas": round(
            idade.total_seconds() / 3600, 1
        )}

    if (
        anterior
        and anterior.get("rodada") == jogo["rodada"]
        and anterior.get("quando") == jogo["quando"]
    ):
        return {"status": "ja_gerado", **resumo, "pasta": anterior.get("pasta")}

    return {"status": "executar", **resumo, "pauta": pauta_do_jogo(jogo)}


def _ler_marcador() -> dict[str, Any] | None:
    try:
        return json.loads(MARCADOR.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _responder(payload: dict[str, Any], codigo: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=False))
    raise SystemExit(codigo)


def _pasta_nova(inicio: float) -> Path | None:
    pastas = [
        pasta
        for pasta in (BASE / "exports").glob("redacao-*")
        if pasta.is_dir() and pasta.stat().st_mtime >= inicio
    ]
    return max(pastas, key=lambda pasta: pasta.stat().st_mtime) if pastas else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Roda a redação quando o Flamengo jogou nas últimas horas."
    )
    parser.add_argument(
        "--forcar",
        action="store_true",
        help="Ignora o marcador e redigir de novo mesmo com o jogo já feito.",
    )
    parser.add_argument(
        "--sem-executar",
        action="store_true",
        help="Só informa o que faria, sem chamar o pipeline.",
    )
    args = parser.parse_args()

    jogo, erro = coletar_jogo()
    if jogo is None:
        _responder({"status": "sem_dados", "erro": erro}, 2)

    agora = datetime.now(FUSO)
    anterior = None if args.forcar else _ler_marcador()
    decisao = decidir(jogo, agora, anterior)

    if decisao["status"] != "executar" or args.sem_executar:
        _responder(decisao)

    inicio = time.monotonic()
    processo = subprocess.run(
        [sys.executable, str(BASE / "main.py"), decisao["pauta"]],
        cwd=BASE,
        capture_output=True,
        text=True,
        check=False,
    )
    duracao = round(time.monotonic() - inicio, 1)

    PASTA_LOGS.mkdir(parents=True, exist_ok=True)
    log = PASTA_LOGS / f"rotina-{agora:%Y-%m-%d-%H%M}.log"
    log.write_text(
        f"$ main.py {decisao['pauta']}\n\n{processo.stdout}\n--- stderr ---\n{processo.stderr}",
        encoding="utf-8",
    )

    if processo.returncode != 0:
        _responder(
            {
                "status": "falhou",
                **resumo_do_jogo(jogo),
                "codigo": processo.returncode,
                "log": str(log),
                "erro": (processo.stderr or processo.stdout)[-800:],
            },
            1,
        )

    pasta = _pasta_nova(inicio)
    if pasta is None:
        _responder({"status": "falhou", "log": str(log), "erro": "nenhuma pasta nova em exports"},
                   1)

    completa = (pasta / "completa.md").read_text(encoding="utf-8")
    versoes = [numero for numero, _ in separar_versoes(completa)]
    marcador = {
        "rodada": jogo["rodada"],
        "quando": jogo["quando"],
        "pasta": pasta.name,
        "gerado_em": agora.isoformat(timespec="seconds"),
        "versoes": versoes,
    }
    MARCADOR.write_text(json.dumps(marcador, ensure_ascii=False, indent=2), encoding="utf-8")

    _responder(
        {
            "status": "gerado",
            **resumo_do_jogo(jogo),
            "pasta": str(pasta),
            "versoes": versoes,
            "duracao_segundos": duracao,
            "log": str(log),
        }
    )


if __name__ == "__main__":
    main()
