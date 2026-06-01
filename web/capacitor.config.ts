import type { CapacitorConfig } from "@capacitor/cli";

// Set CAPACITOR_SERVER_URL env var to override the server URL at build time.
// For development: http://<your-local-ip>:3000
// For production: https://your-deployed-app.vercel.app
const serverUrl = process.env.CAPACITOR_SERVER_URL;

const config: CapacitorConfig = {
  appId: "com.trove.app",
  appName: "Trove",
  // webDir is required by Capacitor CLI.
  // In hosted mode (server.url set), the WebView loads from the remote URL.
  // We point to "public" (always exists) so that `cap sync` never errors.
  webDir: "public",
  server: serverUrl
    ? {
        url: serverUrl,
        cleartext: serverUrl.startsWith("http://"), // allow HTTP for local dev
      }
    : undefined,
  plugins: {
    Keyboard: {
      // Resize the WebView body when keyboard appears/disappears.
      // This keeps the chat input visible above the keyboard.
      resize: "body",
      resizeOnFullScreen: true,
    },
    StatusBar: {
      // Dark-text status bar (suits Trove light header, or adapt for dark theme).
      // overlaysWebView: false → status bar does NOT overlap WebView content.
      style: "Dark",
      overlaysWebView: false,
      backgroundColor: "#131316", // --bg-canvas dark
    },
    App: {
      // No special config — default back-button behaviour on Android is fine.
    },
  },
};

export default config;
