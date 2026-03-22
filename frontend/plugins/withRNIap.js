const { withAppBuildGradle } = require('@expo/config-plugins');

const withRNIap = (config) => {
  return withAppBuildGradle(config, (config) => {
    const buildGradle = config.modResults.contents;

    if (!buildGradle.includes("missingDimensionStrategy")) {
      config.modResults.contents = buildGradle.replace(
        /defaultConfig\s*\{/,
        `defaultConfig {\n        missingDimensionStrategy 'store', 'play'`
      );
    }

    return config;
  });
};

module.exports = withRNIap;
