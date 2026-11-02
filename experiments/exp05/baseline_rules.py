"""基础条件规则，供样例对照。"""
import re

RULES = [
    {"id": "R_IF_THEN", "priority": 1},
    {"id": "R_FOR", "priority": 2},
    {"id": "R_VISITOR_PROFILE", "priority": 3},
    {"id": "R_COMPANION_CONTEXT", "priority": 4},
    {"id": "R_LOCAL_SCENE", "priority": 3},
    {"id": "R_CAUSE_ADVICE", "priority": 3},
    {"id": "R_ACCESS_REQUIREMENT", "priority": 3},
]

_ADVICE_RE = re.compile(r"不建议|建议|不妨|最好|推荐|应当|应该|不得|不宜|禁止|避免|勿|不要|不能|可以|请|尽量|就把|则|那我一定")
_IF_RE = re.compile(r"如果|假如|若(?:是|想|要)?|只要")
_FOR_RE = re.compile(r"对于")
_COMPANION_RE = re.compile(r"(?:携带|带着|带了|带)\s*(?:老人|孩子|儿童|小孩|婴儿|父母|长者)(?:(?:和|或|及|、)(?:老人|孩子|儿童|小孩|婴儿|父母|长者))*")
_PROFILE_RE = re.compile(r"喜欢[^，,。；;]{1,20}?(?:的朋友|的游客|的人|年轻人)|自由行的游客|时间(?:有限|充足|不够)(?:的话)?|按顺序浏览")
_TRIM_END = " \t\r\n，,、；;：:。.!！?？"
_STORY_RE = re.compile(r"历史上|曾经|当年|传说中|相传|古代|千年前|几百年前")

def _first_advice(text):
    for match in _ADVICE_RE.finditer(text):
        rest = text[match.end():]
        if match.group() == "可以" and re.match(r"\s*(?:的话|时|就|再|以后|之后|说|使|看到|清晰)", rest):
            continue
        if match.group() == "应该" and rest.startswith("能想"):
            continue
        return match
    return None

def _trim_condition(text):
    value = text.strip(_TRIM_END)
    return re.sub(r"\s*(?:则|就|那么)\s*$", "", value).strip(_TRIM_END)

def _is_plausible_condition(text, condition):
    if not condition or len(condition) > 80:
        return False
    if _STORY_RE.search(text) and re.search(r"(?:传说|古人|王朝|遗址)", text):
        return False
    return condition not in {"这样", "如此", "那样", "什么"}

def _candidate(sentence, condition, advice, rule_id, mode, context_ids):
    return {"sentence_id": sentence.get("sentence_id"), "doc_id": sentence.get("doc_id"),
            "condition_text": condition, "advice_text": advice, "rule_id": rule_id,
            "condition_mode": mode, "context_sentence_ids": context_ids}

def _extract_explicit(sentence):
    text = str(sentence.get("text") or "")
    result = []
    triggers = list(_IF_RE.finditer(text))
    for index, trigger in enumerate(triggers):
        stop = triggers[index + 1].start() if index + 1 < len(triggers) else len(text)
        tail = text[trigger.end():stop]
        delimiter = re.search(r"[,，]", tail)
        if delimiter is None:
            continue
        condition = _trim_condition(tail[:delimiter.start()])
        advice = tail[delimiter.end():].strip(_TRIM_END)
        action = _first_advice(advice)
        if action is None and not re.match(r"(?:穿|在[^,，]{0,8}(?:散步|拍照)|提前|选择|乘坐|走|租)", advice):
            continue
        if re.match(r"(?:你应该能想|就不能享受|声波|也可以使)", advice):
            continue
        next_profile = _PROFILE_RE.search(advice)
        if next_profile and next_profile.start() > 0:
            advice = advice[:next_profile.start()].strip(_TRIM_END)
        if _is_plausible_condition(text, condition) and advice:
            result.append(_candidate(sentence, condition, advice, "R_IF_THEN", "explicit",
                                     [sentence["sentence_id"]]))

    for pattern in (_FOR_RE, _COMPANION_RE, _PROFILE_RE):
        for match in pattern.finditer(text):
            if pattern is _COMPANION_RE and _positive_companion_condition(text[:match.end()]) is None:
                continue
            if any(match.start() >= trigger.start() and match.start() < trigger.end() + 12 for trigger in triggers):
                continue
            tail = text[match.end():]
            action = _first_advice(tail)
            trimmed = tail.lstrip(_TRIM_END)
            if re.match(r"(?:早点|提前|要|就)", trimmed):
                advice = trimmed.strip(_TRIM_END)
            elif action:
                advice = tail[action.start():].strip(_TRIM_END)
            elif match.group().endswith("的话"):
                advice = trimmed.split(",相信")[0].strip(_TRIM_END)
            else:
                continue
            if advice:
                result.append(_candidate(sentence, match.group(), advice, "R_VISITOR_PROFILE",
                                         "context", [sentence["sentence_id"]]))

    local = re.search(r"(?:园区|景区|里面|这里)[^,，。]{0,6}(?:很大|容易迷路)|预订房间|(?:在[^,，。]{0,12})?遛娃|逛完[^,，。]{1,10}", text)
    if local:
        tail = text[local.end():]
        action = re.search(r"最好|建议|教育好|出来直接", tail)
        if action:
            result.append(_candidate(sentence, local.group(), tail[action.start():].strip(_TRIM_END),
                                     "R_LOCAL_SCENE", "context", [sentence["sentence_id"]]))
    cause = re.search(r"由于([^,，。]{2,35})[,，]([^。]*建议[^。]+)", text)
    if cause:
        result.append(_candidate(sentence, cause.group(1), cause.group(2).strip(_TRIM_END),
                                 "R_CAUSE_ADVICE", "context", [sentence["sentence_id"]]))
    access = re.search(r"((?:转入|进入)[^,，。需]{1,8})(需[^,，。)）]+)", text)
    if access:
        result.append(_candidate(sentence, access.group(1), access.group(2),
                                 "R_ACCESS_REQUIREMENT", "explicit", [sentence["sentence_id"]]))
    return result

def _positive_companion_condition(text):
    match = _COMPANION_RE.search(text)
    if match is None:
        return None
    prefix = text[max(0, match.start() - 8):match.start()]
    if re.search(r"(?:不建议|不推荐|不适合|不应|不能|不|未|勿|禁止|不要|无需|无须)\s*$", prefix):
        return None
    return match.group()

def _extract_context(previous, sentence):
    if previous is None or previous.get("doc_id") is None:
        return None
    if previous.get("doc_id") != sentence.get("doc_id"):
        return None
    condition = _positive_companion_condition(str(previous.get("text") or ""))
    if condition is None:
        return None
    text = str(sentence.get("text") or "")
    if not re.match(r"\s*(?:建议|可以|最好|尽量|不妨|不要)", text):
        return None
    advice_match = _first_advice(text)
    if advice_match is None:
        return None
    advice = text[advice_match.start():].strip()
    if not advice:
        return None
    return _candidate(sentence, condition, advice, "R_COMPANION_CONTEXT", "context",
                      [previous.get("sentence_id"), sentence.get("sentence_id")])

def extract_candidates(sentences):
    candidates = []
    for index, sentence in enumerate(sentences):
        found = _extract_explicit(sentence)
        if not found:
            previous = sentences[index - 1] if index else None
            candidate = _extract_context(previous, sentence)
            found = [candidate] if candidate else []
        candidates.extend(found)
    return candidates

__all__ = ["RULES", "extract_candidates"]
