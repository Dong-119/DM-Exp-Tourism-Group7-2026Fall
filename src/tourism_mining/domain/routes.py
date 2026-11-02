"""Domain rules and transformations for tourism routes."""

from __future__ import annotations

import re
from typing import Any

OFFICIAL_ROUTE_ID = "GG_F01"
TIMED_ROUTE_ID = "GG_S01"
TRAVEL_ROUTE_ID = "GG_T05"

POI_ALIASES = {
    "干清宫": "乾清宫",
}

SITE_ALIASES = {
    "紫禁城": "故宫",
    "故宫博物院": "故宫",
}

TIME_BUCKETS = ("morning", "noon", "afternoon", "unknown")
PHASE_MAP = {
    "上午": "morning",
    "中午": "noon",
    "午间": "noon",
    "下午": "afternoon",
}

TRAVEL_STEP_ANNOTATIONS = {
    "GG_T01": [
        {
            "quote": "我们就这样从上面写这故宫博物院5个大字的神武门进入紫禁城。",
            "poi": "神武门",
            "step_type": "entry",
            "activity": "从神武门进入紫禁城",
            "time_slot": "morning",
        },
        {
            "quote": "早上我们从神武门进来紫禁城，经过顺贞门，首先看到的是御花园",
            "poi": "御花园",
            "step_type": "visit",
            "activity": "到御花园游览",
            "time_slot": "morning",
        },
        {
            "quote": "在经过御花园，走过坤宁门后，我们来到坤宁宫",
            "poi": "坤宁宫",
            "step_type": "visit",
            "activity": "到坤宁宫参观",
            "time_slot": "morning",
        },
        {
            "quote": "经过交泰殿后来到内廷最具规模的建筑-干清宫",
            "poi": "干清宫",
            "step_type": "visit",
            "activity": "经过交泰殿后参观乾清宫",
            "time_slot": "morning",
        },
        {
            "quote": "在参观完坤宁宫，交泰殿，干清宫后，我们来到位于后廷中轴线西侧，继续参观慈禧太后垂帘听政的养心殿，还有永寿宫的清代妃嫔生活展跟储秀宫的溥仪生活展。",
            "poi": "养心殿",
            "step_type": "visit",
            "activity": "参观养心殿",
            "time_slot": "morning",
        },
        {
            "quote": "在参观完坤宁宫，交泰殿，干清宫后，我们来到位于后廷中轴线西侧，继续参观慈禧太后垂帘听政的养心殿，还有永寿宫的清代妃嫔生活展跟储秀宫的溥仪生活展。",
            "poi": "永寿宫",
            "step_type": "visit",
            "activity": "参观清代妃嫔生活展",
            "time_slot": "morning",
        },
        {
            "quote": "在参观完坤宁宫，交泰殿，干清宫后，我们来到位于后廷中轴线西侧，继续参观慈禧太后垂帘听政的养心殿，还有永寿宫的清代妃嫔生活展跟储秀宫的溥仪生活展。",
            "poi": "储秀宫",
            "step_type": "visit",
            "activity": "参观溥仪生活展",
            "time_slot": "morning",
        },
        {
            "quote": "在参观完溥仪生活展后，再度回到御花园来，准备循原路从神武门离开",
            "poi": "御花园",
            "step_type": "visit",
            "activity": "返回御花园",
            "time_slot": "morning",
        },
        {
            "quote": "在参观完溥仪生活展后，再度回到御花园来，准备循原路从神武门离开",
            "poi": "神武门",
            "step_type": "exit",
            "activity": "准备从神武门离开",
            "time_slot": "morning",
        },
        {
            "quote": "下午则是由天安门广场经午门进入前朝，参观紫禁城最主要的三大殿，以及钟表馆根珍宝馆。",
            "poi": "午门",
            "step_type": "entry",
            "activity": "从午门进入前朝",
            "time_slot": "afternoon",
        },
        {
            "quote": "下午则是由天安门广场经午门进入前朝，参观紫禁城最主要的三大殿，以及钟表馆根珍宝馆。",
            "poi": "前朝三大殿",
            "step_type": "visit",
            "activity": "参观三大殿",
            "time_slot": "afternoon",
        },
        {
            "quote": "下午则是由天安门广场经午门进入前朝，参观紫禁城最主要的三大殿，以及钟表馆根珍宝馆。",
            "poi": "钟表馆",
            "step_type": "visit",
            "activity": "参观钟表馆",
            "time_slot": "afternoon",
        },
        {
            "quote": "下午则是由天安门广场经午门进入前朝，参观紫禁城最主要的三大殿，以及钟表馆根珍宝馆。",
            "poi": "珍宝馆",
            "step_type": "visit",
            "activity": "参观珍宝馆",
            "time_slot": "afternoon",
        },
    ],
    "GG_T05": [
        {"quote": "从午门走进故宫", "poi": "午门", "step_type": "entry", "activity": "从午门进入"},
        {"quote": "一路欣赏着，来到了太和殿前。", "poi": "太和殿", "step_type": "visit", "activity": "游览太和殿"},
        {"quote": "我们游览了干清宫的雄壮气势", "poi": "干清宫", "step_type": "visit", "activity": "游览乾清宫"},
        {"quote": "紧接着，我们来到了故宫珍宝馆", "poi": "珍宝馆", "step_type": "visit", "activity": "参观珍宝馆"},
        {"quote": "从故宫南门进，从北面的神武门出了。", "poi": "神武门", "step_type": "exit", "activity": "从神武门离开"},
    ],
}


def canonical_name(name: str) -> str:
    normalized = re.sub(r"\s+", "", name.strip())
    return POI_ALIASES.get(normalized, normalized)


def canonical_site_name(name: str) -> str:
    normalized = re.sub(r"\s+", "", name.strip())
    return SITE_ALIASES.get(normalized, normalized)


def point_from_label(label: str) -> tuple[str, str | None]:
    match = re.fullmatch(r"\s*([^（(]+?)\s*[（(]([^）)]+)[）)]\s*", label)
    if match:
        return canonical_name(match.group(1)), match.group(2).strip()
    return canonical_name(label), None


def split_route_chain(text: str) -> list[str]:
    parts = re.split(r"\s*(?:→|➜|⟶|->|(?<=[\u4e00-\u9fff）)])-(?=[\u4e00-\u9fff（]))\s*", text.strip())
    return [part.strip(" \t，。；;") for part in parts if part.strip(" \t，。；;")]


def make_step(
    order: int,
    raw_label: str,
    *,
    source_quote: str,
    time_slot: str = "unknown",
    time_start: str | None = None,
    time_end: str | None = None,
    time_source: str = "not_stated",
    activity: str | None = None,
    step_type: str = "visit",
    start: int | None = None,
    end: int | None = None,
) -> dict[str, Any]:
    point, parenthetical_activity = point_from_label(raw_label)
    descriptive_location = (
        point.endswith("休息点")
        or point.endswith("休息处")
        or point == "前朝三大殿"
    )
    return {
        "order": order,
        "poi": point,
        "poi_id": f"poi:故宫:{point}",
        "poi_kind": "descriptive_location" if descriptive_location else "named_poi",
        "raw_label": raw_label,
        "activity": activity or parenthetical_activity,
        "step_type": step_type,
        "time_slot": time_slot,
        "time_start": time_start,
        "time_end": time_end,
        "time_source": time_source,
        "source_quote": source_quote,
        "source_span": {"start": start, "end": end} if start is not None and end is not None else None,
    }


def hierarchy(steps: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result = {bucket: [] for bucket in TIME_BUCKETS}
    for step in steps:
        bucket = step["time_slot"]
        if bucket not in result:
            raise ValueError(f"Unknown time bucket: {bucket}")
        result[bucket].append(step)
    return result


def parse_official_chain(document: dict[str, Any]) -> dict[str, Any]:
    text = document["clean_content"]
    match = re.search(r"推荐行进顺序\s*[：:]\s*([^\n。；]+)", text)
    if not match:
        raise ValueError(f"No recommended route chain found in {document['doc_id']}")
    labels = split_route_chain(match.group(1))
    if len(labels) < 2:
        raise ValueError(f"Route chain has fewer than two steps in {document['doc_id']}")
    steps = []
    search_from = match.start(1)
    for order, label in enumerate(labels, start=1):
        start = text.find(label, search_from, match.end(1))
        if start < 0:
            raise ValueError(f"Could not locate route step {label!r} in {document['doc_id']}")
        steps.append(
            make_step(
                order,
                label,
                source_quote=label,
                step_type="entry" if order == 1 else "exit" if order == len(labels) else "visit",
                start=start,
                end=start + len(label),
            )
        )
        search_from = start + len(label)
    return {
        "route_id": "route-GG-official-facts",
        "scenic_name": canonical_site_name(document["scenic_name"]),
        "route_kind": "official_route_facts",
        "provenance_kind": document["provenance_kind"],
        "document_id": document["doc_id"],
        "title": document["title"],
        "reference_url": document.get("reference_url"),
        "parse_method": "recommended_order_chain",
        "time_policy": "The source explicitly states that no time of day or per-stop time is given.",
        "steps": steps,
        "time_hierarchy": hierarchy(steps),
    }


def parse_numbered_timed_route(document: dict[str, Any]) -> dict[str, Any]:
    text = document["clean_content"]
    steps: list[dict[str, Any]] = []
    current_phase = "unknown"
    section_pattern = re.compile(r"^\s*(上午|中午|午间|下午)\s*[：:]", re.MULTILINE)
    sections = list(section_pattern.finditer(text))
    phase_at: list[tuple[int, str]] = [(m.start(), PHASE_MAP[m.group(1)]) for m in sections]
    lines = text.splitlines(keepends=True)
    offset = 0
    for line in lines:
        for position, phase in phase_at:
            if position < offset + len(line):
                current_phase = phase
        match = re.match(
            r"\s*(\d+)\.\s*(\d{1,2}:\d{2})\s*[—–-]\s*(\d{1,2}:\d{2})\s*[，,]\s*([^：:，,]+)\s*[：:]\s*(.*)",
            line,
        )
        if match:
            order = int(match.group(1))
            start_time, end_time, raw_label, activity = match.group(2, 3, 4, 5)
            label_start = offset + match.start(4)
            activity = re.split(r"[，,]此步骤共", activity, maxsplit=1)[0].strip()
            steps.append(
                make_step(
                    order,
                    raw_label.strip(),
                    source_quote=line.strip(),
                    time_slot=current_phase,
                    time_start=start_time,
                    time_end=end_time,
                    time_source="explicit_in_source",
                    activity=activity,
                    step_type="entry" if order == 1 else "visit",
                    start=label_start,
                    end=label_start + len(raw_label.strip()),
                )
            )
        offset += len(line)
    if not steps:
        raise ValueError(f"No numbered timed steps found in {document['doc_id']}")
    if [step["order"] for step in steps] != list(range(1, len(steps) + 1)):
        raise ValueError(f"Numbered steps are not contiguous in {document['doc_id']}")
    steps[-1]["step_type"] = "exit"
    return {
        "route_id": "route-GG-synthetic-timed-fixture",
        "scenic_name": canonical_site_name(document["scenic_name"]),
        "route_kind": "synthetic_teaching_fixture",
        "provenance_kind": document["provenance_kind"],
        "document_id": document["doc_id"],
        "title": document["title"],
        "reference_url": document.get("reference_url"),
        "parse_method": "time_header_and_numbered_steps",
        "time_policy": "Times and time-of-day sections are copied only where explicitly stated in the teaching fixture.",
        "steps": steps,
        "time_hierarchy": hierarchy(steps),
    }


def parse_annotated_travelogue(document: dict[str, Any]) -> dict[str, Any]:
    text = document["clean_content"]
    steps: list[dict[str, Any]] = []
    annotations = TRAVEL_STEP_ANNOTATIONS.get(document["doc_id"])
    if annotations is None:
        raise ValueError(f"No reviewed route annotations for {document['doc_id']}")
    for order, annotation in enumerate(annotations, start=1):
        quote = annotation["quote"]
        start = text.find(quote)
        if start < 0:
            raise ValueError(f"Annotation quote not found in {document['doc_id']}: {quote}")
        steps.append(
            make_step(
                order,
                annotation["poi"],
                source_quote=quote,
                step_type=annotation["step_type"],
                activity=annotation.get("activity"),
                time_slot=annotation.get("time_slot", "unknown"),
                time_source="explicit_phase_in_source" if annotation.get("time_slot") else "not_stated",
                start=start,
                end=start + len(quote),
            )
        )
    return {
        "route_id": f"route-GG-traveler-{document['doc_id']}",
        "scenic_name": canonical_site_name(document["scenic_name"]),
        "route_kind": "traveler_actual_route",
        "provenance_kind": document["provenance_kind"],
        "document_id": document["doc_id"],
        "title": document["title"],
        "reference_url": document.get("original_article_url"),
        "source_note": "Sequence is a conservative manual annotation of explicitly narrated entry, visit, and exit evidence; named neighboring buildings are not assumed visited.",
        "parse_method": "evidence_anchored_manual_annotation",
        "time_policy": "Only explicit time-of-day wording is assigned; no clock time or stop duration is inferred.",
        "steps": steps,
        "time_hierarchy": hierarchy(steps),
    }


def lcs_length(left: list[str], right: list[str]) -> int:
    row = [0] * (len(right) + 1)
    for left_item in left:
        previous = 0
        for index, right_item in enumerate(right, start=1):
            old = row[index]
            if left_item == right_item:
                row[index] = previous + 1
            else:
                row[index] = max(row[index], row[index - 1])
            previous = old
    return row[-1]


def compare_routes(official: dict[str, Any], traveler: dict[str, Any]) -> dict[str, Any]:
    official_ids = [step["poi_id"] for step in official["steps"]]
    traveler_ids = [step["poi_id"] for step in traveler["steps"]]
    official_set = set(official_ids)
    traveler_set = set(traveler_ids)
    shared = [point for point in official_ids if point in traveler_set]
    shared_order = lcs_length(
        [point for point in official_ids if point in traveler_set],
        [point for point in traveler_ids if point in official_set],
    )
    return {
        "scenic_name": official["scenic_name"],
        "official_route_id": official["route_id"],
        "traveler_route_id": traveler["route_id"],
        "metric_definitions": {
            "official_route_coverage": "Shared distinct POIs / official route POIs.",
            "traveler_route_alignment": "Shared distinct POIs / traveler route POIs.",
            "shared_order_consistency": "LCS length of the two shared-POI sequences / number of shared distinct POIs.",
        },
        "official_route_step_count": len(official_ids),
        "traveler_route_step_count": len(traveler_ids),
        "shared_pois_in_official_order": [step["poi"] for step in official["steps"] if step["poi_id"] in traveler_set],
        "traveler_only_pois": [step["poi"] for step in traveler["steps"] if step["poi_id"] not in official_set],
        "official_only_pois": [step["poi"] for step in official["steps"] if step["poi_id"] not in traveler_set],
        "shared_poi_count": len(shared),
        "official_route_coverage": len(shared) / len(set(official_ids)) if official_ids else 0.0,
        "traveler_route_alignment": len(shared) / len(set(traveler_ids)) if traveler_ids else 0.0,
        "shared_order_consistency": shared_order / len(shared) if shared else None,
        "shared_order_lcs_length": shared_order,
        "time_comparison": "Not calculated: neither source provides comparable per-stop or time-of-day data.",
    }


def validate_routes(routes: list[dict[str, Any]], documents: dict[str, dict[str, Any]]) -> None:
    for route in routes:
        source_text = documents[route["document_id"]]["clean_content"]
        orders = [step["order"] for step in route["steps"]]
        if orders != list(range(1, len(orders) + 1)):
            raise ValueError(f"Non-contiguous step order in {route['route_id']}")
        for step in route["steps"]:
            span = step["source_span"]
            if span is not None:
                if not (0 <= span["start"] < span["end"] <= len(source_text)):
                    raise ValueError(f"Invalid source span in {route['route_id']} step {step['order']}")
                if source_text[span["start"]:span["end"]] != step["source_quote"] and route["parse_method"] != "time_header_and_numbered_steps":
                    raise ValueError(f"Evidence span mismatch in {route['route_id']} step {step['order']}")
            if step["poi"] != canonical_name(step["poi"]):
                raise ValueError(f"Unnormalized POI in {route['route_id']}: {step['poi']}")

