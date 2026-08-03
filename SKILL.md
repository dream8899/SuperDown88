---
name: superdown88
description: Safely and efficiently archive public social-media videos with yt-dlp, prioritizing Instagram and supporting WeChat Channels, TikTok, YouTube/Shorts, and other supported sites. Use for one video, creator/profile/channel updates, cross-platform channel registries, browser-assisted URL discovery, incremental no-duplicate downloads, verification, or recovery from extractor changes across macOS, Linux, Windows, Codex, CLI, Computer Use, Chrome/CDP, Playwright, Kimi WebBridge, and manual workflows.
---

# SuperDown88

Use `yt-dlp` for media transfer. Use all browser tools only to discover canonical public
post URLs. Prefer public, logged-out downloads; login state is never part of the transfer path.

Read [references/installation-and-agent-adapters.md](references/installation-and-agent-adapters.md)
before first use on a device or with an unfamiliar Agent. Read
[references/field-guide.md](references/field-guide.md) when diagnosing a failure,
choosing a fallback, or changing platform behavior. For reusable multi-account work,
instantiate [references/task-template.md](references/task-template.md).
For `weixin.qq.com/sph/` links, read
[references/wechat-channels.md](references/wechat-channels.md) before transfer; WeChat
Channels has a platform-specific browser/client handoff because yt-dlp currently lacks a
native extractor.

## Non-negotiable boundary

- Permit an authorized logged-in browser to discover canonical post URLs/IDs only.
- Start every transfer with `--ignore-config --no-cookies`; never pass cookies, browser
  profiles, session files, localStorage, authorization headers, or temporary CDN URLs.
- For WeChat Channels, permit a browser resolver to consume one public share URL and save
  one local file, but never persist or hand off its temporary signed media URL. Treat local
  proxy/root-certificate capture as a separate privileged mode requiring explicit approval.
- Stop and classify public-transfer failures. Do not escalate to authenticated download,
  proxy rotation, CAPTCHA bypass, user-agent rotation, retries, reload loops, or concurrency.

## Execution path

1. Confirm the media is public or the user is authorized to archive it. Inspect existing
   creator metadata, archive, verified files, terminal failures, and channel registry first.
2. Run `python3 scripts/safe_social_archiver.py doctor --check-updates`. Do not update
   tools during an active batch; request approval before applying an update.
3. For one canonical video URL, run public yt-dlp directly. For profiles/channels,
   choose discovery in this order: native verified collection extractor; bounded anonymous
   Instagram discovery; authorized browser URL discovery; manual canonical-URL export.
4. Normalize every discovery result into a one-URL-per-line file. Canonical URLs/media IDs
   are the handoff contract between Agents; browser media URLs are not.
5. Compare IDs against `metadata.tsv`, `.download-archive.txt`, verified filenames, and
   the registry. Enqueue only new IDs, newest first; for Instagram stop discovery at the
   first known shortcode unless explicitly backfilling.
6. For an existing Instagram archive, scan only `CREATOR/*.mp4` directly under the creator
   directory. Ignore every child directory (remix, publishing, quarantine, review). Use
   `Video_Download/reconcile_instagram_metadata.py` to normalize filename-derived IDs,
   remove creator-name prefixes, strip post-processing suffixes such as `__h264-aac`,
   and rebuild metadata in newest-first order. Move duplicate files to quarantine; never
   delete them.
7. Download a five-item pilot. Expand only after all five verify; then run serial batches
   of at most 20. Stop the batch on its first error.
8. Verify files with `ffprobe`, update creator records plus the channel registry, classify
   inaccessible items, and preserve the source/state/logs for the next Agent.
9. After every verified batch, update the shared SuperMedia catalog. Read
   [references/media-lineage-contract.md](references/media-lineage-contract.md), then run
   `scripts/media_asset_catalog.py --root VIDEO_DOWNLOAD_ROOT sync --platform CHANNEL
   --sources-only`. The platform-native media ID is the permanent `source_key`; filenames
   and sequence numbers are not identity.

## Safety and pacing

- Browser discovery: use the designated existing tab/window, scroll one viewport at a time,
  wait a randomized 3–8 seconds, and stop after two no-new-ID passes, visible feed end, or
  requested limit. Modal navigation is a maximum-five-item repair method, never enumeration.
- Transfers: one fragment, zero yt-dlp retries, 12–18 second randomized delay for profile/
  channel batches, default 20 items, hard cap 100 only when explicitly requested.
- Stop immediately for 429, challenge/checkpoint/CAPTCHA, login requests, blank/timeout
  pages, empty pagination, invalid output, or repeated failures. Preserve state and honor
  the recorded cooldown rather than refreshing.
- Treat displayed post counts as estimates. A deleted, hidden, private, or unexposed item
  is an accounted terminal state, not justification for repeated scraping.

## Directory and registry contract

Use one channel root and one creator directory per account:

```text
Video_Download/
└── instagram/
    ├── creator_registry.tsv
    ├── channel_index.md
    ├── CREATOR/
    │   ├── README.md
    │   ├── metadata.tsv
    │   ├── .download-archive.txt
    │   ├── batch-log.jsonl
    │   └── verified-source.mp4
    └── quarantine/
```

Keep a single `(channel, canonical creator)` registry row. Store the profile URL, media
directory, verified count, known-ID count, last scan, aliases, and terminal status. Do not
rename/resequence a work merely because an older batch used another filename.

Run the local registry scanner after every batch:

```bash
python3 Video_Download/update_creator_registry.py --root Video_Download/instagram
python3 scripts/media_asset_catalog.py --root Video_Download sync \
  --platform instagram --sources-only
```

The source inventory still scans only top-level creator files. The shared catalog may scan
child directories separately to recover derivative lineage; those files never increase the
downloaded-source count.

Reconcile an existing Instagram channel before an incremental visit. The fast default
uses non-empty top-level files for inventory; add `--verify` when a full ffprobe pass is
worth the extra time:

```bash
python3 Video_Download/reconcile_instagram_metadata.py \
  --root Video_Download/instagram
python3 Video_Download/update_creator_registry.py \
  --root Video_Download/instagram
```

## Commands

Check tools:

```bash
python3 scripts/safe_social_archiver.py doctor --check-updates
```

Normalize browser/Agent output, then archive only five public URLs:

```bash
python3 scripts/safe_social_archiver.py normalize-discovery raw-discovery.txt \
  --instagram-profile CREATOR --output sources.txt
python3 scripts/safe_social_archiver.py archive --sources-file sources.txt \
  --output-dir '/absolute/Video_Download/instagram/CREATOR' --max-items 5
```

For Instagram profile discovery, use anonymous discovery only; the browser is a bounded
fallback for URLs, not a downloader:

```bash
uv run --with 'instaloader==4.15.2' python3 scripts/safe_social_archiver.py \
  discover-instagram 'https://www.instagram.com/CREATOR/' \
  --known '/absolute/Video_Download/instagram/CREATOR/metadata.tsv' \
  --max-items 5 --output sources.txt
```

`metadata.tsv` may use the 12-column form with `视频地址`; the local batch downloader accepts
both that form and the legacy four-column form. Prefer canonical URL fields when present.
Use `social_batch_downloader.py` only for a bounded manifest batch; otherwise retain the
portable canonical URL list and use the wrapper above.

## Maintenance

When a platform changes, stop, run `doctor`, update yt-dlp only with approval, run unit
tests, then one public dry run and one real public item. Patch only the remaining proven
need; do not reproduce extractor logic or make iGram/private APIs a dependency.

Self-improvement is controlled. Task runs may append evidence-only candidates, but must
never rewrite this file, scripts, references, templates, schemas, safety boundaries, or
defaults. Runtime metadata and account state are not Skill knowledge. Before proposing or
applying any learned change, read
[references/controlled-evolution.md](references/controlled-evolution.md); core changes require
a separate maintenance task, a pre-committed human approval record, tests, diff review, and
`scripts/controlled_evolution_guard.py`. Never fabricate approval or promote by recurrence.

Every Skill update must be published and synchronized to all existing local installations
before the task is considered complete. Run the local sync scanner after committing; it
updates only directories whose frontmatter is `name: superdown88`, never deletes target
files, and accepts additional Agent roots explicitly:

```bash
python3 scripts/sync_local_installs.py
python3 scripts/sync_local_installs.py --root /path/to/another/agent/skills
git push
```

If the scanner reports no targets, record that the current installation is the only local
copy. Do not silently create unrequested duplicate installations.

## 本地资产中心（无需 Agent）

下载、Remix 或上传批次结束后，可用 `scripts/supermedia_console.py` 更新同一份
SuperMedia SQLite 账本。它会自动发现渠道、创建数据库备份、加独占锁、同步、审计并
导出报表；不会下载、上传或读取登录态：

```bash
python3 scripts/supermedia_console.py --root "/absolute/Video_Download" update
python3 scripts/supermedia_console.py --root "/absolute/Video_Download" serve --open
```

浏览器管理台固定绑定 `127.0.0.1`，仅可执行更新和人工补全已核验的 HOLD 血缘。
完整需求见 [references/supermedia-asset-center-requirements.md](references/supermedia-asset-center-requirements.md)，
跨系统使用方式见 [references/supermedia-asset-center-guide.md](references/supermedia-asset-center-guide.md)。

```bash
python3 scripts/test_safe_social_archiver.py
python3 scripts/test_wechat_channels_register.py
python3 scripts/test_controlled_evolution_guard.py
python3 scripts/test_media_asset_catalog.py
python3 scripts/test_supermedia_console.py
python3 /Users/solo/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```
