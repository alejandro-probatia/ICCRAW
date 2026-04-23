use anyhow::{bail, Context, Result};
use camino::Utf8Path;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ChartType {
    ColorChecker24,
    It8,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct Point2 {
    pub x: f32,
    pub y: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PatchDetection {
    pub patch_id: String,
    pub polygon: [Point2; 4],
    pub sample_region: [Point2; 4],
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChartDetectionResult {
    pub chart_type: ChartType,
    pub confidence_score: f32,
    pub valid_patch_ratio: f32,
    pub homography: [f64; 9],
    pub chart_polygon: [Point2; 4],
    pub patches: Vec<PatchDetection>,
    pub warnings: Vec<String>,
}

#[derive(Debug, Default)]
pub struct StubChartDetector;

impl StubChartDetector {
    pub fn detect(&self, image_path: &Utf8Path, chart_type: ChartType) -> Result<ChartDetectionResult> {
        if !image_path.exists() {
            bail!("image does not exist: {}", image_path);
        }

        let bytes = std::fs::read(image_path)
            .with_context(|| format!("failed reading chart image {}", image_path))?;
        if bytes.is_empty() {
            bail!("chart image is empty: {}", image_path);
        }

        let (cols, rows) = match chart_type {
            ChartType::ColorChecker24 => (6, 4),
            ChartType::It8 => (12, 10),
        };

        let mut patches = Vec::with_capacity(cols * rows);
        let chart_polygon = [
            Point2 { x: 0.10, y: 0.10 },
            Point2 { x: 0.90, y: 0.10 },
            Point2 { x: 0.90, y: 0.90 },
            Point2 { x: 0.10, y: 0.90 },
        ];

        let width = 0.80_f32;
        let height = 0.80_f32;
        let step_x = width / cols as f32;
        let step_y = height / rows as f32;

        for r in 0..rows {
            for c in 0..cols {
                let left = 0.10 + c as f32 * step_x;
                let top = 0.10 + r as f32 * step_y;
                let right = left + step_x;
                let bottom = top + step_y;

                // The sample region is shrunk to avoid edge contamination.
                let margin_x = step_x * 0.15;
                let margin_y = step_y * 0.15;

                patches.push(PatchDetection {
                    patch_id: format!("P{:02}", r * cols + c + 1),
                    polygon: [
                        Point2 { x: left, y: top },
                        Point2 { x: right, y: top },
                        Point2 {
                            x: right,
                            y: bottom,
                        },
                        Point2 { x: left, y: bottom },
                    ],
                    sample_region: [
                        Point2 {
                            x: left + margin_x,
                            y: top + margin_y,
                        },
                        Point2 {
                            x: right - margin_x,
                            y: top + margin_y,
                        },
                        Point2 {
                            x: right - margin_x,
                            y: bottom - margin_y,
                        },
                        Point2 {
                            x: left + margin_x,
                            y: bottom - margin_y,
                        },
                    ],
                });
            }
        }

        let mut warnings = Vec::new();
        if bytes.len() < 1024 {
            warnings.push("very small input file may reduce chart detection reliability".to_string());
        }

        Ok(ChartDetectionResult {
            chart_type,
            confidence_score: 0.70,
            valid_patch_ratio: 1.0,
            homography: [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
            chart_polygon,
            patches,
            warnings,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::{ChartType, StubChartDetector};
    use camino::Utf8Path;
    use tempfile::tempdir;

    #[test]
    fn detects_colorchecker_stub_layout() {
        let dir = tempdir().expect("temp dir");
        let image = dir.path().join("chart.tiff");
        std::fs::write(&image, vec![1_u8; 2048]).expect("write chart fixture");

        let detector = StubChartDetector;
        let result = detector
            .detect(
                Utf8Path::from_path(image.as_path()).expect("utf8 path"),
                ChartType::ColorChecker24,
            )
            .expect("detect");

        assert_eq!(result.patches.len(), 24);
        assert!(result.confidence_score > 0.5);
    }

    #[test]
    fn fails_for_missing_input() {
        let detector = StubChartDetector;
        let result = detector.detect(Utf8Path::new("/tmp/missing-chart.tiff"), ChartType::ColorChecker24);
        assert!(result.is_err());
    }
}
