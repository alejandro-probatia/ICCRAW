use std::fs;

use anyhow::{Context, Result};
use camino::Utf8Path;
use icc_raw::{MockRawDecoder, RawDecoder, RawMetadata};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DemosaicAlgorithm {
    Bilinear,
    Vng,
    Amaze,
    Rcd,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "mode", rename_all = "snake_case")]
pub enum BlackLevelMode {
    Metadata,
    Fixed { value: u16 },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum WhiteBalanceMode {
    CameraMetadata,
    Fixed,
    NeutralPatch,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "mode", rename_all = "snake_case")]
pub enum ToneCurve {
    Linear,
    Gamma { gamma: String },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DenoiseMode {
    Off,
    Conservative,
    Aggressive,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SharpenMode {
    Off,
    Mild,
    Strong,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum InputColorAssumption {
    CameraNative,
    EmbeddedMatrix,
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SamplingStrategyMode {
    Median,
    TrimmedMean,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SamplingStrategyRecipe {
    pub mode: SamplingStrategyMode,
    pub trim_percent: f32,
    pub reject_saturated: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Recipe {
    pub demosaic_algorithm: DemosaicAlgorithm,
    pub black_level_mode: BlackLevelMode,
    pub white_balance_mode: WhiteBalanceMode,
    pub wb_multipliers: Option<[f32; 4]>,
    pub exposure_compensation: f32,
    pub tone_curve: ToneCurve,
    pub output_linear: bool,
    pub denoise: DenoiseMode,
    pub sharpen: SharpenMode,
    pub input_color_assumption: InputColorAssumption,
    pub working_space: String,
    pub output_space: String,
    pub chart_reference: Option<String>,
    pub illuminant_metadata: Option<String>,
    pub sampling_strategy: SamplingStrategyRecipe,
    pub profiling_mode: bool,
}

impl Default for Recipe {
    fn default() -> Self {
        Self {
            demosaic_algorithm: DemosaicAlgorithm::Rcd,
            black_level_mode: BlackLevelMode::Metadata,
            white_balance_mode: WhiteBalanceMode::Fixed,
            wb_multipliers: Some([1.0, 1.0, 1.0, 1.0]),
            exposure_compensation: 0.0,
            tone_curve: ToneCurve::Linear,
            output_linear: true,
            denoise: DenoiseMode::Off,
            sharpen: SharpenMode::Off,
            input_color_assumption: InputColorAssumption::CameraNative,
            working_space: "scene_linear_camera_rgb".to_string(),
            output_space: "scene_linear_camera_rgb".to_string(),
            chart_reference: None,
            illuminant_metadata: None,
            sampling_strategy: SamplingStrategyRecipe {
                mode: SamplingStrategyMode::TrimmedMean,
                trim_percent: 0.1,
                reject_saturated: true,
            },
            profiling_mode: true,
        }
    }
}

impl Recipe {
    pub fn from_path(path: &Utf8Path) -> Result<Self> {
        let raw = fs::read_to_string(path)
            .with_context(|| format!("failed to read recipe file {}", path))?;

        match path.extension().unwrap_or_default().to_ascii_lowercase().as_str() {
            "yaml" | "yml" => {
                serde_yaml::from_str(&raw).with_context(|| format!("invalid YAML recipe in {}", path))
            }
            "json" => {
                serde_json::from_str(&raw).with_context(|| format!("invalid JSON recipe in {}", path))
            }
            _ => serde_yaml::from_str(&raw)
                .or_else(|_| serde_json::from_str(&raw))
                .with_context(|| format!("unsupported recipe extension for {}", path)),
        }
    }

    pub fn scientific_guard_report(&self) -> ScientificGuardReport {
        let mut warnings = Vec::new();

        if self.profiling_mode {
            if self.denoise != DenoiseMode::Off {
                warnings.push("denoise is enabled in profiling_mode".to_string());
            }
            if self.sharpen != SharpenMode::Off {
                warnings.push("sharpen is enabled in profiling_mode".to_string());
            }
            if !matches!(self.tone_curve, ToneCurve::Linear) {
                warnings.push("tone curve is non-linear in profiling_mode".to_string());
            }
            if !self.output_linear {
                warnings.push("output_linear is false in profiling_mode".to_string());
            }
        }

        ScientificGuardReport {
            is_scientific_safe: warnings.is_empty(),
            warnings,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScientificGuardReport {
    pub is_scientific_safe: bool,
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DevelopArtifacts {
    pub raw_metadata: RawMetadata,
    pub recipe: Recipe,
    pub scientific_guard: ScientificGuardReport,
    pub output_tiff: String,
    pub audit_tiff: Option<String>,
}

#[derive(Debug, Default)]
pub struct ControlledPipeline;

impl ControlledPipeline {
    pub fn develop(
        &self,
        input_raw: &Utf8Path,
        recipe: &Recipe,
        out_tiff: &Utf8Path,
        audit_linear_tiff: Option<&Utf8Path>,
    ) -> Result<DevelopArtifacts> {
        let decoder = MockRawDecoder;
        let raw_metadata = decoder
            .read_metadata(input_raw)
            .with_context(|| format!("failed to read raw metadata from {}", input_raw))?;

        let guard = recipe.scientific_guard_report();

        let output_bytes = format!(
            "ICCRAW_TIFF_STUB\ninput={}\nworking_space={}\noutput_space={}\n",
            input_raw, recipe.working_space, recipe.output_space
        );

        fs::write(out_tiff, output_bytes)
            .with_context(|| format!("failed to write output TIFF stub to {}", out_tiff))?;

        let audit_tiff = if let Some(audit_path) = audit_linear_tiff {
            let audit_bytes = format!(
                "ICCRAW_AUDIT_LINEAR_STUB\ninput={}\nprofiling_mode={}\n",
                input_raw, recipe.profiling_mode
            );
            fs::write(audit_path, audit_bytes)
                .with_context(|| format!("failed to write audit TIFF stub to {}", audit_path))?;
            Some(audit_path.to_string())
        } else {
            None
        };

        Ok(DevelopArtifacts {
            raw_metadata,
            recipe: recipe.clone(),
            scientific_guard: guard,
            output_tiff: out_tiff.to_string(),
            audit_tiff,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::{ControlledPipeline, DenoiseMode, Recipe, SharpenMode, ToneCurve};
    use camino::Utf8Path;
    use tempfile::tempdir;

    #[test]
    fn recipe_default_is_scientific_safe() {
        let recipe = Recipe::default();
        let guard = recipe.scientific_guard_report();
        assert!(guard.is_scientific_safe);
        assert!(guard.warnings.is_empty());
    }

    #[test]
    fn recipe_guard_warns_about_non_neutral_ops() {
        let mut recipe = Recipe::default();
        recipe.denoise = DenoiseMode::Conservative;
        recipe.sharpen = SharpenMode::Mild;
        recipe.tone_curve = ToneCurve::Gamma {
            gamma: "2.2".to_string(),
        };

        let guard = recipe.scientific_guard_report();
        assert!(!guard.is_scientific_safe);
        assert!(guard.warnings.len() >= 3);
    }

    #[test]
    fn develop_writes_output_files() {
        let dir = tempdir().expect("temp dir");
        let input = dir.path().join("capture.nef");
        let out = dir.path().join("out.tiff");
        let audit = dir.path().join("audit_linear.tiff");

        std::fs::write(&input, b"raw fixture").expect("write input");

        let pipeline = ControlledPipeline;
        let result = pipeline
            .develop(
                Utf8Path::from_path(&input).expect("utf8"),
                &Recipe::default(),
                Utf8Path::from_path(&out).expect("utf8"),
                Some(Utf8Path::from_path(&audit).expect("utf8")),
            )
            .expect("develop");

        assert_eq!(result.output_tiff, out.to_string_lossy());
        assert!(out.exists());
        assert!(audit.exists());
    }
}
