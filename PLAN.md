# AI 跑团游戏 — 开发计划

基于 **Python + Streamlit + LangChain** 的文字跑团（TRPG）游戏。

---

## 项目定位

**AI 跑团游戏**：玩家扮演角色，AI 担任 **KP（主持人）**，负责叙事、NPC 对话、规则判定与剧情推进。

| 组件 | 职责 |
|------|------|
| **Streamlit** | 聊天界面、角色面板、骰子、存档 |
| **LangChain** | LLM 调用、Prompt 管理、记忆、工具链 |
| **Python** | 游戏逻辑、状态机、数据持久化 |

---

## 核心功能模块

### 1. 游戏会话层

- 多轮对话（玩家输入 → KP 叙事 → 可选行动选项）
- 会话历史与上下文窗口管理
- 支持「继续上次冒险」/「新游戏」

### 2. 角色系统

- 创建角色：姓名、职业/背景、属性（STR/DEX/INT 等）
- 生命值、技能、背包
- 角色卡展示（Streamlit sidebar 或 expander）

### 3. KP（AI 主持人）引擎

- **系统 Prompt**：世界观、规则风格（COC / D&D 简化版 / 原创）
- **叙事生成**：场景描述、NPC 台词、事件触发
- **判定逻辑**：玩家声明行动 → 掷骰 → AI 解读结果并续写

### 4. 骰子与规则

- 常用骰：`1d20`、`2d6`、`1d100`（理智检定等）
- 可封装为 LangChain **Tool**，让 AI 主动调用
- 或由前端按钮触发，结果注入 Prompt

### 5. 记忆与状态

- **短期记忆**：最近 N 轮对话（ConversationBufferWindowMemory）
- **长期记忆**：关键事件摘要（SummaryMemory 或向量库）
- **结构化状态**：当前场景、在场 NPC、任务进度（JSON / SQLite）

### 6. 存档与读档

- 保存：角色 + 对话摘要 + 游戏状态
- 本地 JSON/SQLite，或 Streamlit session state + 文件

---

## 技术架构

```
┌─────────────────────────────────────────────────┐
│              Streamlit Frontend                  │
│  [聊天区] [角色卡] [骰子] [设置] [存档]           │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│           Game Orchestrator (Python)             │
│  状态机 · 回合流程 · 存档读写                     │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              LangChain Layer                     │
│  ChatModel · PromptTemplate · Memory · Tools     │
│  [掷骰Tool] [查规则Tool] [更新状态Tool]          │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│         LLM API (OpenAI / 本地 / 其他)           │
└─────────────────────────────────────────────────┘
```

---

## 目录结构

```
text_game_b/
├── app.py                 # Streamlit 入口
├── requirements.txt
├── .env.example           # API Key 等
├── config/
│   └── settings.py        # 模型、温度、世界观配置
├── prompts/
│   ├── kp_system.txt      # KP 系统 Prompt
│   └── templates.py       # LangChain PromptTemplate
├── game/
│   ├── models.py          # Character, GameState, Scene
│   ├── dice.py            # 掷骰逻辑
│   ├── rules.py           # 属性检定、伤害等
│   └── orchestrator.py    # 主游戏循环
├── chain/
│   ├── kp_chain.py        # KP 对话链
│   ├── memory.py          # 记忆管理
│   └── tools.py           # LangChain Tools（骰子等）
├── ui/
│   ├── chat.py            # 聊天组件
│   ├── character_sheet.py # 角色面板
│   └── components.py      # 通用 UI
├── data/
│   ├── saves/             # 存档
│   └── scenarios/         # 预设模组 JSON
└── tests/
    └── test_dice.py
```

---

## 分阶段开发计划

### Phase 1：最小可玩原型（约 1–2 周）

**目标**：能聊、能掷骰、有基本 KP 感

- [x] 初始化项目与依赖（`streamlit`, `langchain`, `langchain-openai` 等）
- [x] Streamlit 聊天界面 + 简单角色输入
- [x] KP 系统 Prompt（原创轻量规则即可）
- [x] 基础 LangChain 对话链（无 Memory 也可先跑通）
- [x] 手动掷骰按钮，结果写入下一轮 Prompt

**验收标准**：玩家描述行动，AI 叙事；点骰子后有结果并影响剧情。

---

### Phase 2：角色与规则（约 1 周）

**目标**：有「跑团」结构，而不只是聊天

- [x] `Character` 数据模型与角色创建流程
- [x] 属性检定：`1d20 + 属性修正 vs DC`
- [x] 将掷骰封装为 LangChain Tool，KP 可主动要求检定
- [x] Sidebar 角色卡（HP、属性、背包）

**验收标准**：KP 说「做一次敏捷检定」，系统能掷骰并给出 Pass/Fail 叙事。

---

### Phase 3：记忆与状态（约 1–2 周）

**目标**：长会话不丢设定、剧情连贯

- [x] ConversationBufferWindowMemory（最近 10–20 轮）
- [x] `GameState`：场景 ID、任务、NPC 关系
- [x] 每 N 轮自动生成「剧情摘要」写入长期记忆
- [x] Prompt 注入：当前场景 + 摘要 + 角色状态

**验收标准**：玩 30+ 轮后，AI 仍能记住关键 NPC 和任务。

---

### Phase 4：模组与存档（约 1 周）

**目标**：可重复游玩、可中断续玩

- [x] 预设模组 JSON（标题、开场、关键节点、结局条件）
- [x] 存档/读档（角色 + 状态 + 摘要）
- [x] 主菜单：新游戏 / 继续 / 选模组

**验收标准**：关掉浏览器再打开，能从存档继续。

---

### Phase 5：体验优化（可选）

- [x] 流式输出（`st.write_stream`）
- [x] 行动建议按钮（AI 生成 2–3 个选项）
- [x] 多世界观切换（克苏鲁 / 奇幻 / 赛博朋克 Prompt 包）
- [x] 简单战斗回合（先攻、攻击、伤害）
- [x] 场景图像（DALL·E / Stable Diffusion API）

---

## 关键设计决策

| 决策点 | 建议 |
|--------|------|
| **规则复杂度** | MVP 用简化原创规则，避免完整 D&D/COC 规则书 |
| **LLM 选型** | 开发用 GPT-4o-mini；叙事质量要求高时用 GPT-4o 或 Claude |
| **骰子谁掷** | 玩家点按钮 + AI 通过 Tool 请求检定，两种都支持 |
| **状态谁维护** | 结构化状态用 Python 存；叙事细节交给 LLM + 摘要 |
| **防跑题** | 系统 Prompt 强调「遵循模组节点 + 不要凭空改设定」 |

---

## 依赖

```txt
streamlit>=1.28.0
langchain>=0.3.0
langchain-openai>=0.2.0
langchain-community>=0.3.0
python-dotenv>=1.0.0
pydantic>=2.0.0
```

---

## 核心流程示意

### KP Chain

```python
def player_turn(user_input, game_state, character):
    # 1. 可选：解析是否需要检定
    # 2. 组装 prompt：系统 + 世界观 + 角色 + 状态 + 记忆 + 用户输入
    # 3. 调用 LangChain ChatModel（可 bind tools: roll_dice）
    # 4. 若 AI 调用 roll_dice → 执行 → 再喂回模型
    # 5. 更新 GameState、追加记忆
    # 6. 返回 KP 叙事文本
```

### Streamlit 主循环

```python
# session_state: messages, character, game_state
# 用户输入 → orchestrator.player_turn() → 追加到 messages → st.chat_message 展示
```

---

## 风险与应对

| 风险 | 应对 |
|------|------|
| AI 胡编设定 | 结构化 `GameState` + 摘要；Prompt 约束「不得 contradict 状态表」 |
| 上下文超长 | 窗口记忆 + 定期摘要；只注入当前场景相关 NPC |
| 检定不公平 | 骰子结果由 Python 生成，不由 LLM「假装」掷骰 |
| Streamlit 刷新丢状态 | `st.session_state` + 定期写存档文件 |

---

## 待确认事项

开始编码前需确定：

1. **世界观**：原创短模组 / 克苏鲁 / 奇幻？
2. **LLM**：OpenAI API / 本地 Ollama / 其他？
3. **规则风格**：简化 D&D 式 / COC 式 / 完全原创？

---

## 下一步

从 **Phase 1** 开始：搭建项目骨架（`app.py`、KP Prompt、基础对话链），实现最小可玩原型。
