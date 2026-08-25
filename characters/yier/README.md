# 一二 / yier

- `source/yier_prototype.blend`：共同 GLB 与游戏参考模型的原始导入留档。
- `source/yier_work-v001.blend`：一二分离、缩放并对齐游戏参考后的恢复点。
- `source/yier_work-v002.blend`：拆件前恢复点；9 个网格、15,354 顶点、27,767 三角面。
- `source/yier_work-v003.blend`：一二完整首版恢复点；蓝帽仍合并在 `Head`。
- `source/yier_work-v004.blend`：当前基线。默认 `Head` 已移除蓝帽，蓝帽按官方 `Hat_Baseballcap` 的精确局部坐标独立导出；发布资源名为 `YierCap`。旧 v004 工作区内部保留历史对象名 `YierBlueCap`；`HAT_ROOT_REFERENCE` 用于 Blender 戴帽预览。
- `references/`：只保存人工参考图、网页链接及 `SOURCES.md`；下载模型原件固定保存在工作区 `assets/source_yier/`。
- `textures/`：保存烘焙和绘制源文件；最终 PNG 放进资源包。

v004 角色包位于 `exports/Resources/174-yier/`，帽子位于 `exports/Resources/HATS/YierCap/`，并已安装到本机 OC2DIYChef。当前 `prefer.txt` 为 `174-yier HAT=YierCap`。结构、UV、法线、OBJ 往返、HatBase 坐标和安装后文件哈希均已通过；详情见 `references/V004_OPTIONAL_HAT_REPORT.md`。具体身体权重阈值和坐标基准见 `references/OC2_BINDING_NOTES.md`。
