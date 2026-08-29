# Git 备份与恢复

本仓库只备份可启动工程、测试、文档、配置模板和教学样例。以下内容不会进入 Git：

- API Key、`.env`、`key.txt` 和本机模型设置；
- `backend/data` 中的数据库、课程索引、上传原件和提取缓存；
- `.runtime`、日志、测试缓存、依赖、构建产物和生成截图；
- 历史完整项目副本和 `.backups` 离线快照。

因此 Git 用于恢复工程版本，不用于恢复教师的运行数据和本地课程文件。运行数据需要另行做加密文件备份。

## 日常备份

在项目根目录执行：

```powershell
.\scripts\git-backup.ps1 -Message "backup: 完成双向目录同步"
```

脚本依次执行：

1. 后端完整测试；
2. 前端 ESLint 和生产构建；
3. 暂存变更；
4. 拦截大于 50 MB 的文件和疑似密钥；
5. 检查补丁格式并创建提交。

仅在紧急情况下使用 `-SkipTests`。配置远端后可增加 `-Push`，在提交成功后推送。

## 配置远端

先在 GitHub、GitLab 或 Gitee 创建私有空仓库，再执行：

```powershell
git remote add origin <private-repository-url>
git push -u origin main
```

后续可以使用：

```powershell
.\scripts\git-backup.ps1 -Message "backup: 描述本次改动" -Push
```

## 离线单文件快照

```powershell
.\scripts\git-bundle.ps1
```

默认输出到被 Git 忽略的 `.backups`。应将 `.bundle` 文件复制到项目目录之外的另一块磁盘或受控网盘。

恢复：

```powershell
git clone D:\backup\multi-agent-platform-20260812-120000.bundle restored-project
cd restored-project
Copy-Item .env.example .env
python -m pip install -r backend\requirements.txt
npm --prefix frontend install
.\run.bat
```

## 恢复某个工程版本

查看历史：

```powershell
git log --oneline --decorate --graph
```

建议从旧版本创建恢复分支，不直接覆盖当前工作区：

```powershell
git switch -c restore-check <commit-id>
```

确认后再决定是否合并回 `main`。
