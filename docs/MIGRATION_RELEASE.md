Windows 运行数据快照，配套本仓库当前版本。

附件包含中间数据库、补充数据、演示依赖、历史报告及 Windows 渲染工具。压缩流按 512 MiB 分包；不要逐个手动解压。文件清单及 SHA-256 见 runtime-manifest.json。

在另一台 Windows 电脑克隆仓库，安装 Python 3.12 x64、Microsoft Word 和 GitHub CLI，登录有权限的 GitHub 账号，然后双击 setup_new_computer.cmd。初始化程序会下载、核验并恢复数据，随用随删压缩分包。详见仓库 docs/MIGRATION.md。

该快照不包含旧录屏、重复 ZIP、历史失败任务、个人聊天或 API 密钥。原始 Excel 和 Word 模板保存在 Git 仓库的 data 目录。
