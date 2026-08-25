# 一二 / Sign OC2DIYChef 特别版 v{{VERSION}}

作者：**DUKEY**

![Sign 在 Overcooked! 2 中的实机效果](images/sign-in-game.png)

这是供本地单机使用的一二 `Sign` 特别版安装包。资源目录与游戏内配置名均为
`Sign`，内部联网标识仍由 `INFO` 中的 ID `174` 提供，目录名不带 `174-` 前缀。
默认不戴帽子，可选专属帽为 `SignCap`。包内还包含角色专属尾气调色 GUI，以及
已通过实机验证的
OC2DIYLevel 0.9.0 异步加载兼容插件。

## 已验证环境

- Windows Steam 标准版 Overcooked! 2（x86）
- BepInEx 5.4.22 x86（包内包含官方原版，已有兼容版本时不会覆盖）
- OC2DIYChef v1.2，固定上游提交 `93ab0554`（包内包含）
- OC2DIYChefTrailColor 0.2.2 + GUI 0.2.2，按 F10 打开
- OC2DIYLevel 0.9.0 + OC2DIYLevelAsyncLoader 0.1.0（原关卡插件需已安装）

Steam Crossplay Beta/Epic x64 版本尚未验证，不能使用本包内的 x86 BepInEx。

## 一键安装

1. 完整解压 ZIP，不要直接在压缩包内运行脚本。
2. 关闭 Overcooked! 2。
3. 把 ZIP 直接解压到含有 `Overcooked2.exe` 的游戏主目录；解压后只会新增一个
   `Sign-OC2DIYChef-Special-v{{VERSION}}` 文件夹，不要把其中的文件拆散复制出来。
4. 进入这个新文件夹，双击 `Install-Sign.bat`。

目录结构示例：

```text
Overcooked! 2/
├─ Overcooked2.exe
└─ Sign-OC2DIYChef-Special-v{{VERSION}}/
   ├─ Install-Sign.bat
   ├─ Install-Sign.ps1
   ├─ PACKAGE-VERSION.txt
   └─ payload/
```

BAT 只把安装文件夹的上一级作为游戏目录，避免装到另一个游戏副本。安装开始前会
验证 `SHA256SUMS.txt` 中列出的全部包文件，并检查游戏、BepInEx 架构和运行状态。

也可以手动运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Sign.ps1 `
  -GameDir '..'
```

## 安装内容

安装成功后的核心路径：

```text
BepInEx/plugins/OC2DIYChef/OC2DIYChef.dll
BepInEx/plugins/OC2DIYChef/Resources/Sign/
BepInEx/plugins/OC2DIYChef/Resources/HATS/SignCap/
BepInEx/plugins/OC2DIYChefTrailColor/
BepInEx/plugins/OC2HostUtilities/v1.8.0/HostUtilities.dll
BepInEx/plugins/OC2DIYLevelAsyncLoader/                # 条件安装
```

`prefer.txt` 中会保留其他角色设置，并确保一二只有这一行：

```text
Sign HAT=None
```

因此脚本安装后默认无帽。OC2DIYChef 1.2 没有自定义帽选择界面；如需启用专属帽，
关闭游戏后把上面一行改为 `Sign HAT=SignCap`，再重新启动游戏。需要恢复无帽时
改回 `Sign HAT=None`。同一角色不要保留两行配置。

一二的默认粒子校准值是 `WalkColor=C54579FF`、`DashColor=5BAC2EFF`；这两个值
已在当前游戏粒子材质下实机确认为“走路白色、冲刺浅粉色”。安装器不会覆盖已经
存在的尾气配置。按 F10 可使用调色盘分别调整每个角色，修改不会影响其他角色。

## 尾气 Utils / HostUtilities

尾气功能必须使用 HostUtilities 1.8.0 Core。安装器会先检查全体插件目录：

- 标准路径中已存在唯一且哈希匹配的 1.8.0：直接使用，不重复安装。
- 完全不存在：从上游官方 Release 下载，核对压缩包与 DLL 的固定 SHA-256 后安装。
- 默认网络失败：依次尝试 `127.0.0.1:12334` 和 `127.0.0.1:7890`。
- 存在其他版本或重复 DLL：为避免重复插件 GUID，不强制覆盖，并跳过尾气组件。

HostUtilities 上游未提供明确的再分发许可证，因此它不直接放在公开 ZIP 内，而由
一键安装器从官方地址取得。若下载失败，一二和帽子仍会完成安装。也可主动跳过：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Sign.ps1 `
  -GameDir 'D:\SteamLibrary\steamapps\common\Overcooked! 2' `
  -SkipTrailColor
```

## 异步关卡兼容插件

包内包含 DUKEY 制作的 `OC2DIYLevelAsyncLoader.dll`，但不包含 OC2DIYLevel 本体、
地图或存档。安装器仅在 `common` 存在，且以下两个 DLL 精确匹配已验证的 0.9.0
组合时启用：

```text
BepInEx/plugins/OC2DIYLevel/OC2DIYLevel.dll
SHA-256: 18387FF6923281198518D67EDDA3B8E728A4E5AA7407104E03A1F0AC82811D06
BepInEx/plugins/OC2DIYLevel/LevelEditorStub.dll
SHA-256: 28155A7CBF359D6C8900C76F369BB224971A77F3CAE74FB8846717EFBD4B15D1
```

兼容插件会在标题界面逐包异步加载，显示进度，完成后刷新“更多关卡”入口。通用正式
包默认不按名称跳过地图；如果日志已经确认一批地图的同名 `info*` AssetBundle 冲突，
可把配置中的 `SkipDuplicateInfoNames` 改为 `true`。当前已验证电脑上已有的 `true`
配置会被保留。加载失败时允许回退到原同步初始化。不匹配或未安装 OC2DIYLevel 时，
安装器会明确跳过此组件，不影响一二模型。

## 备份与回滚

安装器会把被替换的一二资源、OC2DIYChef 文件、尾气插件、异步插件和原始
`prefer.txt` 保存到：

```text
<游戏目录>/BepInEx/SignPackageBackups/<时间戳>/
```

需要回滚时先关闭游戏，再把该目录内的文件按原相对路径复制回游戏目录。

## 校验与许可

`SHA256SUMS.txt` 覆盖 ZIP 内除清单自身以外的全部文件。模型署名和第三方依赖说明
见 `THIRD_PARTY_NOTICES.md` 与 `licenses/`。本包是非官方、非商业本地 MOD；与
Ghost Town Games、Team17 或角色权利人无隶属或背书关系。
