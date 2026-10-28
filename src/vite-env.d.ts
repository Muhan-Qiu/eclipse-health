/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 后端 API 根地址，默认 http://127.0.0.1:8765/api/v1 */
  readonly VITE_API_BASE?: string;
  /** 兼容旧变量名；VITE_API_BASE 优先 */
  readonly VITE_API_BASE_URL?: string;
  /** "true" 时使用本地演示数据；默认走真实 API */
  readonly VITE_USE_MOCK?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
