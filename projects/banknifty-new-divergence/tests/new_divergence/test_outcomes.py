from banknifty_profiler.new_divergence.engine import run_replay
from banknifty_profiler.new_divergence.outcomes import evaluate_basis_outcomes

from .helpers import green_episode_events


def test_outcomes_are_retrospective_and_zero_weight() -> None:
    engine = run_replay(green_episode_events())
    rows = evaluate_basis_outcomes(engine.transitions, engine.observations, horizons_minutes=(1,))
    assert len(rows) == 1
    assert rows[0]["production_weight"] == 0
    assert "NOT ENGINE INPUT" in rows[0]["classification"]


def test_engine_source_does_not_import_outcomes() -> None:
    import ast
    import inspect
    import banknifty_profiler.new_divergence.engine as engine_module

    tree = ast.parse(inspect.getsource(engine_module))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any("outcomes" in name for name in imported)
