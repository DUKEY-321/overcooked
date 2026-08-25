# Sign 特别版命名迁移

状态：`SPECIAL_BRANCH_RUNTIME_RENAME`。

- 分支：`special/sign`
- 角色资源目录：`Resources/Sign/`
- 协议 ID：`Sign/INFO` 中的 `ID=174`
- 默认偏好：`Sign HAT=None`
- 可选帽：`Resources/HATS/SignCap/`
- 戴帽偏好：`Sign HAT=SignCap`

本迁移不改变 v004 网格、UV、贴图、HatBase 坐标或角色 ID，只改变运行时资源名、
安装脚本和尾气配置身份。旧 `174-yier`、`YierCap` 与 `YierBlueCap` 在升级安装时会
先移入时间戳备份目录，避免同一 ID 被重复加载。

原始 `V004_OPTIONAL_HAT_REPORT.md` 保留旧路径、旧配置和旧哈希，作为历史验收证据，
不对其中记录做覆盖式改写。
