use std::collections::HashMap;

use anyhow::{bail, Context, Result};
use camino::Utf8Path;
use icc_chart_detection::ChartDetectionResult;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReferencePatch {
    pub patch_id: String,
    pub reference_rgb: [f64; 3],
    pub reference_lab: [f64; 3],
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReferenceCatalog {
    pub chart_name: String,
    pub chart_version: String,
    pub illuminant: String,
    pub observer: String,
    pub patches: Vec<ReferencePatch>,
}

impl ReferenceCatalog {
    pub fn from_path(path: &Utf8Path) -> Result<Self> {
        let raw = std::fs::read_to_string(path)
            .with_context(|| format!("failed reading reference catalog {}", path))?;
        serde_json::from_str::<Self>(&raw)
            .with_context(|| format!("invalid reference catalog JSON {}", path))
    }

    fn patch_map(&self) -> HashMap<&str, &ReferencePatch> {
        self.patches
            .iter()
            .map(|patch| (patch.patch_id.as_str(), patch))
            .collect()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum SamplingMethod {
    Median,
    TrimmedMean,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SamplingStrategy {
    pub method: SamplingMethod,
    pub trim_percent: f32,
    pub reject_saturated: bool,
}

impl Default for SamplingStrategy {
    fn default() -> Self {
        Self {
            method: SamplingMethod::TrimmedMean,
            trim_percent: 0.1,
            reject_saturated: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PatchSample {
    pub patch_id: String,
    pub measured_rgb: [f64; 3],
    pub reference_rgb: [f64; 3],
    pub reference_lab: [f64; 3],
    pub excluded_pixel_ratio: f32,
    pub saturated_pixel_ratio: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SampleSet {
    pub chart_name: String,
    pub chart_version: String,
    pub illuminant: String,
    pub strategy: SamplingStrategy,
    pub samples: Vec<PatchSample>,
    pub missing_reference_patches: Vec<String>,
}

pub fn sample_chart(
    detection: &ChartDetectionResult,
    reference: &ReferenceCatalog,
    strategy: SamplingStrategy,
) -> Result<SampleSet> {
    let patch_map = reference.patch_map();
    let mut samples = Vec::new();
    let mut missing = Vec::new();

    for (idx, patch) in detection.patches.iter().enumerate() {
        let Some(reference_patch) = patch_map.get(patch.patch_id.as_str()) else {
            missing.push(patch.patch_id.clone());
            continue;
        };

        // Placeholder deterministic measurement model to keep CLI and tests functional
        // before OpenCV-based pixel sampling is integrated.
        let jitter = ((idx % 7) as f64) * 0.001;
        let measured_rgb = [
            (reference_patch.reference_rgb[0] * (1.0 + jitter)).clamp(0.0, 1.0),
            (reference_patch.reference_rgb[1] * (1.0 - jitter)).clamp(0.0, 1.0),
            (reference_patch.reference_rgb[2] * (1.0 + jitter * 0.5)).clamp(0.0, 1.0),
        ];

        samples.push(PatchSample {
            patch_id: patch.patch_id.clone(),
            measured_rgb,
            reference_rgb: reference_patch.reference_rgb,
            reference_lab: reference_patch.reference_lab,
            excluded_pixel_ratio: strategy.trim_percent,
            saturated_pixel_ratio: 0.0,
        });
    }

    if samples.is_empty() {
        bail!("no matching patches between detection result and reference catalog");
    }

    Ok(SampleSet {
        chart_name: reference.chart_name.clone(),
        chart_version: reference.chart_version.clone(),
        illuminant: reference.illuminant.clone(),
        strategy,
        samples,
        missing_reference_patches: missing,
    })
}

#[cfg(test)]
mod tests {
    use icc_chart_detection::{ChartType, StubChartDetector};

    use super::{sample_chart, ReferenceCatalog, ReferencePatch, SamplingMethod, SamplingStrategy};
    use camino::Utf8Path;
    use tempfile::tempdir;

    fn test_reference() -> ReferenceCatalog {
        let patches = (1..=24)
            .map(|i| ReferencePatch {
                patch_id: format!("P{:02}", i),
                reference_rgb: [0.1 + i as f64 * 0.01, 0.2, 0.3],
                reference_lab: [50.0, 0.0, 0.0],
            })
            .collect();

        ReferenceCatalog {
            chart_name: "ColorChecker 24".to_string(),
            chart_version: "2005".to_string(),
            illuminant: "D50".to_string(),
            observer: "2".to_string(),
            patches,
        }
    }

    #[test]
    fn samples_detected_patches() {
        let dir = tempdir().expect("temp dir");
        let chart_path = dir.path().join("chart.tiff");
        std::fs::write(&chart_path, vec![7_u8; 4096]).expect("write chart");

        let detector = StubChartDetector;
        let detection = detector
            .detect(
                Utf8Path::from_path(chart_path.as_path()).expect("utf8"),
                ChartType::ColorChecker24,
            )
            .expect("detect");

        let samples = sample_chart(
            &detection,
            &test_reference(),
            SamplingStrategy {
                method: SamplingMethod::TrimmedMean,
                trim_percent: 0.1,
                reject_saturated: true,
            },
        )
        .expect("sample");

        assert_eq!(samples.samples.len(), 24);
        assert!(samples.missing_reference_patches.is_empty());
    }

    #[test]
    fn loads_reference_catalog_from_json() {
        let dir = tempdir().expect("temp dir");
        let path = dir.path().join("ref.json");

        let catalog = test_reference();
        let json = serde_json::to_string_pretty(&catalog).expect("serialize catalog");
        std::fs::write(&path, json).expect("write catalog");

        let loaded = ReferenceCatalog::from_path(Utf8Path::from_path(path.as_path()).expect("utf8"))
            .expect("load catalog");
        assert_eq!(loaded.patches.len(), 24);
    }
}
