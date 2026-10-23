# plus/ — fork 专属内容

本目录存放 nautilus-plus 相对上游 nautilus 的全部**自有内容**。C 层已还原为上游原样(不再有 fork 改动),这里只剩 Python 插件与文档。

**为什么独立成目录**:上游 nautilus 已有 `docs/`(man 页 + gtk-doc 参考)和 `extensions/`(meson 管理的 C 扩展)——把我们的文档和 Python 扩展放进去会污染上游结构、增加合并摩擦。`plus/` 是独立命名空间,上游合并永不触碰。

## 结构

```
plus/
├── README.md        # 本文件:目录导航
├── install.sh       # 安装插件到 ~/.local/share/nautilus-python/extensions/
├── docs/            # 项目文档体系
│   ├── requirements.md   # 原始需求(短、笼统)
│   ├── design/           # 功能设计(按功能一个文件)
│   │   ├── desc.md
│   │   └── file-desc.md
│   ├── research.md       # 技术调研(已验证的机制/死路)
│   ├── pitfalls.md       # 踩坑记录
│   └── CHANGELOG.md      # 版本日志
├── dev-demo/        # 手工验收用夹具
├── extensions/
│   └── python/nautilus-meta/   # 插件本体(nautilus-python)
└── skills/folder-yaml/         # 给 agent 的技能包(`.folder.yaml` 格式与操作)
```

## 架构

纯 Python 插件,不改 C。业务全部在 `extensions/python/nautilus-meta/nautilus-meta.py`:

- **InfoProvider**:读 `.folder.yaml`,写入 `desc` 扩展属性
- **ColumnProvider**:注册列表视图「描述」列,同一属性
- **MenuProvider**:修改描述 / 修改注释 / 全局显示开关

图标视图靠 nautilus 自带的 captions 机制显示 `desc`(见 `docs/design/desc.md`)。

## 安装

```bash
plus/install.sh
```

脚本把插件复制到 `~/.local/share/nautilus-python/extensions/` 并重启 nautilus。不需要构建、不需要 pkexec。

依赖:`nautilus-python`、`python-yaml`(Arch:`pkexec pacman -S nautilus-python python-yaml`)。

## 开发验收流程(必做)

```bash
python3 -m unittest discover -s plus/extensions/python/nautilus-meta -p 'test_*.py'
plus/install.sh
nautilus plus/dev-demo
```

- 验收内容:`plus/dev-demo/` 含 `alpha-project`、`beta-project`(有 desc)、`gamma-project`(仅 file-desc)、`plain-dir`(无 yaml)、`notes.txt`(普通文件)
- 图标视图检查描述副标题;列表视图右键列头勾选「描述」列;右键「修改描述 / 修改注释」可用;没有归档相关菜单项
