from datetime import UTC, datetime

from fla10_agents.editorial.store import EditorialRepository
from fla10_agents.models import EditorialProposal, MonitoringSignal


def make_signal(external_id: str = "sig-1", title: str = "Flamengo treina") -> MonitoringSignal:
    return MonitoringSignal(
        provider="Teste",
        external_id=external_id,
        title=title,
        published_at=datetime(2026, 11, 10, 12, 0, tzinfo=UTC),
        last_seen_at=datetime(2026, 11, 10, 12, 0, tzinfo=UTC),
    )


def make_proposal(
    proposal_id: str = "p1",
    dedupe_key: str = "onde_assistir:evt-1",
    related_published: list[str] | None = None,
) -> EditorialProposal:
    return EditorialProposal(
        proposal_id=proposal_id,
        title="Flamengo x Palmeiras: onde assistir",
        format="onde_assistir",
        editorial_question="Como assistir?",
        angle="Serviço de jogo.",
        why_now="Jogo na semana.",
        related_published=related_published or [],
        dedupe_key=dedupe_key,
        created_at=datetime(2026, 11, 10, 12, 0, tzinfo=UTC),
    )


def test_save_signal_deduplicates_by_provider_and_external_id(tmp_path) -> None:
    database = tmp_path / "editorial.db"

    with EditorialRepository(database) as store:
        assert store.save_signal(make_signal()) is True
        assert store.save_signal(make_signal(title="Flamengo treina com desfalque")) is False

        signals = store.list_signals()

    assert len(signals) == 1
    assert signals[0].title == "Flamengo treina com desfalque"


def test_provider_is_normalized_for_deduplication(tmp_path) -> None:
    database = tmp_path / "editorial.db"

    with EditorialRepository(database) as store:
        assert store.save_signal(make_signal()) is True
        duplicate = make_signal()
        duplicate.provider = "  teste  "
        assert store.save_signal(duplicate) is False
        assert len(store.list_signals()) == 1


def test_save_signal_refreshes_last_seen_at(tmp_path) -> None:
    database = tmp_path / "editorial.db"
    old = datetime(2020, 1, 1, tzinfo=UTC)

    with EditorialRepository(database) as store:
        signal = make_signal()
        signal.last_seen_at = old
        store.save_signal(signal)

        stored = store.list_signals()[0]

    assert stored.last_seen_at > old


def test_save_proposal_is_idempotent_and_preserves_human_decision(tmp_path) -> None:
    database = tmp_path / "editorial.db"

    with EditorialRepository(database) as store:
        first = store.save_proposal(make_proposal())
        assert first.created is True

        store.decide_proposal("p1", "approved")

        second = store.save_proposal(
            make_proposal(proposal_id="p2", related_published=["Matéria publicada"])
        )

        assert second.created is False
        assert second.proposal.proposal_id == "p1"
        stored = store.get_proposal("p1")

    assert stored is not None
    assert stored.editorial_decision == "approved"
    assert stored.related_published == ["Matéria publicada"]


def test_list_proposals_filters_by_status(tmp_path) -> None:
    database = tmp_path / "editorial.db"

    with EditorialRepository(database) as store:
        store.save_proposal(make_proposal("p1", "k1"))
        store.save_proposal(make_proposal("p2", "k2"))
        store.decide_proposal("p2", "rejected")

        approved = store.list_proposals(status="approved")
        rejected = store.list_proposals(status="rejected")

    assert approved == []
    assert [proposal.proposal_id for proposal in rejected] == ["p2"]


def test_decide_proposal_rejects_unknown_decision_and_proposal(tmp_path) -> None:
    database = tmp_path / "editorial.db"

    with EditorialRepository(database) as store:
        store.save_proposal(make_proposal())

        try:
            store.decide_proposal("p1", "decisao_invalida")
        except ValueError as exc:
            assert "Decisão inválida" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("decisão inválida deveria falhar")

        try:
            store.decide_proposal("missing", "approved")
        except KeyError as exc:
            assert "missing" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("proposta inexistente deveria falhar")


def test_publication_registry_feeds_redundancy(tmp_path) -> None:
    database = tmp_path / "editorial.db"

    with EditorialRepository(database) as store:
        store.register_publication(
            "Flamengo x Palmeiras: onde assistir",
            url="https://example.com/materia",
            published_at=datetime(2026, 11, 11, 10, 0, tzinfo=UTC),
        )
        titles = store.list_published_titles()

    assert titles == ["Flamengo x Palmeiras: onde assistir"]
