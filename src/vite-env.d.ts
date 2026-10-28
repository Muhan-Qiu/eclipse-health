/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 后端 API 根地址，默认 http://127.0.0.1:8765/api/v1 */
  readonly VITE_API_BASE_URL?: string;
  /** "true" 时使用本地 mock 数据；dev 默认 true，build 默认 false */
  readonly VITE_USE_MOCK?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
