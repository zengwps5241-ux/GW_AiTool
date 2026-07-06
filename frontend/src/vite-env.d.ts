/// <reference types="vite/client" />

interface ImportMetaEnv {
  // 不再使用编译时认证模式变量
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
