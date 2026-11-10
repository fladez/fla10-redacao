"""Teste ponta a ponta da CLI das fases 2 e 3, sem chamada externa."""

import json
import sys

from fla10_agents import cli
from fla10_agents.editorial.store import EditorialRepository
from tests.support import (
    FakeProvider,
    make_dossier,
    make_proposal,
    make_writing_vault,
    write_state,
    writing_payload,
)


def run_cli(monkeypatch, argv: list[str], capsys) -> tuple[int, object, str]:
    monkeypatch.setattr(sys, "argv", ["fla10", *argv])
    try:
        cli.main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    else:  # pragma: no cover - main sempre encerra com SystemExit
        code = 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out) if captured.out.strip() else None
    return code, payload, captured.err


def test_cli_writing_to_publication_flow(monkeypatch, tmp_path, capsys) -> None:
    database = tmp_path / "editorial.db"
    vault = make_writing_vault(tmp_path)
    write_state(database, proposal=make_proposal(), dossier=make_dossier())

    provider = FakeProvider(json.dumps(writing_payload(), ensure_ascii=False))
    monkeypatch.setattr(cli, "build_llm_provider", lambda: provider)

    code, generated, stderr = run_cli(
        monkeypatch,
        [
            "redacao",
            "gerar",
            "p1",
            "--model",
            "fake/model",
            "--vault",
            str(vault),
            "--database",
            str(database),
        ],
        capsys,
    )
    assert code == 0, stderr
    assert generated["title"].startswith("Flamengo x Palmeiras")
    draft_id = generated["draft_id"]
    assert generated["decision"] == "awaiting_human"

    code, reviewed, _ = run_cli(
        monkeypatch,
        [
            "redacao",
            "revisar",
            draft_id,
            "--deterministico",
            "--database",
            str(database),
        ],
        capsys,
    )
    assert code == 0
    assert reviewed["verdict"] == "pronto_para_avaliacao_humana"

    code, approved, _ = run_cli(
        monkeypatch,
        ["redacao", "aprovar", draft_id, "--database", str(database)],
        capsys,
    )
    assert code == 0
    assert approved["decision"] == "approved"

    code, package, _ = run_cli(
        monkeypatch,
        ["publicacao", "preparar", draft_id, "--database", str(database)],
        capsys,
    )
    assert code == 0
    package_id = package["package_id"]
    assert package["status"] == "prepared"

    code, _, _ = run_cli(
        monkeypatch,
        [
            "publicacao",
            "exportar",
            package_id,
            "--output",
            str(tmp_path / "exports"),
            "--database",
            str(database),
        ],
        capsys,
    )
    assert code == 0
    assert (tmp_path / "exports" / package_id / "article.html").is_file()

    code, published, _ = run_cli(
        monkeypatch,
        [
            "publicacao",
            "registrar",
            package_id,
            "--url",
            "https://fla10.news/materia",
            "--published-at",
            "2026-11-10T12:00:00+00:00",
            "--confirmar",
            "Confirmado no painel do site.",
            "--database",
            str(database),
        ],
        capsys,
    )
    assert code == 0
    assert published["status"] == "published"

    with EditorialRepository(database) as store:
        assert store.list_published_titles() == [generated["title"]]


def test_cli_blocks_publication_without_approval(monkeypatch, tmp_path, capsys) -> None:
    database = tmp_path / "editorial.db"
    vault = make_writing_vault(tmp_path)
    write_state(database, proposal=make_proposal(), dossier=make_dossier())

    monkeypatch.setattr(
        cli,
        "build_llm_provider",
        lambda: FakeProvider(json.dumps(writing_payload(), ensure_ascii=False)),
    )

    code, generated, _ = run_cli(
        monkeypatch,
        [
            "redacao",
            "gerar",
            "p1",
            "--vault",
            str(vault),
            "--database",
            str(database),
        ],
        capsys,
    )
    assert code == 0

    code, _, stderr = run_cli(
        monkeypatch,
        [
            "publicacao",
            "preparar",
            generated["draft_id"],
            "--database",
            str(database),
        ],
        capsys,
    )
    assert code != 0
    assert "aprovação humana" in stderr
