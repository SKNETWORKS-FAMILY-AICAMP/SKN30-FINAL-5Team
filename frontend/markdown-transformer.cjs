// Bundle the policy source verbatim so native and web show the same document.
const { getDefaultConfig } = require('expo/metro-config');
const upstream = require(
  getDefaultConfig(__dirname).transformer.babelTransformerPath,
);

module.exports.transform = (args) =>
  upstream.transform(
    args.filename.endsWith('.md')
      ? { ...args, src: `module.exports = ${JSON.stringify(args.src)};` }
      : args,
  );
