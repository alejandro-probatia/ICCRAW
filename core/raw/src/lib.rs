use std::fs::File;
use std::io::{BufReader, Read};

use camino::Utf8Path;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CfaPattern {
    BayerRggb,
    BayerBggr,
    BayerGbrg,
    BayerGrbg,
    XTrans,
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum WhiteBalanceSource {
    CameraMetadata,
    FixedMultipliers,
    NeutralPatch,
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RawMetadata {
    pub source_file: String,
    pub input_sha256: String,
    pub camera_model: Option<String>,
    pub cfa_pattern: CfaPattern,
    pub available_white_balance: WhiteBalanceSource,
    pub wb_multipliers: Option<[f32; 4]>,
    pub black_level: Option<u16>,
    pub white_level: Option<u16>,
    pub color_matrix_hint: Option<[[f32; 3]; 3]>,
    pub iso: Option<u32>,
    pub exposure_time_seconds: Option<f32>,
    pub lens_model: Option<String>,
    pub capture_datetime_utc: Option<String>,
    pub dimensions: Option<(u32, u32)>,
    pub intermediate_working_space: String,
}

#[derive(Debug, Error)]
pub enum RawError {
    #[error("raw source file does not exist: {0}")]
    NotFound(String),
    #[error("failed to read raw source file {path}: {source}")]
    Read {
        path: String,
        #[source]
        source: std::io::Error,
    },
}

pub trait RawDecoder {
    fn read_metadata(&self, input: &Utf8Path) -> Result<RawMetadata, RawError>;
}

#[derive(Debug, Default)]
pub struct MockRawDecoder;

impl MockRawDecoder {
    fn infer_camera_model(path: &Utf8Path) -> Option<String> {
        let stem = path
            .file_stem()
            .map(|s| s.replace(['_', '-'], " "))
            .unwrap_or_else(|| "unknown-camera".to_string());
        Some(format!("MockCam {}", stem))
    }

    fn infer_cfa(path: &Utf8Path) -> CfaPattern {
        match path.extension().unwrap_or_default().to_ascii_lowercase().as_str() {
            "raf" => CfaPattern::XTrans,
            "cr3" | "cr2" | "nef" | "arw" | "dng" => CfaPattern::BayerRggb,
            _ => CfaPattern::Unknown,
        }
    }

    fn sha256_hex(path: &Utf8Path) -> Result<String, RawError> {
        let file = File::open(path).map_err(|source| RawError::Read {
            path: path.to_string(),
            source,
        })?;

        let mut reader = BufReader::new(file);
        let mut hasher = Sha256::new();
        let mut buffer = [0_u8; 8192];

        loop {
            let read = reader.read(&mut buffer).map_err(|source| RawError::Read {
                path: path.to_string(),
                source,
            })?;
            if read == 0 {
                break;
            }
            hasher.update(&buffer[..read]);
        }

        Ok(format!("{:x}", hasher.finalize()))
    }
}

impl RawDecoder for MockRawDecoder {
    fn read_metadata(&self, input: &Utf8Path) -> Result<RawMetadata, RawError> {
        if !input.exists() {
            return Err(RawError::NotFound(input.to_string()));
        }

        let input_sha256 = Self::sha256_hex(input)?;
        let file_size = std::fs::metadata(input)
            .map_err(|source| RawError::Read {
                path: input.to_string(),
                source,
            })?
            .len();

        Ok(RawMetadata {
            source_file: input.to_string(),
            input_sha256,
            camera_model: Self::infer_camera_model(input),
            cfa_pattern: Self::infer_cfa(input),
            available_white_balance: WhiteBalanceSource::Unknown,
            wb_multipliers: None,
            black_level: Some(512),
            white_level: Some(16383),
            color_matrix_hint: None,
            iso: Some(100),
            exposure_time_seconds: Some(1.0_f32 / 125.0_f32),
            lens_model: Some("Mock Lens 50mm F2".to_string()),
            capture_datetime_utc: None,
            dimensions: Some((
                6000_u32,
                (file_size as u32 % 2500).saturating_add(3000_u32),
            )),
            intermediate_working_space: "scene_linear_camera_rgb".to_string(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::{CfaPattern, MockRawDecoder, RawDecoder};
    use camino::Utf8Path;
    use tempfile::tempdir;

    #[test]
    fn reads_mock_metadata_for_existing_file() {
        let dir = tempdir().expect("temp dir");
        let file_path = dir.path().join("capture.nef");
        std::fs::write(&file_path, b"synthetic raw bytes").expect("write fixture");

        let decoder = MockRawDecoder;
        let metadata = decoder
            .read_metadata(Utf8Path::from_path(file_path.as_path()).expect("utf8 path"))
            .expect("metadata");

        assert_eq!(metadata.cfa_pattern, CfaPattern::BayerRggb);
        assert!(metadata.input_sha256.len() >= 64);
        assert_eq!(metadata.intermediate_working_space, "scene_linear_camera_rgb");
    }

    #[test]
    fn fails_when_input_is_missing() {
        let decoder = MockRawDecoder;
        let result = decoder.read_metadata(Utf8Path::new("/tmp/does-not-exist.raw"));
        assert!(result.is_err());
    }
}
