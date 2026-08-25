# 一二源模型留档目录

本目录已经保存 Sketchfab 模型“表情包的一二布布Yier”的下载原件与原样解压文件。界面核对确认该场景同时包含左侧的一二和右侧的布布，因此它是两名角色的共同源模型；目录名保留为 `source_yier` 只是为了不移动已经校验的原件：

- `sketchfab_b15f13be_original_dae.zip`：Sketchfab 原始 DAE 下载外层包；
- `original_dae_download/source/temp_export.zip`：外层包内的原始导出 ZIP；
- `original_dae_download/model/temp_export.dae`：从原始导出 ZIP 解出的 DAE；
- `yier_b15f13be_converted.glb`：Sketchfab 提供的 GLB 转换版本，初始化脚本优先使用它；
- `SHA256SUMS.txt`：上述文件的校验值。

本目录只保存下载原件及原样解压内容。人工参考图、网页链接和来源清单放在 `characters/yier/references/`；Blender 生成文件放在 `characters/yier/source/`。不要在本目录直接做减面、重命名或覆盖式转换。

来源、下载日期、许可和署名记录见 `characters/yier/references/SOURCES.md` 与 `LICENSES/yier-sketchfab-b15f13be.md`。

推荐顺序：GLB、glTF、FBX、OBJ、DAE。初始化脚本会递归查找，并只自动选择优先级最高的一种格式，避免同一个模型的多个下载格式被重复导入。glTF 的 `.bin` 和贴图必须保留原相对路径。DAE 依赖 Blender 的 Collada 导入器；当前项目已保留 GLB，因此不需要额外安装 Collada 扩展。

不要把账号 Cookie、访问令牌或其他登录凭据放进此目录。
