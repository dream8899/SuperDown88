# Errors

## [ERR-20260803-001] wechat_channels_public_resolver_cli

**Logged**: 2026-08-03T03:00:00Z
**Priority**: medium
**Status**: resolved
**Area**: infra

### Summary
微信视频号公开解析页在浏览器成功，但同域 CLI GET/POST 均在 20–30 秒超时。

### Error
`curl: (28) Connection timed out`

### Context
- 输入为单个公开 `weixin.qq.com/sph/` 分享链接。
- 浏览器单次查询能返回匹配的作者、标题和原始视频下载。
- 未传 Cookie、登录态或授权头，也未连续刷新。

### Suggested Fix
把公开解析页限制为浏览器单链接备用；CLI 超时立即停止，长期保存稳定分享 ID，不保存
临时签名媒体地址。批量模式需另行批准微信客户端本地捕获方案。

### Metadata
- Reproducible: yes
- Related Files: references/wechat-channels.md

### Resolution
- **Resolved**: 2026-08-03T03:00:00Z
- **Notes**: 已固化浏览器降级路径、停止条件与本地注册脚本。

---

## [ERR-20260803-002] skill_quick_validate_missing_pyyaml

**Logged**: 2026-08-03T03:05:00Z
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
官方 `quick_validate.py` 在系统 Python 中因缺少 PyYAML 无法启动。

### Error
`ModuleNotFoundError: No module named 'yaml'`

### Context
- 所有功能单元测试已通过。
- 失败发生在校验器导入阶段，尚未读取 Skill。

### Suggested Fix
使用 `uv run --with pyyaml python .../quick_validate.py SKILL_DIR` 临时隔离运行，不修改
系统 Python。

### Metadata
- Reproducible: yes
- Related Files: SKILL.md

### Resolution
- **Resolved**: 2026-08-03T03:05:00Z
- **Notes**: 改用 uv 临时依赖执行校验。

---
