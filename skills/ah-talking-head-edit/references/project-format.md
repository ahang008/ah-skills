# 独立口播剪辑项目格式

## 边界和依赖

本格式由本项目独立定义，格式名是 `ah-talking-head-project`，版本为 `1`。它是可编辑 JSON，不是剪映原生草稿。MP4 单独由 FFmpeg 渲染。默认原速，无 BGM，不自动根据静音或转写时间删除语音。保留区间由人做语义选择。

运行依赖 Python 3.9 或更新版本的标准库，以及单独安装的 FFmpeg、ffprobe。可执行文件先从 PATH 查找，再使用 `/opt/homebrew/bin/ffmpeg` 和 `/opt/homebrew/bin/ffprobe` 兜底。每个命令支持 `--ffmpeg` 和 `--ffprobe` 覆盖。编码依赖 `libx264` 和 `aac`。`doctor` 检查版本和实际需要的编码器、滤镜。

本实现未读取或复制旧 yichen、jianying-headless 引擎、Skill、模板、测试、schema、源码截取或记忆文件。此声明描述本次实现过程，不是法律保证。

## 输入计划

从新 Skill 根目录运行命令，`scripts/clip.py` 接收一个本地授权影音文件和 JSON 计划，可另传 UTF-8 SRT。

```json
{
  "clips": [
    {
      "source_start": 1.0,
      "source_end": 5.0,
      "speed": 1.0,
      "decision": "保留用户确认的完整表达",
      "protected_speech": [
        {"start": 1.2, "end": 4.8, "note": "这一句必须完整保留"}
      ],
      "caption_edits": []
    }
  ]
}
```

- 所有时间单位为秒，使用源视频播放时间轴。数字必须有限，布尔值不能充当数字。JSON 不允许重复字段或 NaN、Infinity。
- `source_start` 必须非负，`source_end` 必须大于起点且不超过 ffprobe 实际视频时长。缺少视频流时长时会扫描所选视频流包的实际边界，不用更长的音频尾部或容器时长授权不存在的画面。
- 区间必须按源顺序排列且互不重叠。相邻区间可首尾连接。
- `speed` 可省略，默认 `1`。支持 `0.5` 至 `2` 的有限数值，包含 `0.5`、`1`、`1.2` 和 `2`。
- 每段必须保留至少一个源帧和一个输出帧。输入必须包含可播放的视频流和音频流，帧率为 1 至 120 fps。
- `decision` 是必填非空文本，记录保留这段的语义决定，不承担自动语义判定。
- `protected_speech` 可省略。每条 `start`、`end` 必须全部位于所属区间中。切断已标注语音或让它跨越片段边界都会被拒绝。该检查只保护明确标注的语音，不能证明未标注语音完整。
- `caption_edits` 可省略。每条包含原始 SRT 的整数 `cue` 编号、`source_start`、`source_end` 和非空 `text`。替换 bounds 必须位于原 cue 和保留区间的交集中，可以缩小该交集。

## 字幕局部保留

原始 SRT 必须从 1 连续编号，时间单调不重叠，无负时间、零时长、空文案或超出源视频的时间。支持中文和多行文本。

一个 cue 如果被完整保留，默认使用原文。如果剪切只保留 cue 的一部分，必须为该保留片段明确给出替换文本和源秒边界，不能静默沿用整句。一个 cue 被切成两段时，两段分别需要替换。

```json
{
  "clips": [
    {
      "source_start": 1.4,
      "source_end": 2.8,
      "decision": "用户确认保留句子中的这一部分",
      "caption_edits": [
        {"cue": 1, "source_start": 1.4, "source_end": 2.7, "text": "用户确认的节选文本"}
      ]
    }
  ]
}
```

以上数字只演示结构，必须根据真实视频和字幕重新填写。SRT 输出按毫秒舍入；舍入后出现重叠、零时长或越界会被拒绝。字幕覆盖比例只表示时间覆盖，不证明文案正确或与声音对齐。

## 可编辑项目

`create` 输出如下顶层结构：

```json
{
  "format": "ah-talking-head-project",
  "format_revision": 1,
  "created_utc": "UTC 时间",
  "source": {"file": "源文件绝对路径", "sha256": "SHA-256", "media_at_creation": {}},
  "caption_source": null,
  "clips": [],
  "creation_mapping": {"duration_seconds": 0, "clips": [], "captions": []},
  "verification_limits": {}
}
```

这是结构说明，不是可执行项目：真实项目需要非空 `clips` 和实际哈希、时长。提供 SRT 时 `caption_source` 是含 `file`、`sha256`、`cues` 的对象，`cues` 是已读取的原始 cue。

`clips` 是编辑的主数据。修改区间、速度、保护标记和字幕替换后，`inspect`、`validate`、`render` 都重新计算时间轴。`creation_mapping` 只是创建时快照；与当前区间不同会在 inspect 中明确报告，不会拿旧快照渲染。

映射中每段记录源起止、速度和 `timeline_start`、`timeline_end`。字幕映射记录原 cue、所属片段、源起止、输出起止、最终文本和是否明确替换。输出时长为每个源区间时长除以速度的和。

原始 SRT cue 和 SHA-256 不作为文本编辑入口。文案修改使用 `caption_edits`。源文件或字幕文件哈希不匹配会在创建渲染目录之前失败。不要通过手工改哈希来掩盖素材变化；素材变化后重新创建项目。

## 命令和产物

```sh
python3 scripts/clip.py doctor
python3 scripts/clip.py create --source '/绝对路径/授权视频.mp4' --plan '/绝对路径/计划.json' --project '/绝对路径/新项目.json' --srt '/绝对路径/源字幕.srt'
python3 scripts/clip.py inspect --project '/绝对路径/新项目.json'
python3 scripts/clip.py validate --project '/绝对路径/新项目.json'
python3 scripts/clip.py render --project '/绝对路径/新项目.json' --output-dir '/绝对路径/新渲染目录'
python3 scripts/clip.py audit --output-dir '/绝对路径/新渲染目录'
```

无 SRT 时省略 `--srt`。项目路径必须是新路径，渲染目录必须不存在。路径按实际解析后的文件检查，源文件、已有项目和已有输出均不覆盖。对子进程传递参数数组，不拼接 shell 字符串。

成功渲染目录内包含：

- `edited.mp4`：H.264 视频和 48 kHz AAC 音频。
- `captions.srt`：独立映射字幕；无源字幕时为空文件，不自动生成文字。
- `validation-report.json`：实际流、帧、时长、完整解码检查、输入和输出哈希、真实映射和验证边界。

失败渲染保留 `validation-report.json` 和已有中间产物，状态为 `failed`，不会标记完成。`audit` 只读复核完成报告、输出哈希、字幕时间和实际音视频完整解码，不覆盖原报告。

渲染按 trim、atrim、时间戳归零、速度变换和 concat 完成。各段视频不会因向上舍入帧数而逐段拖长音频时间轴，最后统一采样输出帧率。音频做必要的时间轴补齐。报告记录实际工具版本、命令参数及帧和音频采样分辨率。源文件未被修改。

视频和容器时长容差为 `2 / fps + 2 * 1024 / 48000 + clip_count / 48000` 秒。音频时长容差为 `2 * 1024 / 48000 + clip_count / 48000` 秒。`fps` 是实测源帧率，1024 是 AAC 包采样数。视频边界采样精度为一帧，音频边界为一个采样；机器检查同时要求实际帧存在、尺寸符合预期、音视频流与编码正确及完整解码成功。

机器检查通过之后仍保留 `human_listening: unverified`、`caption_wording_and_audio_alignment: unverified` 和 `native_jianying_project: unsupported_and_unverified`。这些检查不构成完整人工试听，也不构成剪映原生工程验收。

## 测试

完整开发仓库含 `tests/test_clip.py`；从该开发仓库根目录运行：

```sh
python3 -B -m unittest discover -s tests -p test_clip.py -v
```

单独安装Skill时不必运行开发测试套件，用 `doctor` 和当次产物的 `audit` 验证运行环境与实际输出。开发测试的合成素材和输出只写入 `evidence/core-tests`，不纳入发布包。测试检查计划拒绝、保护语音、字幕歧义、速度映射、哈希变化、路径别名、失败回执和实际音视频编码解码。不同颜色和不同频率的合成片段验证实际画面及声音取段与顺序；20 个含小数帧边界的片段验证舍入误差不逐段累计。
