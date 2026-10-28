use std::sync::atomic::{AtomicBool, Ordering};

use tauri::{
    menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, RunEvent, WindowEvent,
};

#[cfg(debug_assertions)]
use std::process::{Child, Command, Stdio};
#[cfg(debug_assertions)]
use std::sync::Mutex;

/// 关闭窗口时收起到托盘（默认开启），托盘菜单里可切换。
struct CloseToTray(AtomicBool);

/// 页面是否已经加载过；用于区分“首帧未显示”和“用户主动藏到托盘”。
struct PageLoaded(AtomicBool);

#[cfg(debug_assertions)]
struct BackendProcess(Mutex<Option<Child>>);

#[cfg(debug_assertions)]
const DEV_BACKEND_ADDR: &str = "127.0.0.1:8765";
#[cfg(debug_assertions)]
const DEV_BACKEND_DIR: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../backend");
#[cfg(debug_assertions)]
const DEV_BACKEND_PYTHON: &str =
    concat!(env!("CARGO_MANIFEST_DIR"), "/../backend/.venv/Scripts/python.exe");

fn show_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn setup_tray(app: &mut tauri::App) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, "show", "显示主窗口", true, None::<&str>)?;
    let hide = MenuItem::with_id(app, "hide", "隐藏到托盘", true, None::<&str>)?;
    let close_to_tray = CheckMenuItem::with_id(
        app,
        "close_to_tray",
        "关闭窗口时收起到托盘",
        true,
        true,
        None::<&str>,
    )?;
    let separator = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, "quit", "退出 eclipse health", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[&show, &hide, &separator, &close_to_tray, &separator, &quit],
    )?;

    let mut builder = TrayIconBuilder::with_id("main-tray")
        .tooltip("eclipse health")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => show_main(app),
            "hide" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.hide();
                }
            }
            "quit" => app.exit(0),
            "close_to_tray" => {
                // CheckMenuItem 会自行切换勾选状态，这里同步一份给窗口关闭逻辑使用。
                if let Some(state) = app.try_state::<CloseToTray>() {
                    let next = !state.0.load(Ordering::Relaxed);
                    state.0.store(next, Ordering::Relaxed);
                }
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main(tray.app_handle());
            }
        });

    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }
    builder.build(app)?;
    Ok(())
}

/// venv 的 python.exe 在 Windows 上是启动器，会再派生真正的解释器；
/// 只 kill 启动器会遗留 uvicorn，所以按进程树结束。
#[cfg(all(debug_assertions, target_os = "windows"))]
fn kill_dev_backend(child: &mut Child) {
    let pid = child.id().to_string();
    let _ = Command::new("taskkill")
        .args(["/PID", pid.as_str(), "/T", "/F"])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
    let _ = child.wait();
}

#[cfg(all(debug_assertions, not(target_os = "windows")))]
fn kill_dev_backend(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}

#[cfg(debug_assertions)]
fn dev_backend_reachable() -> bool {
    use std::net::{SocketAddr, TcpStream};
    use std::time::Duration;

    let addr = DEV_BACKEND_ADDR.parse::<SocketAddr>().expect("valid backend addr");
    TcpStream::connect_timeout(&addr, Duration::from_millis(250)).is_ok()
}

/// dev 下随桌面壳启动 FastAPI；退出时由 RunEvent 结束子进程。
/// 生产打包的 PyInstaller sidecar 属于 B3，这里只覆盖 `tauri dev`。
#[cfg(debug_assertions)]
fn spawn_dev_backend() -> Option<Child> {
    if dev_backend_reachable() {
        println!("[dev] backend already listening on {DEV_BACKEND_ADDR}, reusing it");
        return None;
    }
    if !std::path::Path::new(DEV_BACKEND_PYTHON).exists() {
        eprintln!("[dev] backend venv not found at {DEV_BACKEND_PYTHON}; start it manually");
        return None;
    }

    match Command::new(DEV_BACKEND_PYTHON)
        .args([
            "-m",
            "uvicorn",
            "eclipse_health_backend.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
        ])
        .current_dir(DEV_BACKEND_DIR)
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
    {
        Ok(child) => {
            println!("[dev] started backend (pid {})", child.id());
            Some(child)
        }
        Err(error) => {
            eprintln!("[dev] failed to start backend: {error}");
            None
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // 单实例插件必须最先注册：第二个实例只聚焦已有窗口。
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_main(app);
        }))
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_opener::init())
        .manage(CloseToTray(AtomicBool::new(true)))
        .manage(PageLoaded(AtomicBool::new(false)))
        .setup(|app| {
            setup_tray(app)?;

            #[cfg(debug_assertions)]
            {
                let child = spawn_dev_backend();
                app.manage(BackendProcess(Mutex::new(child)));
            }

            // 窗口默认不可见，页面加载后再显示；页面一直没加载成功时也能在 12s 后看到窗口。
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                std::thread::sleep(std::time::Duration::from_secs(12));
                let loaded = handle
                    .try_state::<PageLoaded>()
                    .map(|state| state.0.load(Ordering::Relaxed))
                    .unwrap_or(false);
                if loaded {
                    return;
                }
                if let Some(window) = handle.get_webview_window("main") {
                    let _ = window.show();
                }
            });
            Ok(())
        })
        .on_page_load(|webview, _payload| {
            if webview.label() == "main" {
                webview
                    .app_handle()
                    .state::<PageLoaded>()
                    .0
                    .store(true, Ordering::Relaxed);
                let _ = webview.window().show();
            }
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                if window.label() != "main" {
                    return;
                }
                let close_to_tray = window
                    .app_handle()
                    .try_state::<CloseToTray>()
                    .map(|state| state.0.load(Ordering::Relaxed))
                    .unwrap_or(true);
                if close_to_tray {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                #[cfg(debug_assertions)]
                if let Some(mut child) = app
                    .state::<BackendProcess>()
                    .0
                    .lock()
                    .expect("backend mutex poisoned")
                    .take()
                {
                    kill_dev_backend(&mut child);
                }
            }
        });
}
