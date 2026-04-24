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


def test_recipe_default_raw_developer_is_libraw(tmp_path: Path):
    recipe_file = tmp_path / "recipe.yml"
    recipe_file.write_text("{}", encoding="utf-8")
    recipe = load_recipe(recipe_file)
    assert recipe.raw_developer == "libraw"
    assert recipe.demosaic_algorithm == "dcb"


def test_recipe_nested_sampling_strategy_preserves_parameters(tmp_path: Path):
    recipe_file = tmp_path / "recipe.yml"
    recipe_file.write_text(
        """
sampling_strategy:
  mode: trimmed_mean
  trim_percent: 0.2
  reject_saturated: false
""",
        encoding="utf-8",
    )
    recipe = load_recipe(recipe_file)

    assert recipe.sampling_strategy == "trimmed_mean"
    assert recipe.sampling_trim_percent == 0.2
    assert recipe.sampling_reject_saturated is False
