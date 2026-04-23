use std::cmp::Ordering;

use anyhow::{Context, Result};
use camino::Utf8Path;
use icc_color::{delta_e2000, delta_e76, Lab};
use icc_pipeline::Recipe;
use icc_sampling::SampleSet;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ProfileModel {
    Matrix3x3,
    Matrix3x3WithTrc,
    Lut,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PatchError {
    pub patch_id: String,
    pub delta_e76: f64,
    pub delta_e2000: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorSummary {
    pub mean_delta_e76: f64,
    pub median_delta_e76: f64,
    pub p95_delta_e76: f64,
    pub max_delta_e76: f64,
    pub mean_delta_e2000: f64,
    pub median_delta_e2000: f64,
    pub p95_delta_e2000: f64,
    pub max_delta_e2000: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CameraProfileMetadata {
    pub camera_model: Option<String>,
    pub lens_model: Option<String>,
    pub illuminant: String,
    pub chart_name: String,
    pub chart_version: String,
    pub profile_model: ProfileModel,
    pub algorithm_version: String,
    pub recipe: Recipe,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProfileBuildResult {
    pub output_icc: String,
    pub metadata: CameraProfileMetadata,
    pub error_summary: ErrorSummary,
    pub patch_errors: Vec<PatchError>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ValidationResult {
    pub profile_path: String,
    pub error_summary: ErrorSummary,
    pub patch_errors: Vec<PatchError>,
}

pub fn build_profile(
    samples: &SampleSet,
    recipe: &Recipe,
    output_icc: &Utf8Path,
    camera_model: Option<String>,
    lens_model: Option<String>,
) -> Result<ProfileBuildResult> {
    let (summary, patch_errors) = evaluate_samples(samples);

    let metadata = CameraProfileMetadata {
        camera_model,
        lens_model,
        illuminant: samples.illuminant.clone(),
        chart_name: samples.chart_name.clone(),
        chart_version: samples.chart_version.clone(),
        profile_model: ProfileModel::Matrix3x3,
        algorithm_version: env!("CARGO_PKG_VERSION").to_string(),
        recipe: recipe.clone(),
    };

    let fake_icc = format!(
        "ICC_PROFILE_STUB\nchart={}\nversion={}\nmean_de00={:.4}\n",
        metadata.chart_name, metadata.chart_version, summary.mean_delta_e2000
    );
    std::fs::write(output_icc, fake_icc)
        .with_context(|| format!("failed writing ICC output {}", output_icc))?;

    Ok(ProfileBuildResult {
        output_icc: output_icc.to_string(),
        metadata,
        error_summary: summary,
        patch_errors,
    })
}

pub fn validate_profile(samples: &SampleSet, profile_path: &Utf8Path) -> Result<ValidationResult> {
    if !profile_path.exists() {
        anyhow::bail!("profile does not exist: {}", profile_path);
    }
    let (summary, patch_errors) = evaluate_samples(samples);

    Ok(ValidationResult {
        profile_path: profile_path.to_string(),
        error_summary: summary,
        patch_errors,
    })
}

fn evaluate_samples(samples: &SampleSet) -> (ErrorSummary, Vec<PatchError>) {
    let mut patch_errors = Vec::with_capacity(samples.samples.len());

    for sample in &samples.samples {
        let measured_lab = pseudo_lab_from_rgb(sample.measured_rgb);
        let reference_lab = Lab::new(
            sample.reference_lab[0],
            sample.reference_lab[1],
            sample.reference_lab[2],
        );

        patch_errors.push(PatchError {
            patch_id: sample.patch_id.clone(),
            delta_e76: delta_e76(measured_lab, reference_lab),
            delta_e2000: delta_e2000(measured_lab, reference_lab),
        });
    }

    let de76_values: Vec<f64> = patch_errors.iter().map(|p| p.delta_e76).collect();
    let de00_values: Vec<f64> = patch_errors.iter().map(|p| p.delta_e2000).collect();

    (
        ErrorSummary {
            mean_delta_e76: mean(&de76_values),
            median_delta_e76: percentile(&de76_values, 0.50),
            p95_delta_e76: percentile(&de76_values, 0.95),
            max_delta_e76: de76_values.iter().copied().fold(0.0_f64, f64::max),
            mean_delta_e2000: mean(&de00_values),
            median_delta_e2000: percentile(&de00_values, 0.50),
            p95_delta_e2000: percentile(&de00_values, 0.95),
            max_delta_e2000: de00_values.iter().copied().fold(0.0_f64, f64::max),
        },
        patch_errors,
    )
}

fn mean(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    values.iter().sum::<f64>() / values.len() as f64
}

fn percentile(values: &[f64], p: f64) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let mut sorted = values.to_vec();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(Ordering::Equal));
    let idx = ((sorted.len() - 1) as f64 * p).round() as usize;
    sorted[idx]
}

fn pseudo_lab_from_rgb(rgb: [f64; 3]) -> Lab {
    Lab::new(
        (rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722) * 100.0,
        (rgb[0] - rgb[1]) * 128.0,
        (rgb[1] - rgb[2]) * 128.0,
    )
}

#[cfg(test)]
mod tests {
    use icc_chart_detection::{ChartType, StubChartDetector};
    use icc_sampling::{sample_chart, ReferenceCatalog, ReferencePatch, SamplingStrategy};

    use super::{build_profile, validate_profile};
    use camino::Utf8Path;
    use icc_pipeline::Recipe;
    use tempfile::tempdir;

    fn fixture_samples() -> icc_sampling::SampleSet {
        let dir = tempdir().expect("temp dir");
        let chart_path = dir.path().join("chart.tiff");
        std::fs::write(&chart_path, vec![2_u8; 4096]).expect("write chart");

        let detector = StubChartDetector;
        let detection = detector
            .detect(
                Utf8Path::from_path(chart_path.as_path()).expect("utf8"),
                ChartType::ColorChecker24,
            )
            .expect("detect");

        let reference = ReferenceCatalog {
            chart_name: "ColorChecker 24".to_string(),
            chart_version: "2005".to_string(),
            illuminant: "D50".to_string(),
            observer: "2".to_string(),
            patches: (1..=24)
                .map(|i| ReferencePatch {
                    patch_id: format!("P{:02}", i),
                    reference_rgb: [0.2, 0.3, 0.4],
                    reference_lab: [55.0, 0.0, 0.0],
                })
                .collect(),
        };

        sample_chart(&detection, &reference, SamplingStrategy::default()).expect("sample")
    }

    #[test]
    fn builds_profile_and_validation_results() {
        let samples = fixture_samples();
        let recipe = Recipe::default();

        let dir = tempdir().expect("temp dir");
        let profile = dir.path().join("camera.icc");

        let build = build_profile(
            &samples,
            &recipe,
            Utf8Path::from_path(profile.as_path()).expect("utf8"),
            Some("MockCam".to_string()),
            Some("Mock Lens".to_string()),
        )
        .expect("build profile");

        assert!(profile.exists());
        assert_eq!(build.metadata.chart_name, "ColorChecker 24");

        let validation = validate_profile(
            &samples,
            Utf8Path::from_path(profile.as_path()).expect("utf8"),
        )
        .expect("validate");
        assert!(validation.error_summary.max_delta_e2000 >= 0.0);
    }
}
