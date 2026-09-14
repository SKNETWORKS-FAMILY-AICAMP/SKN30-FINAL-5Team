const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);
config.resolver.sourceExts.push('md');
config.transformer.babelTransformerPath =
  require.resolve('./markdown-transformer.cjs');
module.exports = config;
