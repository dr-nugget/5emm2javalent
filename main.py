"""Converts 5emm JSON statblock to javalent Fantasy Statblock"""

import json
from argparse import ArgumentParser
from collections import Counter
from math import floor
from pathlib import Path

import yaml
from num2words import num2words


ABILITIES = {
    "STR": "strength",
    "DEX": "dexterity",
    "CON": "constitution",
    "INT": "intelligence",
    "WIS": "wisdom",
    "CHA": "charisma",
}


def calc_modifier(score: int) -> int:
    """Converts an ability score to a modifier."""
    return (score - 10) // 2


def dice_avg(dice_type: int) -> float:
    """Returns the average roll of a dice type."""
    return (dice_type + 1) / 2


def calc_dice(count: int, dice_type: int) -> int:
    """Returns the floored average of {count}d{dice_type}."""
    return floor(count * dice_avg(dice_type))


def damage_str(count: int, dice_type: int, modifier: int, damage_type: str) -> str:
    """Returns the string for damage."""
    return (
        f"{calc_dice(count, dice_type) + modifier} "
        f"({count}d{dice_type}{modifier:+}) "
        f"{damage_type} damage"
    )


def process_multiattack(json_stats: dict) -> str:
    """Generate the text for multiattacks."""
    # Adapted from `processMultiattackTokens` in the 5emm code
    # https://github.com/ebshimizu/5e-monster-maker/blob/892cc096e5dc5b927afa7c337de87f74325a320d/src/components/rendering/useProcessTokens.ts#L342

    rendered_ma = []

    for ma in json_stats["multiattacks"]:
        # Map attacks
        collated_attacks = Counter(ma["attacks"])

        # Render attacks
        attacks = []
        items = collated_attacks.items()
        for index, (id_, count) in enumerate(items):
            name = get_action(id_, json_stats)["name"]
            text = ""
            if index == len(items) - 1 and len(items) > 1:
                text += "and "
            text += f"{num2words(count)} {name} attack"
            if count > 1:
                text += "s"
            attacks.append(text)

        # Map actions
        collated_actions = Counter(ma["actions"])

        # Render actions
        actions = []
        for id_, count in collated_actions.items():
            name = get_action(id_, json_stats)["name"]
            attacks.append(f"{num2words(count)} {name}")

        # The full string
        if actions:
            multiattack_all = (
                f"uses {', '.join(actions)} followed by {', '.join(attacks)}"
                if attacks
                else ""
            )
        else:
            multiattack_all = f"makes {', '.join(attacks)}"

        rendered_ma.append(multiattack_all)

    # Render everything
    multiattack_all = f"{json_stats['name']} {' or '.join(rendered_ma)}."
    return multiattack_all


def get_action(id_: str, json_stats: dict) -> dict:
    """Get the attack or action with the given ID."""
    for attack in json_stats["attacks"]:
        if attack["id"] == id_:
            return attack
    for action in json_stats["actions"]:
        if action["id"] == id_:
            return action
    raise ValueError(f"Attack with ID {id_} not found")


def process_attacks(json_stats: dict) -> list[dict[str, str]]:
    """Generates the list of attacks"""
    attacks = []
    for attack in json_stats["attacks"]:
        attack_str = ""
        distance = attack["distance"]
        if distance == "BOTH":
            distance = "Melee or Ranged"
        attack_str += f"{distance} {attack['kind']} Attack: ".title()

        modifier = attack["modifier"]
        if modifier["override"]:
            modifier = modifier["overrideValue"]
        else:
            modifier = calc_modifier(json_stats["stats"][modifier["stat"]])
        attack_str += f"{modifier:+} to hit, "

        reach = ""
        range_ = ""
        if attack["distance"] in {"BOTH", "MELEE"}:
            reach = f"reach {attack['range']['reach']} ft."
        if attack["distance"] in {"BOTH", "RANGED"}:
            range_ = f"range {attack['range']['standard']/attack['range']['long']} ft."
        attack_str += " or ".join(filter(None, [reach, range_])) + ", "

        targets = attack["targets"]
        attack_str += f"{num2words(targets)} target{'s' if targets > 1 else ''}. "

        description = "Hit: "
        modifier = attack["damage"]["modifier"]
        if modifier["override"]:
            modifier = modifier["overrideValue"]
        else:
            modifier = calc_modifier(json_stats["stats"][modifier["stat"]])
        description += damage_str(
            attack["damage"]["count"],
            attack["damage"]["dice"],
            modifier,
            attack["damage"]["type"],
        )

        alternate_damage = attack["alternateDamage"]
        if alternate_damage["active"]:
            description += ", or "
            modifier = alternate_damage["modifier"]
            if modifier["override"]:
                modifier = modifier["overrideValue"]
            else:
                modifier = calc_modifier(json_stats["stats"][modifier["stat"]])
            description += damage_str(
                alternate_damage["count"],
                alternate_damage["dice"],
                modifier,
                attack["damage"]["type"],
            )
            description += f" {alternate_damage['condition']}"

        additional_damages = attack["additionalDamage"]
        if additional_damages:
            description += " plus "
            for i, damage in enumerate(additional_damages, start=1):
                description += damage_str(
                    damage["count"],
                    damage["dice"],
                    0,
                    damage["type"],
                )
                if i == len(additional_damages) - 1:
                    description += ", and "
                elif i < len(additional_damages):
                    description += ", "

        description += "."
        if attack["description"]:
            description += f" {attack['description']}"

        attacks.append(
            {
                "name": attack["name"],
                "desc": process_description(description, json_stats),
            }
        )

    return attacks


def process_action(action: dict, json_stats: dict) -> dict[str, str]:
    """Processes a single action, bonus action, or reaction"""
    name = action["name"]
    limited_use = action.get("limitedUse")
    # TODO: Implement actions that recharge on short rest
    if limited_use and limited_use["count"]:
        name += f" ({limited_use['count']}/day)"
    return {
        "name": name,
        "desc": process_description(action["description"], json_stats),
    }


def process_description(description: str, json_stats: dict) -> str:
    """Processes a description, replacing tags in braces with the correct text."""
    # Save DCs and attack modifiers
    prof_bonus = json_stats["proficiency"]
    for ability in ABILITIES:
        bonus = calc_modifier(json_stats["stats"][ability]) + prof_bonus
        description = description.replace(
            f"{{DC:{ability}}}",
            f"DC {8 + bonus}",
        ).replace(
            f"{{A:{ability}}}",
            f"{bonus:+}",
        )

    # Name
    name_str = json_stats["name"]
    if json_stats["useArticleInToken"]:
        name_str = f"the {name_str}"
    description = description.replace(
        "{monster.name}",
        name_str,
    ).replace(
        "{NAME}",
        name_str,
    )

    # Proficiency
    description = description.replace(
        "{monster.proficiency}",
        f"{prof_bonus}",
    )

    # Armor class
    description = description.replace(
        "{monster.AC}",
        f"{json_stats['AC']}",
    )

    # HP
    dice_count = json_stats["HP"]["HD"]
    hp_bonus = calc_modifier(json_stats["stats"]["CON"]) * dice_count
    description = description.replace(
        "{monster.hp}",
        f"{dice_count}d{json_stats['HP']['type']}{hp_bonus:+}",
    )

    return description


def process_legendary_actions(json_stats: dict) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for action_info in json_stats["legendaryActions"]["actions"]:
        action = get_action(action_info["actionId"], json_stats)
        if action["legendaryOnly"]:
            action = process_action(action, json_stats)
        else:
            action = {
                "name": action["name"],
                "desc": f"The {json_stats['name']} uses its {action['name']} action.",
            }
        cost = action_info["cost"]
        if cost != 1:
            action["name"] += f" (Costs {cost} Actions)"
    return actions


def process_speed(json_stats: dict) -> str:
    """Returns the string of speeds."""
    speed_strs = []
    for speed in json_stats["speeds"]:
        type_ = speed["type"]
        distance = speed["speed"]

        if type_ == "walk":
            string = f"{distance} ft."
        else:
            string = f"{type_} {distance} ft."

        if speed["note"]:
            string += f" ({speed['note']})"
        speed_strs.append(string)
    return ", ".join(speed_strs)


def parse_stats(json_stats: dict) -> dict:
    """
    Parses a dictionary stats from a 5emm statblock and returns a dictionary of
    javalent Fantasy Statblock stats.
    """

    stats = {"layout": "Basic 5e Layout", "dice": True}

    # Stats used for calculating other stats
    proficiency_bonus = json_stats["proficiency"]
    abilities = json_stats["stats"]

    # Identically named attributes
    identical_attributes = [
        "name",
        "size",
        "type",
        "alignment",
        "languages",
    ]
    for attr in identical_attributes:
        stats[attr] = json_stats[attr]

    # Other one-liner attributes
    stats["ac"] = json_stats["AC"]
    stats["cr"] = json_stats["CR"]
    stats["damage_vulnerabilities"] = ", ".join(json_stats["vulnerabilities"])
    stats["damage_resistances"] = ", ".join(json_stats["resistances"])
    stats["damage_immunities"] = ", ".join(json_stats["immunities"])
    stats["condition_immunities"] = ", ".join(json_stats["conditions"])

    # Speed
    stats["speed"] = process_speed(json_stats)

    # Ability scores
    stats["abilities"] = [
        abilities["STR"],
        abilities["DEX"],
        abilities["CON"],
        abilities["INT"],
        abilities["WIS"],
        abilities["CHA"],
    ]

    # Hit dice and hp
    hp_info = json_stats["HP"]
    num_dice = hp_info["HD"]
    dice_type = hp_info["type"]
    stats["hp"] = floor(
        dice_avg(dice_type) * num_dice + calc_modifier(abilities["CON"]) * num_dice
    )
    stats["hit_dice"] = f"{num_dice}d{dice_type}"

    # Saving throws
    saves = {}
    for abbr, stat in ABILITIES.items():
        json_save = json_stats["saves"][abbr]
        if json_save["override"]:
            saves[stat] = json_save["overrideValue"]
        elif json_save["proficient"]:
            saves[stat] = calc_modifier(abilities[abbr]) + proficiency_bonus

    # Skills
    skills = {}
    for json_skill in json_stats["skills"]:
        name = json_skill["skill"]["label"].lower()
        if json_skill["override"]:
            skills[name] = json_skill["overrideValue"]
        elif json_skill["proficient"]:
            skills[name] = (
                calc_modifier(abilities[json_skill["skill"]["stat"]])
                + proficiency_bonus
            )
            if json_skill["expertise"]:
                skills[name] += proficiency_bonus
    stats["skillsaves"] = skills

    # Senses
    sense_strs = []
    json_senses = json_stats["senses"]
    for sense in json_senses:
        distance = json_senses[sense]
        if distance:
            sense_strs.append(f"{sense.title()} {distance} ft.")
    # Passive perception
    perception = 0
    if "perception" in skills:
        perception += skills["perception"]
    sense_strs.append(f"Passive Perception {perception}")
    stats["senses"] = ", ".join(sense_strs)

    # TODO: Implement spells

    # Traits
    traits = []
    for json_trait in json_stats["traits"]:
        name = json_trait["name"]
        if (uses := json_trait["limitedUse"])["count"]:
            name.append(f" ({uses['count']}/{uses['rate']})")

        traits.append(
            {
                "name": name,
                "desc": process_description(json_trait["description"], json_stats),
            }
        )
    stats["traits"] = traits

    # Actions
    stats["actions"]: list[dict[str, str]] = []
    multiattack = process_multiattack(json_stats)
    if multiattack:
        stats["actions"].append(
            {"name": "Multiattack", "desc": process_multiattack(json_stats)}
        )
    stats["actions"].extend(process_attacks(json_stats))
    stats["actions"].extend(
        [
            process_action(action, json_stats)
            for action in json_stats["actions"]
            if not (action["legendaryOnly"] or action["bonusAction"])
        ]
    )

    # Reactions
    stats["reactions"] = [
        process_action(reaction, json_stats) for reaction in json_stats["reactions"]
    ]

    # Bonus actions
    stats["bonus_actions"] = [
        process_action(a, json_stats) for a in json_stats["actions"] if a["bonusAction"]
    ]

    stats["legendary_actions"] = process_legendary_actions(json_stats)

    return stats


def main(path: Path):
    """Main function"""
    with open(path, encoding="utf-8", mode="r") as f:
        json_stats = json.load(f)
    stats = parse_stats(json_stats)
    output = yaml.safe_dump(stats, sort_keys=False, indent=2)
    print(
        f"```statblock\n{output}\n```".strip()
    )


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    main(args.path.resolve())
