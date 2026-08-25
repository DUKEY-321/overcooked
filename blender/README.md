# 一二 / 布布 Blender 原型初始化

入口脚本：`F:\dev\overcooke\blender\init_yier_prototype.py`

脚本只读取下面的现有厨师资源，并将网格及可读取贴图打包进新 `.blend`；它不会写入或修改 D 盘：

`D:\SteamLibrary\steamapps\common\Overcooked! 2\BepInEx\plugins\OC2DIYChef\Resources\171-pinkpig`

## 初始化前

1. 如果已经下载 Sketchfab 的一二模型，优先使用 glTF/GLB，将下载包解压到：
   `F:\dev\overcooke\assets\source_yier`
2. 该目录为空也可以初始化，之后在 Blender 中把源模型导入 `SOURCE_YIER`。
3. 确认 `F:\dev\overcooke\characters\yier\source\yier_prototype.blend` 不存在。脚本绝不覆盖同名文件。
4. 初始化脚本故意禁止在交互式 Blender 窗口运行，只允许下面的 `--background --factory-startup` 隔离方式；这样不会清空用户正在编辑的场景。

本项目已经校验并解压 Blender 5.2.0 便携版。可以从 PowerShell 先在隔离的后台进程生成文件：

```powershell
& 'F:\dev\overcooke\tools\blender-5.2.0-windows-x64\blender.exe' `
  --background --factory-startup `
  --python 'F:\dev\overcooke\blender\init_yier_prototype.py'
```

生成后运行只读结构验收：

```powershell
& 'F:\dev\overcooke\tools\blender-5.2.0-windows-x64\blender.exe' `
  --background 'F:\dev\overcooke\characters\yier\source\yier_prototype.blend' `
  --python 'F:\dev\overcooke\blender\verify_yier_prototype.py'
```

两步都通过后，再双击 `.blend` 或用该便携版打开进行编辑。首次运行新下载的软件前应由使用者确认。

## 当前可编辑基线

共同 GLB 已确认同时包含一二和布布。当前里程碑为：

- `F:\dev\overcooke\characters\yier\source\yier_work-v004.blend`（一二默认无帽与可选蓝帽）
- `F:\dev\overcooke\characters\bubu\source\bubu_work-v002.blend`

`v001` 是分离、对齐后的恢复点；`v002` 是拆件前恢复点；`v003` 是蓝帽仍合并在 Head 的完整首版。一二 `v004` 已将蓝帽转换到官方 HatBase 局部坐标并输出独立 HATS 资源。不要直接在共同导入留档 `yier_prototype.blend` 上做部件拆分。

一二 v004 的只读结构与 OBJ 往返验收：

```powershell
& 'F:\dev\overcooke\tools\blender-5.2.0-windows-x64\blender.exe' `
  --background 'F:\dev\overcooke\characters\yier\source\yier_work-v004.blend' `
  --python 'F:\dev\overcooke\blender\verify_yier_v004_optional_hat.py' `
  -- --resources-root 'F:\dev\overcooke\exports\Resources'
```

可随时在独立后台进程中重新验收，例如：

```powershell
& 'F:\dev\overcooke\tools\blender-5.2.0-windows-x64\blender.exe' `
  --background 'F:\dev\overcooke\characters\yier\source\yier_work-v002.blend' `
  --python 'F:\dev\overcooke\blender\verify_character_workspace.py' `
  -- --character YIER --revision v002
```

把 `YIER` 和文件名替换为 `BUBU` / `bubu_work-v002.blend` 即可验收布布。验收脚本只读，不保存场景。

## 生成内容

- `REF_EXISTING`：从 `171-pinkpig` 导入的成功样本。默认隐藏、禁止选择、禁止渲染；只需在 Outliner 切换显示器图标来比对比例。
- `SOURCE_YIER`：一二原始模型、清理、减面和重拓扑工作区。脚本会递归查找源文件，优先级依次为 GLB、glTF、FBX、OBJ、DAE，避免同一模型的多个下载格式重复导入。当前下载包中的 `original_dae_download\model\temp_export.dae` 会作为兜底源；若 Blender 没有 Collada 导入器，改用 Sketchfab GLB，或先启用官方 Collada 扩展。
- `EXPORT_PARTS`：只放最终可导出的游戏网格。
- `OPTIONAL_HATS`：HatBase 局部坐标的可选帽导出网格；发布名为 `YierCap`。旧 v004 工作区内部仍可能保留历史名 `YierBlueCap`，验证器同时兼容两者。
- `HAT_ROOT_REFERENCE`：只供 Blender 预览原戴帽位置，禁止直接导出到游戏。
- `WORKSPACE_GUIDES`：原点、参考中心、正视和侧视正交相机。默认活动相机是 `CAM_FRONT`。
- `README_YIER.txt`：保存在 `.blend` 内的部件命名速查。

场景使用米制单位。OBJ 进出轴约定为 `Forward -Z / Up Y`，与初始化时导入参考模型的转换保持一致。

首版至少按以下名称拆件：

- `Head`
- `Eyes`
- `Eyes2_Blinks`
- `Hand_Open_L` / `Hand_Open_R`
- `Hand_Grip_L` / `Hand_Grip_R`
- `Body_Body`
- `Body_Bottom`

若脚本报错，不会保存半成品。先解决错误，再通过 **File > New > General** 新建干净场景重跑。若目标 `.blend` 已存在，先手动改名或移动备份；不要删除后盲目重跑。
