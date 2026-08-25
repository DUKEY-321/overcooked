# 一二 / Yier OC2DIYChef v0.4.0-test

这是供其他电脑验证的一二非商业测试包。默认角色 ID 为 `174`，帽子固定为
`YierCap`。包内安装器会保留其他角色的 `prefer.txt` 配置，并在修改前创建备份。

## 已验证环境

- Windows Steam 标准版 Overcooked! 2（x86）
- BepInEx 5.4.22 x86（包内包含官方原版）
- OC2DIYChef v1.2，固定上游提交 `93ab0554`（包内包含）
- 可选尾气 GUI：`OC2DIYChefTrailColor` 0.2.0，F10 打开

Steam Crossplay Beta/Epic x64 版本尚未验证，不能使用本包内的 x86 BepInEx。

## 安装

1. 完整解压 ZIP，不要直接在压缩包内运行脚本。
2. 关闭 Overcooked! 2。
3. 在 PowerShell 中运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Yier.ps1 `
  -GameDir 'D:\SteamLibrary\steamapps\common\Overcooked! 2'
```

如果不需要走路/冲刺尾气 GUI：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Yier.ps1 `
  -GameDir 'D:\SteamLibrary\steamapps\common\Overcooked! 2' `
  -SkipTrailColor
```

未提供 `-GameDir` 时，安装器会检查常见 Steam 目录；找到多个候选时会要求显式指定。

尾气插件依赖 HostUtilities 1.8.0。该依赖没有随 ZIP 再分发；安装器会从作者的
官方 Release 下载 `HostUtilities.Core.zip`，核对固定 SHA-256 后安装。下载失败时，
一二和 `YierCap` 仍会安装，只会跳过尾气插件。

## 安装结果

```text
BepInEx/plugins/OC2DIYChef/Resources/174-yier/
BepInEx/plugins/OC2DIYChef/Resources/HATS/YierCap/
BepInEx/plugins/OC2DIYChefTrailColor/          # 可选
```

`prefer.txt` 中应有且仅有一行：

```text
174-yier HAT=YierCap
```

启动游戏后在选人界面选择 `174-yier`。安装尾气插件时按 F10 可为不同角色分别设置
走路烟雾和冲刺尾气颜色。

## 备份与回滚

安装器会把被替换的一二资源、OC2DIYChef 文件、尾气 DLL 和原始 `prefer.txt` 保存到：

```text
<游戏目录>/BepInEx/YierPackageBackups/<时间戳>/
```

需要回滚时先关闭游戏，把该目录内的文件按原相对路径复制回游戏目录。不要直接覆盖
其他玩家或其他角色正在使用的 `prefer.txt`；可只删除 `174-yier HAT=YierCap` 行。

## 校验与许可

`SHA256SUMS.txt` 覆盖 ZIP 内所有文件。模型署名和第三方依赖说明见
`THIRD_PARTY_NOTICES.md` 与 `licenses/`。本包是非官方、非商业测试 MOD；与
Ghost Town Games、Team17 或角色权利人无隶属或背书关系。
