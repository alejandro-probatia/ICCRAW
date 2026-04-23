use std::fs;
use std::io::Read;

use anyhow::{Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use icc_pipeline::{ControlledPipeline, Recipe};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BatchManifestEntry {
    pub source_raw: String,
    pub source_sha256: String,
    pub output_tiff: String,
    pub output_sha256: String,
    pub profile_path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BatchManifest {
    pub recipe_sha256: String,
    pub profile_path: String,
    pub software_version: String,
    pub entries: Vec<BatchManifestEntry>,
}

pub fn batch_develop(
    raws_dir: &Utf8Path,
    recipe: &Recipe,
    profile_path: &Utf8Path,
    output_dir: &Utf8Path,
) -> Result<BatchManifest> {
    fs::create_dir_all(output_dir)
        .with_context(|| format!("failed to create output directory {}", output_dir))?;

    let recipe_sha256 = {
        let bytes = serde_json::to_vec(recipe).context("failed to serialize recipe")?;
        let mut hasher = Sha256::new();
        hasher.update(bytes);
        format!("{:x}", hasher.finalize())
    };

    let raw_paths = collect_raw_paths(raws_dir)?;
    let pipeline = ControlledPipeline;
    let mut entries = Vec::new();

    for raw_path in raw_paths {
        let stem = raw_path
            .file_stem()
            .ok_or_else(|| anyhow::anyhow!("raw file without stem: {}", raw_path))?;
        let out_tiff: Utf8PathBuf = output_dir.join(format!("{}.tiff", stem));

        pipeline.develop(&raw_path, recipe, &out_tiff, None)?;

        entries.push(BatchManifestEntry {
            source_raw: raw_path.to_string(),
            source_sha256: file_sha256(&raw_path)?,
            output_tiff: out_tiff.to_string(),
            output_sha256: file_sha256(&out_tiff)?,
            profile_path: profile_path.to_string(),
        });
    }

    Ok(BatchManifest {
        recipe_sha256,
        profile_path: profile_path.to_string(),
        software_version: env!("CARGO_PKG_VERSION").to_string(),
        entries,
    })
}

fn collect_raw_paths(raws_dir: &Utf8Path) -> Result<Vec<Utf8PathBuf>> {
    let mut raws = Vec::new();
    for entry in fs::read_dir(raws_dir).with_context(|| format!("failed to read {}", raws_dir))? {
        let entry = entry.context("failed reading dir entry")?;
        let path = entry.path();
        if !path.is_file() {
            continue;
        }

        let ext = path
            .extension()
            .and_then(|v| v.to_str())
            .unwrap_or_default()
            .to_ascii_lowercase();

        if matches!(ext.as_str(), "raw" | "cr2" | "cr3" | "nef" | "arw" | "dng" | "raf") {
            let utf8 = Utf8PathBuf::from_path_buf(path).map_err(|p| {
                anyhow::anyhow!(
                    "found non utf-8 path in raws directory: {}",
                    p.to_string_lossy()
                )
            })?;
            raws.push(utf8);
        }
    }

    raws.sort();
    Ok(raws)
}

fn file_sha256(path: &Utf8Path) -> Result<String> {
    let mut file = fs::File::open(path).with_context(|| format!("failed opening {}", path))?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 8192];
    loop {
        let read = file
            .read(&mut buffer)
            .with_context(|| format!("failed reading {}", path))?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }

    Ok(format!("{:x}", hasher.finalize()))
}

#[cfg(test)]
mod tests {
    use super::batch_develop;
    use camino::Utf8Path;
    use icc_pipeline::Recipe;
    use tempfile::tempdir;

    #[test]
    fn runs_batch_stub_export_and_builds_manifest() {
        let dir = tempdir().expect("temp dir");
        let raws = dir.path().join("raws");
        let out = dir.path().join("out");
        let profile = dir.path().join("camera.icc");
        std::fs::create_dir_all(&raws).expect("mkdir raws");
        std::fs::write(raws.join("a.nef"), b"raw a").expect("write raw a");
        std::fs::write(raws.join("b.cr3"), b"raw b").expect("write raw b");
        std::fs::write(&profile, b"icc placeholder").expect("write profile");

        let manifest = batch_develop(
            Utf8Path::from_path(raws.as_path()).expect("utf8 raws"),
            &Recipe::default(),
            Utf8Path::from_path(profile.as_path()).expect("utf8 profile"),
            Utf8Path::from_path(out.as_path()).expect("utf8 out"),
        )
        .expect("batch develop");

        assert_eq!(manifest.entries.len(), 2);
        assert!(out.join("a.tiff").exists());
        assert!(out.join("b.tiff").exists());
    }
}
