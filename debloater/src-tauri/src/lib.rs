use std::fs;
use std::os::unix::fs::PermissionsExt;

const BACKEND_BIN: &[u8] = include_bytes!("../backend-x86_64-unknown-linux-gnu");

fn ensure_sidecar() {
  if let Ok(exe_path) = std::env::current_exe() {
    if let Some(exe_dir) = exe_path.parent() {
      let targets = [
        exe_dir.join("backend-x86_64-unknown-linux-gnu"),
        exe_dir.join("backend"),
      ];
      for target in &targets {
        if !target.exists() {
          if let Ok(_) = fs::write(target, BACKEND_BIN) {
            let _ = fs::set_permissions(target, fs::Permissions::from_mode(0o755));
          }
        }
      }
    }
  }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  ensure_sidecar();

  tauri::Builder::default()
    .plugin(tauri_plugin_shell::init())
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while building tauri application");
}

