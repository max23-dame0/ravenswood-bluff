import asyncio
from typing import Any
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.state.game_state import GameState, PlayerState, GamePhase
from src.state.event_log import GameEvent
from src.agents.ai_agent import AIAgent, Persona
from src.agents.memory.working_memory import Observation

class MockBackend:
    def __init__(self):
        self.captured_prompt = None

    async def generate(self, messages, **kwargs):
        self.captured_prompt = messages[0].content if messages else ""
        from src.llm.base_backend import LLMResponse
        from src.llm.base_backend import Message
        return LLMResponse(message=Message(role="assistant", content='{"action": "none"}'), usage={})

async def main():
    # 构造假玩家和假局势
    player = PlayerState(player_id="p6", name="Player 6", is_alive=True, role_id="imp", team="evil")
    teammate = PlayerState(player_id="p8", name="Player 8", is_alive=True, role_id="baron", team="evil")
    target = PlayerState(player_id="p1", name="Player 1", is_alive=True, role_id="washerwoman", team="good")
    
    state = GameState(
        players=(player, teammate, target),
        phase=GamePhase.DAY_DISCUSSION,
        day_number=1,
        round_number=1
    )
    
    agent = AIAgent(
        player_id="p6",
        name="Player 6",
        persona=Persona(
            description="你谁也不信，觉得每个人都在撒谎。你会抓住细节反复质问，试图从对方的反应中寻找破绽。",
            speaking_style="怀疑、犀利、经常连珠炮式提问"
        ),
        backend=MockBackend()
    )
    agent.team = "evil"
    agent.perceived_role_id = "imp"
    
    visible_state = agent._build_visible_state(state)
    
    # 塞入一些记忆
    # Objective memory
    agent.working_memory.remember_objective_info("evil_teammates", "【绝密推演可用】已知邪恶同伴名单：Player 8", day_number=1, round_number=1)
    agent.working_memory.remember_objective_info("nomination", "Player 1 提名了 Player 6", day_number=1, round_number=1)
    
    # Private memory
    agent.working_memory.remember_private_info("night_info", "你的 3 个不在场角色：厨师, 管家, 占卜师", day_number=1, round_number=1)
    
    # Public memory
    agent.working_memory.remember_public_info("public_fact", "Player 7 公开跳身份为 占卜师", day_number=1, round_number=1)
    
    # Impressions & thoughts
    agent.working_memory.impressions.append("目前局势对我极其不利，我必须全力反击。")
    agent.working_memory.internal_thoughts.append("如果我不投票，可能会被处决。")
    
    # Recent observations
    agent.working_memory.observations.append(Observation(observation_id="obs1", phase=GamePhase.DAY_DISCUSSION, round_number=1, content="Player 1 说：我觉得 6 号很有问题。"))
    
    # 伪造合法动作
    from src.agents.ai_agent import AgentActionLegalContext
    legal_context = AgentActionLegalContext(
        can_speak=True,
        can_nominate=True,
        can_vote=False,
    )
    
    # W3-C/A3-MEM-3: 严格按 MemoryTier 分块提取记忆
    objective_memories = agent.working_memory.get_objective_memory_summaries()
    high_confidence_memories = agent.working_memory.get_private_memory_summaries()
    public_memories = agent.working_memory.get_public_memory_summaries()
    
    tier_text_blocks = []
    if objective_memories:
        tier_text_blocks.append("【绝对客观事实 (OBJECTIVE - 100%可信)】\n" + "\n".join([f"- {m}" for m in objective_memories]))
    if high_confidence_memories:
        tier_text_blocks.append("【高可信度线索 (HIGH_CONFIDENCE - 夜晚结果或私密信息)】\n" + "\n".join([f"- {m}" for m in high_confidence_memories]))
    if public_memories:
        tier_text_blocks.append("【公开讨论与声明 (PUBLIC - 可能存在欺骗与伪装)】\n" + "\n".join([f"- {m}" for m in public_memories[-15:]]))
    
    tiered_memory_text = "\n\n".join(tier_text_blocks)
    obs_text = agent.working_memory.get_recent_context(agent._obs_limit)
    episodic_text = agent.episodic_memory.get_summary(max_episodes=8)
    social_text = agent.social_graph.get_graph_summary()
    visible_state_text = agent._build_visible_state_summary(visible_state)
    
    visible_players = ", ".join(
        f"{p.name}({p.player_id},{'alive' if p.is_alive else 'dead'})"
        for p in visible_state.players
    )
    action_type = "speak"
    action_context = agent._build_action_context(visible_state, legal_context, action_type)
    persona_block = agent._build_persona_prompt_block(action_type, visible_state)

    system_prompt = f"""你是一名正在玩《血染钟楼》(Blood on the Clocktower) 的真实玩家。
你的名字是 {agent.name}，你认知的角色是 {agent.perceived_role_id}，阵营是 {agent.team}。
你的个性是：{agent.persona.description}，表达风格是：{agent.persona.speaking_style}。

【核心原则：玩家优先级】
1. **你是玩家，不是 AI**：表现得像一个人在和朋友社交。会有犹豫、怀疑、幽默或偶尔的强势。
2. **社交推演**：除了规则和技能，更要关注别人的发言逻辑以及过往行为的一致性。
3. **保密与欺骗 (CRITICAL)**：
   - 如果你是邪恶阵营：**绝对不可**在公开频道（speak）中直接承认你的真实身份或泄露队友、真实技能结果。你必须伪装成一个好人。**严禁直接背诵你的私密信息或队友名单**。
   - 如果你是正义阵营：也要保护好你的关键信息，除非你认为说出来对正义方更有利。
   - 所有的【高可信度线索】和【绝对客观事实】都是你的私人底牌，**严禁**直接照抄到 content 中。你必须经过拟人化的加工。
4. **沉浸式对话**：发言要自然，像在群聊或面杀现场。禁止使用“我更信的一条线”、“根据事实记录”等生硬开场。
5. **拒绝机械复述**：不要单纯复述场上的已知公共信息（如：谁死了、谁被提名了）。这些信息每个人都知道。你应当关注的是这些信息背后的意义，或者别人没发现的疑点。
6. **长线记忆**：不要只看眼前，要结合你在“往期回忆”和“社交图谱”中记录的线索。
7. **记忆权重**：【绝对客观事实】与【高可信度线索】是你推演的基石。如果公开说法和高可信信息冲突，请更偏向高可信信息。

{persona_block}

【你的记忆与档案】
{episodic_text}

{social_text}

【你可见的局势摘要】
{visible_state_text}

当前游戏状态：
- 阶段：{visible_state.phase} (第 {visible_state.day_number} 天, 第 {visible_state.round_number} 轮)
- 你看到的身份：{agent.perceived_role_id} ({agent.team} 阵营)
- 当前玩家列表：{visible_players}
- 当前需要执行的动作类型：{action_type}
- 当前动作补充要求：{action_context}

【你的目标】
{"作为邪恶阵营，隐藏恶魔，混淆视听，剪除正义之士。" if agent.team == "evil" else "作为正义阵营，通过逻辑与沟通找出恶魔并处决。"}

【核心分层记忆】
{tiered_memory_text}

【近期临时观察 (仅供参考上下文)】
{obs_text}

【JSON 格式规范】
请务必返回如下结构的 JSON，不要包含任何多余文字：
{{
  "action": "speak/nominate/vote/night_action/slayer_shot/skip_discussion/none",
  "content": "你的中文发言内容 (仅 speak 时需要)",
  "tone": "语气 (calm/passionate/accusatory/defensive)",
  "target": "player_id (nominate/slayer_shot 时为字符串；night_action 时若角色需多目标可为 [id1, id2] 或 'id1,id2')",
  "targets": ["player_id1", "player_id2"],
  "decision": true/false (仅 vote 时需要),
  "reasoning": "此处写下你作为一个玩家的真实心境和逻辑推理（不公开）"
}}"""

    out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'docs', 'alpha-1.0-plan', 'sample_prompt.md'))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# 当前 AI 动作决策 Prompt 结构样例\n\n```text\n")
        f.write(system_prompt)
        f.write("\n```\n")
    print(f"Prompt exported to {out_path}")

if __name__ == "__main__":
    asyncio.run(main())
