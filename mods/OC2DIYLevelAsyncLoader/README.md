# OC2DIYLevelAsyncLoader

Author: **DUKEY**

Independent BepInEx compatibility plugin for the official OC2DIYLevel 0.9.0
runtime. It does not modify or redistribute `OC2DIYLevel.dll`.

## Behaviour

- Verifies the exact official OC2DIYLevel 0.9.0 DLL by MVID and SHA-256.
- Intercepts its synchronous `DIYLevelAssetBundleManager.Initialize()` call.
- Loads `common*` and `info*` AssetBundles serially with Unity coroutines,
  `AssetBundle.LoadFromFileAsync`, and `LoadAssetAsync`.
- Publishes OC2DIYLevel's initialized state only after all fields are ready.
- Refreshes the More Levels and Custom Arcade UI after loading completes.
- Shows a non-interactive progress panel.
- After the first `info*` file with a given name loads successfully, skips
  later same-name conflicts. If the first copy is damaged, the next copy is
  still attempted. This avoids moving level files.

## Supported dependency

- OC2DIYLevel 0.9.0, plugin GUID `dev.gua.overcooked.diylevel`
- Expected SHA-256:
  `18387FF6923281198518D67EDDA3B8E728A4E5AA7407104E03A1F0AC82811D06`
- BepInEx 5.4.22 x86 / Overcooked! 2

If compatibility validation fails, this plugin does not intercept anything and
the original synchronous initializer remains active.

## Configuration

Configuration is written to:

```text
BepInEx/config/dukey.oc2.diylevel.asyncloader.cfg
```

Defaults:

- `PreloadOnStartup = true`
- `ShowProgress = true`
- `SkipDuplicateInfoNames = false`
- `FallbackToSynchronous = true`

## Limitations

`SkipDuplicateInfoNames` is intentionally disabled by the plugin's code default
and the Yier v1.0.0 release configuration. Enable it only when logs have
confirmed that same-name bundles conflict. The current tested installation
keeps it enabled because all 11 same-name groups there were already confirmed
by Unity's AssetBundle errors.

Asynchronous loading removes the long continuous main-thread stall but does not
remove the final memory cost of successfully loaded level bundles. Legacy level
packs use large LZMA AssetBundles, so individual completion frames can still
show a short hitch. Different versions using the same `info*` bundle name still
cannot coexist; the first directory returned by the original enumeration wins.

Remove `OC2DIYLevelAsyncLoader.dll` to restore OC2DIYLevel's original behaviour.
