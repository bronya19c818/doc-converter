# Windows Docker 启动、更新与独立 PR 验证

入口文件存在但 tini 报 `exec /usr/local/bin/docker-entrypoint.sh failed: No such file or directory` 时，应先检查脚本换行。CRLF 会把 shebang 的解释器路径变成 `/bin/sh\r`。本轮提供两层防护：Git 属性 `*.sh text eol=lf` 保证检出 LF；Dockerfile 在 COPY 后统一移除行尾 CR，再设置执行权限。字体目录仍只读挂载，数据卷保留。

## 更新已有 PR 测试目录

在已有测试目录执行；路径按本机实际位置修改。`git status` 如存在未提交修改，先提交或保存再更新，避免覆盖手动改动。下述 `--ff-only` 会在分叉时停止。

```powershell
Set-Location 'D:\2subject\workspace\doc-converter-pr2'
git status --short
git remote -v
git fetch origin feat/issue-1-auto-normalization
git switch feat/issue-1-auto-normalization
git merge --ff-only origin/feat/issue-1-auto-normalization
$env:DOC_CONVERTER_PORT = '8766'
$env:DOC_CONVERTER_WINDOWS_FONTS = 'C:/Windows/Fonts'
docker compose -p doc-converter-pr2 build --pull app
docker compose -p doc-converter-pr2 up -d --force-recreate app
docker compose -p doc-converter-pr2 ps
Invoke-RestMethod 'http://localhost:8766/health'
Invoke-RestMethod 'http://localhost:8766/api/style-packs'
Start-Process 'http://localhost:8766'
```

持续使用同一个 `-p` 项目名；更换项目名会使用另一组数据卷。测试端口 8766 与正式端口 8765 分离。更新无需 `down -v`，不要删除已有数据卷。

## 首次建立独立 worktree

先检查远端是否是 `bronya19c818/doc-converter`；旧 `qwertwqq` 仓库地址不等于当前 PR 所在仓库。下面为旧仓库添加独立远端，不修改原 origin。

```powershell
Set-Location 'D:\2subject\workspace\doc-converter'
git remote -v
git remote add issue3 https://github.com/bronya19c818/doc-converter.git
git fetch issue3 feat/issue-1-auto-normalization
git worktree add '..\doc-converter-pr2' -b test/issue-3 issue3/feat/issue-1-auto-normalization
Set-Location '..\doc-converter-pr2'
$env:DOC_CONVERTER_PORT = '8766'
$env:DOC_CONVERTER_WINDOWS_FONTS = 'C:/Windows/Fonts'
docker compose -p doc-converter-pr2 up -d --build
```

若远端 issue3 已存在，跳过 `remote add`。该 worktree 以后用 `git fetch issue3 feat/issue-1-auto-normalization` 和 `git merge --ff-only issue3/feat/issue-1-auto-normalization` 更新，保持 `test/issue-3` 分支即可；不要套用上述 origin 分支命令。若原仓库 origin 就是本次仓库，可直接使用 origin。

## 故障排查以容器和页面实际结果为准

```powershell
docker compose -p doc-converter-pr2 logs --tail 100 app
docker compose -p doc-converter-pr2 exec app python -c "from pathlib import Path; p=Path('/usr/local/bin/docker-entrypoint.sh'); print(p.exists(), bytes([13]) in p.read_bytes())"
docker compose -p doc-converter-pr2 exec app sh -c 'ls -l /usr/local/bin/docker-entrypoint.sh; head -1 /usr/local/bin/docker-entrypoint.sh'
```

预期脚本存在、CR 检查为 False，首行 `#!/bin/sh`，具备执行权限。构建和入口正常后，分别导入 MD、DOC、DOCX，完成生成、下载和预览，再切换样式重试。样式页曾经通过强制刷新恢复，不作为已确认组件缺陷处理；当前首页 HTML 使用 `Cache-Control: no-cache`，避免新旧 HTML 和哈希资源混用。更新后旧标签页仍显示异常时使用 Ctrl+F5。未修改 StyleEditor 或表单功能。

## 自动验收包括真实 CRLF 构建和运行

CI 的 `docker-runtime` 作业复制真实构建上下文，主动将入口改为 CRLF，然后执行实际 `docker build`、默认 ENTRYPOINT/tini 启动、Docker HEALTHCHECK、首页及样式 API、MD/DOC/DOCX 生成、DOCX 下载、PDF 预览、重复转换以及重启后数据卷读取。测试只创建唯一临时容器和临时卷，并只清理自己创建的资源。

Docker 随机宿主端口可能在重启后重新分配，验收脚本会重新读取映射并建立新连接。Windows Compose 使用上面的固定 8766 端口，不受这个测试端口变化影响。CI 运行于 Linux Docker，CRLF 上下文复现 Windows Git 检出问题；实际 Windows 字体与现场排版仍由本机验收。

可复现完整容器验收（本机需 Python/uv）：

```powershell
uv run python scripts/verify_docker_runtime.py --build-crlf --output artifacts/docker-runtime
```
