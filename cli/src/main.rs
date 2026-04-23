use std::path::PathBuf;

use anyhow::{bail, Context, Result};
use camino::Utf8PathBuf;
use clap::{Parser, Subcommand, ValueEnum};
use icc_chart_detection::{ChartDetectionResult, ChartType, StubChartDetector};
use icc_export::batch_develop;
use icc_pipeline::{ControlledPipeline, Recipe};
use icc_profiling::{build_profile, validate_profile, ProfileBuildResult, ValidationResult};
use icc_raw::{MockRawDecoder, RawDecoder};
use icc_reporting::{read_json, write_json, RunContext};
use icc_sampling::{sample_chart, ReferenceCatalog, SampleSet, SamplingStrategy};

#[derive(Debug, Parser)]
#[command(name = "app")]
#[command(about = "CLI para pipeline colorimétrico reproducible en fotografía técnico-científica")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Debug, Subcommand)]
enum Commands {
    RawInfo {
        input: PathBuf,
    },
    Develop {
        input: PathBuf,
        #[arg(long)]
        recipe: PathBuf,
        #[arg(long)]
        out: PathBuf,
        #[arg(long)]
        audit_linear: Option<PathBuf>,
    },
    DetectChart {
        input: PathBuf,
        #[arg(long)]
        out: PathBuf,
        #[arg(long)]
        preview: Option<PathBuf>,
        #[arg(long, value_enum, default_value = "colorchecker24")]
        chart_type: CliChartType,
    },
    SampleChart {
        input: PathBuf,
        #[arg(long)]
        detection: PathBuf,
        #[arg(long)]
        reference: PathBuf,
        #[arg(long)]
        out: PathBuf,
    },
    BuildProfile {
        samples: PathBuf,
        #[arg(long)]
        recipe: PathBuf,
        #[arg(long)]
        out: PathBuf,
        #[arg(long)]
        report: PathBuf,
    },
    BatchDevelop {
        input: PathBuf,
        #[arg(long)]
        recipe: PathBuf,
        #[arg(long)]
        profile: PathBuf,
        #[arg(long)]
        out: PathBuf,
    },
    ValidateProfile {
        samples: PathBuf,
        #[arg(long)]
        profile: PathBuf,
        #[arg(long)]
        out: PathBuf,
    },
}

#[derive(Debug, Clone, Copy, ValueEnum)]
enum CliChartType {
    Colorchecker24,
    It8,
}

impl From<CliChartType> for ChartType {
    fn from(value: CliChartType) -> Self {
        match value {
            CliChartType::Colorchecker24 => ChartType::ColorChecker24,
            CliChartType::It8 => ChartType::It8,
        }
    }
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    run(cli)
}

fn run(cli: Cli) -> Result<()> {
    match cli.command {
        Commands::RawInfo { input } => cmd_raw_info(&input),
        Commands::Develop {
            input,
            recipe,
            out,
            audit_linear,
        } => cmd_develop(&input, &recipe, &out, audit_linear.as_deref()),
        Commands::DetectChart {
            input,
            out,
            preview,
            chart_type,
        } => cmd_detect_chart(&input, &out, preview.as_deref(), chart_type.into()),
        Commands::SampleChart {
            input,
            detection,
            reference,
            out,
        } => cmd_sample_chart(&input, &detection, &reference, &out),
        Commands::BuildProfile {
            samples,
            recipe,
            out,
            report,
        } => cmd_build_profile(&samples, &recipe, &out, &report),
        Commands::BatchDevelop {
            input,
            recipe,
            profile,
            out,
        } => cmd_batch_develop(&input, &recipe, &profile, &out),
        Commands::ValidateProfile {
            samples,
            profile,
            out,
        } => cmd_validate_profile(&samples, &profile, &out),
    }
}

fn cmd_raw_info(input: &PathBuf) -> Result<()> {
    let input = as_utf8_path(input)?;
    let decoder = MockRawDecoder;
    let metadata = decoder.read_metadata(input.as_ref())?;
    println!("{}", serde_json::to_string_pretty(&metadata)?);
    Ok(())
}

fn cmd_develop(
    input: &PathBuf,
    recipe_path: &PathBuf,
    out: &PathBuf,
    audit_linear: Option<&std::path::Path>,
) -> Result<()> {
    let input = as_utf8_path(input)?;
    let recipe_path = as_utf8_path(recipe_path)?;
    let out = as_utf8_path(out)?;
    let audit_linear = audit_linear
        .map(as_utf8_path_from_std)
        .transpose()?
        .map(|p| p.to_owned());

    let recipe = Recipe::from_path(recipe_path.as_ref())?;
    let pipeline = ControlledPipeline;
    let artifacts = pipeline.develop(
        input.as_ref(),
        &recipe,
        out.as_ref(),
        audit_linear.as_deref(),
    )?;

    let run = RunContext::gather();
    let payload = serde_json::json!({
        "run_context": run,
        "develop": artifacts,
    });

    println!("{}", serde_json::to_string_pretty(&payload)?);
    Ok(())
}

fn cmd_detect_chart(
    input: &PathBuf,
    out: &PathBuf,
    preview: Option<&std::path::Path>,
    chart_type: ChartType,
) -> Result<()> {
    let input = as_utf8_path(input)?;
    let out = as_utf8_path(out)?;
    let preview = preview.map(as_utf8_path_from_std).transpose()?;

    let detector = StubChartDetector;
    let detection = detector.detect(input.as_ref(), chart_type)?;
    write_json(out.as_ref(), &detection)?;

    if let Some(preview) = preview {
        let preview_text = format!(
            "OVERLAY_STUB\nchart={:?}\npatches={}\n",
            detection.chart_type,
            detection.patches.len()
        );
        std::fs::write(preview.as_std_path(), preview_text)
            .with_context(|| format!("failed writing preview overlay {}", preview))?;
    }

    println!("{}", serde_json::to_string_pretty(&detection)?);
    Ok(())
}

fn cmd_sample_chart(
    input_chart: &PathBuf,
    detection_path: &PathBuf,
    reference_path: &PathBuf,
    out: &PathBuf,
) -> Result<()> {
    let input_chart = as_utf8_path(input_chart)?;
    let detection_path = as_utf8_path(detection_path)?;
    let reference_path = as_utf8_path(reference_path)?;
    let out = as_utf8_path(out)?;

    if !input_chart.exists() {
        bail!("chart image does not exist: {}", input_chart);
    }

    let detection: ChartDetectionResult = read_json(detection_path.as_ref())?;
    let reference = ReferenceCatalog::from_path(reference_path.as_ref())?;
    let samples = sample_chart(&detection, &reference, SamplingStrategy::default())?;

    write_json(out.as_ref(), &samples)?;
    println!("{}", serde_json::to_string_pretty(&samples)?);
    Ok(())
}

fn cmd_build_profile(
    samples_path: &PathBuf,
    recipe_path: &PathBuf,
    output_profile: &PathBuf,
    report_path: &PathBuf,
) -> Result<()> {
    let samples_path = as_utf8_path(samples_path)?;
    let recipe_path = as_utf8_path(recipe_path)?;
    let output_profile = as_utf8_path(output_profile)?;
    let report_path = as_utf8_path(report_path)?;

    let samples: SampleSet = read_json(samples_path.as_ref())?;
    let recipe = Recipe::from_path(recipe_path.as_ref())?;

    let result: ProfileBuildResult =
        build_profile(&samples, &recipe, output_profile.as_ref(), None, None)?;

    write_json(report_path.as_ref(), &result)?;
    println!("{}", serde_json::to_string_pretty(&result)?);
    Ok(())
}

fn cmd_batch_develop(
    input_dir: &PathBuf,
    recipe_path: &PathBuf,
    profile_path: &PathBuf,
    out_dir: &PathBuf,
) -> Result<()> {
    let input_dir = as_utf8_path(input_dir)?;
    let recipe_path = as_utf8_path(recipe_path)?;
    let profile_path = as_utf8_path(profile_path)?;
    let out_dir = as_utf8_path(out_dir)?;

    let recipe = Recipe::from_path(recipe_path.as_ref())?;
    let manifest = batch_develop(
        input_dir.as_ref(),
        &recipe,
        profile_path.as_ref(),
        out_dir.as_ref(),
    )?;

    let manifest_path = out_dir.join("batch_manifest.json");
    write_json(manifest_path.as_ref(), &manifest)?;
    println!("{}", serde_json::to_string_pretty(&manifest)?);
    Ok(())
}

fn cmd_validate_profile(samples_path: &PathBuf, profile_path: &PathBuf, out: &PathBuf) -> Result<()> {
    let samples_path = as_utf8_path(samples_path)?;
    let profile_path = as_utf8_path(profile_path)?;
    let out = as_utf8_path(out)?;

    let samples: SampleSet = read_json(samples_path.as_ref())?;
    let result: ValidationResult = validate_profile(&samples, profile_path.as_ref())?;
    write_json(out.as_ref(), &result)?;
    println!("{}", serde_json::to_string_pretty(&result)?);
    Ok(())
}

fn as_utf8_path(path: &PathBuf) -> Result<Utf8PathBuf> {
    as_utf8_path_from_std(path.as_path())
}

fn as_utf8_path_from_std(path: &std::path::Path) -> Result<Utf8PathBuf> {
    Utf8PathBuf::from_path_buf(path.to_path_buf()).map_err(|non_utf8| {
        anyhow::anyhow!(
            "path contains non-utf8 characters: {}",
            non_utf8.to_string_lossy()
        )
    })
}

#[cfg(test)]
mod tests {
    use super::Cli;
    use clap::Parser;

    #[test]
    fn parses_raw_info_command() {
        let cli = Cli::parse_from(["app", "raw-info", "capture.nef"]);
        assert!(format!("{cli:?}").contains("RawInfo"));
    }

    #[test]
    fn parses_build_profile_command() {
        let cli = Cli::parse_from([
            "app",
            "build-profile",
            "samples.json",
            "--recipe",
            "recipe.yml",
            "--out",
            "camera.icc",
            "--report",
            "report.json",
        ]);
        assert!(format!("{cli:?}").contains("BuildProfile"));
    }
}
