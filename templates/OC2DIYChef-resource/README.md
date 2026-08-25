# OC2DIYChef 资源包模板

在 `exports/Resources/` 下新建一个稳定的 ASCII 目录名，然后从本目录复制 `INFO.template` 为 `INFO`。

必需文件：

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

当前插件接受的可选 OBJ：

```text
Eyes.obj
Eyebrows.obj
Eyes2_Blinks.obj
Tail.obj
Head1.obj
Head2.obj
Body_NeckTie.obj
Body_Top.obj
Body_Bottom.obj
Body_Tail.obj
Body_Body.obj
Wheelchair.obj
Knife.obj
```

`Body_Body.obj` 可以有意导出为空，以移除原版身体；其余模型不应为空。独立贴图和材质按 `t_<部件>.png`、`m_<部件>.txt` 命名。身体部件会依次回退到 `t_Body.png`/`m_Body.txt`，再回退到头部贴图/材质。

OBJ 导出建议：只导出选中部件、应用变换、UV/法线、前向/上轴与已经验证的样本保持一致。插件导入时会按面角展开顶点，因此校验器的 `face-corners` 比 Blender 顶点数更接近运行时索引压力。
