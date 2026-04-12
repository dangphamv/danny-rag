from src.retrieval.hybrid import RRF_K, rrf_fuse
from src.retrieval.types import ScoredChunk


def chunk(point_id: str, score: float = 0.0) -> ScoredChunk:
    return ScoredChunk(
        point_id=point_id,
        doc_id="d1",
        chunk_index=0,
        text=f"text-{point_id}",
        title="t",
        source_uri="s",
        score=score,
    )


def test_rrf_k_is_60() -> None:
    assert RRF_K == 60


def test_rrf_fuse_combines_two_lists() -> None:
    # b at rank 0 in both lists — unambiguously the highest combined score.
    # a at rank 1 in both — unambiguously second. (Symmetric inputs would
    # produce ties that depend on dict insertion order.)
    dense = [chunk("b"), chunk("a"), chunk("c")]
    sparse = [chunk("b"), chunk("a"), chunk("d")]
    fused = rrf_fuse(dense, sparse)
    ids = [c.point_id for c in fused]
    assert ids[0] == "b"
    assert ids[1] == "a"
    # c (dense only, rank 2) and d (sparse only, rank 2) tail
    assert set(ids[2:]) == {"c", "d"}


def test_rrf_fuse_preserves_chunks_with_zero_overlap() -> None:
    dense = [chunk("x")]
    sparse = [chunk("y")]
    fused = rrf_fuse(dense, sparse)
    assert {c.point_id for c in fused} == {"x", "y"}


def test_rrf_fuse_score_is_sum_of_reciprocal_ranks() -> None:
    dense = [chunk("a"), chunk("b")]
    sparse = [chunk("a")]
    fused = rrf_fuse(dense, sparse, k=60)
    a = next(c for c in fused if c.point_id == "a")
    # rank 0 in dense → 1/(60+1) = 1/61
    # rank 0 in sparse → 1/(60+1) = 1/61
    # total = 2/61
    expected = 2 / 61
    assert abs(a.score - expected) < 1e-9


def test_rrf_fuse_empty_inputs() -> None:
    assert rrf_fuse([], []) == []
    one = [chunk("a")]
    assert [c.point_id for c in rrf_fuse(one, [])] == ["a"]
    assert [c.point_id for c in rrf_fuse([], one)] == ["a"]
