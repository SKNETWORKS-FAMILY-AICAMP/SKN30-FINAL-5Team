# Campsite Scene Editor

Temporary, web-only tooling for producing a `scene-layout.json` in the logical
1672 × 941 campsite coordinate system.

- Development URL: `/scene-editor`
- Start command: `npm.cmd run scene-editor`, then open
  `http://localhost:8082/scene-editor`
- Local persistence key: `campsite-scene-editor-layout-v1`
- Bundled asset discovery: `sceneAssets.web.ts` uses Metro `require.context()`
  for the six existing campsite PNG directories.
- Local folder discovery: `Open PNG Folder` reads every PNG in the folder and
  its descendants. Files are grouped by their relative directory. Known folder
  names (`clouds`, `leaves`, `bulbs`, `lanterns`, `flowers`, and `grass`) get
  their motion defaults; every other folder is loaded as `custom` with no
  motion.
- Background selection: click `BG` beside any listed PNG, or use
  `Choose Background PNG`. The selected `source` is exported in the layout's
  optional `background` object. Layouts exported before this field existed
  continue to use the bundled background.
- Native isolation: the files without `.web` provide empty stubs, so Android
  and iOS do not evaluate the editor registry.

Local files never leave the browser. Browser security does not let the editor
reopen a local folder after a refresh, so select the same folder before
importing a layout that references `local/...` sources. The editor keeps a
failed auto-saved layout intact and retries it as matching folders are opened.
Chrome and Edge provide the most reliable recursive folder picker support.

`scene-layout.json` is an editor artifact. The House renderer still uses its
own bundled imports and hard-coded positions; exporting a layout does not
automatically change the application backdrop.

To remove the tool later, delete this directory and the Scene Editor tests,
then remove the two Scene Editor imports and route guard from `src/app/App.tsx`.
The House implementation and campsite source assets do not depend on this
editor.
