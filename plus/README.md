# plus/ — fork 专属内容

本目录存放 nautilus-plus 相对上游 nautilus 的全部**自有内容**,与上游代码隔离。

**为什么独立成目录**:上游 nautilus 已有 `docs/`(man 页 + gtk-doc 参考)和 `extensions/`(meson 管理的 C 扩展)——把我们的文档和 Python 扩展放进去会污染上游结构、增加合并摩擦。`plus/` 是独立命名空间,上游合并永不触碰。

## 结构

```
plus/
├── README.md        # 本文件:目录导航
├── docs/            # 项目文档体系(可扩展)
│   ├── requirements.md   # 原始需求(短、笼统)
│   ├── design/           # 功能设计(按功能一个文件)
│   │   └── desc.md
│   ├── research.md       # 技术调研(已验证的机制/死路/fork 钩子蓝图)
│   ├── pitfalls.md       # 踩坑记录
│   └── CHANGELOG.md      # 版本日志
└── extensions/
    ├── skills/           # 给 agent 的技能包(folder-yaml:`.folder.yaml` 格式与操作)
    └── python/           # Python 扩展(业务层,nautilus-python 插件)
        └── nautilus-meta/
```

## 开发分工

- **C 层**(本仓库主树):只放**通用能力**——Python 扩展够不到、或必须做成通用机制的东西(分组/排序与视图过滤、文件移动事件广播)。C 里不写业务:不解析 `.folder.yaml`、不判断功能开关
- **Python 层**(`extensions/python/`):业务逻辑(.folder.yaml 解析、开关、菜单)——修改快速迭代,装到 `~/.local/share/nautilus-python/extensions/` 即可

详见 `docs/research.md` 的架构决策章节。

## 安装到系统(nautilus-plus 独立身份)

fork 以 **nautilus-plus** 身份并行安装,与系统 nautilus 不冲突(设计见 `docs/design/plus-identity.md`):

```bash
# 新电脑依赖一次装齐(构建 + fork 运行时 + Python 扩展运行时)
pkexec pacman -S --needed meson glib2-devel gobject-introspection blueprint-compiler \
  itstool libselinux nautilus-python python-yaml bubblewrap localsearch xdg-user-dirs-gtk

meson setup build --prefix=/usr -Dprofile=Plus -Ddocs=false   # prefix 必须为 /usr(见 pitfalls.md 第 12 条)
ninja -C build
pkexec ninja -C build install                                  # 覆盖安装(fork 已不修改任何发行版包拥有的文件,升级不会破坏它)
rm -f ~/.local/share/nautilus-python/extensions/nautilus-meta.py  # 删除旧用户副本,避免双菜单(pitfalls #5)
nautilus-plus                                                  # 启动;zh_CN 下显示「文件管理器增强版」
```

- 二进制 `nautilus-plus`、应用 ID `org.gnome.NautilusPlus`,与系统 nautilus 可同时运行
- 不注册 `org.freedesktop.FileManager1`——系统 nautilus 仍是默认文件管理器
- 图标、桌面文件、D-Bus service、搜索提供者均带 `NautilusPlus` 前缀;gschema/soname/翻译与系统共享
- **Python 扩展随安装装到 `/usr/share/nautilus-python/extensions/`**(所有用户生效);与 `~/.local/...` 副本同存会双菜单(pitfalls #5),系统装后删用户副本

## 开发验收流程(必做)

任何 C/Python 改动完成后,**先本地安装到系统,再打开 demo 文件夹**人工验收:

```bash
ninja -C build && pkexec ninja -C build install   # 构建 + 装到系统(pkexec 会弹图形密码框)
nautilus-plus plus/dev-demo                      # 打开 demo 文件夹验收
```

- fork 独立应用 ID,与系统 nautilus 并行不冲突,无需退出系统实例;改扩展后 `nautilus-plus -q` 重启生效
- 验收内容:`plus/dev-demo/` 应包含 `alpha-project`(desc + archived)、`beta-project`(仅 desc)、`gamma-project`(仅 archived)、`plain-dir`(无 yaml)、`notes.txt`;分别用图标视图和列表视图检查分组/描述显示效果
