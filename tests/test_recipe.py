from pathlib import Path

from iccraw.core.models import Recipe
from iccraw.core.recipe import load_recipe, scientific_guard


def test_recipe_default_scientific_safe():
    guard = scientific_guard(Recipe())
    assert guard.is_scientific_safe
    assert guard.warnings == []


def test_recipe_warns_non_neutral():
    r = Recipe(denoise="mild", sharpen="mild", tone_curve="gamma:2.2", output_linear=False)
    g = scientific_guard(r)
    assert not g.is_scientific_safe
    assert len(g.warnings) >= 3


def test_recipe_default_raw_developer_is_dcraw(tmp_path: Path):
    recipe_file = tmp_path / "recipe.yml"
    recipe_file.write_text("{}", encoding="utf-8")
    recipe = load_recipe(recipe_file)
    assert recipe.raw_developer == "dcraw"
