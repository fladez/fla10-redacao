"""Comandos de diagnóstico e avaliação para o MVP."""

import argparse
import sys

from fla10_agents.config import Settings
from fla10_agents.editorial.github_reader import EditorialSourceError, GitHubEditorialReader
from fla10_agents.evaluation import ModelEvaluationError, run_report_test


def check_editorial() -> int:
    settings = Settings.from_env()
    with GitHubEditorialReader(settings) as reader:
        context = reader.read_bootstrap_context()
    print(f"Repositório: {context.repository}")
    print(f"Branch: {context.branch}")
    print(f"Commit editorial: {context.commit_sha}")
    print("Documentos lidos:")
    for path in context.files:
        print(f"- {path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="fla10")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check-editorial", help="Testa a leitura do vault editorial.")
    subparsers.add_parser(
        "run-report-test",
        help="Executa a comparação cega dos três modelos no caso A força da Nação.",
    )
    args = parser.parse_args()

    try:
        if args.command == "check-editorial":
            raise SystemExit(check_editorial())
        if args.command == "run-report-test":
            output_dir = run_report_test()
            print("Teste concluído. Arquivos salvos localmente em:")
            print(output_dir)
            print("Não publique os resultados nem a chave de cegamento antes da avaliação.")
            raise SystemExit(0)
    except (ValueError, EditorialSourceError, ModelEvaluationError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
