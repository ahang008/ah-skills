# 阿杭 Skills




阿杭公开的 Codex Skills 集合。




这里不堆提示词，也不把概念 Demo 当成成品。工具 Skill 来自真实工作流，包含可运行脚本、使用边界、测试和来源说明；系列入口提供制作范围与外部依赖的编排，具体运行能力由依赖提供。




阿杭的X链接：https://x.com/Astronaut_1216，微信是zephyr136，欢迎查看个人网站：zephyr8.asia



![ah-douyin-clean-downloader 工作流](assets/ah-douyin-clean-downloader-flow.png)




## 已公开 Skills




| Skill | 能做什么 | 状态 |
|---|---|---|
| [ah-think](https://github.com/ahang008/ah-think) | 澄清目标与取舍，检查现实条件和反馈，帮助思考并保留自主决定；当前为试用 MVP | [v0.1.2 试用](https://github.com/ahang008/ah-think/releases/tag/v0.1.2) |
| [ah-douyin-clean-downloader](https://github.com/ahang008/ah-douyin-clean-downloader) | 把抖音官方链接或分享口令发给 Codex，获取无抖音平台角标的播放源，保留原音视频，并在桌面按博主自动分类 | [v0.1.0](https://github.com/ahang008/ah-douyin-clean-downloader/releases/tag/v0.1.0) |
| [ah-longform-clip-matrix](https://github.com/ahang008/ah-longform-clip-matrix) | 围绕不同观众问题跨位置重组长口播，生成切片候选、来源时间映射与明确的内容验收状态；[查看架构图](https://github.com/ahang008/ah-longform-clip-matrix/blob/main/assets/长内容切片矩阵Skill架构.png)和[可编辑源文件](https://github.com/ahang008/ah-longform-clip-matrix/blob/main/docs/长内容切片矩阵Skill架构.excalidraw) | 已发布 |
| [ah-ai-blogger-video](skills/ah-ai-blogger-video) | AI博主系列入口：选择字幕、倍速与归档参数，调用另行安装的剪辑引擎和封面 Skill | 系列入口；外部依赖另装 |
| [ah-weightloss-video](skills/ah-weightloss-video) | 减肥系列入口：沿用本系列已确认的制作参数，调用另行安装的剪辑引擎与封面流程 | 系列入口；外部依赖另装 |
| [ah-gemini-script-polisher](skills/ah-gemini-script-polisher) | 把 Codex 已确认的上下文交给 Gemini 润色中文口播，核对完整正文与事实；Flash 写作、Pro 讨论桥的架构 | 首版试用；官网桥接 |




后续新增工具 Skill 统一使用 `ah-` 前缀，并建立独立 GitHub 仓库。本仓库负责品牌目录和索引，同时收录阿杭独立编写的两个系列入口，以及本次明确发布在此仓库的 Gemini 写作桥试用包；系列入口只编排外部 Skill，不包含第三方剪辑引擎。来源、发布范围和依赖许可见 [来源说明](PROVENANCE.md)与[第三方说明](THIRD_PARTY_NOTICES.md)。




## 安装单个 Skill




```text
安装这个 Skill：https://github.com/ahang008/ah-douyin-clean-downloader
```




把上面这句话发给 Codex。安装完成后，新开一轮对话，再发送抖音官方链接或完整分享口令即可。




具体环境要求、触发规则和使用边界见对应 Skill 的 README 和 SKILL.md。




## 仓库约定




- 工具 Skill 默认使用独立 GitHub 仓库；`skills/` 保存上述系列入口和 Gemini 写作桥的公开试用包。本机已安装的 Skill 保持原有路径，公开版本不自动覆盖本机版本。

合作推广：受众是跨境出海、独立开发者、AI视频爱好者。产品推广、模型测评。相关产品如需推广，可以和我联系。微信 Zephyr136。邮箱 a1165094791@gmail.com。X：https://x.com/Astronaut_1216
