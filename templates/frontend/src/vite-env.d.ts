/// <reference types="vite/client" />

declare global {
  interface Window {
    /** Backend base URL, injected by the care_fe host. */
    CARE_API_URL: string;
    /** The host's auth context object. React is shared, so useContext() works across the boundary. */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    AuthUserContext: React.Context<any>;
    /** The full careConfig object. */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    __CORE_ENV__: Record<string, any>;
    /** Per-plugin runtime metadata from plug_config, keyed by slug. Frozen. */
    __CARE_PLUGIN_RUNTIME__?: {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      meta: Record<string, Record<string, any>>;
    };
  }
}

export {};
