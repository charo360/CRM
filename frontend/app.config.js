export default {
  expo: {
    name: "Zilo",
    slug: "zilo",
    version: "1.0.0",
    orientation: "portrait",
    runtimeVersion: {
      policy: "appVersion"
    },
    updates: {
      url: "https://u.expo.dev/a548a1a8-7dac-4a37-9a14-9b7667ccd1dc",
      enabled: true,
      checkAutomatically: "ON_LOAD",
      fallbackToCacheTimeout: 0
    },
    icon: "./assets/images/icon.png",
    scheme: "zilo",
    userInterfaceStyle: "automatic",
    newArchEnabled: true,
    ios: {
      bundleIdentifier: "com.zilo.reply",
      supportsTablet: true,
      infoPlist: {
        NSContactsUsageDescription: "Import customers from your contacts"
      }
    },
    android: {
      package: "com.zilo.reply",
      versionCode: 10,
      adaptiveIcon: {
        foregroundImage: "./assets/images/adaptive-icon.png",
        backgroundColor: "#2DB843"
      },
      edgeToEdgeEnabled: true,
      softwareKeyboardLayoutMode: "resize",
      permissions: ["android.permission.READ_CONTACTS"]
    },
    web: {
      bundler: "metro",
      output: "static",
      favicon: "./assets/images/favicon.png"
    },
    plugins: [
      "expo-router",
      "expo-font",
      "expo-web-browser",
      "@react-native-community/datetimepicker",
      [
        "expo-splash-screen",
        {
          image: "./assets/images/splash-image.png",
          imageWidth: 200,
          resizeMode: "contain",
          backgroundColor: "#2DB843"
        }
      ],
      [
        "expo-contacts",
        {
          contactsPermission: "Allow Zilo to access your contacts to import customers."
        }
      ],
      [
        "expo-notifications",
        {
          icon: "./assets/images/icon.png",
          color: "#25D366",
          sounds: []
        }
      ]
    ],
    experiments: {
      typedRoutes: true
    },
    extra: {
      backendUrl: process.env.EXPO_PUBLIC_BACKEND_URL || "https://crm-1-pnfo.onrender.com",
      eas: {
        projectId: "a548a1a8-7dac-4a37-9a14-9b7667ccd1dc"
      }
    }
  }
};
