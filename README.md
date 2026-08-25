# Overcooked! 2 DIY Chef 工作区

这个仓库用于制作“一二”和“布布”的 `OC2DIYChef` 资源。目前发布的是一二
v004 非商业测试版：角色 ID 为 `174`，默认帽子为 `YierCap`，并可选安装
角色专属走路/冲刺尾气颜色 GUI。

## 下载与安装

请从 [GitHub Releases](https://github.com/DUKEY-321/overcooked/releases)
下载最新的 `Yier-OC2DIYChef-*.zip`，完整解压后关闭游戏。把解压目录内的全部文件
复制到含有 `Overcooked2.exe` 的游戏主目录，然后双击：

```text
Install-Yier.bat
```

批处理会确认当前目录就是 Overcooked! 2 主目录，再调用安装器。也可以手动运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Yier.ps1 `
  -GameDir 'D:\SteamLibrary\steamapps\common\Overcooked! 2'
```

测试包面向 Windows Steam 标准版（x86），内含 BepInEx 5.4.22 x86、固定版本的
OC2DIYChef、一二角色、`YierCap` 和尾气插件。HostUtilities 1.8.0 因上游未提供
可再分发许可证，不直接放进 Release；安装器会从上游官方地址下载并校验 SHA-256。
若不需要尾气功能，可添加 `-SkipTrailColor`，角色和帽子仍可正常安装。

安装器会备份已有 `prefer.txt` 和所有将被替换的文件，不会覆盖其他厨师的帽子配置。
安装后 `prefer.txt` 中只保留一条 `174-yier HAT=YierCap`。F10 打开尾气颜色 GUI。

Steam Crossplay Beta/Epic x64 版本尚未验证。

## 目录

```text
assets/
  source_yier/           一二的原始下载包与原样解压文件（只读留档）
blender/                 Blender 初始化和只读验收脚本，不存放生成的 .blend
characters/
  yier/                  一二：Blender 源文件、人工参考图/链接和工作贴图
  bubu/                  布布：Blender 源文件、人工参考图/链接和工作贴图
exports/Resources/      通过检查后，待复制到 OC2DIYChef/Resources 的资源包
templates/              INFO 与资源目录清单模板
LICENSES/               来源、许可和署名记录
scripts/                只读资源校验脚本
packaging/yier/         一二 Release 的安装器、说明和默认配置
tools/                  本机 Blender 便携环境与官方校验文件（运行时不提交）
```

## 文件流转约定

1. 已下载的共同 Sketchfab 场景同时包含一二和布布，原件及原样解压文件固定放在 `assets/source_yier/` 作为只读留档；只有将来取得另一份独立布布源文件时才新建 `assets/source_bubu/`。
2. 人工收集的正/侧/背面参考图、网页链接和来源清单放进 `characters/<角色>/references/`，不要在这里重复存模型下载包。
3. `blender/` 只放自动化脚本。共同导入留档为 `characters/yier/source/yier_prototype.blend`；按角色分离后的里程碑使用 `characters/<角色>/source/<角色>_work-vNNN.blend`。一二当前产出基线为 `yier_work-v004.blend`，布布仍冻结在 `bubu_work-v002.blend`；旧版本保留为恢复点。
4. 烘焙前的 PSD/KRA/源贴图放在 `characters/<角色>/textures/`。
5. Blender 导出的 OBJ、PNG、材质 TXT 和 `INFO` 只放在 `exports/Resources/<资源包名>/`；自定义帽放在 `exports/Resources/HATS/<帽名>/`。名称应稳定且只使用 ASCII，例如 `174-yier` 和 `YierCap`。
6. ID 必须先和已安装资源检查冲突，再写入 `INFO`。`0..63` 为 AYCE 保留，建议从 `64..254` 中选择未占用值。
7. 只有严格校验通过的资源包才进入 Release；`Install-Yier.bat` 只负责检查游戏目录并调用 `Install-Yier.ps1`，实际写入前安装器会备份受影响文件。

不要修改 `assets/source_*` 中的下载原件。初始化脚本会把源模型导入 `.blend`；在 `.blend` 内保留一个未经减面、拆件的原始 Collection，再复制出工作 Collection，便于回滚。下载压缩包默认被 Git 忽略，需另行备份并在来源清单记录 SHA-256。

## OC2DIYChef 最小资源包

最少需要以下文件，文件名保持完全一致：

```text
INFO
Head.obj
Hand_Grip_L.obj
Hand_Grip_R.obj
Hand_Open_L.obj
Hand_Open_R.obj
t_Head.png
m_Head.txt
```

可选 OBJ 名称见 [templates/OC2DIYChef-resource/README.md](templates/OC2DIYChef-resource/README.md)。不要把 `.blend`、FBX、MTL 或参考图放进最终资源包。

一二 v004 的蓝帽使用插件要求的独立结构：

```text
HATS/YierCap/
  YierCap.obj
  t_YierCap.png
  m_YierCap.txt
```

插件 1.2 只通过 `prefer.txt` 固定角色帽子，不提供独立帽子选择界面。一二发布包默认使用 `174-yier HAT=YierCap`；同一角色不能同时保留两行。

## 校验

在工作区根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Test-OC2DIYChefResource.ps1
```

发布前使用严格模式，并显式提供现有资源目录做 ID 冲突检查：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Test-OC2DIYChefResource.ps1 `
  -RequirePackages `
  -ExistingResourcesPath 'D:\SteamLibrary\steamapps\common\Overcooked! 2\BepInEx\plugins\OC2DIYChef\Resources'
```

也可以只检查一个资源包：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Test-OC2DIYChefResource.ps1 `
  -Path '.\exports\Resources\174-yier' -RequirePackages
```

自定义帽使用单独的严格校验器：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Test-OC2DIYChefHat.ps1 `
  -Path '.\exports\Resources\HATS\YierCap' -RequireHats
```

校验器只读文件并返回退出码：`0` 表示无错误，`1` 表示存在错误。默认空工程是合法初始化状态；加 `-RequirePackages` 后，未发现资源包会报错。

## 发布前清单

- Blender 中应用 Rotation/Scale，并逐件确认原点、法线、UV 和左右手方向。
- 每个 OBJ 使用允许的精确文件名；面角展开数必须低于 16 位索引上限。
- `t_Head.png`/`t_Body.png` 优先使用 512×512 PNG；需要厨师颜色替换的身体区域必须保留 Alpha。
- `INFO` 中只有一个严格格式的 `ID=<整数>`。
- 在 `LICENSES/` 完成模型、纹理、角色形象和参考素材的许可/署名记录。
- 实机验证选人、眨眼、开合手、跑动、冲刺、拿取、切菜、投掷和炮台/背包遮挡。

规范依据：OC2DIYChef 上游 README 与其 `DIYChefCustomisation.cs` 中的部件白名单。上游项目：<https://github.com/gua248/Overcooked2-DIYChef>。

## 许可证

本仓库原创代码和脚本使用 [MIT License](LICENSE)。一二模型和帽子来自
Sketchfab 上传者小王子（`hong2695429209`）发布的 CC BY 4.0 模型，完整署名、
修改说明与第三方依赖见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和
[LICENSES](LICENSES/)。这是非官方、非商业测试 MOD；MIT 不覆盖第三方模型、
角色形象、游戏资产或商标。
