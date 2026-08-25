# OC2DIYChef 1.2 绑定与动作适配记录

本记录依据本机 `OC2DIYChef 1.2` DLL、现有资源和上游 commit `93ab0554` 源码整理。插件最终只读取 OBJ；它不会采用 Blender/GLB 的骨架、动画或顶点组，而是复制游戏原厨师 prefab，保留 Skeleton 与 Animator，再替换对应的 `SkinnedMeshRenderer` 网格并运行时生成权重。

## 部件与骨骼

| OBJ 部件 | 游戏骨骼/部件 |
| --- | --- |
| `Head` / `Head1` / `Head2` | `Head` |
| `Eyes` | `Eyes` |
| `Eyes2_Blinks` | `Eyes2_Blinks` |
| `Eyebrows` | `Eyebrows` |
| `Hand_Grip_L` / `Hand_Open_L` | `LeftHand` |
| `Hand_Grip_R` / `Hand_Open_R` | `RightHand` |
| `Body_Bottom` | `Jnt_Body` |
| `Body_Top` | `Body_Top` |
| `Body_NeckTie` | `NeckTie` |
| `Body_Tail` / `Tail` | `Jnt_Tail` |

源码证据：<https://github.com/gua248/Overcooked2-DIYChef/blob/93ab0554ba55bd298d00ff4b05e78c8ef0beb345/DIYChefCustomisation.cs#L513-L533>

除 `Body_Body` 外，每个 OBJ 的全部顶点都是 100% 单骨权重。Blender 中手工涂的权重不会保留。

## `Body_Body` 六档权重

插件仅用 `Body_Top` 与 `Jnt_Body` 两骨，并按 OBJ 顶点的绝对 Y 坐标离散分档：

| 顶点 Y | Body_Top | Jnt_Body |
| --- | ---: | ---: |
| `> 0.54` | 1.00 | 0.00 |
| `0.46–0.54` | 0.75 | 0.25 |
| `0.38–0.46` | 0.50 | 0.50 |
| `0.30–0.38` | 0.30 | 0.70 |
| `0.22–0.30` | 0.10 | 0.90 |
| `≤ 0.22` | 0.00 | 1.00 |

源码证据：<https://github.com/gua248/Overcooked2-DIYChef/blob/93ab0554ba55bd298d00ff4b05e78c8ef0beb345/DIYChefCustomisation.cs#L713-L770>

布线时应在 `0.22 / 0.30 / 0.38 / 0.46 / 0.54` 附近安排横向环线，避免长三角形跨越多个权重区。`Body_Bottom` 只会刚性跟随 `Jnt_Body`。一旦提供 `Body_Body.obj`，插件会移除原游戏身体 renderer；全自制身体只能获得这套上下两骨的弹簧式变形，无法获得原版四肢的多骨蒙皮。

## 状态切换

- `Eyes.obj` 与 `Eyes2_Blinks.obj` 是睁眼/闭眼两个独立网格，不使用形态键插值。
- `Hand_Open_*` 与 `Hand_Grip_*` 是张开/抓握两个独立网格。
- 同侧两个手型必须保持手腕边界、中心和尺寸一致，避免切换跳动。
- 睁眼与闭眼网格也必须共用深度、中心和外轮廓基准。

官方指南：<https://github.com/gua248/Overcooked2-DIYChef/blob/master/README/README-zh.md#自制厨师指南>

## 本地 `171-pinkpig` 坐标基准

- Head：X `-0.43～0.43`，Y `0.57～1.21`，Z `-0.34～0.38`
- Body_Body：X `-0.25～0.25`，Y `0.21～0.70`
- 左手：X `0.22～0.40`；右手：X `-0.40～-0.22`
- 手部 Y：`0.43～0.61`
- 睁眼 Y：`0.80～0.93`，Z `0.27～0.33`

一二源模型的量级和坐标远大于此基准。导入后需要以粉猪叠模的眼位、手位和脚底为准统一比例/朝向；自动缩放只能作为起点。

## 面数与导出

首版建议预算：

- Head：8k–12k 三角面；
- Body_Body：4k–8k；
- 睁眼与闭眼合计：1k–3k；
- 每只手每个状态：0.5k–1k；
- 全资源：约 22k–32k；
- 任一 OBJ 尽量低于 20k 三角面。

插件的 OBJ 导入器会把面角展开成 Unity 顶点，且没有设置 32 位索引；三角化后 20k 面约对应 60k 面角，是较稳妥的单文件上限。导出前应应用 Transform、预先三角化、导出法线，并优先使用完整 `v/vt/vn`。MTL、OBJ group 和多材质不会形成多套游戏材质，每个部件应烘焙成一张 512×512 RGBA 图集。

OBJ 导入器：<https://github.com/gua248/Overcooked2-DIYChef/blob/93ab0554ba55bd298d00ff4b05e78c8ef0beb345/ObjImporter.cs>

## 两阶段实机路线

1. 先不提供 `Body_Body.obj`：只替换一二的头、睁/闭眼和四个手型，验证走、跑、冲刺、拿取、切菜、投掷、眨眼和大厅动作。
2. 再加入完整一二身体：针对六档权重带检查弹跳、穿模、手距和厨具遮挡，并与第一阶段对照动作损失。
