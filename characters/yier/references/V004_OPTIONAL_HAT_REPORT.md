# 一二 v004：默认无帽与可选蓝帽

状态：`INSTALLED_WITH_YIERCAP`。

## 当前产物

- Blender：`F:\dev\overcooke\characters\yier\source\yier_work-v004.blend`
- Blender SHA-256：`FDCC615C294EA927DE71DDF87343DC2DA16957BE72BD306A3711AAD38D3F9909`
- 默认角色包：`F:\dev\overcooke\exports\Resources\174-yier`
- 帽子：`F:\dev\overcooke\exports\Resources\HATS\YierCap`
- 游戏安装目录：`D:\SteamLibrary\steamapps\common\Overcooked! 2\BepInEx\plugins\OC2DIYChef\Resources`
- 当前配置：`174-yier HAT=YierCap`
- `prefer.txt` SHA-256：`5F95426F269DAA769EDC847ED907CE41C086821FBD26DA0DAC87144CF04D9148`

v003 工作区资源已归档到 `F:\dev\overcooke\exports\archive\174-yier-v003`；游戏端 v003 已移到 `OC2DIYChef\Backups\174-yier-v003-before-v004`，没有删除。

## 精确拆分

蓝帽来自源材质 `YIER_material_8`，由外壳、内壳和帽檐连接层 3 个断开组件组成，共 698 顶点、1,296 三角面。棕色耳朵属于另一个源材质，继续留在 `Head`。

| 资源 | 顶点 | 三角面 |
| --- | ---: | ---: |
| 默认 Head | 2,686 | 4,224 |
| 默认角色包合计 | — | 20,235 |
| YierCap | 698 | 1,296 |
| 戴帽时合计 | — | 21,531 |

帽子不能沿用 Head 的角色根坐标。插件克隆官方 `Hat_Baseballcap`，其相对 `Mesh` 的位置为 `(0, 1.036182165, -0.106847078)`。v004 因此在 Blender 中对帽顶点减去 `(0, 0.106847078, 1.036182165)`，再按 `Forward -Z / Up Y` 导出。转换后的 OBJ bounds 为：

```text
X -0.483926 .. 0.488358
Y -0.449599 .. 0.173640
Z -0.284223 .. 0.541188
```

## 使用

不使用帽子时：

```text
174-yier HAT=None
```

当前发布默认使用蓝帽：

```text
174-yier HAT=YierCap
```

OC2DIYChef 1.2 不会把自定义帽加入独立 UI；它只读取 `prefer.txt` 给角色固定帽子，并忽略同一角色的重复行。因此不能同时写无帽和有帽两行。若以后必须在角色选择界面直接切换，应再制作一个 `ID=176` 的有帽角色变体；`175` 继续预留给布布。

## 验证结果

- Blender v004 结构、UV、帽子偏移和 11 个 OBJ 往返：通过。
- 默认角色包严格校验：`0 errors / 0 warnings`。
- `YierCap` 严格校验：`0 errors / 0 warnings`，3,888 face-corners。
- 游戏目录全量 5 个角色包校验：`0 errors / 0 warnings`。
- 工作区与游戏安装目录逐文件 SHA-256 一致。
- v004 戴帽正、侧、背三张渲染与 v003 对应渲染逐像素完全一致；无帽渲染确认两只棕耳朵均保留。

仍需玩家实机确认大厅、奔跑、冲刺、切菜和投掷时的动态遮挡。默认资源和可选帽已就位，不需要再次复制文件。
