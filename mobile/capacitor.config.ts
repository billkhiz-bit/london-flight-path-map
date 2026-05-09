import type { CapacitorConfig } from '@capacitor/cli';

// Sky Score Capacitor configuration.
//
// `webDir` is where Capacitor expects the static web assets to live;
// our `npm run build:web` script copies index.html, manifest, sw.js,
// icons/, js/ from the parent directory into ./www so the WebView has
// everything it needs.
//
// `appId` is the reverse-DNS identifier shared between iOS and Android
// stores. Once published, NEVER change it — Apple and Google use it as
// the immutable app identity. uk.co.skyscore.app mirrors the domain.
//
// `appName` is the display name on the home screen / app drawer.
//
// The plugins block configures the splash screen and status bar; both
// are deliberate so the first-launch experience matches the web app's
// light theme rather than Capacitor's default cyan flash.

const config: CapacitorConfig = {
  appId: 'uk.co.skyscore.app',
  appName: 'Sky Score',
  webDir: 'www',
  // Allow the WebView to reach the AWS API endpoints. Without this,
  // mixed-origin fetches from the capacitor:// scheme can be blocked.
  server: {
    androidScheme: 'https',
    cleartext: false,
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 1500,
      backgroundColor: '#e4e3e0',
      androidSplashResourceName: 'splash',
      androidScaleType: 'CENTER_CROP',
      showSpinner: false,
      splashFullScreen: true,
      splashImmersive: false,
    },
    StatusBar: {
      style: 'DEFAULT',
      backgroundColor: '#fafaf9',
      overlaysWebView: false,
    },
  },
};

export default config;
