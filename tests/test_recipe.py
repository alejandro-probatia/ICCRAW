from pathlib import Path

from probraw.core.models import Recipe
from probraw.core.recipe import load_recipe, scientific_guard


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
    assert recipe.demosaic_edge_quality == 0
    assert recipe.false_color_suppression_steps == 0
    assert recipe.four_color_rgb is False


def test_recipe_loads_raw_demosaic_options(tmp_path: Path):
    recipe_file = tmp_path / "recipe.yml"
    recipe_file.write_text(
        """
demosaic_edge_quality: "3"
false_color_suppression_steps: "2"
four_color_rgb: "true"
""",
        encoding="utf-8",
    )
    recipe = load_recipe(recipe_file)

    assert recipe.demosaic_edge_quality == 3
    assert recipe.false_color_suppression_steps == 2
    assert recipe.four_color_rgb is True


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
