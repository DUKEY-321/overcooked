# 布布 / bubu

- `source/bubu_work-v001.blend`：从共同 GLB 分离、缩放并对齐游戏参考后的恢复点。
- `source/bubu_work-v002.blend`：当前工作基线；仅移除了 13 组完全重合且反向绕序的壳体，现为 6 个网格、8,338 顶点、14,528 三角面，并已通过独立重开校验。
- `references/`：只保存人工参考图、网页链接及 `SOURCES.md`；当前布布与一二共用已校验的 `assets/source_yier/` Sketchfab 场景。
- `textures/`：保存烘焙和绘制源文件；最终 PNG 放进资源包。

尽量复用一二已经验证的部件拆分、尺寸基准和手型拓扑。从 `bubu_work-v002.blend` 继续制作；受限打印模型仍然只做页面级造型观察，不下载、不导入、不改模。导出目标位于工作区根目录的 `exports/Resources/<ID>-bubu/`。
