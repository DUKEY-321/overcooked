# Third-party notices

## Mod author

**Author: DUKEY**

The original installer, OC2DIYChef adaptation work, packaging scripts,
`OC2DIYChefTrailColor` plugins and `OC2DIYLevelAsyncLoader` compatibility plugin
in this project are produced and maintained by DUKEY. Third-party models and
dependencies remain credited to their respective authors below.

## Sign character / Yier source model

The released `Sign` character meshes, textures and `SignCap` are adapted from the
Sketchfab model **“表情包的一二布布Yier”**, uploaded by **小王子**
(`hong2695429209`):

<https://sketchfab.com/3d-models/yier-b15f13be61224129ba3123c0041206c2>

The source model is offered under the
[Creative Commons Attribution 4.0 International license](https://creativecommons.org/licenses/by/4.0/).
This project modified it by cleaning and separating meshes, reducing or
rebuilding game-facing geometry, creating OC2DIYChef body/hand/blink parts,
adjusting UVs and textures, aligning scale and origins, and separating the cap
as `SignCap`.

CC BY 4.0 applies to the licensed model file. The repository does not claim
that the uploader or this project owns every underlying right in the “一二和布布”
character design. No trademark, character-merchandising, endorsement or other
right is granted by this repository.

## OC2DIYChef

The release package includes `OC2DIYChef.dll` from commit `93ab0554` of
[gua248/Overcooked2-DIYChef](https://github.com/gua248/Overcooked2-DIYChef/tree/93ab0554),
distributed under its MIT license. The upstream license text is included in
the release package.

## BepInEx

The complete release package includes the official x86 build of
[BepInEx 5.4.22](https://github.com/BepInEx/BepInEx/releases/tag/v5.4.22).
Its license and bundled-component notices are retained in the package.

## HostUtilities

`OC2DIYChefTrailColor` depends on HostUtilities 1.8.0. Because the
HostUtilities release repository does not provide a redistributable license,
its DLL is not included in the public ZIP. When the required version is not
already installed, the one-click installer downloads the official Core archive
from the author's release page and verifies both the archive and DLL with
pinned SHA-256 values before enabling the trail-colour plugins.

## OC2DIYLevel

`OC2DIYLevelAsyncLoader` is an independent compatibility plugin for the exact
0.9.0 build of
[gua248/Overcooked2-LevelEditor](https://github.com/gua248/Overcooked2-LevelEditor/releases/tag/v0.9).
It does not modify or redistribute `OC2DIYLevel.dll`, `LevelEditorStub.dll`,
custom level bundles or custom-level save files. No explicit redistribution
license for the OC2DIYLevel runtime was found in the upstream repository, so
users must obtain and install it separately. The installer activates the async
compatibility plugin only after verifying the supported original DLL hash.

## Game trademarks and assets

Overcooked! 2 is owned by its respective rights holders. This is an unofficial,
non-commercial fan-made mod and is not affiliated with or endorsed by
Ghost Town Games, Team17, Sketchfab, or the original character-IP owner. No
game executable, `Assembly-CSharp.dll`, Unity runtime, or extracted game asset
is included. The README's in-game screenshot is included only to illustrate the
mod and remains subject to the game rights holders' rights; the project's MIT
license does not cover the game imagery shown in it.
