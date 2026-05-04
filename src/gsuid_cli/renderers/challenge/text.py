from __future__ import annotations

from collections.abc import Mapping, Sequence

from gsuid_cli.renderers.challenge.common import timestamp_text
from gsuid_cli.renderers.common import int_value, sequence, text_value

DIFFICULTY_LABELS = {
    1: "简单模式",
    2: "普通模式",
    3: "困难模式",
    4: "卓越模式",
    5: "月喻模式",
}
RANKING_LABELS = {
    "damage_rank": "最强一击",
    "defeat_rank": "最多击破",
    "take_damage_rank": "承受伤害",
    "energy_skill_rank": "元素爆发",
}


def render_challenge_abyss_text(
    *,
    uid: str,
    abyss: Mapping[str, object],
    summary: Mapping[str, object],
) -> str:
    names = _summary_avatar_names(summary)
    lines = [f"深境螺旋 - {_nickname(summary)}", f"UID: {uid}"]
    lines.append(f"挑战次数: {int_value(abyss.get('total_battle_times'))}")
    if abyss.get("max_floor") not in (None, ""):
        lines.append(f"最高层数: {abyss['max_floor']}")
    if abyss.get("total_star") not in (None, ""):
        lines.append(f"总星数: {abyss['total_star']}")

    rankings = _mapping(abyss.get("rankings"))
    ranking_lines = []
    for key, label in RANKING_LABELS.items():
        character = _first_mapping(rankings.get(key))
        if character:
            ranking_lines.append(
                f"  - {label}: {_character_name(character, names)} {character.get('value')}"
            )
    if ranking_lines:
        lines.extend(["", "战绩排行:"])
        lines.extend(ranking_lines)

    floors = _abyss_floors(abyss)
    if not floors:
        lines.extend(["", "暂无深境螺旋楼层记录"])
        return _finish(lines)

    lines.extend(["", "楼层:"])
    for floor in floors:
        index = int_value(floor.get("index"))
        star = int_value(floor.get("star"))
        max_star = int_value(floor.get("max_star"), 9)
        heading = f"  - 第{index}层: {star}/{max_star}星"
        settle = text_value(floor.get("settle_time"))
        if settle and settle not in {"0", "0000-00-00 00:00:00"}:
            heading += f"，结算 {settle}"
        lines.append(heading)
        for level_index, level in enumerate(_mapping_list(floor.get("levels")), start=1):
            lines.append(f"    第{level_index}间: {int_value(level.get('star'))}/3星")
            for battle_index, battle in enumerate(_mapping_list(level.get("battles")), start=1):
                time_text = timestamp_text(battle.get("timestamp"))
                if time_text:
                    lines.append(f"      第{battle_index}队: {time_text}")
                avatars = _character_names(_mapping_list(battle.get("avatars")), names)
                if avatars:
                    lines.append(f"        角色: {'、'.join(avatars)}")
    return _finish(lines)


def render_challenge_theater_text(
    *,
    uid: str,
    theater: Mapping[str, object],
    summary: Mapping[str, object],
) -> str:
    names = _summary_avatar_names(summary)
    session = _mapping(theater.get("selected"))
    detail = _mapping(session.get("detail"))
    stat = _mapping(session.get("stat")) or _mapping(detail.get("detail_stat"))
    fight = _mapping(detail.get("fight_statisic"))
    schedule = _mapping(session.get("schedule"))
    lines = [f"幻想真境剧诗 - {_nickname(summary)}", f"UID: {uid}"]
    difficulty_id = int_value(stat.get("difficulty_id"))
    difficulty = DIFFICULTY_LABELS.get(difficulty_id)
    if difficulty_id and difficulty:
        lines.append(f"难度: {difficulty}")
    max_round, medal = _theater_round_medal_counts(stat)
    if max_round or medal:
        lines.append(f"幕数/星章: {int_value(stat.get('max_round_id'))}幕，{medal}/{max_round}")
    time_range = _time_range(schedule.get("start_time"), schedule.get("end_time"))
    if time_range:
        lines.append(f"时间: {time_range}")
    total_time = int_value(fight.get("total_use_time"))
    if total_time:
        lines.append(f"用时: {total_time // 60}分{total_time % 60}秒")
    max_damage = _mapping(fight.get("max_damage_avatar"))
    if max_damage:
        lines.append(f"最高伤害: {_character_name(max_damage, names)} {max_damage.get('value')}")

    rounds = _filtered_theater_rounds(_mapping_list(detail.get("rounds_data")))
    if not rounds:
        lines.extend(["", "暂无幻想真境剧诗挑战记录"])
        return _finish(lines)

    lines.extend(["", "幕次:"])
    for round_data in rounds:
        label = (
            f"圣牌{int_value(round_data.get('tarot_serial_no'))}"
            if round_data.get("is_tarot")
            else f"第{int_value(round_data.get('round_id'))}幕"
        )
        medal_text = "已获星章" if round_data.get("is_get_medal") else "未获星章"
        lines.append(f"  - {label}: {medal_text}")
        enemies = [
            text_value(enemy.get("name")) for enemy in _mapping_list(round_data.get("enemies"))
        ]
        enemies = [enemy for enemy in enemies if enemy]
        if enemies:
            lines.append(f"    敌人: {'、'.join(enemies)}")
        buffs = _theater_buff_texts(round_data)
        if buffs:
            lines.append(f"    幻剧之花: {'、'.join(buffs)}")
        avatars = _character_names(_mapping_list(round_data.get("avatars")), names)
        if avatars:
            lines.append(f"    角色: {'、'.join(avatars)}")
    return _finish(lines)


def render_challenge_hard_text(
    *,
    uid: str,
    hard: Mapping[str, object],
    summary: Mapping[str, object],
) -> str:
    names = _summary_avatar_names(summary)
    schedule, single = _hard_sections(hard)
    lines = [f"幽境危战 - {_nickname(summary)}", f"UID: {uid}"]
    time_range = _time_range(schedule.get("start_time"), schedule.get("end_time"), date_only=True)
    if time_range:
        lines.append(f"时间: {time_range}")
    best = _mapping(single.get("best"))
    if best:
        if best.get("difficulty") not in (None, ""):
            lines.append(f"最高难度: {best['difficulty']}")
        if best.get("second") not in (None, ""):
            lines.append(f"最佳用时: {best['second']}秒")

    challenges = _mapping_list(single.get("challenge"))
    if not challenges:
        lines.extend(["", "暂无幽境危战挑战记录"])
        return _finish(lines)

    lines.extend(["", "关卡:"])
    for challenge in challenges:
        name = text_value(challenge.get("name")) or "未命名关卡"
        seconds = int_value(challenge.get("second"))
        lines.append(f"  - {name}: {seconds}秒" if seconds else f"  - {name}")
        monster = _mapping(challenge.get("monster"))
        if monster:
            monster_text = text_value(monster.get("name")) or "敌人"
            level = int_value(monster.get("level"))
            if level:
                monster_text += f" Lv{level}"
            lines.append(f"    敌人: {monster_text}")
        teams = _character_names(_mapping_list(challenge.get("teams")), names)
        if teams:
            lines.append(f"    队伍: {'、'.join(teams)}")
        best_avatars = _mapping_list(challenge.get("best_avatar"))
        if best_avatars:
            lines.append(f"    最强一击: {_hard_best_avatar_text(best_avatars[0], names)}")
        if len(best_avatars) > 1:
            lines.append(f"    最高总伤: {_hard_best_avatar_text(best_avatars[1], names)}")
    return _finish(lines)


def render_challenge_hard_rank_text(data: Mapping[str, object]) -> str:
    lines = [
        "幽境危战排行",
        f"可用: {'是' if data.get('available') else '否'}",
        f"数量: {data.get('count', 0)}",
    ]
    limitations = [
        text
        for text in (text_value(item) for item in sequence(data.get("source_limitations")))
        if text
    ]
    if limitations:
        lines.extend(["", "来源限制:"])
        lines.extend(f"  - {limitation}" for limitation in limitations)
    return _finish(lines)


def _theater_round_medal_counts(stat: Mapping[str, object]) -> tuple[int, int]:
    difficulty_id = int_value(stat.get("difficulty_id"))
    max_round = int_value(stat.get("max_round_id"))
    medal = int_value(stat.get("medal_num"))
    if difficulty_id == 5:
        max_round = 12
        medal += int_value(stat.get("tarot_finished_cnt"))
    return max_round, medal


def _filtered_theater_rounds(rounds: list[Mapping[str, object]]) -> list[Mapping[str, object]]:
    tarot_count = sum(1 for item in rounds if item.get("is_tarot") is True)
    if tarot_count <= 2:
        return rounds
    return [
        item
        for item in rounds
        if not item.get("is_tarot", False) or item.get("is_get_medal", False)
    ]


def _theater_buff_texts(round_data: Mapping[str, object]) -> list[str]:
    splendour = _mapping(round_data.get("splendour_buff"))
    lines = []
    for buff in _mapping_list(splendour.get("buffs")):
        name = text_value(buff.get("name")) or "祝福"
        level = int_value(buff.get("level"))
        lines.append(f"{name} Lv{level}" if level else name)
    return lines


def _hard_sections(hard: Mapping[str, object]) -> tuple[Mapping[str, object], Mapping[str, object]]:
    root = hard.get("hard_challenge")
    root = root if isinstance(root, Mapping) else hard
    sessions = root.get("data") if isinstance(root, Mapping) else None
    session = {}
    if isinstance(sessions, list) and sessions and isinstance(sessions[0], Mapping):
        session = sessions[0]
    elif isinstance(root, Mapping):
        session = root
    schedule = session.get("schedule") if isinstance(session.get("schedule"), Mapping) else {}
    single = session.get("single") if isinstance(session.get("single"), Mapping) else session
    return schedule, single if isinstance(single, Mapping) else {}


def _hard_best_avatar_text(avatar: Mapping[str, object], names: Mapping[str, str]) -> str:
    name = _character_name(avatar, names)
    value = avatar.get("dps") or avatar.get("value")
    return f"{name} {value}" if value not in (None, "") else name


def _time_range(start: object, end: object, *, date_only: bool = False) -> str | None:
    start_text = timestamp_text(start, date_only=date_only)
    end_text = timestamp_text(end, date_only=date_only)
    if start_text and end_text:
        return f"{start_text} 至 {end_text}"
    return start_text or end_text or None


def _nickname(summary: Mapping[str, object]) -> str:
    role = _mapping(summary.get("role"))
    return text_value(role.get("nickname")) or "旅行者"


def _character_names(
    characters: Sequence[Mapping[str, object]],
    names: Mapping[str, str],
) -> list[str]:
    return [name for character in characters if (name := _character_name(character, names))]


def _character_name(character: Mapping[str, object], names: Mapping[str, str]) -> str:
    name = text_value(character.get("name"))
    if name:
        return name
    avatar_id = character.get("avatar_id", character.get("id"))
    mapped = names.get(str(avatar_id))
    if mapped:
        return mapped
    return f"角色{avatar_id}" if avatar_id not in (None, "") else "未知角色"


def _summary_avatar_names(summary: Mapping[str, object]) -> dict[str, str]:
    names = {}
    for avatar in _mapping_list(summary.get("avatars")):
        avatar_id = avatar.get("id", avatar.get("avatar_id"))
        name = text_value(avatar.get("name"))
        if avatar_id not in (None, "") and name:
            names[str(avatar_id)] = name
    return names


def _abyss_floors(abyss: Mapping[str, object]) -> list[Mapping[str, object]]:
    return sorted(
        [
            floor
            for floor in _mapping_list(abyss.get("floors"))
            if int_value(floor.get("index")) >= 9
        ],
        key=lambda floor: int_value(floor.get("index")),
    )


def _first_mapping(value: object) -> Mapping[str, object]:
    values = _mapping_list(value)
    return values[0] if values else {}


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    return [item for item in sequence(value) if isinstance(item, Mapping)]


def _finish(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"
