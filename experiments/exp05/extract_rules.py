"""条件建议候选抽取与保守去重。"""

import re
import unicodedata
from copy import deepcopy

RULES = [
    {"id": "R_IF_THEN", "priority": 1, "pattern": "如果/假如/若/只要 + 条件 + 建议"},
    {"id": "R_ONLY_THEN", "priority": 1, "pattern": "只有/仅当/仅在/唯有 + 条件 + 才/方才"},
    {"id": "R_UNLESS", "priority": 1, "pattern": "除非 + 条件 + 否则"},
    {"id": "R_FOR", "priority": 2, "pattern": "对于 + 适用情形 + 建议"},
    {"id": "R_VISITOR_PROFILE", "priority": 3, "pattern": "陪同对象/偏好/时间 + 建议"},
    {"id": "R_COMPANION_CONTEXT", "priority": 4, "pattern": "前句陪同对象 + 本句建议"},
    {"id": "R_LOCAL_SCENE", "priority": 3, "pattern": "限定游览场景 + 建议"},
    {"id": "R_CAUSE_ADVICE", "priority": 3, "pattern": "由于情形 + 建议"},
    {"id": "R_ACCESS_REQUIREMENT", "priority": 3, "pattern": "进入场景 + 操作要求"},
]

_ADVICE_RE = re.compile(r"不建议|建议|不妨|最好|推荐|应当|应该|不得|不宜|禁止|避免|勿|不要|不能|可以|请|尽量|就把|则|那我一定")
_IF_RE = re.compile(r"如果|假如|倘若|若(?:是|想|要)?|只要")
_FOR_RE = re.compile(r"对于")
_COMPANION_RE = re.compile(r"(?:携带|带着|带了|带)\s*(?:老人|孩子|儿童|小孩|婴儿|父母|长者)(?:(?:和|或|及|、)(?:老人|孩子|儿童|小孩|婴儿|父母|长者))*")
_PROFILE_RE = re.compile(r"喜欢[^，,。；;]{1,20}?(?:的朋友|的游客|的人|年轻人)|自由行的游客|时间(?:有限|充足|不够)(?:的话)?|按顺序浏览")
_TRIM_END = " \t\r\n，,、；;：:。.!！?？"
_NEGATION_RE = re.compile(r"不建议|不宜|不应|不必|不要|不能|不可|不得|不允许|不适合|无需|无须|禁止|严禁|勿|未|没有|不(?=带|含|同意|需要|支持)")
_STORY_RE = re.compile(r"历史上|曾经|当年|传说中|相传|古代|千年前|几百年前")
_ONLY_RE = re.compile(r"只有|仅当|仅在|唯有")
_UNLESS_RE = re.compile(r"除非")
_CONSEQUENCE_RE = re.compile(r"方才|才能|方能|那么|则|就|才|便")
_ALL_CONDITION_RE = re.compile(r"并且|而且|以及|同时|且|[和与]")
_ANY_CONDITION_RE = re.compile(r"或者|要么|或")
_HARD_BOUNDARY_RE = re.compile(r"[；;。！？!?]")
_PAST_RE = re.compile(r"历史上|曾经|当年|传说中|相传|古代|千年前|几百年前|上次|上回|那次|以前|过去|当时|去年|昨天|早知道")
_REGRET_RE = re.compile(r"就好了|早知道|就行了|就可以了|就能了|就不会|多好")
_CAPACITY_RE = re.compile(r"(?:我|我们|他|她)?[^，,。；;]{0,24}(?:会|能|可以|有能力)[^，,。；;]{0,12}(?:就好了|就行了)")
_ADVICE_START_RE = re.compile(r"^(?:(?:同时|并且|而且|并|也)\s*)?(?:建议|不建议|不妨|最好|推荐|应(?:当|该)?|不应|不宜|不承诺|不保证|禁止|避免|勿|不要|不能|不得|不可|需(?:要)?|请|尽量|优先|停止|取消|删减|减少|缩减|安排|加入|选择|确认|核实|查看|查询|服从|保留|延长|调整|提前|执行|落实|预定|预订|穿|带|走|乘坐|进入|离开|退出|按|在[^，,。；;]{0,12}(?:散步|拍照|增加|安排|保留|减少|缩减|休息|停留|调整)|把[^，,。；;]{1,16}(?:预定|预订|安排|确认|落实|整理|准备|标记|写清|做好|好|妥)|每[^，,。；;]{0,24}安排|租(?:用)?|可以|可|先|再|不去)")
_SUBJECT_RE = re.compile(r"游客(?:甲|乙|丙|丁|A|B|C|D|[一二三四])|第[一二三四1-4]组|(?:另一|其他|别的)(?:组|队|批|位)?游客|我们|咱们|你们|我|你|他们|她们|他|她|同伴|同行者|导游")

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


def _candidate(sentence, condition, advice, rule_id, mode, context_ids, operator=None):
    if operator is None:
        operator = "context" if mode == "context" else "all"
    return {"sentence_id": sentence.get("sentence_id"), "doc_id": sentence.get("doc_id"),
            "condition_text": condition, "advice_text": advice, "rule_id": rule_id,
            "condition_mode": mode, "condition_operator": operator, "context_sentence_ids": context_ids}


def _advice_excerpt(text):
    value = str(text or "").lstrip(_TRIM_END)
    value = re.sub(r"^(?:那么|方才|才能|方能|则|就|才|便)\s*", "", value)
    return value.strip(_TRIM_END)


def _looks_like_advice(text):
    return bool(_ADVICE_START_RE.match(_advice_excerpt(text)))


def _condition_operator(condition):
    has_all, has_any = bool(_ALL_CONDITION_RE.search(condition)), bool(_ANY_CONDITION_RE.search(condition))
    if has_all and has_any:
        return None
    return "any" if has_any else "all"


def _clause_end(text, start, next_trigger=None):
    stops = [match.start() for match in _HARD_BOUNDARY_RE.finditer(text, start)]
    if next_trigger is not None:
        stops.append(next_trigger)
    return min(stops) if stops else len(text)


def _find_if_split(tail):
    separators = [(m.start(), m.end()) for m in re.finditer(r"[,，]", tail)]
    separators.extend((m.start(), m.end()) for m in _CONSEQUENCE_RE.finditer(tail))
    for condition_end, advice_start in sorted(separators):
        condition = _trim_condition(tail[:condition_end])
        if condition and _looks_like_advice(tail[advice_start:]):
            return condition_end, advice_start
    return None


def _is_counterfactual_or_historical(condition, clause):
    return bool(_PAST_RE.search(condition) or _REGRET_RE.search(clause) or _CAPACITY_RE.search(clause))


def _append_explicit(result, occupied, sentence, condition, advice, rule_id, operator, start, end):
    if not condition or not advice or not _looks_like_advice(advice):
        return
    if not _is_plausible_condition(str(sentence.get("text") or ""), condition):
        return
    result.append(_candidate(sentence, condition, advice, rule_id, "explicit",
                             [sentence.get("sentence_id")], operator))
    occupied.append((start, end))


def _extract_explicit(sentence):
    text = str(sentence.get("text") or "")
    result, occupied = [], []
    for trigger in _UNLESS_RE.finditer(text):
        end = _clause_end(text, trigger.end())
        otherwise = re.search(r"否则", text[trigger.end():end])
        if otherwise is None:
            continue
        split = trigger.end() + otherwise.start()
        condition = _trim_condition(text[trigger.end():split])
        advice = _advice_excerpt(text[split + len("否则"):end])
        if _condition_operator(condition) is None or _is_counterfactual_or_historical(condition, text[trigger.start():end]):
            continue
        _append_explicit(result, occupied, sentence, condition, advice, "R_UNLESS", "unless", trigger.start(), end)

    for trigger in _ONLY_RE.finditer(text):
        if re.search(r"(?:如果|假如|倘若|若(?:是|想|要)?|只要)\s*$", text[:trigger.start()]):
            continue
        end = _clause_end(text, trigger.end())
        tail = text[trigger.end():end]
        for marker in re.finditer(r"方才|才能|方能|才", tail):
            condition = _trim_condition(tail[:marker.start()])
            advice = _advice_excerpt(tail[marker.end():])
            if (not condition or _condition_operator(condition) is None
                    or _is_counterfactual_or_historical(condition, text[trigger.start():end])
                    or not _looks_like_advice(advice)):
                continue
            _append_explicit(result, occupied, sentence, condition, advice, "R_ONLY_THEN", "necessary",
                             trigger.start(), end)
            break

    triggers = list(_IF_RE.finditer(text))
    for index, trigger in enumerate(triggers):
        next_trigger = triggers[index + 1].start() if index + 1 < len(triggers) else None
        end = _clause_end(text, trigger.end(), next_trigger)
        tail = text[trigger.end():end]
        split = _find_if_split(tail)
        if split is None:
            continue
        condition_end, advice_start = split
        condition = _trim_condition(tail[:condition_end])
        advice = _advice_excerpt(tail[advice_start:])
        operator = _condition_operator(condition)
        if (not condition or operator is None
                or _is_counterfactual_or_historical(condition, text[trigger.start():end])):
            continue
        _append_explicit(result, occupied, sentence, condition, advice, "R_IF_THEN", operator, trigger.start(), end)

    for pattern in (_FOR_RE, _COMPANION_RE, _PROFILE_RE):
        for match in pattern.finditer(text):
            if ((pattern is _COMPANION_RE and _positive_companion_condition(text[:match.end()]) is None)
                    or any(start <= match.start() < end for start, end in occupied)):
                continue
            tail = text[match.end():]
            action = _first_advice(tail)
            trimmed = tail.lstrip(_TRIM_END)
            if re.match(r"(?:早点|提前|要|就)", trimmed):
                advice = trimmed.strip(_TRIM_END)
            elif action:
                advice = tail[action.start():].strip(_TRIM_END)
            elif match.group().endswith("的话"):
                advice = re.split(r"[,，]相信", trimmed, maxsplit=1)[0].strip(_TRIM_END)
            else:
                continue
            if advice:
                result.append(_candidate(sentence, match.group(), advice, "R_VISITOR_PROFILE",
                                         "context", [sentence.get("sentence_id")]))

    local = re.search(r"(?:园区|景区|里面|这里)[^,，。]{0,6}(?:很大|容易迷路)|预订房间|(?:在[^,，。]{0,12})?遛娃|逛完[^,，。]{1,10}", text)
    if local:
        tail = text[local.end():]
        action = re.search(r"最好|建议|教育好|出来直接", tail)
        if action:
            result.append(_candidate(sentence, local.group(), tail[action.start():].strip(_TRIM_END),
                                     "R_LOCAL_SCENE", "context", [sentence.get("sentence_id")]))

    cause = re.search(r"由于([^,，。]{2,35})[,，]([^。]*建议[^。]+)", text)
    if cause and not _is_counterfactual_or_historical(cause.group(1), cause.group(0)):
        result.append(_candidate(sentence, cause.group(1), cause.group(2).strip(_TRIM_END),
                                 "R_CAUSE_ADVICE", "context", [sentence.get("sentence_id")]))

    access = re.search(r"((?:转入|进入)[^,，。需]{1,8})(需[^,，。)）]+)", text)
    if access:
        result.append(_candidate(sentence, access.group(1), access.group(2),
                                 "R_ACCESS_REQUIREMENT", "explicit", [sentence.get("sentence_id")]))
    return result


def _positive_companion_condition(text):
    match = _COMPANION_RE.search(text)
    if match is None:
        return None
    prefix = text[max(0, match.start() - 8):match.start()]
    if re.search(r"(?:不建议|不推荐|不适合|不应|不能|不|未|勿|禁止|不要|无需|无须)\s*$", prefix):
        return None
    return match.group()


def _subject_identities(text):
    groups = {"我": "narrator", "我们": "narrator", "咱们": "narrator",
              "他": "third-person", "他们": "third-person", "她": "third-person", "她们": "third-person",
              "你": "addressee", "你们": "addressee"}
    return {groups.get(token, "other-visitors" if token.startswith(("另一", "其他", "别的")) else token)
            for token in _SUBJECT_RE.findall(str(text or ""))}


def _same_subject_context(previous, sentence):
    previous_ids = _subject_identities(previous.get("text", ""))
    current_ids = _subject_identities(sentence.get("text", ""))
    if previous_ids and current_ids:
        return bool(previous_ids & current_ids)
    return "other-visitors" not in (previous_ids | current_ids)


def _extract_context(previous, sentence):
    if (previous is None or previous.get("doc_id") is None
            or previous.get("doc_id") != sentence.get("doc_id")):
        return None
    previous_paragraph = previous.get("paragraph_index")
    if previous_paragraph is None or previous_paragraph != sentence.get("paragraph_index"):
        return None
    if not _same_subject_context(previous, sentence):
        return None
    condition = _positive_companion_condition(str(previous.get("text") or ""))
    if condition is None:
        return None
    text = str(sentence.get("text") or "")
    if not re.match(r"\s*(?:不建议|建议|可以|最好|尽量|不妨|不应|不宜|不能|不要|请|优先|先)", text):
        return None
    advice_match = _first_advice(text)
    if advice_match is None:
        return None
    advice = text[advice_match.start():].strip()
    if not advice:
        return None
    return _candidate(sentence, condition, advice, "R_COMPANION_CONTEXT", "context",
                      [previous.get("sentence_id"), sentence.get("sentence_id")], "context")


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


def normalize_for_dedup(text):
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return "".join(char for char in value
                   if not char.isspace() and not unicodedata.category(char).startswith("P"))


def _negation_signature(text):
    return tuple(_NEGATION_RE.findall(str(text or "")))


def _provenance_signature(record):
    kinds = {normalize_for_dedup(record["provenance_kind"])} if record.get("provenance_kind") else set()
    kinds.update(normalize_for_dedup(item["provenance_kind"])
                 for item in record.get("evidence", []) or []
                 if isinstance(item, dict) and item.get("provenance_kind"))
    return tuple(sorted(kinds))


def _visitor_signature(record):
    values = record["visitor_types"] if "visitor_types" in record else record.get("visitor_type")
    if values is None:
        values = []
    elif not isinstance(values, (list, tuple, set, frozenset)):
        values = [values]
    return tuple(sorted({normalize_for_dedup(value) for value in values}))


def _semantic_key(record):
    return (_provenance_signature(record),
            normalize_for_dedup(record.get("condition_operator", "")),
            normalize_for_dedup(record.get("condition_mode", "")),
            normalize_for_dedup(record.get("condition_text", "")),
            normalize_for_dedup(record.get("target_scope", "")),
            _visitor_signature(record),
            normalize_for_dedup(record.get("condition_type", "")),
            _negation_signature(record.get("condition_text", "")),
            _negation_signature(record.get("advice_text", "")),
            _negation_signature(record.get("target_scope", "")))


def _sentence_keys(record):
    keys = {(record.get("doc_id"), record["sentence_id"])} if record.get("sentence_id") is not None else set()
    keys.update((item.get("doc_id", record.get("doc_id")), item["sentence_id"])
                for item in record.get("evidence", []) or []
                if isinstance(item, dict) and item.get("sentence_id") is not None)
    return keys


def _shared_sentence(left, right):
    return bool(_sentence_keys(left) & _sentence_keys(right))


def _advice_match_reason(left, right):
    first = normalize_for_dedup(left.get("advice_text", ""))
    second = normalize_for_dedup(right.get("advice_text", ""))
    if first == second:
        return "建议文本规范化后完全相同"
    if not first or not second or not _shared_sentence(left, right):
        return None
    shorter, longer = sorted((first, second), key=len)
    if len(shorter) >= 5 and len(shorter) / len(longer) >= 0.75:
        if longer.startswith(shorter) or longer.endswith(shorter):
            return "同句建议呈前缀或后缀包含，按较完整文本合并"
    content = lambda value: re.sub(r"^(?:建议大家|建议游客|建议|可以|最好)", "", value)
    return "同句建议仅有建议性前缀差异" if content(first) == content(second) else None


def _can_merge(left, right):
    return _advice_match_reason(left, right) if _semantic_key(left) == _semantic_key(right) else None


def deduplicate(records):
    merged, groups, buckets, merge_log = [], [], {}, []
    for source_index, record in enumerate(records):
        current, key = deepcopy(record), _semantic_key(record)
        match_index = reason = None
        for candidate_index in buckets.get(key, []):
            for member in groups[candidate_index]:
                reason = _can_merge(member, current)
                if reason:
                    match_index = candidate_index
                    break
            if match_index is not None:
                break
        if match_index is None:
            current["evidence"] = list(current.get("evidence", []) or [])
            match_index = len(merged)
            merged.append(current)
            groups.append([current])
            buckets.setdefault(key, []).append(match_index)
            continue

        target = merged[match_index]
        if len(current.get("advice_text", "")) > len(target.get("advice_text", "")):
            target["advice_text"] = current["advice_text"]
            spans = current.get("spans") or {}
            if "advice_text" in spans:
                target.setdefault("spans", {})["advice_text"] = dict(spans["advice_text"])
        target.setdefault("evidence", []).extend(current.get("evidence", []) or [])
        groups[match_index].append(current)
        merge_log.append({"kept_index": match_index, "merged_index": source_index, "reason": reason})
    return merged, merge_log


__all__ = ["RULES", "extract_candidates", "deduplicate", "normalize_for_dedup"]
