use std::path::PathBuf;

fn main() {
    // Tauri 的 bundle.externalBin 要求 sidecar 文件在构建期存在。
    // - debug / `npm run tauri dev` 不跑 sidecar（dev 直接用 backend/.venv），放一个空占位即可；
    // - release 必须由 scripts/build_release.ps1 先打包并拷贝真实 sidecar，缺失时直接报错，
    //   避免产出一个“能装但起不来”的安装包。
    let profile = std::env::var("PROFILE").unwrap_or_default();
    let target = std::env::var("TARGET").unwrap_or_default();
    let manifest_dir = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR"));
    let sidecar = manifest_dir
        .join("binaries")
        .join(format!("eclipse-health-backend-{target}.exe"));

    if !sidecar.exists() {
        if profile == "debug" {
            if let Some(parent) = sidecar.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            let _ = std::fs::write(&sidecar, b"");
        } else {
            panic!(
                "sidecar missing: {} — run scripts/build_release.ps1 first",
                sidecar.display()
            );
        }
    }
    println!("cargo:rerun-if-changed=binaries");

    // onedir sidecar 的 _internal（Tauri resources）同理：debug 放占位目录，
    // release 必须由 build_release.ps1 同步真实文件，否则 sidecar 起不来。
    let internal = manifest_dir.join("_internal");
    if !internal.is_dir() {
        if profile == "debug" {
            let _ = std::fs::create_dir_all(&internal);
            let _ = std::fs::write(internal.join(".keep"), b"");
        } else {
            panic!(
                "sidecar runtime missing: {} — run scripts/build_release.ps1 first",
                internal.display()
            );
        }
    }
    println!("cargo:rerun-if-changed=_internal");

    tauri_build::build()
}
