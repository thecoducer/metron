import js from "@eslint/js";

const browserGlobals = {
    window: "readonly",
    document: "readonly",
    console: "readonly",
    fetch: "readonly",
    setTimeout: "readonly",
    clearTimeout: "readonly",
    setInterval: "readonly",
    clearInterval: "readonly",
    navigator: "readonly",
    location: "readonly",
    history: "readonly",
    localStorage: "readonly",
    sessionStorage: "readonly",
    URLSearchParams: "readonly",
    URL: "readonly",
    Promise: "readonly",
    MutationObserver: "readonly",
    IntersectionObserver: "readonly",
    ResizeObserver: "readonly",
    CustomEvent: "readonly",
    Event: "readonly",
    EventTarget: "readonly",
    AbortController: "readonly",
    FormData: "readonly",
    requestAnimationFrame: "readonly",
    cancelAnimationFrame: "readonly",
    getComputedStyle: "readonly",
    matchMedia: "readonly",
    alert: "readonly",
    confirm: "readonly",
    crypto: "readonly",
    Response: "readonly",
    Request: "readonly",
    Headers: "readonly",
    performance: "readonly",
    BroadcastChannel: "readonly",
};

const serviceWorkerGlobals = {
    self: "readonly",
    caches: "readonly",
    clients: "readonly",
    skipWaiting: "readonly",
    importScripts: "readonly",
    indexedDB: "readonly",
    fetch: "readonly",
    console: "readonly",
    addEventListener: "readonly",
    Promise: "readonly",
    URL: "readonly",
    Response: "readonly",
    Request: "readonly",
};

// Classic script files (no import/export, var declarations are expected legacy)
const legacyScriptFiles = [
    "app/static/js/exposure.js",
    "app/static/js/refresh-ui.js",
    "app/static/js/portfolio-ui.js",
    "app/static/js/nav.js",
    "app/static/js/pwa-install.js",
];

export default [
    js.configs.recommended,
    {
        // ES module JS files (use import/export)
        files: ["app/static/js/**/*.js"],
        ignores: legacyScriptFiles,
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: "module",
            globals: {
                ...browserGlobals,
                // Loaded as <script> before ES modules in HTML templates
                RefreshUI: "readonly",
            },
        },
        rules: {
            "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
            "no-console": "off",
            "eqeqeq": ["error", "always"],
            "no-var": "error",
            "prefer-const": "warn",
        },
    },
    {
        // Legacy script-style JS files (no import/export)
        files: legacyScriptFiles,
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: "script",
            globals: {
                ...browserGlobals,
                // Formatter is loaded as a global via <script> tag in some pages
                Formatter: "readonly",
            },
        },
        rules: {
            "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
            "no-console": "off",
            "eqeqeq": ["error", "always"],
            "no-var": "warn",
            "prefer-const": "warn",
        },
    },
    {
        // Service worker
        files: ["app/static/service-worker.js"],
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: "script",
            globals: serviceWorkerGlobals,
        },
        rules: {
            "no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
            "no-console": "off",
            "eqeqeq": ["error", "always"],
            "no-var": "warn",
            "prefer-const": "warn",
        },
    },
];
