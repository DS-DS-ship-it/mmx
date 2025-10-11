use assert_cmd::Command;

#[test]
fn help_works() {
    let mut cmd = Command::cargo_bin("mmx").unwrap();
    cmd.arg("--help").assert().success();
}
