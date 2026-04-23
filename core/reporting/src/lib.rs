use anyhow::{Context, Result};
use camino::Utf8Path;
use serde::{de::DeserializeOwned, Deserialize, Serialize};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DependencyVersion {
    pub name: String,
    pub version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunContext {
    pub software_version: String,
    pub git_commit: String,
    pub timestamp_utc: String,
    pub deterministic_mode: bool,
    pub dependencies: Vec<DependencyVersion>,
}

impl RunContext {
    pub fn gather() -> Self {
        let deterministic_mode = std::env::var("ICC_DETERMINISTIC")
            .map(|value| value == "1")
            .unwrap_or(false);

        let timestamp = if deterministic_mode {
            "1970-01-01T00:00:00Z".to_string()
        } else {
            OffsetDateTime::now_utc()
                .format(&Rfc3339)
                .unwrap_or_else(|_| "unknown-timestamp".to_string())
        };

        Self {
            software_version: env!("CARGO_PKG_VERSION").to_string(),
            git_commit: std::env::var("GIT_COMMIT").unwrap_or_else(|_| "unknown".to_string()),
            timestamp_utc: timestamp,
            deterministic_mode,
            dependencies: vec![
                DependencyVersion {
                    name: "libraw".to_string(),
                    version: "not-linked-yet".to_string(),
                },
                DependencyVersion {
                    name: "lcms2".to_string(),
                    version: "not-linked-yet".to_string(),
                },
                DependencyVersion {
                    name: "opencv".to_string(),
                    version: "not-linked-yet".to_string(),
                },
            ],
        }
    }
}

pub fn write_json<T: Serialize>(path: &Utf8Path, value: &T) -> Result<()> {
    let bytes = serde_json::to_vec_pretty(value).context("failed serializing json")?;
    std::fs::write(path, bytes).with_context(|| format!("failed writing {}", path))?;
    Ok(())
}

pub fn read_json<T: DeserializeOwned>(path: &Utf8Path) -> Result<T> {
    let raw = std::fs::read_to_string(path).with_context(|| format!("failed reading {}", path))?;
    serde_json::from_str(&raw).with_context(|| format!("invalid json in {}", path))
}

#[cfg(test)]
mod tests {
    use super::{read_json, write_json, RunContext};
    use camino::Utf8Path;
    use tempfile::tempdir;

    #[test]
    fn gathers_run_context() {
        let context = RunContext::gather();
        assert!(!context.software_version.is_empty());
        assert!(context.dependencies.len() >= 3);
    }

    #[test]
    fn writes_and_reads_json() {
        let dir = tempdir().expect("temp dir");
        let path = dir.path().join("context.json");

        let context = RunContext::gather();
        write_json(Utf8Path::from_path(path.as_path()).expect("utf8 path"), &context).expect("write");

        let loaded: RunContext =
            read_json(Utf8Path::from_path(path.as_path()).expect("utf8 path")).expect("read");
        assert_eq!(loaded.software_version, context.software_version);
    }
}
