from icc_entrada.models import Recipe
from icc_entrada.recipe import scientific_guard


def test_recipe_default_scientific_safe():
    guard = scientific_guard(Recipe())
    assert guard.is_scientific_safe
    assert guard.warnings == []


def test_recipe_warns_non_neutral():
    r = Recipe(denoise="mild", sharpen="mild", tone_curve="gamma:2.2", output_linear=False)
    g = scientific_guard(r)
    assert not g.is_scientific_safe
    assert len(g.warnings) >= 3
