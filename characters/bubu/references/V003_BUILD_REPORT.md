# 布布 v003 首个完整游戏产出

状态：`FIRST_INSTALLABLE_CANDIDATE`。模型资源、动作状态网格和静态门禁已完成；正式合并前仍需在 Overcooked! 2 中验证选人、待机、跑动、冲刺、拿取、切菜和投掷。

## 产物

- Blender：`F:\dev\overcooke\characters\bubu\source\bubu_work-v003.blend`
- Blender SHA-256：`BB0AC313BAC8183E03EC2996604AF370C32E209C3FA3B9FE9CCED6B6F815B260`
- 资源包：`F:\dev\overcooke\exports\Resources\175-bubu`
- 角色 ID：`175`；构建时本机已安装资源占用 `170..174`，未发现冲突。
- 图集：`t_Head.png` 与 `t_Body.png` 均为 512×512 RGBA，内容一致，SHA-256 为 `FC57887F40D7F0707C6EA20206476F35A532DE6D9EB9B15C1AE8BEF708372EF5`。

## 部件与动作适配

| 部件 | 顶点 | 三角面 | 处理 |
| --- | ---: | ---: | --- |
| `Head` | 3,910 | 6,808 | 大头、双耳、耳内、口鼻与面颊；六色平面图集 |
| `Eyes` | 334 | 330 | 左右睁眼独立于头部 |
| `Eyes2_Blinks` | 334 | 330 | 以每只眼中心做 X×1.12、Z×0.18，深度保持不变 |
| `Hand_Open_L/R` | 各 554 | 各 1,104 | 以现有成功厨师的手部中心和高度重新对齐 |
| `Hand_Grip_L/R` | 各 554 | 各 1,104 | 首版与同侧 Open 同拓扑，切换不跳位 |
| `Body_Body` | 554 | 1,104 | 中央躯干使用 OC2DIYChef 的 `Body_Top/Jnt_Body` 六档权重 |
| `Body_Bottom` | 1,108 | 2,208 | 两只脚刚性跟随 `Jnt_Body`，避免跨权重带拉扯 |
| `Body_Tail` | 554 | 1,104 | 后方独立尾巴，绑定 `Jnt_Tail` |

导出文件总计 9,010 顶点、16,300 三角面。运行时只显示一种眼睛状态及每侧一种手状态，同屏为 13,762 三角面。

## 网格清理

- v002 已移除 13 组同材质完全重合的反绕壳，共 8,116 三角面。
- v003 继续审计 10 组跨材质正反面壳，共移除 766 三角面。
- 跨材质组逐组件保留朝外绕序；面颊的两处 31 面粉色片按实际朝向保留，没有整材质删除。
- 所有导出对象使用 Identity Transform、三角面、单一图集材质、非退化 UV 和导出法线。

## 已通过门禁

- v002 构建前 dry-run：39 个源组件、29 个可见组件，映射统计精确匹配。
- v003 独立重开：10 个导出对象、9,010 顶点、16,300 三角面。
- OBJ 逐件重新导入：面数、边界和 UV 与 Blender 工作区一致。
- 身体最大单三角高度跨度：`0.02598694`；五个权重平面穿越数：`[0, 48, 48, 48, 48]`。
- 正、侧、背及睁眼/眨眼渲染：无缺面、反面壳或眼位跳动。
- `Test-OC2DIYChefResource.ps1`：`0 errors / 0 warnings`，并完成本机现有 Resources 的 ID 冲突检查。

## 实机测试重点

1. 选人界面和大厅：确认头部比例、耳朵方向和脚底高度。
2. 待机与眨眼：确认闭眼不陷入脸部，眼睛切换无闪跳。
3. 走路、跑动和冲刺：确认躯干双骨弹性自然，刚性双脚不拉伸或漂浮。
4. 拿盘子、食材、灭火器、切菜和投掷：确认左右手方向与厨具接触点。
5. 背包、炮台及载具：确认尾巴和大头不会严重遮挡交互提示。

## 本机部署与首次启动

- 已复制到 `D:\SteamLibrary\steamapps\common\Overcooked! 2\BepInEx\plugins\OC2DIYChef\Resources\175-bubu`。
- `prefer.txt` 已增加且仅增加一条 `175-bubu HAT=None`，原有 `Sign HAT=None` 和其他角色配置保留。
- 安装前偏好备份：`OC2DIYChef\Backups\bubu-v003-before-install-20260826-123822\prefer.txt`。
- 游戏启动后 BepInEx 5.4.22 与 OC2DIYChef 1.2 完成加载和补丁安装，日志没有 Error/Fatal；用户按 Esc 接管并结束窗口控制，因此尚未把“布布选中后的动作观感”记为通过。

源场景由 Sketchfab 用户小王子（`hong2695429209`）上传，依据 CC BY 4.0 使用；OC2 适配作者为 DUKEY。角色形象的底层权利状态仍按仓库许可记录为 `PENDING`，当前用于本地、非商业测试。
