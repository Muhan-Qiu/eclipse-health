use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tauri::{
    menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, RunEvent, WindowEvent,
};

#[cfg(all(target_os = "windows", not(debug_assertions)))]
use std::os::windows::process::CommandExt;

/// 关闭窗口时收起到托盘（默认开启），托盘菜单与前端命令都可切换。
struct CloseToTray(AtomicBool);

/// 页面是否已经加载过；用于区分“首帧未显示”和“用户主动藏到托盘”。
struct PageLoaded(AtomicBool);

struct BackendProcess(Mutex<Option<Child>>);

/// 持久化的桌面偏好，供 B4-04 设置页通过 `invoke` 读写。
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct DesktopSettings {
    close_to_tray: bool,
    splash_enabled: bool,
}

impl Default for DesktopSettings {
    fn default() -> Self {
        Self {
            close_to_tray: true,
            splash_enabled: true,
        }
    }
}

struct DesktopPrefs(Mutex<DesktopSettings>);

/// 托盘里的“关闭时收起到托盘”勾选项，命令改设置时同步勾选状态。
struct TrayCloseItem(Mutex<Option<CheckMenuItem<tauri::Wry>>>);

const BACKEND_ADDR: &str = "127.0.0.1:8765";
const HEALTH_PATH: &str = "/api/v1/health";
const SETTINGS_FILE: &str = "desktop-settings.json";

#[cfg(all(target_os = "windows", not(debug_assertions)))]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[cfg(debug_assertions)]
const DEV_BACKEND_DIR: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../backend");
#[cfg(debug_assertions)]
const DEV_BACKEND_PYTHON: &str =
    concat!(env!("CARGO_MANIFEST_DIR"), "/../backend/.venv/Scripts/python.exe");

#[cfg(not(debug_assertions))]
const SIDECAR_NAME: &str = "eclipse-health-backend.exe";

// --------------------------------------------------------------------------- 基础设施
fn show_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn backend_reachable() -> bool {
    let addr = BACKEND_ADDR.parse::<SocketAddr>().expect("valid backend addr");
    TcpStream::connect_timeout(&addr, Duration::from_millis(250)).is_ok()
}

/// 用最小 HTTP 请求确认 8765 上的是我们自己的后端（而不是别的进程占着端口）。
#[cfg_attr(debug_assertions, allow(dead_code))]
fn backend_healthy() -> bool {
    let Ok(mut stream) = TcpStream::connect_timeout(
        &BACKEND_ADDR.parse::<SocketAddr>().expect("valid backend addr"),
        Duration::from_millis(500),
    ) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(1500)));
    let request = format!(
        "GET {HEALTH_PATH} HTTP/1.1\r\nHost: {BACKEND_ADDR}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut buffer = [0u8; 64];
    let read = stream.read(&mut buffer).unwrap_or(0);
    String::from_utf8_lossy(&buffer[..read]).contains(" 200 ")
}

/// venv 的 python.exe 在 Windows 上是启动器，会再派生真正的解释器；
/// 只 kill 启动器会遗留 uvicorn/worker，所以按进程树结束。
fn kill_process_tree(child: &mut Child) {
    let pid = child.id().to_string();
    let _ = Command::new("taskkill")
        .args(["/PID", pid.as_str(), "/T", "/F"])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
    let _ = child.wait();
}

fn settings_path(app: &AppHandle) -> Option<PathBuf> {
    app.path()
        .app_config_dir()
        .ok()
        .map(|dir| dir.join(SETTINGS_FILE))
}

fn load_desktop_settings(app: &AppHandle) -> DesktopSettings {
    let Some(path) = settings_path(app) else {
        return DesktopSettings::default();
    };
    match std::fs::read_to_string(&path) {
        Ok(text) => serde_json::from_str(&text).unwrap_or_default(),
        Err(_) => DesktopSettings::default(),
    }
}

fn store_desktop_settings(app: &AppHandle, settings: &DesktopSettings) {
    let Some(path) = settings_path(app) else {
        return;
    };
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(text) = serde_json::to_string_pretty(settings) {
        let _ = std::fs::write(path, text);
    }
}

fn update_settings<F: FnOnce(&mut DesktopSettings)>(app: &AppHandle, mutate: F) -> DesktopSettings {
    let state = app.state::<DesktopPrefs>();
    let mut guard = state.0.lock().expect("settings mutex poisoned");
    mutate(&mut guard);
    let snapshot = guard.clone();
    drop(guard);
    store_desktop_settings(app, &snapshot);
    snapshot
}

// --------------------------------------------------------------------------- 托盘
fn setup_tray(app: &mut tauri::App, close_to_tray: bool) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, "show", "显示主窗口", true, None::<&str>)?;
    let hide = MenuItem::with_id(app, "hide", "隐藏到托盘", true, None::<&str>)?;
    let close_item = CheckMenuItem::with_id(
        app,
        "close_to_tray",
        "关闭窗口时收起到托盘",
        true,
        close_to_tray,
        None::<&str>,
    )?;
    let separator = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, "quit", "退出 eclipse health", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[&show, &hide, &separator, &close_item, &separator, &quit],
    )?;

    if let Some(state) = app.try_state::<TrayCloseItem>() {
        *state.0.lock().expect("tray item mutex poisoned") = Some(close_item.clone());
    }

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
                // CheckMenuItem 会自行切换勾选状态，这里读取新值并持久化。
                let next = app
                    .try_state::<TrayCloseItem>()
                    .and_then(|state| {
                        state
                            .0
                            .lock()
                            .ok()
                            .and_then(|guard| guard.as_ref().map(|item| item.is_checked().unwrap_or(true)))
                    })
                    .unwrap_or(true);
                if let Some(state) = app.try_state::<CloseToTray>() {
                    state.0.store(next, Ordering::Relaxed);
                }
                update_settings(app, |settings| settings.close_to_tray = next);
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

// --------------------------------------------------------------------------- 后端（dev）
#[cfg(debug_assertions)]
fn spawn_backend() -> Option<Child> {
    if backend_reachable() {
        println!("[dev] backend already listening on {BACKEND_ADDR}, reusing it");
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

// --------------------------------------------------------------------------- 后端（release）
#[cfg(not(debug_assertions))]
fn sidecar_path() -> Option<PathBuf> {
    let exe_dir = std::env::current_exe().ok()?.parent()?.to_path_buf();
    Some(exe_dir.join(SIDECAR_NAME))
}

#[cfg(not(debug_assertions))]
fn production_data_dir(app: &AppHandle) -> Option<PathBuf> {
    if let Some(base) = std::env::var_os("LOCALAPPDATA") {
        return Some(PathBuf::from(base).join("eclipse-health"));
    }
    app.path()
        .data_dir()
        .ok()
        .map(|dir| dir.join("eclipse-health"))
}

#[cfg(not(debug_assertions))]
fn spawn_backend(app: &AppHandle) -> Option<Child> {
    if backend_reachable() {
        if backend_healthy() {
            println!("[prod] backend already healthy on {BACKEND_ADDR}, reusing it");
            return None;
        }
        eprintln!(
            "[prod] port {BACKEND_ADDR} is occupied by another process; analytics may fail to start"
        );
    }

    let Some(sidecar) = sidecar_path() else {
        eprintln!("[prod] cannot resolve sidecar path");
        return None;
    };
    if !sidecar.is_file() {
        eprintln!("[prod] sidecar not found at {}", sidecar.display());
        return None;
    }
    let Some(data_dir) = production_data_dir(app) else {
        eprintln!("[prod] cannot resolve %LOCALAPPDATA% for the data directory");
        return None;
    };

    let mut command = Command::new(&sidecar);
    command
        .arg("--port")
        .arg("8765")
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--data-dir")
        .arg(&data_dir)
        .env("EH_DATA_DIR", &data_dir)
        .env("EH_PORT", "8765")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(target_os = "windows")]
    command.creation_flags(CREATE_NO_WINDOW);

    match command.spawn() {
        Ok(child) => {
            println!(
                "[prod] started sidecar (pid {}) data={}",
                child.id(),
                data_dir.display()
            );
            Some(child)
        }
        Err(error) => {
            eprintln!("[prod] failed to start sidecar: {error}");
            None
        }
    }
}

/// release：健康检查通过后再显示主窗口；最多等 90 秒，超时也显示（让用户看到错误态）。
#[cfg(not(debug_assertions))]
fn wait_for_backend_then_show(handle: AppHandle) {
    std::thread::spawn(move || {
        let started = std::time::Instant::now();
        loop {
            if backend_healthy() {
                println!("[prod] backend healthy after {}ms", started.elapsed().as_millis());
                show_main(&handle);
                return;
            }
            if started.elapsed() > Duration::from_secs(90) {
                eprintln!("[prod] backend not healthy after 90s; showing window anyway");
                show_main(&handle);
                return;
            }
            std::thread::sleep(Duration::from_millis(250));
        }
    });
}

// --------------------------------------------------------------------------- 命令
#[tauri::command]
fn get_desktop_settings(app: AppHandle) -> DesktopSettings {
    app.state::<DesktopPrefs>()
        .0
        .lock()
        .expect("settings mutex poisoned")
        .clone()
}

#[tauri::command]
fn set_close_to_tray(app: AppHandle, enabled: bool) -> DesktopSettings {
    if let Some(state) = app.try_state::<CloseToTray>() {
        state.0.store(enabled, Ordering::Relaxed);
    }
    if let Some(state) = app.try_state::<TrayCloseItem>() {
        if let Ok(guard) = state.0.lock() {
            if let Some(item) = guard.as_ref() {
                let _ = item.set_checked(enabled);
            }
        }
    }
    update_settings(&app, |settings| settings.close_to_tray = enabled)
}

#[tauri::command]
fn set_splash_enabled(app: AppHandle, enabled: bool) -> DesktopSettings {
    update_settings(&app, |settings| settings.splash_enabled = enabled)
}

// --------------------------------------------------------------------------- 入口
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // 单实例插件必须最先注册：第二个实例只聚焦已有窗口。
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_main(app);
        }))
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(CloseToTray(AtomicBool::new(true)))
        .manage(PageLoaded(AtomicBool::new(false)))
        .manage(TrayCloseItem(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            get_desktop_settings,
            set_close_to_tray,
            set_splash_enabled
        ])
        .setup(|app| {
            let settings = load_desktop_settings(app.handle());
            app.manage(DesktopPrefs(Mutex::new(settings.clone())));
            app.state::<CloseToTray>()
                .0
                .store(settings.close_to_tray, Ordering::Relaxed);
            setup_tray(app, settings.close_to_tray)?;

            #[cfg(debug_assertions)]
            let child = spawn_backend();
            #[cfg(not(debug_assertions))]
            let child = spawn_backend(app.handle());
            app.manage(BackendProcess(Mutex::new(child)));

            #[cfg(not(debug_assertions))]
            wait_for_backend_then_show(app.handle().clone());

            // dev 仍按页面加载显示窗口；release 由健康检查线程负责。
            // 页面一直没加载成功时也能在 12 秒后看到窗口（README/托盘仍可操作）。
            #[cfg(debug_assertions)]
            {
                let handle = app.handle().clone();
                std::thread::spawn(move || {
                    std::thread::sleep(Duration::from_secs(12));
                    let loaded = handle
                        .try_state::<PageLoaded>()
                        .map(|state| state.0.load(Ordering::Relaxed))
                        .unwrap_or(false);
                    if loaded {
                        return;
                    }
                    show_main(&handle);
                });
            }
            Ok(())
        })
        .on_page_load(|webview, _payload| {
            if webview.label() == "main" {
                webview
                    .app_handle()
                    .state::<PageLoaded>()
                    .0
                    .store(true, Ordering::Relaxed);
                #[cfg(debug_assertions)]
                {
                    let _ = webview.window().show();
                }
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
                if let Some(mut child) = app
                    .state::<BackendProcess>()
                    .0
                    .lock()
                    .expect("backend mutex poisoned")
                    .take()
                {
                    kill_process_tree(&mut child);
                }
            }
        });
}
