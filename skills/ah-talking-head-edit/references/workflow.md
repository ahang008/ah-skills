# 独立口播剪辑工作流

## 请求示例

以下是可移植输入示例。执行时替换实际文件和已审核区间，不能将示例数字套用于其他素材。

> 使用 $ah-talking-head-edit 做独立口播剪辑。输入是我有权使用的 `输入/授权口播.mp4` 与 `输入/授权口播.srt`。保留已经核听的源区间 0.5 至 3.5 秒、6.0 至 9.0 秒，删除中间重录。保持原速，不加音乐。第一段字幕 cue 1 原本覆盖 0 至 4 秒，我已核听保留发音并确认保留文字为"先说结论"；第二段完整保留 cue 2。按下面计划交付可编辑 JSON 工程、MP4、同步 SRT 和校验报告，输出到新的目录。记录本次实际人工听音范围。

输入 SRT 示例:

```srt
1
00:00:00,000 --> 00:00:04,000
先说结论这句重来

2
00:00:06,000 --> 00:00:09,000
再解释原因
```

计划保存为 `任务/01-独立口播剪辑计划.json`:

```json
{
  "clips": [
    {
      "source_start": 0.5,
      "source_end": 3.5,
      "speed": 1,
      "decision": "按用户已核听边界保留首句，删除后续重录",
      "protected_speech": [
        {"start": 0.6, "end": 3.3, "note": "用户已核听的完整发音"}
      ],
      "caption_edits": [
        {"cue": 1, "source_start": 0.5, "source_end": 3.5, "text": "先说结论"}
      ]
    },
    {
      "source_start": 6.0,
      "source_end": 9.0,
      "speed": 1,
      "decision": "保留完整解释句",
      "protected_speech": [
        {"start": 6.0, "end": 9.0, "note": "用户要求完整保留"}
      ],
      "caption_edits": []
    }
  ]
}
```

此例删除 3.5 至 6.0 秒；不得根据字幕文字再猜缩音节。cue 1 被部分保留，所以替换字幕必须给出保留区间和保留文字。上述发音与数字仅由示例请求指定，不是脚本推断结果。

## 命令顺序

定位 `SKILL.md` 所在的 Skill 根目录。以下全部在该目录执行，`输入/` 与 `任务/` 由当次任务提供，输出目录尚不存在。可独立搬移整个 Skill 目录；不要只复制 `SKILL.md`。

```sh
python3 scripts/clip.py doctor
python3 scripts/clip.py create --help
python3 scripts/clip.py create --source 输入/授权口播.mp4 --plan 任务/01-独立口播剪辑计划.json --project 任务/02-独立口播剪辑工程.json --srt 输入/授权口播.srt
python3 scripts/clip.py inspect --project 任务/02-独立口播剪辑工程.json
python3 scripts/clip.py validate --project 任务/02-独立口播剪辑工程.json
python3 scripts/clip.py render --project 任务/02-独立口播剪辑工程.json --output-dir 任务/03-独立口播剪辑交付
python3 scripts/clip.py audit --output-dir 任务/03-独立口播剪辑交付
```

在有空格的实际路径外加 shell 引号。`doctor` 未通过时依据其输出处理缺失运行条件，不自动安装全局依赖。导出和审计前先查看对应 `--help`。

脚本先从 `PATH` 查找 FFmpeg 和 ffprobe，再使用 Homebrew 路径兜底；各子命令均可用 `--ffmpeg` 和 `--ffprobe` 指定可执行文件路径。

成功导出后读取目录内的 `edited.mp4`、`captions.srt` 和 `validation-report.json`。无源 SRT 时脚本只输出空字幕文件，不能将它宣称为已生成字幕；用户要求字幕时须先提供可靠时间戳和文字。失败报告与残留文件不得列为完成交付。

## 改计划与验收

- 修改计划后重新创建工程并复验，再导出到新的目录。禁止覆盖或删除原素材。
- 按源时间顺序排列 clips，不得重叠或倒序。第一版速度支持 `0.5` 至 `2`，默认 `1`；用户要求超出此范围时如实说明限制，不静默改成另一速度。
- 用原始 cue 的连续整数编号引用字幕。部分 cue 的每个保留片段均须明确替换文字；替换边界必须位于该原 cue 与所属 clip 的交集内。
- 若一句话在多段中保留，分别确认各片段文字、发音边界和上下文。已有字幕文字不能证明端点准确。
- `protected_speech` 只保护明确标出的源区间，不能代替语义或听音验收。任何保护区间越过 clip 边界都须修复。
- 以实际返回的产物路径和审计内容汇报，不凭扩展名、JSON 存在或进程退出判断全部完成。
- 单列人工听音状态。仅用户提供的审核边界只能记为用户已核听；代理只有实际听过才记录代理核听。机器检查不能升级为全片人工核听。
- 外置 SRT 的局部替换不会改画面内烧录字幕。输入成片已有字幕时，输出会保留这些画面；说明画面旧字幕与外置字幕的差异，不宣称完成画面字幕替换。
- 原生剪映草稿、直接导入、音乐混合、自动 ASR 和自动静音剪切均不属于本版交付。
