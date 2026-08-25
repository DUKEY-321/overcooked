# OC2DIYChefTrailColor

Character-specific running-smoke and dash-trail colours for the local
Overcooked! 2 `OC2DIYChef` setup.

The core plugin extends the already-installed HostUtilities 1.8.0 particle
colour path. It does not modify game asset bundles or shared materials.

The optional GUI plugin opens with `F10` and provides a searchable, scrollable
character selector, separate running/dash controls, an HSV palette, RGB
sliders, HEX input, live preview and explicit persistence.

## Character profiles

- All 61 official chefs listed by the installed OC2DIYChef build are available.
- Every DIY chef found below `OC2DIYChef\Resources` is available.
- New characters encountered at runtime are added automatically.
- Profiles other than Sign are disabled by default, so their original
  HostUtilities/game colours are preserved until the user enables or edits
  them in the GUI.
- The special character resource is `Sign` with ID `174`. It uses
  `[Character.Sign]`, while its stable runtime identity remains
  `diy:174:Chef_Sign`.

Character identity is persistent across sessions: official chefs use their
`ChefAvatarData.HeadName`, while DIY chefs use their resource ID and HeadName.

## Build

```powershell
& 'F:\64gram_workplace\BuildTools2022\MSBuild\Current\Bin\MSBuild.exe' `
  '.\Core\OC2DIYChefTrailColor.csproj' `
  /t:Rebuild /p:Configuration=Release /p:Platform=AnyCPU /m
```

The project targets .NET Framework 3.5 and references the installed game's
assemblies without copying them into the output directory.

Build the GUI after the core:

```powershell
& 'F:\64gram_workplace\BuildTools2022\MSBuild\Current\Bin\MSBuild.exe' `
  '.\GUI\OC2DIYChefTrailColorGUI.csproj' `
  /t:Rebuild /p:Configuration=Release /p:Platform=AnyCPU /m
```
