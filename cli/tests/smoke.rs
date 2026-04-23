use assert_cmd::Command;
use predicates::str::contains;
use tempfile::tempdir;

#[test]
fn raw_info_command_prints_json() {
    let dir = tempdir().expect("temp dir");
    let input = dir.path().join("capture.nef");
    std::fs::write(&input, b"raw bytes").expect("write fixture");

    let mut cmd = Command::cargo_bin("app").expect("binary");
    cmd.arg("raw-info").arg(&input);
    cmd.assert()
        .success()
        .stdout(contains("camera_model"))
        .stdout(contains("input_sha256"));
}

#[test]
fn detect_chart_writes_detection_file() {
    let dir = tempdir().expect("temp dir");
    let chart = dir.path().join("chart.tiff");
    let out = dir.path().join("detection.json");
    std::fs::write(&chart, vec![9_u8; 2048]).expect("write chart");

    let mut cmd = Command::cargo_bin("app").expect("binary");
    cmd.arg("detect-chart")
        .arg(&chart)
        .arg("--out")
        .arg(&out)
        .arg("--chart-type")
        .arg("colorchecker24");

    cmd.assert().success().stdout(contains("confidence_score"));
    assert!(out.exists());
}
